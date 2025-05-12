package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/IBM/sarama"
)

// Configuration from environment variables with defaults
var (
	kafkaBroker         = getEnv("KAFKA_BROKER", "kafka:9092")
	kafkaTopic          = getEnv("KAFKA_TOPIC", "throughput-topic")
	consumerGroupID     = getEnv("CONSUMER_GROUP_ID", "kafka-throughput-consumer-group")
	consumerClientID    = getEnv("CONSUMER_CLIENT_ID", "kafka-throughput-consumer")
	maxRetries          = getEnvAsInt("MAX_RETRIES", 5)
	initialRetryDelayS  = getEnvAsInt("INITIAL_RETRY_DELAY_S", 5)
	logInterval         = 5000 // Messages between log entries
)

func getEnv(key, defaultValue string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return defaultValue
}

func getEnvAsInt(key string, defaultValue int) int {
	if value, exists := os.LookupEnv(key); exists {
		if intVal, err := strconv.Atoi(value); err == nil {
			return intVal
		}
	}
	return defaultValue
}

func setupLogger() *log.Logger {
	return log.New(os.Stdout, "", log.LstdFlags)
}

func createConsumerGroup() (sarama.ConsumerGroup, error) {
	config := sarama.NewConfig()
	config.Consumer.Group.Rebalance.Strategy = sarama.BalanceStrategyRoundRobin
	config.Consumer.Offsets.Initial = sarama.OffsetNewest
	config.ClientID = consumerClientID

	// Retry logic for connecting to Kafka
	var consumerGroup sarama.ConsumerGroup
	var err error
	for retry := 0; retry < maxRetries; retry++ {
		consumerGroup, err = sarama.NewConsumerGroup([]string{kafkaBroker}, consumerGroupID, config)
		if err == nil {
			return consumerGroup, nil
		}

		log.Printf("Attempt %d/%d: Could not connect to Kafka broker at %s. Error: %v",
			retry+1, maxRetries, kafkaBroker, err)

		if retry < maxRetries-1 {
			delay := time.Duration(initialRetryDelayS*(1<<retry)) * time.Second
			log.Printf("Retrying in %v...", delay)
			time.Sleep(delay)
		}
	}
	return nil, fmt.Errorf("failed to connect after %d attempts: %v", maxRetries, err)
}

type Consumer struct {
	logger *log.Logger
	ready  chan bool
	msgCount int64
}

func (c *Consumer) Setup(_ sarama.ConsumerGroupSession) error {
	close(c.ready)
	return nil
}

func (c *Consumer) Cleanup(_ sarama.ConsumerGroupSession) error {
	return nil
}

func (c *Consumer) ConsumeClaim(session sarama.ConsumerGroupSession, claim sarama.ConsumerGroupClaim) error {
	for message := range claim.Messages() {
		c.msgCount++
		if c.msgCount%int64(logInterval) == 0 {
			c.logger.Printf("Consumed %d messages. Last offset: %d", c.msgCount, message.Offset)
		}
		session.MarkMessage(message, "")
	}
	return nil
}

func main() {
	logger := setupLogger()
	logger.Println("--- Kafka Throughput Demo Consumer (Go) ---")
	logger.Printf("Target Kafka Broker: %s", kafkaBroker)
	logger.Printf("Target Kafka Topic: %s", kafkaTopic)
	logger.Printf("Consumer Group ID: %s", consumerGroupID)
	logger.Printf("Client ID: %s", consumerClientID)

	consumerGroup, err := createConsumerGroup()
	if err != nil {
		logger.Fatalf("Error creating consumer group: %v", err)
	}
	defer consumerGroup.Close()

	ctx, cancel := context.WithCancel(context.Background())
	consumer := &Consumer{
		logger: logger,
		ready:  make(chan bool),
	}

	// Handle graceful shutdown
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-signals
		logger.Println("Consumer interrupted. Shutting down...")
		cancel()
	}()

	// Start consuming
	for {
		topics := []string{kafkaTopic}
		err := consumerGroup.Consume(ctx, topics, consumer)
		if err != nil {
			logger.Printf("Error from consumer: %v", err)
		}
		if ctx.Err() != nil {
			break
		}
		consumer.ready = make(chan bool)
	}

	logger.Printf("Total messages processed by this instance: %d", consumer.msgCount)
}
