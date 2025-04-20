# Recent Changes (v0.4.1)

## New chaos-monkey Example for Kubernetes Testing

The vibectl 0.4.1 release introduces a new chaos-monkey example that demonstrates advanced Kubernetes resilience testing:

- **Red vs. Blue Team Scenario**: Competitive environment with blue team maintaining stability and red team simulating disruptions
- **Containerized vibectl Agents**: Demonstrates using vibectl within Kubernetes pods for automation
- **Metrics Collection**: Built-in performance evaluation to measure system resilience
- **K8s Integration**: Seamless interaction with existing Kubernetes clusters

## Bug Fixes & Improvements

- **Format String Handling**: Fixed KeyError issues when prompt templates contain format placeholders
- **Robust Prompt Processing**: Added fallback string replacement method for reliable template handling
- **Code Quality**: Resolved linting issues in chaos-monkey components

## Getting Started with Chaos Monkey

```bash
# Navigate to the example directory
cd examples/k8s-sandbox/chaos-monkey

# Set up the demo environment
./setup.sh

# Start the red vs. blue team scenario
./start-scenario.sh

# Monitor resilience metrics
./show-metrics.sh

# Clean up when finished
./cleanup.sh
```

See the example README for detailed configuration options and customization.
