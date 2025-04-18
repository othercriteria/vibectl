# Overseer Component Structure

This document outlines the structure and organization of the overseer component in the chaos-monkey demo.

## Directory Structure

```
overseer/
├── Dockerfile           # Container definition
├── README.md            # Component documentation
├── STRUCTURE.md         # This file
├── overseer.py          # Main application
├── requirements.txt     # Python dependencies
├── static/              # Static assets
│   └── style.css        # Additional CSS styles
└── templates/           # HTML templates
    └── index.html       # Main dashboard template
```

## Component Architecture

The overseer follows a simple Flask-based architecture with the following components:

### Core Application (overseer.py)

The main Python application responsible for:

1. **Data Collection**:
   - Scraping poller status data via Docker exec commands
   - Collecting agent logs from container stdout/stderr
   - Calculating uptime metrics and service availability statistics

2. **Web Server**:
   - Flask application providing the web UI
   - API endpoints for JSON data access
   - WebSocket support via Socket.IO for real-time updates

3. **Background Processes**:
   - Scheduled tasks for periodic data updates
   - Event handling for client connections
   - Error handling and recovery

### Frontend Dashboard (templates/index.html)

A responsive web UI providing:

1. **Service Status Panel**:
   - Current service state with visual indicators
   - Response time and availability metrics
   - Pod readiness information

2. **Visualization**:
   - Status history chart (time series)
   - Status distribution chart (doughnut)
   - Uptime percentage and status counts

3. **Agent Log Displays**:
   - Separate panels for blue and red agent logs
   - Color-coded log entries by severity
   - Real-time log updates via WebSockets

## Integration Points

The overseer integrates with other components:

1. **Poller**:
   - Reads status JSON files from the poller container
   - Processes status information for visualization

2. **Agent Containers**:
   - Follows logs from blue and red agent containers
   - Parses log output for meaningful display

3. **Docker**:
   - Uses Docker SDK to interact with containers
   - Executes commands inside containers to fetch data
   - Monitors container health and status

## Data Flow

1. Overseer starts up and initializes Flask server
2. Background scheduler runs data collection jobs at specified intervals
3. Data is stored in memory and written to persistent volume
4. Web clients connect to the server via HTTP or WebSockets
5. Updates are pushed to clients in real-time as data changes
6. API endpoints provide JSON access to current and historical data
