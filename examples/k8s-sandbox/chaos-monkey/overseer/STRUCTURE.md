# Overseer Component Structure

This document outlines the structure and organization of the overseer component in the chaos-monkey demo.

## Directory Structure

```
overseer/
├── Dockerfile           # Container definition
├── README.md            # Component documentation
├── STRUCTURE.md         # This file
├── build.sh             # Build script with debug and verbose options
├── overseer.py          # Main application
├── requirements.txt     # Python dependencies
└── frontend/            # React frontend application
    ├── public/          # Public assets for React app
    ├── src/             # React source code
    │   ├── components/  # React components
    │   ├── hooks/       # Custom React hooks
    │   ├── services/    # API services
    │   ├── App.js       # Main React application
    │   ├── App.css      # Main application styles
    │   ├── index.js     # React entry point
    │   └── index.css    # Global styles
    └── package.json     # Frontend dependencies
```

## Component Architecture

The overseer follows a modern architecture with a Flask backend and React frontend:

### Core Application (overseer.py)

The main Python application responsible for:

1. **Data Collection**:
   - Monitoring Kubernetes cluster status, nodes, and pods
   - Scraping poller status data via Docker exec commands
   - Collecting agent logs from container stdout/stderr
   - Calculating uptime metrics and service availability statistics
   - Cleaning log content by stripping ANSI color codes and timestamps
   - Detecting data staleness based on the last successful poller/cluster update time.

2. **Web Server**:
   - Flask application serving the React frontend
   - API endpoints for JSON data access
   - WebSocket support via Socket.IO for real-time updates
   - Emits `staleness_update` event when data freshness changes.
   - Static file serving for React build artifacts

3. **Background Processes**:
   - Scheduled tasks for periodic data updates
   - Includes a task to periodically check for data staleness.
   - Event handling for client connections
   - Error handling and recovery

### Frontend Application (frontend/)

A modern React application providing:

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

## Build Process

The build process creates a Docker image containing both the Flask backend and React frontend:

1. **Frontend Build**:
   - React application is built using Node.js
   - Static assets are generated in the `build` directory
   - CSS and JavaScript are bundled and optimized

2. **Backend Integration**:
   - Frontend build artifacts are copied to the `/app/static/` directory in the container
   - Flask routes are configured to serve the React application
   - All paths are handled appropriately to support React Router

3. **Build Options**:
   - Standard build: `./build.sh`
   - Verbose output: `./build.sh --verbose`
   - Debug tag: `./build.sh --debug`
   - Combined options: `./build.sh --verbose --debug`

## Future Improvements

Planned enhancements to the overseer component:

1. **Resource Utilization**:
   - Add real-time metrics for CPU and memory usage
   - Visualize resource trends over time
   - Add alerts for resource contention

2. **Log Filtering**:
   - Add ability to filter logs by severity
   - Add search functionality across log entries
   - Support regex-based log filtering

3. **UI Improvements**:
   - Add light/dark mode toggle
   - Improve mobile responsiveness
   - Add more detailed metrics views

4. **API Enhancement**:
   - Expand API capabilities for external monitoring tools
   - Add authentication for API access
   - Implement rate limiting for API endpoints

## Data Flow

1. Overseer starts up and initializes Flask server at the beginning of the demo
2. Immediately begins monitoring Kubernetes cluster status
3. Background scheduler runs data collection jobs at specified intervals
   - Updates last successful data fetch timestamp.
   - Periodically checks if data is stale based on the timestamp.
4. Data is stored in memory and written to persistent volume
5. Web clients load the React application via Flask routes
6. React application connects to backend API and WebSockets
7. Updates are pushed to clients in real-time as data changes
   - Backend pushes `staleness_update` events when freshness status changes.
   - Frontend displays warning banner based on `staleness_update` events.
8. API endpoints provide JSON access to current and historical data

---

© 2025 Daniel Klein. Part of the [vibectl](https://github.com/othercriteria/vibectl) project.
