package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"math/rand"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/IBM/sarama"
	"github.com/google/uuid"
)

// Configuration from environment variables with defaults
var (
	kafkaBroker                    = getEnv("KAFKA_BROKER", "k8s-sandbox:9092")
	kafkaTopic                     = getEnv("KAFKA_TOPIC", "throughput-topic")
	producerClientID               = getEnv("PRODUCER_CLIENT_ID", "kafka-throughput-producer")
	statusDir                      = getEnv("STATUS_DIR", "/tmp/status")
	producerStatsFile              = filepath.Join(statusDir, "producer_stats.txt")
	latencyFile                    = filepath.Join(statusDir, "e2e_latency_ms.txt")
	kminionProducerActualRateFile  = filepath.Join(statusDir, "producer_actual_rate_value.txt")
	initialMessageRate, _          = strconv.Atoi(getEnv("MESSAGE_RATE_PER_SECOND", "1000"))
	messageSizeBytes, _            = strconv.Atoi(getEnv("MESSAGE_SIZE_BYTES", "1024"))
	maxRetries, _                  = strconv.Atoi(getEnv("MAX_RETRIES", "30"))
	initialRetryDelayS, _          = strconv.Atoi(getEnv("INITIAL_RETRY_DELAY_S", "5"))
	targetLatencyMs, _             = strconv.ParseFloat(getEnv("TARGET_LATENCY_MS", "5.0"), 64)
	targetRateMargin, _            = strconv.ParseFloat(getEnv("TARGET_RATE_MARGIN", "0.80"), 64)
	targetRateMult, _              = strconv.ParseFloat(getEnv("TARGET_RATE_MULT", "1.03"), 64)
	maxMessageRate, _              = strconv.Atoi(getEnv("MAX_MESSAGE_RATE", "50000"))
)

var partitionSkew float64

// init function for robust parsing and validation of partitionSkew
func init() {
	skewStr := getEnv("PARTITION_SKEW", "0.0")
	var errParse error
	partitionSkew, errParse = strconv.ParseFloat(skewStr, 64)
	if errParse != nil {
		log.Fatalf("Invalid PARTITION_SKEW value: %s. Error: %v", skewStr, errParse)
	}
	if partitionSkew < 0.0 || partitionSkew > 1.0 {
		log.Fatalf("PARTITION_SKEW must be between 0.0 and 1.0, got: %.2f", partitionSkew)
	}
	// No need to log here, main will log it if needed or it's used directly
}

// Message represents our Kafka message payload
type Message struct {
	Sequence   int64     `json:"sequence"`
	Timestamp  float64   `json:"timestamp"`
	Data       string    `json:"data"`
}

// ProducerStats tracks producer statistics
type ProducerStats struct {
	mu            sync.Mutex
	targetRate    int
	messageSize   int
	lastWriteTime time.Time
}

// Global stats instance
var stats = &ProducerStats{
	targetRate:  initialMessageRate,
	messageSize: messageSizeBytes,
}

// BatchConfig holds batching configuration
type BatchConfig struct {
	MaxBatchSize  int
	MaxBatchDelay time.Duration
}

// MessageBatch represents a batch of messages to be sent
type MessageBatch struct {
	messages []*sarama.ProducerMessage
	size     int
}

// Global batch config
const (
	batchesPerSecond = 20 // 50ms between batches
)

var batchConfig = BatchConfig{
	MaxBatchSize:  5000, // Max messages in an app-level batch. Sarama also has its own flush limits.
	MaxBatchDelay: time.Second / time.Duration(batchesPerSecond),
}

var effectiveMaxTokensForBucket float64 // New global for token bucket capacity

// TokenBucket implements a simple token bucket rate limiter
type TokenBucket struct {
	mu            sync.Mutex
	tokens        float64
	rate          float64    // tokens per second
	lastRefill    time.Time
	maxTokens     float64
}

func newTokenBucket(rate float64, configuredMaxTokens float64) *TokenBucket {
	now := time.Now()
	initialTokens := configuredMaxTokens // Start full
	return &TokenBucket{
		tokens:     initialTokens,
		rate:       rate,
		lastRefill: now,
		maxTokens:  configuredMaxTokens,
	}
}

func (tb *TokenBucket) refill() {
	now := time.Now()
	elapsed := now.Sub(tb.lastRefill).Seconds()
	newTokens := elapsed * tb.rate
	tb.tokens = math.Min(tb.maxTokens, tb.tokens + newTokens)
	tb.lastRefill = now
	log.Printf("TokenBucket.refill: refilled %.2f tokens, total now %.2f", newTokens, tb.tokens)
}

func (tb *TokenBucket) take(n float64) bool {
	tb.mu.Lock()
	defer tb.mu.Unlock()

	log.Printf("TokenBucket.take: attempting to take %.2f tokens", n)
	tb.refill()
	log.Printf("TokenBucket.take: after refill, have %.2f tokens", tb.tokens)
	if tb.tokens >= n {
		tb.tokens -= n
		log.Printf("TokenBucket.take: took %.2f tokens, %.2f remaining", n, tb.tokens)
		return true
	}
	log.Printf("TokenBucket.take: not enough tokens (need %.2f, have %.2f)", n, tb.tokens)
	return false
}

func (tb *TokenBucket) setRate(rate float64) {
	tb.mu.Lock()
	defer tb.mu.Unlock()
	tb.rate = rate
}

// getEnv gets an environment variable or returns a default value
func getEnv(key, defaultValue string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return defaultValue
}

// writeProducerStats writes the current producer stats to file
func (p *ProducerStats) writeStats() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	// Only write if more than 1 second has passed since last write
	if time.Since(p.lastWriteTime) < time.Second {
		return nil
	}

	statsStr := fmt.Sprintf("target_rate=%d,size=%d", p.targetRate, p.messageSize)
	if err := os.MkdirAll(statusDir, 0755); err != nil {
		return fmt.Errorf("failed to create status directory: %w", err)
	}

	if err := os.WriteFile(producerStatsFile, []byte(statsStr), 0644); err != nil {
		return fmt.Errorf("failed to write producer stats: %w", err)
	}

	p.lastWriteTime = time.Now()
	return nil
}

// readMetricFromFile reads a metric value from a file
func readMetricFromFile(filePath string) (float64, error) {
	data, err := os.ReadFile(filePath)
	if err != nil {
		return 0, err
	}

	value, err := strconv.ParseFloat(string(data), 64)
	if err != nil {
		return 0, fmt.Errorf("failed to parse metric value: %w", err)
	}

	return value, nil
}

// createMessage creates a message with the given sequence number and size
func createMessage(sequence int64, sizeBytes int) ([]byte, error) {
	// Calculate padding size (accounting for JSON overhead)
	baseMsg := Message{
		Sequence:  sequence,
		Timestamp: float64(time.Now().UnixNano()) / 1e9,
		Data:      "",
	}

	baseJSON, err := json.Marshal(baseMsg)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal base message: %w", err)
	}

	paddingSize := sizeBytes - len(baseJSON)
	if paddingSize < 0 {
		paddingSize = 0
	}

	// Create the final message with padding
	msg := Message{
		Sequence:  sequence,
		Timestamp: float64(time.Now().UnixNano()) / 1e9,
		Data:      string(make([]byte, paddingSize)),
	}

	return json.Marshal(msg)
}

// adjustMessageRate adjusts the message rate based on current conditions
func adjustMessageRate(currentRate int, actualRate float64, actualLatency float64) int {
	// If we don't have metrics yet, hold current rate
	if actualRate == 0 || actualLatency == 0 {
		return currentRate
	}

	// If latency is too high, hold current rate
	if actualLatency >= targetLatencyMs {
		return currentRate
	}

	// If actual rate is below target rate margin, hold current rate
	if actualRate < float64(currentRate)*targetRateMargin {
		return currentRate
	}

	// Increase rate by configured multiplier
	newRate := int(float64(currentRate) * targetRateMult)

	// Cap at configured max message rate
	if newRate > maxMessageRate {
		newRate = maxMessageRate
	}

	return newRate
}

// createMessageBatch creates a batch of messages
func createMessageBatch(startSeq int64, count int, sizeBytes int) (*MessageBatch, error) {
	log.Printf("Creating message batch: startSeq=%d, count=%d, sizeBytes=%d, skew_factor=%.2f", startSeq, count, sizeBytes, partitionSkew)
	batch := &MessageBatch{
		messages: make([]*sarama.ProducerMessage, 0, count),
	}

	for i := 0; i < count; i++ {
		msgBytes, err := createMessage(startSeq+int64(i), sizeBytes)
		if err != nil {
			log.Printf("Error creating message %d: %v", i, err)
			return nil, err
		}

		var keyEncoder sarama.Encoder
		var producerMsg *sarama.ProducerMessage

		if rand.Float64() < partitionSkew {
			keyEncoder = sarama.StringEncoder("skew_key_0")
			producerMsg = &sarama.ProducerMessage{
				Topic:     kafkaTopic,
				Value:     sarama.ByteEncoder(msgBytes),
				Key:       keyEncoder,
				Partition: 0,
			}
		} else {
			keyEncoder = sarama.StringEncoder(uuid.New().String())
			producerMsg = &sarama.ProducerMessage{
				Topic: kafkaTopic,
				Value: sarama.ByteEncoder(msgBytes),
				Key:   keyEncoder,
			}
		}

		batch.messages = append(batch.messages, producerMsg)
		batch.size++
	}
	log.Printf("Successfully created batch of %d messages", batch.size)
	return batch, nil
}

// sendBatch sends a batch of messages
func sendBatch(producer sarama.AsyncProducer, batch *MessageBatch) {
	log.Printf("sendBatch: Sending %d messages to AsyncProducer.Input()", batch.size)
	for i, msg := range batch.messages {
		select {
		case producer.Input() <- msg:
		case <-time.After(1 * time.Second): // Timeout to prevent deadlock if Input() is full and not draining
			log.Printf("sendBatch: Timeout enqueuing message %d/%d to producer.Input(). Producer buffer might be full.", i+1, batch.size)
			// Optionally, we could stop trying to send the rest of the batch here
			return
		}
	}
	log.Printf("sendBatch: All %d messages enqueued to AsyncProducer.Input()", batch.size)
}

func main() {
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
	log.Printf("--- Kafka Throughput Demo Producer (Go - Async) ---")
	log.Printf("Target Kafka Broker: %s", kafkaBroker)
	log.Printf("Target Kafka Topic: %s", kafkaTopic)
	log.Printf("Initial Message Rate: %d/s", initialMessageRate)
	log.Printf("Message Size: %d bytes", messageSizeBytes)
	log.Printf("Client ID: %s", producerClientID)
	log.Printf("Max Message Rate: %d/s", maxMessageRate)
	log.Printf("Target Rate Margin: %.2f", targetRateMargin)
	log.Printf("Target Rate Multiplier: %.2f", targetRateMult)

	// partitionSkew is initialized in the init() function
	log.Printf("Partition Skew Factor: %.2f", partitionSkew)

	// Calculate effectiveMaxTokensForBucket after all env vars are parsed
	effectiveMaxTokensForBucket = float64(maxMessageRate / batchesPerSecond)
	if effectiveMaxTokensForBucket < 100 { // Ensure a minimum reasonable capacity
		effectiveMaxTokensForBucket = 100
	}
	log.Printf("Token Bucket Max Tokens (Capacity): %.2f", effectiveMaxTokensForBucket)

	config := sarama.NewConfig()
	config.Producer.RequiredAcks = sarama.WaitForLocal
	config.Producer.Retry.Max = 3
	config.Producer.Flush.Frequency = 5 * time.Millisecond
	config.Producer.Flush.Bytes = 5 * 1024 * 1024
	config.Producer.Flush.Messages = 5000
	config.Producer.Compression = sarama.CompressionSnappy
	config.Producer.MaxMessageBytes = 1000000
	config.Net.MaxOpenRequests = 20
	config.Producer.Return.Successes = true // Important for AsyncProducer
	config.Producer.Return.Errors = true   // Important for AsyncProducer
	config.ClientID = producerClientID
	config.ChannelBufferSize = 1024

	var producer sarama.AsyncProducer // Changed to AsyncProducer
	var err error
	for retries := 0; retries < maxRetries; retries++ {
		producer, err = sarama.NewAsyncProducer([]string{kafkaBroker}, config)
		if err == nil {
			log.Printf("AsyncProducer initialized successfully.")
			break
		}
		delay := time.Duration(initialRetryDelayS*(1<<retries)) * time.Second
		log.Printf("Failed to create AsyncProducer (attempt %d/%d): %v. Retrying in %v...",
			retries+1, maxRetries, err, delay)
		time.Sleep(delay)
	}
	if err != nil {
		log.Fatalf("Failed to create AsyncProducer after %d retries: %v", maxRetries, err)
	}
	defer func() {
		log.Printf("Attempting to close AsyncProducer...")
		if err := producer.Close(); err != nil {
			log.Printf("Error closing producer: %v", err)
		}
		log.Printf("AsyncProducer closed.")
	}()

	// Goroutine to handle successful deliveries
	go func() {
		for succ := range producer.Successes() {
			_ = succ // Avoid unused variable error if logging is commented out
		}
		log.Printf("Producer Successes channel closed.")
	}()

	// Goroutine to handle delivery errors
	go func() {
		for err := range producer.Errors() {
			log.Printf("Failed to send message: %v", err)
			// Here you could implement logic to retry, refund tokens, etc.
			// For now, just logging. If a message fails, tokens are still spent.
		}
		log.Printf("Producer Errors channel closed.")
	}()

	// Initialize stats
	if err := stats.writeStats(); err != nil {
		log.Printf("Warning: Failed to write initial stats: %v", err)
	}

	// Setup context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Handle signals for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-sigChan
		log.Printf("Received shutdown signal. Flushing messages...")
		cancel()
	}()

	// Initialize token bucket for rate control
	tokenBucket := newTokenBucket(float64(stats.targetRate), effectiveMaxTokensForBucket)
	log.Printf("Initialized token bucket with rate %.2f/s, capacity: %.2f, current tokens: %.2f",
		float64(stats.targetRate), effectiveMaxTokensForBucket, tokenBucket.tokens)

	// Message sending loop with batching
	var sequence int64
	intervalStart := time.Now()
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()

	// Rate control variables
	targetRatePerBatch := stats.targetRate / batchesPerSecond
	if targetRatePerBatch < 1 {
		targetRatePerBatch = 1
	}
	log.Printf("Initial batch size: %d messages (target rate: %d/s, batches: %d/s)",
		targetRatePerBatch, stats.targetRate, batchesPerSecond)

	rateLimiter := time.NewTicker(batchConfig.MaxBatchDelay)
	defer rateLimiter.Stop()

	log.Printf("Starting main message loop with batch delay: %v", batchConfig.MaxBatchDelay)

	for {
		select {
		case <-ctx.Done():
			log.Printf("Shutting down producer via ctx.Done()...")
			// producer.AsyncClose() // Start the graceful shutdown process for AsyncProducer
			return
		case <-ticker.C:
			log.Printf("Ticker tick received, checking metrics...")
			// Calculate actual rate for this interval - Now using KMinion's reported rate
			elapsed := time.Since(intervalStart).Seconds()
			// internalActualRate := 0.0 // Keep for logging if desired, but not for rate adjustment
			// if elapsed > 0 { // Avoid division by zero if interval is too short
			// 	internalActualRate = float64(atomic.LoadInt64(&messagesSentThisInterval)) / elapsed
			// }

			kminionActualRate, err := readMetricFromFile(kminionProducerActualRateFile)
			if err != nil {
				log.Printf("Warning: Failed to read KMinion actual rate from %s: %v. Rate adjustment might be impaired.", kminionProducerActualRateFile, err)
				// Optionally, decide on a fallback behavior, e.g., hold current rate or use internal rate if available and desired.
				// For now, if kminion rate is unavailable, adjustMessageRate will receive 0 and likely hold the rate.
			}

			// Read current latency
			actualLatency, err := readMetricFromFile(latencyFile)
			if err != nil {
				// Only log if it's not the expected "N/A" or missing file case
				if err.Error() != "failed to parse metric value: strconv.ParseFloat: parsing \"N/A\": invalid syntax" &&
				   !strings.Contains(err.Error(), "no such file or directory") {
					log.Printf("Warning: Failed to read latency: %v", err)
				}
			}

			// Adjust rate based on conditions using KMinion's rate
			newRate := adjustMessageRate(stats.targetRate, kminionActualRate, actualLatency)
			if newRate != stats.targetRate {
				log.Printf("Adjusting rate from %d to %d/s (KMinion Actual: %.2f/s, Latency: %.2fms)", stats.targetRate, newRate, kminionActualRate, actualLatency)
				stats.targetRate = newRate
				tokenBucket.setRate(float64(newRate))
				// Update batch size for new rate
				targetRatePerBatch = newRate / batchesPerSecond
				if targetRatePerBatch < 1 {
					targetRatePerBatch = 1
				}
				if err := stats.writeStats(); err != nil {
					log.Printf("Warning: Failed to write stats: %v", err)
				}
			}

			// Log interval stats
			log.Printf("Interval: %.2fs, Target Rate: %d/s, KMinion Actual Rate: %.2f/s, Batch Size: %d, Tokens: %.1f",
				elapsed, stats.targetRate, kminionActualRate,
				targetRatePerBatch, tokenBucket.tokens)

			// Reset for next interval
			// atomic.StoreInt64(&messagesSentThisInterval, 0) // No longer primary
			intervalStart = time.Now()

		case <-rateLimiter.C:
			log.Printf("Rate limiter tick received, checking tokens...")
			tokensNeeded := float64(targetRatePerBatch)
			currentTokens := tokenBucket.tokens // For logging before take()
			log.Printf("Current tokens: %.2f, needed: %.2f", currentTokens, tokensNeeded)

			if tokenBucket.take(tokensNeeded) {
				log.Printf("Got enough tokens, preparing batch...")
				batchSize := targetRatePerBatch
				if batchSize > batchConfig.MaxBatchSize {
					batchSize = batchConfig.MaxBatchSize
				}
				if batchSize <= 0 { // Ensure batchSize is at least 1 if targetRatePerBatch was 0
					log.Printf("Batch size is %d, skipping batch creation.", batchSize)
					continue
				}
				log.Printf("Calculated batch size: %d", batchSize)

				log.Printf("Creating message batch...")
				currentSequence := atomic.LoadInt64(&sequence)
				batch, err := createMessageBatch(currentSequence, batchSize, stats.messageSize)
				if err != nil {
					log.Printf("Error creating message batch: %v", err)
					tokenBucket.refill() // Refund tokens if batch creation failed
					log.Printf("Refilled token bucket after batch creation error")
					continue
				}
				atomic.AddInt64(&sequence, int64(batch.size)) // Increment sequence by actual batch size
				log.Printf("Successfully created batch, attempting to send...")

				sendBatch(producer, batch) // This is now non-blocking
				// atomic.AddInt64(&messagesSentThisInterval, int64(batch.size)) // No longer primary for rate adjustment
				log.Printf("Enqueued batch of %d messages to AsyncProducer, tokens after take: %.2f",
					batch.size, tokenBucket.tokens)

			} else {
				log.Printf("Not enough tokens (need %.2f, have %.2f), waiting for next tick",
					tokensNeeded, currentTokens)
			}
		}
	}
}
