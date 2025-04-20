import React, { useState, useEffect } from 'react';
import { Tabs, Tab, Container, Row, Col, Card, Badge, Alert } from 'react-bootstrap';
import { io } from 'socket.io-client';
import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';

// Initialize socket connection
const socket = io();

function App() {
  const [status, setStatus] = useState({ status: 'LOADING', message: 'Connecting to service...' });
  const [blueAgentLogs, setBlueAgentLogs] = useState([]);
  const [redAgentLogs, setRedAgentLogs] = useState([]);
  const [clusterStatus, setClusterStatus] = useState(null);
  const [overview, setOverview] = useState(null);

  useEffect(() => {
    // Handle socket connections
    socket.on('connect', () => {
      console.log('Connected to server');
    });

    // Handle status updates
    socket.on('status_update', (data) => {
      setStatus(data);
    });

    // Handle blue agent logs
    socket.on('blue_log_update', (logs) => {
      setBlueAgentLogs((prevLogs) => [...prevLogs, ...logs].slice(-200));
    });

    // Handle red agent logs
    socket.on('red_log_update', (logs) => {
      setRedAgentLogs((prevLogs) => [...prevLogs, ...logs].slice(-200));
    });

    // Handle cluster status updates
    socket.on('cluster_update', (data) => {
      setClusterStatus(data);
    });

    // Initial data loading
    fetch('/api/status')
      .then(response => response.json())
      .then(data => setStatus(data))
      .catch(error => console.error('Error loading status:', error));

    fetch('/api/logs/blue')
      .then(response => response.json())
      .then(data => setBlueAgentLogs(data))
      .catch(error => console.error('Error loading blue logs:', error));

    fetch('/api/logs/red')
      .then(response => response.json())
      .then(data => setRedAgentLogs(data))
      .catch(error => console.error('Error loading red logs:', error));

    fetch('/api/overview')
      .then(response => response.json())
      .then(data => setOverview(data))
      .catch(error => console.error('Error loading overview:', error));

    fetch('/api/cluster')
      .then(response => response.json())
      .then(data => setClusterStatus(data))
      .catch(error => console.error('Error loading cluster status:', error));

    // Cleanup on unmount
    return () => {
      socket.off('connect');
      socket.off('status_update');
      socket.off('blue_log_update');
      socket.off('red_log_update');
      socket.off('cluster_update');
    };
  }, []);

  // Helper function to get status badge styling
  const getStatusBadge = (status) => {
    switch (status) {
      case 'HEALTHY':
        return <Badge bg="success">HEALTHY</Badge>;
      case 'DEGRADED':
        return <Badge bg="warning">DEGRADED</Badge>;
      case 'DOWN':
        return <Badge bg="danger">DOWN</Badge>;
      default:
        return <Badge bg="secondary">{status}</Badge>;
    }
  };

  // Render log entries
  const renderLogs = (logs) => {
    return (
      <div className="log-container">
        {logs.map((log, index) => {
          let levelClass = '';
          switch (log.level) {
            case 'ERROR':
              levelClass = 'text-danger';
              break;
            case 'WARNING':
              levelClass = 'text-warning';
              break;
            case 'INFO':
              levelClass = 'text-info';
              break;
            default:
              levelClass = 'text-secondary';
          }

          const timestamp = new Date(log.timestamp).toLocaleTimeString();

          return (
            <div key={index} className={`log-entry ${levelClass}`}>
              <span className="log-timestamp">[{timestamp}]</span> {log.message}
            </div>
          );
        })}
      </div>
    );
  };

  // Render cluster status
  const renderClusterStatus = () => {
    if (!clusterStatus) {
      return <Alert variant="info">Loading cluster information...</Alert>;
    }

    return (
      <div>
        <h3>Nodes</h3>
        <ul>
          {clusterStatus.nodes && clusterStatus.nodes.length > 0 ? (
            clusterStatus.nodes.map((node, index) => (
              <li key={index}>
                {node.name}: {node.ready ? 'Ready' : 'Not Ready'} (CPU: {node.cpu}, Memory: {node.memory})
              </li>
            ))
          ) : (
            <li>No nodes found</li>
          )}
        </ul>

        <h3>Namespaces</h3>
        {clusterStatus.pods && clusterStatus.pods.length > 0 ? (
          clusterStatus.pods.map((ns, index) => (
            <Card key={index} className="mb-3">
              <Card.Header>{ns.namespace} ({ns.status})</Card.Header>
              <Card.Body>
                <h6>{ns.pods.length} Pods</h6>
                <ul>
                  {ns.pods.map((pod, podIndex) => (
                    <li key={podIndex}>
                      {pod.name}: {pod.phase} ({pod.ready})
                    </li>
                  ))}
                </ul>
              </Card.Body>
            </Card>
          ))
        ) : (
          <p>No namespace data available</p>
        )}
      </div>
    );
  };

  // Render system overview
  const renderOverview = () => {
    if (!overview) {
      return <Alert variant="info">Loading system overview...</Alert>;
    }

    const uptime = overview.uptime_percentage || 0;
    const counts = overview.status_counts || { HEALTHY: 0, DEGRADED: 0, DOWN: 0, ERROR: 0 };

    return (
      <Card>
        <Card.Body>
          <h5>System Overview</h5>
          <div className="mb-3">
            <h6>Uptime: {uptime}%</h6>
            <div className="progress">
              <div
                className={`progress-bar ${uptime > 90 ? 'bg-success' : uptime > 70 ? 'bg-warning' : 'bg-danger'}`}
                role="progressbar"
                style={{ width: `${uptime}%` }}
                aria-valuenow={uptime}
                aria-valuemin="0"
                aria-valuemax="100">
                {uptime}%
              </div>
            </div>
          </div>

          <Row className="text-center">
            <Col xs={3}>
              <h6>{counts.HEALTHY || 0}</h6>
              <small className="text-success">Healthy</small>
            </Col>
            <Col xs={3}>
              <h6>{counts.DEGRADED || 0}</h6>
              <small className="text-warning">Degraded</small>
            </Col>
            <Col xs={3}>
              <h6>{counts.DOWN || 0}</h6>
              <small className="text-danger">Down</small>
            </Col>
            <Col xs={3}>
              <h6>{counts.ERROR || 0}</h6>
              <small className="text-info">Error</small>
            </Col>
          </Row>
        </Card.Body>
      </Card>
    );
  };

  return (
    <Container fluid>
      <h1 className="my-4">Chaos Monkey Overseer</h1>

      <Tabs defaultActiveKey="dashboard" className="mb-4">
        <Tab eventKey="dashboard" title="Dashboard">
          <Row>
            <Col md={6}>
              <Card className="mb-4">
                <Card.Body>
                  <Card.Title>Service Status</Card.Title>
                  <div className="d-flex align-items-center">
                    <h3 className="me-2">{getStatusBadge(status.status)}</h3>
                  </div>
                  <p>{status.message}</p>
                  {status.timestamp && (
                    <small className="text-muted">
                      Last updated: {new Date(status.timestamp).toLocaleString()}
                    </small>
                  )}
                </Card.Body>
              </Card>
            </Col>
            <Col md={6}>
              {renderOverview()}
            </Col>
          </Row>
        </Tab>

        <Tab eventKey="logs" title="Agent Logs">
          <Row>
            <Col md={6}>
              <Card className="mb-4">
                <Card.Header>Blue Agent (Defender)</Card.Header>
                <Card.Body>
                  {renderLogs(blueAgentLogs)}
                </Card.Body>
              </Card>
            </Col>
            <Col md={6}>
              <Card className="mb-4">
                <Card.Header>Red Agent (Chaos Monkey)</Card.Header>
                <Card.Body>
                  {renderLogs(redAgentLogs)}
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </Tab>

        <Tab eventKey="cluster" title="Cluster Status">
          <Card>
            <Card.Body>
              {renderClusterStatus()}
            </Card.Body>
          </Card>
        </Tab>
      </Tabs>

      <footer className="my-4 pt-3 text-muted border-top">
        &copy; 2025 Daniel Klein | <a href="https://github.com/othercriteria/vibectl" target="_blank" rel="noreferrer">vibectl on GitHub</a>
      </footer>
    </Container>
  );
}

export default App;
