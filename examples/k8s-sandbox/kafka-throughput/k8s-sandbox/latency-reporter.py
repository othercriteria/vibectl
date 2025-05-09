import json
import logging
import os
import subprocess
import time
from collections import deque

import requests
from prometheus_client.parser import text_string_to_metric_families  # type: ignore

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration
STATUS_DIR = os.environ.get("STATUS_DIR", "/tmp/status")
PRODUCER_STATS_FILE_PATH = os.path.join(
    STATUS_DIR, os.environ.get("PRODUCER_STATS_FILE_NAME", "producer_stats.txt")
)
# New output file paths for UI consumption
UI_LATENCY_FILE_PATH = os.path.join(STATUS_DIR, "e2e_latency_ms.txt")
UI_PRODUCER_TARGET_RATE_FILE_PATH = os.path.join(
    STATUS_DIR, "producer_target_rate_value.txt"
)
UI_PRODUCER_ACTUAL_RATE_FILE_PATH = os.path.join(
    STATUS_DIR, "producer_actual_rate_value.txt"
)
UI_CONSUMER_ACTUAL_RATE_FILE_PATH = os.path.join(
    STATUS_DIR, "consumer_actual_rate_value.txt"
)
TARGET_LATENCY_MS_FILE = os.path.join(STATUS_DIR, "target_latency_ms.txt")

TARGET_LATENCY_MS = os.environ.get("TARGET_LATENCY_MS", "10.0")
CONFIGMAP_NAME = os.environ.get("CONFIGMAP_NAME", "kafka-latency-metrics")
CONFIGMAP_NAMESPACE = os.environ.get("CONFIGMAP_NAMESPACE", "kafka")
# Define keys for ConfigMap
LATENCY_CM_KEY = os.environ.get("LATENCY_CM_KEY", "actual_latency_ms")
TARGET_LATENCY_CM_KEY = os.environ.get("TARGET_LATENCY_CM_KEY", "target_latency_ms")
PRODUCER_TARGET_RATE_CM_KEY = os.environ.get(
    "PRODUCER_TARGET_RATE_CM_KEY", "producer_target_rate"
)
PRODUCER_ACTUAL_RATE_CM_KEY = os.environ.get(
    "PRODUCER_ACTUAL_RATE_CM_KEY", "producer_actual_rate"
)
CONSUMER_ACTUAL_RATE_CM_KEY = os.environ.get(
    "CONSUMER_ACTUAL_RATE_CM_KEY", "consumer_actual_rate"
)
TARGET_CONSUMER_GROUP_ID = os.environ.get(
    "TARGET_CONSUMER_GROUP_ID", "kafka-throughput-consumer-group"
)
TARGET_THROUGHPUT_TOPIC_NAME = os.environ.get(
    "TARGET_THROUGHPUT_TOPIC_NAME", "throughput-topic"
)
CHECK_INTERVAL_S = int(os.environ.get("CHECK_INTERVAL_S", "5"))
KUBECTL_CMD = os.environ.get("KUBECTL_CMD", "kubectl")

KMINION_METRICS_URL = os.environ.get(
    "KMINION_METRICS_URL", "http://kminion:8080/metrics"
)

last_known_data: dict[str, str] = {}
# State for E2E latency moving window
previous_e2e_sum: float | None = None
previous_e2e_count: float | None = None
latency_intervals: deque[tuple[float, float]] = (
    deque()
)  # Stores (interval_avg_latency_seconds, interval_count)
# State for E2E Producer Actual Rate moving window
previous_e2e_produced_count: float | None = None
last_check_time_e2e_producer_rate: float | None = None
producer_e2e_rate_intervals: deque[tuple[float, float]] = (
    deque()
)  # Stores (interval_rate_msg_per_sec, interval_duration_sec)
# State for Consumer Actual Rate moving window (using topic offset sum)
previous_consumer_offset_sum: float | None = None
last_check_time_consumer_offset_rate: float | None = None
consumer_offset_rate_intervals: deque[tuple[float, float]] = (
    deque()
)  # Stores (interval_rate_msg_per_sec, interval_duration_sec)

LATENCY_WINDOW_TARGET_COUNT = 100
LATENCY_WINDOW_MIN_COUNT = 50
MAX_LATENCY_INTERVALS = (
    20  # Safety net for deque size by number of intervals for latency
)

# Constants for rate calculation windows (can be tuned)
RATE_WINDOW_TARGET_SECONDS = (
    60  # Target total duration for rate window (e.g., 1 minute)
)
RATE_WINDOW_MIN_SECONDS = 30  # Minimum duration to keep when trimming
MAX_RATE_INTERVALS = 20  # Max number of distinct rate intervals to store


# --- Moving Window Calculator Class ---
class MovingWindowCalculator:
    def __init__(
        self,
        name: str,
        window_target_weight: float,
        window_min_weight: float,
        max_intervals: int,
        is_latency_calc: bool = False,
    ):
        self.name = name
        self.intervals: deque[tuple[float, float]] = deque()  # Stores (value, weight)
        self.window_target_weight = window_target_weight
        self.window_min_weight = window_min_weight
        self.max_intervals = max_intervals
        self.is_latency_calc = is_latency_calc  # True if this calculates latency (value=avg_latency, weight=count)
        # False if rate (value=rate, weight=duration)

        # State for rate calculations (value per time)
        self.previous_total_metric_value: float | None = None
        self.previous_timestamp: float | None = None

        # State for latency calculations (sum / count)
        self.previous_total_metric_sum: float | None = None
        self.previous_total_metric_count: float | None = None

    def _manage_window(self) -> None:
        # 1. Safety net by number of intervals
        while len(self.intervals) > self.max_intervals:
            removed_val, removed_weight = self.intervals.popleft()
            logging.debug(
                f"[{self.name}] Trimmed window (max intervals). "
                f"Removed: ({removed_val:.4f}, {removed_weight:.2f}). "
                f"New size: {len(self.intervals)}"
            )

        # 2. By total weight in the window
        current_total_weight = sum(weight for _, weight in self.intervals)
        while (
            len(self.intervals) > 1
            and current_total_weight > self.window_target_weight
            and (current_total_weight - self.intervals[0][1]) >= self.window_min_weight
        ):
            removed_val, removed_weight = self.intervals.popleft()
            current_total_weight -= removed_weight
            logging.debug(
                f"[{self.name}] Trimmed window (weight). "
                f"Removed: ({removed_val:.4f}, {removed_weight:.2f}). "
                f"New total weight: {current_total_weight:.2f}. "
                f"Intervals: {len(self.intervals)}"
            )

    def handle_reset(self, reason: str) -> None:
        logging.warning(
            f"[{self.name}] {reason} Clearing window and resetting previous values."
        )
        self.intervals.clear()
        self.previous_total_metric_value = None
        self.previous_timestamp = None
        self.previous_total_metric_sum = None
        self.previous_total_metric_count = None

    def update_rate(
        self, current_total_value: float | None, current_timestamp: float
    ) -> None:
        if current_total_value is None:
            logging.warning(
                f"[{self.name}] Current total value is None, cannot update rate."
            )
            # Rely on existing window data if any, or get_average() will return N/A
            return

        if (
            self.previous_total_metric_value is not None
            and current_total_value < self.previous_total_metric_value
        ):
            self.handle_reset(
                "Counter appears to have reset. "
                f"Old: {self.previous_total_metric_value}, "
                f"New: {current_total_value}."
            )

        if (
            self.previous_total_metric_value is not None
            and self.previous_timestamp is not None
        ):
            delta_value = current_total_value - self.previous_total_metric_value
            delta_time = current_timestamp - self.previous_timestamp

            if delta_time > 0 and delta_value >= 0:
                interval_rate = delta_value / delta_time
                self.intervals.append(
                    (interval_rate, delta_time)
                )  # Weight is delta_time
                logging.debug(
                    f"[{self.name}] Added to window: interval_rate={interval_rate:.2f}, "
                    f"duration={delta_time:.2f}s. Intervals: {len(self.intervals)}"
                )
            elif delta_value < 0:
                logging.warning(
                    f"[{self.name}] Negative delta_value ({delta_value}). Interval not added."
                )
            # elif delta_time <=0 - do nothing, not enough time passed
        elif self.previous_total_metric_value is None:  # First run for this calculator
            logging.info(
                f"[{self.name}] First data point. Will calculate rate on next cycle."
            )

        self.previous_total_metric_value = current_total_value
        self.previous_timestamp = current_timestamp
        self._manage_window()

    def update_latency(
        self, current_total_sum: float | None, current_total_count: float | None
    ) -> None:
        if current_total_sum is None or current_total_count is None:
            logging.warning(
                f"[{self.name}] Current sum or count is None, cannot update latency."
            )
            return

        if (
            self.previous_total_metric_sum is not None
            and current_total_sum < self.previous_total_metric_sum
        ):
            self.handle_reset(
                "Sum counter appears to have reset. "
                f"Old: {self.previous_total_metric_sum}, "
                f"New: {current_total_sum}."
            )
        # Also check count reset, though sum reset usually implies count reset too
        elif (
            self.previous_total_metric_count is not None
            and current_total_count < self.previous_total_metric_count
        ):
            self.handle_reset(
                "Count counter appears to have reset. "
                f"Old: {self.previous_total_metric_count}, "
                f"New: {current_total_count}."
            )

        delta_sum = 0.0
        delta_count = 0.0

        if (
            self.previous_total_metric_sum is not None
            and self.previous_total_metric_count is not None
        ):
            if (
                current_total_sum >= self.previous_total_metric_sum
                and current_total_count >= self.previous_total_metric_count
            ):
                delta_sum = current_total_sum - self.previous_total_metric_sum
                delta_count = current_total_count - self.previous_total_metric_count
            else:  # Anomaly or missed reset after first data point
                logging.warning(
                    f"[{self.name}] Anomaly detected in sum/count post-reset check. Re-initializing interval with current totals."
                )
                delta_sum = current_total_sum
                delta_count = current_total_count
                # Do not clear self.intervals here, let anomaly be a single point if window was already populated
        else:  # First data point or after a reset
            delta_sum = current_total_sum
            delta_count = current_total_count

        if delta_count > 0:
            interval_avg_latency = delta_sum / delta_count if delta_sum >= 0 else 0.0
            self.intervals.append(
                (interval_avg_latency, delta_count)
            )  # Weight is delta_count
            logging.debug(
                f"[{self.name}] Added to window: interval_avg_latency={interval_avg_latency:.4f}, "
                f"delta_count={delta_count}. Intervals: {len(self.intervals)}"
            )
        elif delta_count == 0:
            logging.debug(
                f"[{self.name}] No new messages in this interval. Window not updated with new data."
            )
        else:  # delta_count < 0 should be handled by reset
            logging.warning(
                f"[{self.name}] Negative delta_count ({delta_count}) encountered unexpectedly. Interval not added."
            )

        self.previous_total_metric_sum = current_total_sum
        self.previous_total_metric_count = current_total_count
        self._manage_window()

    def get_average(self) -> str:
        if not self.intervals:
            logging.info(f"[{self.name}] Window is empty. Reporting N/A.")
            return "N/A"

        weighted_sum_of_values = sum(val * weight for val, weight in self.intervals)
        current_total_weight_in_window = sum(weight for _, weight in self.intervals)

        if current_total_weight_in_window == 0:
            logging.info(f"[{self.name}] Total weight in window is 0. Reporting N/A.")
            return "N/A"

        moving_average = weighted_sum_of_values / current_total_weight_in_window

        if self.is_latency_calc:
            moving_average_ms = moving_average * 1000
            logging.info(
                f"[{self.name}] Moving avg: {moving_average_ms:.2f} ms "
                f"(window_weight: {current_total_weight_in_window}, intervals: {len(self.intervals)})"
            )
            return f"{moving_average_ms:.2f}"
        else:  # It's a rate
            logging.info(
                f"[{self.name}] Moving avg: {moving_average:.2f} msg/s "
                f"(window_weight: {current_total_weight_in_window:.2f}s, intervals: {len(self.intervals)})"
            )
            return f"{moving_average:.2f}"


# --- Initialize Calculators ---
e2e_latency_calculator = MovingWindowCalculator(
    name="E2E Latency",
    window_target_weight=LATENCY_WINDOW_TARGET_COUNT,
    window_min_weight=LATENCY_WINDOW_MIN_COUNT,
    max_intervals=MAX_LATENCY_INTERVALS,
    is_latency_calc=True,
)
topic_producer_rate_calculator = MovingWindowCalculator(
    name=f"Producer Rate ({TARGET_THROUGHPUT_TOPIC_NAME})",
    window_target_weight=RATE_WINDOW_TARGET_SECONDS,
    window_min_weight=RATE_WINDOW_MIN_SECONDS,
    max_intervals=MAX_RATE_INTERVALS,
)
consumer_rate_calculator = MovingWindowCalculator(
    name=f"Consumer Rate ({TARGET_CONSUMER_GROUP_ID} on {TARGET_THROUGHPUT_TOPIC_NAME})",
    window_target_weight=RATE_WINDOW_TARGET_SECONDS,
    window_min_weight=RATE_WINDOW_MIN_SECONDS,
    max_intervals=MAX_RATE_INTERVALS,
)


def write_metric_to_file(file_path: str, value: str) -> None:
    """Writes a single metric value to a file."""
    try:
        # Ensure the directory exists (STATUS_DIR should already exist)
        with open(file_path, "w") as f:
            f.write(value)
        logging.debug(f"Wrote '{value}' to {file_path}")
    except Exception as e:
        logging.error(f"Failed to write to {file_path}: {e}")


def extract_specific_metric(
    raw_metrics_text: str,
    target_family_name: str,
    target_sample_name_suffix: str,
    target_labels: dict[str, str] | None = None,
) -> float | None:
    """Extracts a specific metric value from raw Prometheus text."""
    try:
        for family in text_string_to_metric_families(raw_metrics_text):
            if family.name == target_family_name:
                # Construct the full sample name we expect
                expected_sample_name = target_family_name
                if target_sample_name_suffix:  # Append suffix if provided
                    expected_sample_name += target_sample_name_suffix

                logging.debug(
                    f"Searching in family '{family.name}' for sample '{expected_sample_name}' with labels {target_labels}"
                )
                for sample in family.samples:
                    logging.debug(
                        f"  Inspecting sample: {sample.name}, Labels: {sample.labels}, Value: {sample.value}"
                    )
                    if sample.name == expected_sample_name:
                        if target_labels:
                            match = True
                            for key, value in target_labels.items():
                                if sample.labels.get(key) != value:
                                    match = False
                                    break
                            if match:
                                logging.debug(
                                    f"    Found matching sample: {sample.value}"
                                )
                                return float(sample.value)
                        else:  # No labels to match, just name is enough
                            logging.debug(
                                f"    Found matching sample (no labels specified): {sample.value}"
                            )
                            return float(sample.value)
        logging.warning(
            f"Metric '{target_family_name}{target_sample_name_suffix}' with labels {target_labels} not found."
        )
        return None
    except Exception as e:
        logging.error(f"Error in extract_specific_metric for {target_family_name}: {e}")
        return None


def get_kminion_avg_e2e_latency(raw_metrics_text: str) -> str:
    """Calculates a moving average for E2E latency from KMinion metrics."""

    current_sum = extract_specific_metric(
        raw_metrics_text,
        target_family_name="kminion_end_to_end_roundtrip_latency_seconds",
        target_sample_name_suffix="_sum",
    )
    current_count = extract_specific_metric(
        raw_metrics_text,
        target_family_name="kminion_end_to_end_roundtrip_latency_seconds",
        target_sample_name_suffix="_count",
    )

    if current_sum is None or current_count is None:
        logging.warning(
            "Could not extract KMinion E2E sum or count for latency calculation."
        )
        # Return current average from window if fetch failed but window has data
        return e2e_latency_calculator.get_average()

    e2e_latency_calculator.update_latency(current_sum, current_count)
    return e2e_latency_calculator.get_average()


def get_topic_producer_actual_rate(raw_metrics_text: str) -> str:
    """Calculates a moving average for actual producer rate for the target topic from KMinion metrics."""
    current_time = time.time()

    current_high_water_mark_sum = extract_specific_metric(
        raw_metrics_text,
        target_family_name="kminion_kafka_topic_high_water_mark_sum",
        target_sample_name_suffix="",  # Full name is in family.name
        target_labels={"topic_name": TARGET_THROUGHPUT_TOPIC_NAME},
    )

    if current_high_water_mark_sum is None:
        logging.warning(
            f"Could not extract high water mark sum for topic '{TARGET_THROUGHPUT_TOPIC_NAME}' for producer rate."
        )
        return topic_producer_rate_calculator.get_average()

    topic_producer_rate_calculator.update_rate(
        current_high_water_mark_sum, current_time
    )
    return topic_producer_rate_calculator.get_average()


def get_consumer_actual_rate(raw_metrics_text: str) -> str:
    """Calculates a moving average for consumer actual rate using topic offset sum."""
    current_time = time.time()

    current_total_offsets = extract_specific_metric(
        raw_metrics_text,
        target_family_name="kminion_kafka_consumer_group_topic_offset_sum",
        target_sample_name_suffix="",
        target_labels={
            "group_id": TARGET_CONSUMER_GROUP_ID,
            "topic_name": TARGET_THROUGHPUT_TOPIC_NAME,
        },
    )

    if current_total_offsets is None:
        logging.warning(
            "Could not extract consumer group topic offset sum for consumer rate."
        )
        return consumer_rate_calculator.get_average()

    consumer_rate_calculator.update_rate(current_total_offsets, current_time)
    return consumer_rate_calculator.get_average()


def update_configmap_with_kubectl(data_to_update: dict) -> None:
    """Updates the ConfigMap using kubectl patch with the provided data."""
    global last_known_data

    # Check if data has actually changed
    if data_to_update == last_known_data:
        logging.debug(
            "Metrics unchanged (%s). Skipping ConfigMap update.", data_to_update
        )
        return

    logging.info(
        "Metrics changed to %s. Updating ConfigMap %s/%s via kubectl...",
        data_to_update,
        CONFIGMAP_NAMESPACE,
        CONFIGMAP_NAME,
    )

    patch_data = {"data": data_to_update}
    patch_str = json.dumps(patch_data)

    cmd = [
        KUBECTL_CMD,
        "patch",
        "configmap",
        CONFIGMAP_NAME,
        "-n",
        CONFIGMAP_NAMESPACE,
        "--type=merge",
        "-p",
        patch_str,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logging.info("kubectl patch successful: %s", result.stdout.strip())
        last_known_data = data_to_update.copy()
    except subprocess.CalledProcessError as e:
        logging.error(
            "kubectl patch failed (Exit code: %d): %s", e.returncode, e.stderr.strip()
        )
    except FileNotFoundError:
        logging.error(
            "kubectl command ('%s') not found. Ensure it is in PATH.", KUBECTL_CMD
        )
    except Exception as e:
        logging.error("An unexpected error occurred running kubectl: %s", e)


def parse_producer_stats(file_path: str) -> tuple[str, str]:
    """Reads producer stats file and extracts target rate and size."""
    target_rate = "N/A"
    size = "N/A"
    try:
        if os.path.exists(file_path):
            with open(file_path) as f:
                content = f.read().strip()
                if content:
                    stats = {}
                    for item in content.split(","):
                        parts = item.strip().split("=", 1)
                        if len(parts) == 2:
                            stats[parts[0].strip()] = parts[1].strip()
                    target_rate = stats.get("target_rate", "Parse Error")
                    # actual_rate is no longer parsed here
                    size = stats.get("size", "Parse Error")
                else:
                    target_rate = "Empty File"
                    size = "Empty File"
        else:
            target_rate = "Not Found"
            size = "Not Found"
    except Exception as e:
        logging.error(f"Error reading/parsing producer stats {file_path}: {e}")
        target_rate = "Read Error"
        size = "Read Error"
    return target_rate, size


def main() -> None:
    logging.info(
        "--- Metrics Reporter (KMinion E2E Latency & Producer Stats via kubectl) --- "
    )
    logging.info(f"Fetching KMinion E2E Latency from: {KMINION_METRICS_URL}")
    logging.info(f"Monitoring Producer Stats File: {PRODUCER_STATS_FILE_PATH}")
    logging.info(f"Updating ConfigMap: {CONFIGMAP_NAMESPACE}/{CONFIGMAP_NAME}")
    logging.info(
        f"  ConfigMap Keys: {LATENCY_CM_KEY} (KMinion avg E2E), "
        f"{TARGET_LATENCY_CM_KEY}, {PRODUCER_TARGET_RATE_CM_KEY}, "
        f"{PRODUCER_ACTUAL_RATE_CM_KEY}, {CONSUMER_ACTUAL_RATE_CM_KEY}"
    )
    logging.info(f"Writing KMinion E2E Latency to: {UI_LATENCY_FILE_PATH}")
    logging.info(
        f"Writing Producer Target Rate to: {UI_PRODUCER_TARGET_RATE_FILE_PATH}"
    )
    logging.info(
        f"Writing Producer Actual Rate to: {UI_PRODUCER_ACTUAL_RATE_FILE_PATH}"
    )
    logging.info(
        f"Writing Consumer Actual Rate to: {UI_CONSUMER_ACTUAL_RATE_FILE_PATH}"
    )
    logging.info(f"Static Target Latency for ConfigMap: {TARGET_LATENCY_MS} ms")
    logging.info(f"Writing Target Latency for UI to: {TARGET_LATENCY_MS_FILE}")
    logging.info(f"Check interval: {CHECK_INTERVAL_S}s")
    logging.info(f"Using kubectl command: {KUBECTL_CMD}")

    # Ensure STATUS_DIR exists
    if not os.path.exists(STATUS_DIR):
        try:
            os.makedirs(STATUS_DIR, exist_ok=True)
            logging.info(f"Created status directory: {STATUS_DIR}")
        except Exception as e:
            logging.error(f"Failed to create status directory {STATUS_DIR}: {e}")
            # Depending on severity, might want to exit or handle differently

    while True:
        try:
            # Helper to check if a string represents a valid number (int or float)
            # and is not one of the known error strings from parse_producer_stats
            error_strings_from_parser = [
                "N/A",
                "Parse Error",
                "Empty File",
                "Not Found",
                "Read Error",
                "Malformed",
                "No Data",
            ]

            def to_payload_value(parsed_value: str) -> str:
                is_error = parsed_value in error_strings_from_parser
                is_numeric = False
                if not is_error:
                    try:
                        float(parsed_value)  # Check if it can be cast to float
                        is_numeric = True
                    except ValueError:
                        pass  # Not numeric

                if is_numeric:
                    return parsed_value
                else:
                    # If it was an error string from parser, or became non-numeric for other reasons
                    logging.debug(
                        f"Converting '{parsed_value}' to 'N/A' for payload/UI file."
                    )
                    return "N/A"

            # Get current E2E latency from KMinion
            # First, fetch raw metrics once
            raw_kminion_metrics = "N/A"
            try:
                response = requests.get(KMINION_METRICS_URL, timeout=10)
                response.raise_for_status()
                raw_kminion_metrics = response.text
                logging.debug("Successfully fetched KMinion metrics for this cycle.")
            except requests.exceptions.RequestException as e:
                logging.error(
                    f"Error fetching KMinion metrics from {KMINION_METRICS_URL} for this cycle: {e}"
                )
            except Exception as e:  # Catch any other parsing error from KMinion
                logging.error(f"Generic error fetching KMinion metrics: {e}")

            current_e2e_latency_ms = "N/A"
            if raw_kminion_metrics != "N/A":
                current_e2e_latency_ms = get_kminion_avg_e2e_latency(
                    raw_kminion_metrics
                )

            # Calculate consumer commit rate
            current_consumer_rate = "N/A"
            if raw_kminion_metrics != "N/A":
                current_consumer_rate = get_consumer_actual_rate(raw_kminion_metrics)

            # Calculate E2E Producer Actual Rate (moving average from KMinion)
            current_topic_producer_actual_rate = "N/A"
            if raw_kminion_metrics != "N/A":
                current_topic_producer_actual_rate = get_topic_producer_actual_rate(
                    raw_kminion_metrics
                )

            # Read current producer target rate and size (actual rate now from KMinion)
            parsed_target_rate, _ = (
                parse_producer_stats(  # Size is ignored here for now, UI reads it directly
                    PRODUCER_STATS_FILE_PATH
                )
            )

            current_producer_target_rate_for_payload = to_payload_value(
                parsed_target_rate
            )

            # Prepare data payload for ConfigMap
            data_payload_cm = {
                LATENCY_CM_KEY: current_e2e_latency_ms,
                TARGET_LATENCY_CM_KEY: TARGET_LATENCY_MS,
                PRODUCER_TARGET_RATE_CM_KEY: current_producer_target_rate_for_payload,
                PRODUCER_ACTUAL_RATE_CM_KEY: current_topic_producer_actual_rate,
                CONSUMER_ACTUAL_RATE_CM_KEY: current_consumer_rate,
            }

            # Update ConfigMap
            update_configmap_with_kubectl(data_payload_cm)

            # Update files for UI
            write_metric_to_file(UI_LATENCY_FILE_PATH, current_e2e_latency_ms)
            write_metric_to_file(
                UI_PRODUCER_TARGET_RATE_FILE_PATH,
                current_producer_target_rate_for_payload,
            )
            write_metric_to_file(
                UI_PRODUCER_ACTUAL_RATE_FILE_PATH, current_topic_producer_actual_rate
            )  # Use new KMinion based rate
            write_metric_to_file(
                UI_CONSUMER_ACTUAL_RATE_FILE_PATH, current_consumer_rate
            )
            write_metric_to_file(TARGET_LATENCY_MS_FILE, TARGET_LATENCY_MS)

        except Exception as e:
            logging.error("An error occurred in the main loop: %s", e)

        time.sleep(CHECK_INTERVAL_S)


if __name__ == "__main__":
    main()
