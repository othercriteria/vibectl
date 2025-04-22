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

const HealthStatusGraph = () => {
  const [history, setHistory] = useState([]);
  const statusUpdate = useSocket('status_update', null);
  const historyUpdate = useSocket('history_update', null);

  // Fetch initial data
  useEffect(() => {
    const fetchData = async () => {
      const historyData = await apiService.getHistory();
      if (historyData && historyData.length > 0) {
        setHistory(historyData);
      }
    };

    fetchData();
  }, []);

  // Update when we get a new history update
  useEffect(() => {
    if (historyUpdate && Array.isArray(historyUpdate) && historyUpdate.length > 0) {
      setHistory(historyUpdate);
    }
  }, [historyUpdate]);

  // Update when we get a new status update
  useEffect(() => {
    if (statusUpdate && statusUpdate.status !== 'LOADING') {
      setHistory(prevHistory => {
        // Check if this is a duplicate entry
        const lastEntry = prevHistory[prevHistory.length - 1];
        if (lastEntry && lastEntry.timestamp === statusUpdate.timestamp) {
          return prevHistory;
        }

        // Add new entry and limit displayed entries to 50 for better visualization
        // (though backend now stores 1000)
        const newHistory = [...prevHistory, statusUpdate];
        if (newHistory.length > 50) {
          return newHistory.slice(newHistory.length - 50);
        }
        return newHistory;
      });
    }
  }, [statusUpdate]);

  // Status codes for numeric representation
  const getStatusValue = (status) => {
    switch (status) {
      case 'HEALTHY': return 100;
      case 'DEGRADED': return 50;
      case 'DOWN': return 0;
      case 'ERROR': case 'PENDING': case 'LOADING': default: return 25;
    }
  };

  // Generate chart data with colors mapped to health status
  const chartData = {
    labels: history.map(entry => {
      const date = new Date(entry.timestamp);
      return date.toLocaleTimeString();
    }),
    datasets: [
      {
        label: 'Health Status',
        data: history.map(entry => getStatusValue(entry.status)),
        borderColor: 'rgba(75, 192, 192, 1)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        tension: 0.4,
        pointBackgroundColor: history.map(entry => {
          switch (entry.status) {
            case 'HEALTHY': return 'rgba(40, 167, 69, 1)'; // Green
            case 'DEGRADED': return 'rgba(255, 193, 7, 1)'; // Yellow
            case 'DOWN': return 'rgba(220, 53, 69, 1)'; // Red
            default: return 'rgba(108, 117, 125, 1)'; // Gray
          }
        }),
        pointBorderColor: history.map(entry => {
          switch (entry.status) {
            case 'HEALTHY': return 'rgba(40, 167, 69, 1)';
            case 'DEGRADED': return 'rgba(255, 193, 7, 1)';
            case 'DOWN': return 'rgba(220, 53, 69, 1)';
            default: return 'rgba(108, 117, 125, 1)';
          }
        }),
      },
      {
        label: 'Response Time (ms)',
        data: history.map(entry => entry.response_time || 0),
        borderColor: 'rgba(54, 162, 235, 1)',
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        tension: 0.4,
        yAxisID: 'responseTime',
      },
    ],
  };

  // Options for the chart
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: 'Demo Service Health History',
      },
      tooltip: {
        callbacks: {
          label: function(context) {
            const index = context.dataIndex;
            const datasetIndex = context.datasetIndex;

            if (datasetIndex === 0) { // Health Status
              const statusValue = context.raw;
              let statusLabel = 'Unknown';

              if (statusValue === 100) statusLabel = 'HEALTHY';
              else if (statusValue === 50) statusLabel = 'DEGRADED';
              else if (statusValue === 0) statusLabel = 'DOWN';
              else if (statusValue === 25) statusLabel = 'ERROR/PENDING';

              return `Status: ${statusLabel}`;
            } else { // Response Time
              return `Response Time: ${context.raw} ms`;
            }
          }
        }
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        max: 100,
        title: {
          display: true,
          text: 'Health Status'
        },
        ticks: {
          callback: function(value) {
            if (value === 100) return 'HEALTHY';
            if (value === 50) return 'DEGRADED';
            if (value === 0) return 'DOWN';
            return '';
          }
        }
      },
      responseTime: {
        position: 'right',
        beginAtZero: true,
        title: {
          display: true,
          text: 'Response Time (ms)'
        },
        grid: {
          drawOnChartArea: false,
        },
      }
    }
  };

  return (
    <Card className="mb-4">
      <Card.Body>
        <Card.Title><i className="fas fa-chart-line me-2"></i>Health Status Visualization</Card.Title>
        <div style={{ height: '300px' }}>
          {history.length > 0 ? (
            <Line data={chartData} options={chartOptions} />
          ) : (
            <div className="text-center pt-4">
              <p>No health history data available</p>
            </div>
          )}
        </div>
        <div className="text-muted small text-end">
          <i className="fas fa-info-circle me-1"></i>
          Graph displays recent status changes from the last {history.length} checks (storing up to 1000 history points)
        </div>
      </Card.Body>
    </Card>
  );
};

export default HealthStatusGraph;
