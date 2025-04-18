# Chaos Monkey Overseer

The overseer component provides a web-based dashboard for monitoring the chaos monkey demo, including:

- Real-time service availability tracking
- Service health history and status timelines
- Visualization of uptime and overall system health
- Live logs from both the blue (defender) and red (attacker) agents

## Features

- **Service Status Dashboard**: Real-time display of frontend service availability
- **Uptime Visualization**: Historical data on system uptime and reliability
- **Agent Activity Monitoring**: Live logs from both blue and red agents
- **Interactive Charts**: Visual representation of service health over time
- **Responsive Design**: Works on desktop and mobile devices

## Technical Implementation

The overseer is built using:

- **Flask**: Lightweight web server framework
- **Socket.IO**: Real-time bidirectional communication
- **Chart.js**: Interactive data visualization
- **Bootstrap**: Responsive UI components
- **Docker**: Containerized deployment

## Architecture

The overseer:

1. **Scrapes status data** from the poller service
2. **Follows logs** from both red and blue agents
3. **Maintains history** of service availability
4. **Provides visualization** via web dashboard
5. **Updates in real-time** using Socket.IO

## Usage

The overseer is automatically started as part of the demo when you run:

```bash
./run.sh
```

Once running, you can access the dashboard at:

```
http://localhost:8080
```

## Configuration

Configuration is handled via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `METRICS_INTERVAL` | 15 | Interval in seconds between metrics updates |
| `SESSION_DURATION` | 30 | Duration in minutes for the demo session |
| `VERBOSE` | false | Enable verbose logging |
| `PORT` | 8080 | Web server port |
| `HOST` | 0.0.0.0 | Web server host |

## API Endpoints

The overseer provides several API endpoints:

- **GET /api/status**: Current service status
- **GET /api/history**: Service status history
- **GET /api/logs/blue**: Blue agent logs
- **GET /api/logs/red**: Red agent logs
- **GET /api/overview**: System health overview
