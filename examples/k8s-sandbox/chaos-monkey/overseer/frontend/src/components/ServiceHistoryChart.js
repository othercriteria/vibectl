import React from 'react';
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

// Register Chart.js components needed for Line chart
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const ServiceHistoryChart = ({ history }) => {
  if (!history) {
    history = []; // Ensure history is an array
  }

  // Status mapping (from HealthStatusGraph)
  const getStatusValue = (status) => {
    switch (status) {
      case 'HEALTHY': return 100;
      case 'DEGRADED': return 50;
      case 'DOWN': return 0;
      case 'ERROR': case 'PENDING': case 'LOADING': default: return 25;
    }
  };

  // Prepare chart data - adding status dataset
  const chartData = {
    labels: history.map(entry => {
      try {
        const date = new Date(entry.timestamp);
        // Format as UTC time string HH:MM:SS
        return date.toISOString().slice(11, 19) + " UTC";
      } catch (e) {
        console.error("Error parsing timestamp:", entry.timestamp, e);
        return "Invalid Date";
      }
    }),
    datasets: [
      {
        label: 'Health Status', // Added dataset
        data: history.map(entry => getStatusValue(entry.status)),
        borderColor: 'rgba(75, 192, 192, 1)', // Teal line (from HealthStatusGraph)
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        tension: 0.1,
        yAxisID: 'yStatus', // Assign to status axis
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
        pointRadius: 3,
      },
      {
        label: 'Response Time (ms)',
        data: history.map(entry => {
           if (entry.status === 'HEALTHY' || entry.status === 'DEGRADED') {
            const rt = parseFloat(entry.response_time);
            return !isNaN(rt) ? rt : null;
           }
           return null;
        }),
        borderColor: 'rgba(54, 162, 235, 1)',
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        tension: 0.1,
        pointRadius: 3,
        spanGaps: false,
        yAxisID: 'yResponseTime'
      },
    ],
  };

  // Chart options - adding second Y axis
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
        duration: 0
    },
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: 'Service Health & Response Time History', // Updated title
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: {
          label: function(context) {
            const datasetLabel = context.dataset.label || '';
            const value = context.raw;
            // Handle tooltips for both datasets
            if (context.dataset.yAxisID === 'yStatus') {
              let statusLabel = 'Unknown';
              if (value === 100) statusLabel = 'HEALTHY';
              else if (value === 50) statusLabel = 'DEGRADED';
              else if (value === 0) statusLabel = 'DOWN';
              else if (value === 25) statusLabel = 'ERROR/PENDING';
              return `${datasetLabel}: ${statusLabel}`;
            } else if (context.dataset.yAxisID === 'yResponseTime') {
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
            maxTicksLimit: 20
        }
      },
      yStatus: { // Added Status Y Axis config (from HealthStatusGraph)
        type: 'linear',
        position: 'left',
        beginAtZero: true,
        max: 100,
        title: {
          display: true,
          text: 'Health Status'
        },
        ticks: {
          stepSize: 25,
          callback: function(value) {
            if (value === 100) return 'HEALTHY';
            if (value === 50) return 'DEGRADED';
            if (value === 25) return 'ERROR/PENDING';
            if (value === 0) return 'DOWN';
            return null;
          }
        }
      },
      yResponseTime: { // Position Response Time Y Axis to the right
        type: 'linear',
        position: 'right',
        beginAtZero: true,
        suggestedMax: 1000,
        title: {
          display: true,
          text: 'Response Time (ms)',
        },
        grid: { // Only draw grid lines for the left (status) axis
          drawOnChartArea: false,
        },
        ticks: {
            callback: function(value) {
                return `${value} ms`;
            }
        }
      }
    }
  };


  return (
    <Card className="mb-4">
      <Card.Body>
        <Card.Title><i className="fas fa-chart-line me-2"></i>Service Health & Response Time</Card.Title> {/* Updated Title */}
        <div style={{ height: '350px' }}>
          {history.length > 0 ? (
            <Line data={chartData} options={chartOptions} />
          ) : (
            <div className="d-flex justify-content-center align-items-center h-100">
              <p className="text-muted"><i className="fas fa-spinner fa-spin me-2"></i>Waiting for history data...</p>
            </div>
          )}
        </div>
         <div className="text-muted small text-end mt-2">
           <i className="fas fa-info-circle me-1"></i>
           Displaying last {history.length} relevant checks.
         </div>
      </Card.Body>
    </Card>
  );
};

export default ServiceHistoryChart;
