import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Alert, ProgressBar } from 'react-bootstrap';
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
import apiService from '../services/ApiService';
import { useSocket } from '../hooks/useSocket';

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

const Dashboard = () => {
  const currentStatus = useSocket('status_update', { status: 'LOADING', message: 'Loading status...' });
  const serviceOverviewUpdate = useSocket('service_overview_update', null);
  const [history, setHistory] = useState([]);
  const [overview, setOverview] = useState({
    status_counts: { HEALTHY: 0, DEGRADED: 0, DOWN: 0, ERROR: 0 },
    uptime_percentage: 0,
    total_checks: 0,
    db_status: 'unknown'
  });

  // Fetch initial data
  useEffect(() => {
    const fetchData = async () => {
      const historyData = await apiService.getHistory();
      if (historyData && historyData.length > 0) {
        setHistory(historyData);
      }

      const overviewData = await apiService.getOverview();
      if (overviewData) {
        setOverview(overviewData);
      }
    };

    fetchData();
  }, []);

  // Update history when we get a new status update
  useEffect(() => {
    if (currentStatus && currentStatus.status !== 'LOADING') {
      setHistory(prevHistory => {
        const newHistory = [...prevHistory];

        // Check if this is a duplicate entry
        const lastEntry = newHistory[newHistory.length - 1];
        if (lastEntry && lastEntry.timestamp === currentStatus.timestamp) {
          return newHistory;
        }

        // Add new entry and limit to 50 entries
        newHistory.push(currentStatus);
        if (newHistory.length > 50) {
          return newHistory.slice(newHistory.length - 50);
        }
        return newHistory;
      });
    }
  }, [currentStatus]);

  // Update overview when we get a service_overview_update
  useEffect(() => {
    if (serviceOverviewUpdate) {
      setOverview(serviceOverviewUpdate);
    }
  }, [serviceOverviewUpdate]);

  // Graph data
  const chartData = {
    labels: history.map(entry => {
      // Format timestamp for display
      const date = new Date(entry.timestamp);
      return date.toLocaleTimeString();
    }),
    datasets: [
      {
        label: 'Response Time (ms)',
        data: history.map(entry => entry.response_time || 0),
        borderColor: 'rgba(75, 192, 192, 1)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        tension: 0.4,
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
        text: 'Service Response Time',
      },
    },
    scales: {
      y: {
        beginAtZero: true,
      },
    },
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'HEALTHY':
        return 'success';
      case 'DEGRADED':
        return 'warning';
      case 'DOWN':
        return 'danger';
      case 'ERROR':
      case 'PENDING':
      default:
        return 'info';
    }
  };

  return (
    <div>
      <h1 className="mb-4">System Dashboard</h1>

      <Row className="mb-4">
        <Col md={6}>
          <Card className={`shadow-sm p-3 status-card status-${currentStatus.status}`}>
            <Card.Body>
              <Card.Title>Current Status</Card.Title>
              <Alert variant={getStatusBadgeClass(currentStatus.status)}>
                <h4>{currentStatus.status}</h4>
                <p>{currentStatus.message}</p>
              </Alert>
              {currentStatus.response_time && (
                <p>Response Time: {currentStatus.response_time} ms</p>
              )}
              {currentStatus.timestamp && (
                <p>Last Check: {new Date(currentStatus.timestamp).toLocaleString()}</p>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col md={6}>
          <Card className="shadow-sm p-3">
            <Card.Body>
              <Card.Title>System Overview</Card.Title>
              <h5>Uptime: {overview.uptime_percentage}%</h5>
              <ProgressBar
                className="mb-3"
                now={overview.uptime_percentage}
                variant={overview.uptime_percentage > 90 ? 'success' :
                        overview.uptime_percentage > 70 ? 'warning' : 'danger'}
              />
              <Row>
                <Col xs={6} md={3}>
                  <div className="text-center">
                    <div className="h5">{overview.status_counts.HEALTHY}</div>
                    <div className="text-success">Healthy</div>
                  </div>
                </Col>
                <Col xs={6} md={3}>
                  <div className="text-center">
                    <div className="h5">{overview.status_counts.DEGRADED}</div>
                    <div className="text-warning">Degraded</div>
                  </div>
                </Col>
                <Col xs={6} md={3}>
                  <div className="text-center">
                    <div className="h5">{overview.status_counts.DOWN}</div>
                    <div className="text-danger">Down</div>
                  </div>
                </Col>
                <Col xs={6} md={3}>
                  <div className="text-center">
                    <div className="h5">{overview.status_counts.ERROR}</div>
                    <div className="text-info">Error</div>
                  </div>
                </Col>
              </Row>
              <div className="mt-3">
                <p>Database Status: {overview.db_status}</p>
                <p>Total Health Checks: {overview.total_checks}</p>
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row>
        <Col>
          <Card className="shadow-sm p-3">
            <Card.Body>
              <Card.Title>Response Time History</Card.Title>
              <div style={{ height: '300px' }}>
                {history.length > 0 ? (
                  <Line data={chartData} options={chartOptions} />
                ) : (
                  <div className="text-center pt-4">
                    <p>No history data available</p>
                  </div>
                )}
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;
