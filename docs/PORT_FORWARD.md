# Port-Forward Command

The `vibectl port-forward` command provides enhanced port forwarding capabilities with optional traffic monitoring.

## Basic Usage

```bash
# Forward a pod's port to your local machine
vibectl port-forward pod/nginx 8080:80

# Forward a service's port
vibectl port-forward service/database 5432:5432

# Use the vibe interface to describe what you want in natural language
vibectl port-forward vibe "forward port 80 on the web service to my local 8080"
```

## Traffic Monitoring

The port-forward command can provide detailed traffic statistics when you enable traffic monitoring with an intermediate port proxy.

### Enabling Traffic Monitoring

To enable traffic monitoring, you need to configure an intermediate port range:

```bash
# Set a range of ports that can be used for the proxy
vibectl config set intermediate_port_range 10000-11000
```

When this configuration is set, `vibectl port-forward` will:

1. Choose a random port from your configured range
2. Use a proxy layer to monitor traffic between your local port and the Kubernetes resource
3. Display real-time traffic statistics during the session
4. Provide a detailed summary when the session ends

### How It Works

With traffic monitoring enabled:

```
Your Application -> localhost:8080 -> vibectl proxy -> localhost:10123 -> kubectl port-forward -> Kubernetes Pod:80
                      (local port)     (monitors traffic)  (intermediate port)                     (remote port)
```

The proxy layer:
- Counts bytes sent and received
- Measures connection duration and status
- Tracks traffic patterns
- Provides detailed statistics

### Session Summary

When the port-forward session ends, you'll see a detailed summary that includes:

- Connection uptime percentage
- Total data transferred (sent and received)
- Average throughput rates
- Connection attempts and successes
- Full session duration statistics

### Disabling Traffic Monitoring

If you no longer want traffic monitoring:

```bash
vibectl config set intermediate_port_range null
```

## Advanced Options

```bash
# Disable live display
vibectl port-forward pod/nginx 8080:80 --no-live-display

# Show LLM summary of the port-forward session
vibectl port-forward pod/nginx 8080:80 --show-vibe

# Show raw kubectl output
vibectl port-forward pod/nginx 8080:80 --show-raw-output

# Set a specific model for analysis
vibectl port-forward pod/nginx 8080:80 --model claude-3.7-haiku
```

## Security Considerations

When using the traffic monitoring proxy:

1. All traffic passes through a local proxy process on your machine
2. No traffic data is sent to external services (analysis happens locally)
3. The proxy only counts bytes and connection statistics - it doesn't inspect packet contents
4. For sensitive applications, you may prefer to disable monitoring with `vibectl config set intermediate_port_range null`
