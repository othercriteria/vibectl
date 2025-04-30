import React, { useState, useEffect } from 'react';
import { Card } from 'react-bootstrap';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { useSocket } from '../hooks/useSocket';
import apiService from '../services/ApiService';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

// This component manages its own state and data fetching/updates via sockets.
// It does not require props for history or overview data.
const HealthStatusGraph = () => {
  const [history, setHistory] = useState([]);
  const statusUpdate = useSocket('status_update', null);
  const historyUpdate = useSocket('history_update', null);

  // Fetch initial data
  useEffect(() => {
    const fetchData = async () => {
      try {
        const historyData = await apiService.getHistory();
        if (historyData && historyData.length > 0) {
          setHistory(historyData);
        }
      } catch (error) {
        console.error("Error fetching initial history:", error);
      }
    };

    fetchData();
  }, []);

  // Update when we get a new history update
  useEffect(() => {
    if (historyUpdate && Array.isArray(historyUpdate) && historyUpdate.length > 0) {
      // Ensure data is sorted by timestamp if backend doesn't guarantee order
      const sortedHistory = [...historyUpdate].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
      setHistory(sortedHistory);
    }
  }, [historyUpdate]);

  // Update when we get a new status update
  useEffect(() => {
    // DEBUG: Log when the effect runs due to statusUpdate changing
    console.log('[HealthStatusGraph] statusUpdate received:', statusUpdate);

    if (statusUpdate && statusUpdate.status !== 'LOADING') {
      setHistory(prevHistory => {
        // DEBUG: Log inside the setHistory callback
        console.log('[HealthStatusGraph] Updating history state with:', statusUpdate);

        const lastEntry = prevHistory[prevHistory.length - 1];
        if (lastEntry && lastEntry.timestamp === statusUpdate.timestamp) {
          console.log('[HealthStatusGraph] Duplicate timestamp, skipping update.');
          return prevHistory;
        }

        if (lastEntry && new Date(statusUpdate.timestamp) < new Date(lastEntry.timestamp)) {
          console.warn("[HealthStatusGraph] Received out-of-order status update, ignoring for now.");
          return prevHistory;
        }

        const newHistory = [...prevHistory, statusUpdate];
        const maxDataPoints = 100;
        if (newHistory.length > maxDataPoints) {
          return newHistory.slice(newHistory.length - maxDataPoints);
        }
        return newHistory;
      });
    }
  }, [statusUpdate]);

  // Status codes for numeric representation on the Y-axis
  const getStatusValue = (status) => {
    switch (status) {
      case 'HEALTHY': return 100;
      case 'DEGRADED': return 50;
      case 'DOWN': return 0;
      case 'ERROR': case 'PENDING': case 'LOADING': default: return 25; // Assign a value between DOWN and DEGRADED
    }
  };

  // DEBUG: Log the history length before rendering
  console.log('[HealthStatusGraph] Rendering with history length:', history.length);

  // Generate chart data
  const chartData = {
    labels: history.map(entry => {
      try {
        const date = new Date(entry.timestamp);
        return date.toLocaleTimeString(); // Format timestamp for X-axis label
      } catch (e) {
        console.error("Error parsing timestamp:", entry.timestamp, e);
        return "Invalid Date";
      }
    }),
    datasets: [
      {
        label: 'Health Status',
        data: history.map(entry => getStatusValue(entry.status)),
        borderColor: 'rgba(75, 192, 192, 1)', // Teal line
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        tension: 0.1, // Reduce tension for less smoothing, more direct lines
        yAxisID: 'yStatus', // Assign to the status Y-axis
        pointBackgroundColor: history.map(entry => {
          switch (entry.status) {
            case 'HEALTHY': return 'rgba(40, 167, 69, 1)'; // Green
            case 'DEGRADED': return 'rgba(255, 193, 7, 1)'; // Yellow
            case 'DOWN': return 'rgba(220, 53, 69, 1)'; // Red
            default: return 'rgba(108, 117, 125, 1)'; // Gray for others
          }
        }),
        pointBorderColor: history.map(entry => {
          // Match point background color for solid points
          switch (entry.status) {
            case 'HEALTHY': return 'rgba(40, 167, 69, 1)';
            case 'DEGRADED': return 'rgba(255, 193, 7, 1)';
            case 'DOWN': return 'rgba(220, 53, 69, 1)';
            default: return 'rgba(108, 117, 125, 1)';
          }
        }),
        pointRadius: 3, // Make points slightly smaller
      },
      {
        label: 'Response Time (ms)',
        // Only include response time for HEALTHY or DEGRADED states, otherwise use null for gaps
        data: history.map(entry => {
          if (entry.status === 'HEALTHY' || entry.status === 'DEGRADED') {
            // Ensure response_time is a number, default to null if not
            const rt = parseFloat(entry.response_time);
            return !isNaN(rt) ? rt : null;
          } else {
            return null; // Use null to create gaps in the line for other statuses
          }
        }),
        borderColor: 'rgba(54, 162, 235, 1)', // Blue line
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        tension: 0.1, // Match tension
        yAxisID: 'yResponseTime', // Assign to the response time Y-axis
        pointRadius: 3,
      },
    ],
  };

  // Options for the chart
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
        duration: 0 // Disable animation for faster updates
    },
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: 'Demo Service Health History',
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: {
          label: function(context) {
            const datasetLabel = context.dataset.label || '';
            const value = context.raw;

            if (context.dataset.yAxisID === 'yStatus') {
              let statusLabel = 'Unknown';
              if (value === 100) statusLabel = 'HEALTHY';
              else if (value === 50) statusLabel = 'DEGRADED';
              else if (value === 0) statusLabel = 'DOWN';
              else if (value === 25) statusLabel = 'ERROR/PENDING';
              return `${datasetLabel}: ${statusLabel}`;
            } else if (context.dataset.yAxisID === 'yResponseTime') {
              // Only show response time if value is not null
              return value !== null ? `${datasetLabel}: ${value} ms` : null;
            }
            return `${datasetLabel}: ${value}`;
          }
        }
      }
    },
    scales: {
      x: {
        ticks: {
            autoSkip: true,
            maxTicksLimit: 20 // Limit number of x-axis labels for readability
        }
      },
      yStatus: { // Explicit ID for the status axis
        type: 'linear',
        position: 'left',
        beginAtZero: true,
        max: 100,
        title: {
          display: true,
          text: 'Health Status'
        },
        ticks: {
          // Use fixed ticks for clear status representation
          stepSize: 25,
          callback: function(value) {
            if (value === 100) return 'HEALTHY';
            if (value === 50) return 'DEGRADED';
            if (value === 25) return 'ERROR/PENDING';
            if (value === 0) return 'DOWN';
            return null; // Hide intermediate ticks
          }
        }
      },
      yResponseTime: { // Explicit ID for the response time axis
        type: 'linear',
        position: 'right',
        beginAtZero: true,
        suggestedMax: 1000, // Suggest 1 sec max, but allow auto-scaling
        title: {
          display: true,
          text: 'Response Time (ms)'
        },
        grid: {
          drawOnChartArea: false, // Only show grid lines for the status axis
        },
        ticks: {
            // Optional: Customize ticks if needed, e.g., add 'ms'
            callback: function(value) {
                return `${value} ms`;
            }
        }
      }
    }
  };

  return (
    <Card className="mb-4 shadow-sm">
      <Card.Body>
        <Card.Title><i className="fas fa-chart-line me-2"></i>Health Status Visualization</Card.Title>
        <div style={{ height: '350px' }}> {/* Increased height slightly */}
          {history.length > 0 ? (
            <Line data={chartData} options={chartOptions} />
          ) : (
            <div className="d-flex justify-content-center align-items-center h-100">
              <p className="text-muted"><i className="fas fa-spinner fa-spin me-2"></i>Waiting for health data...</p>
            </div>
          )}
        </div>
        <div className="text-muted small text-end mt-2">
          <i className="fas fa-info-circle me-1"></i>
          Displaying last {history.length} checks (up to 100 max). Backend stores more history.
        </div>
      </Card.Body>
    </Card>
  );
};

export default HealthStatusGraph;
