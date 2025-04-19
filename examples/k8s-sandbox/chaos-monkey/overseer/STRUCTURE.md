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
   - Monitoring Kubernetes cluster status, nodes, and pods
   - Scraping poller status data via Docker exec commands
   - Collecting agent logs from container stdout/stderr
   - Calculating uptime metrics and service availability statistics
   - Cleaning log content by stripping ANSI color codes and timestamps

2. **Web Server**:
   - Flask application providing the web UI
   - API endpoints for JSON data access
   - WebSocket support via Socket.IO for real-time updates
   - Tabbed interface for different monitoring views

3. **Background Processes**:
   - Scheduled tasks for periodic data updates
   - Event handling for client connections
   - Error handling and recovery

### Frontend Dashboard (templates/index.html)

A responsive web UI providing:

1. **Cluster Status Panel**:
   - Node status with resource capacity information
   - Namespaces with pod listings
   - Pod readiness and phase status
   - Container resource allocation
   - Visual indicators for pod health

2. **Service Status Panel**:
   - Current service state with visual indicators
   - Response time and availability metrics
   - Pod readiness information

3. **Visualization**:
   - Status history chart (time series)
   - Status distribution chart (doughnut)
   - Uptime percentage and status counts

4. **Agent Log Displays**:
   - Separate panels for blue and red agent logs
   - Color-coded log entries by severity
   - Real-time log updates via WebSockets
   - Clean, formatted logs with improved readability
   - Proper styling for monospace font and spacing

## Integration Points

The overseer integrates with other components:

1. **Kubernetes Integration**:
   - Connects to the k8s-sandbox container
   - Executes kubectl commands to retrieve cluster status
   - Provides early visibility into cluster initialization
   - Monitors the battle state through pod/namespace status

2. **Poller Integration**:
   - Reads status files from the poller container
   - Transforms poller data into dashboard-friendly format
   - Tracks historical service availability

3. **Agent Integration**:
   - Collects logs from blue and red agent containers
   - Processes logs to remove formatting artifacts (ANSI codes, timestamps)
   - Categorizes log entries by severity level

4. **Docker Integration**:
   - Uses Docker SDK to communicate with containers
   - Executes commands in containers to retrieve data
   - Monitors container health and availability

## Future Improvements

Planned enhancements to the overseer component:

1. **Resource Utilization**:
   - Add real-time metrics for CPU and memory usage
   - Visualize resource trends over time
   - Add alerts for resource contention

2. **Timestamp Display**:
   - Implement custom timestamp styling in the frontend
   - Use CSS for better timestamp formatting rather than including in log content
   - Make timestamps optional/toggleable

3. **Log Filtering**:
   - Add ability to filter logs by severity
   - Add search functionality across log entries
   - Support regex-based log filtering

4. **UI Improvements**:
   - Add light/dark mode toggle
   - Improve mobile responsiveness
   - Add more detailed metrics views

## Data Flow

1. Overseer starts up and initializes Flask server at the beginning of the demo
2. Immediately begins monitoring Kubernetes cluster status
3. Background scheduler runs data collection jobs at specified intervals
4. Data is stored in memory and written to persistent volume
5. Web clients connect to the server via HTTP or WebSockets
6. Updates are pushed to clients in real-time as data changes
7. API endpoints provide JSON access to current and historical data
8. Tabbed interface allows users to focus on specific aspects of the system

---

© 2025 Daniel Klein. Part of the [vibectl](https://github.com/othercriteria/vibectl) project.
