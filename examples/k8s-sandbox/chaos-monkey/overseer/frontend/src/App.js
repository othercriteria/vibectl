import React, { useState, useEffect } from 'react';
import { Tabs, Tab, Container, Row, Col, Card, Badge, Alert, Form } from 'react-bootstrap';
import { io } from 'socket.io-client';
import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';
import Terminal from './components/Terminal';

// Initialize socket connection
const socket = io();

function App() {
  const [status, setStatus] = useState({ status: 'LOADING', message: 'Connecting to service...' });
  const [blueAgentLogs, setBlueAgentLogs] = useState([]);
  const [redAgentLogs, setRedAgentLogs] = useState([]);
  const [clusterStatus, setClusterStatus] = useState(null);
  const [overview, setOverview] = useState(null);
  const [autoScroll, setAutoScroll] = useState(true);

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
        return <Badge bg="success"><i className="fas fa-check-circle me-1"></i>HEALTHY</Badge>;
      case 'DEGRADED':
        return <Badge bg="warning"><i className="fas fa-exclamation-triangle me-1"></i>DEGRADED</Badge>;
      case 'DOWN':
        return <Badge bg="danger"><i className="fas fa-times-circle me-1"></i>DOWN</Badge>;
      default:
        return <Badge bg="secondary"><i className="fas fa-question-circle me-1"></i>{status}</Badge>;
    }
  };

  // Render overview component
  const renderOverview = () => {
    if (!overview) {
      return <Alert variant="info"><i className="fas fa-spinner fa-spin me-2"></i>Loading service overview...</Alert>;
    }

    const { status_counts = {}, uptime_percentage = 0 } = overview;

    return (
      <Card className="mb-4">
        <Card.Body>
          <Card.Title><i className="fas fa-chart-pie me-2"></i>Service Overview</Card.Title>
          <div className="d-flex justify-content-between align-items-center mb-3">
            <div>
              <div><i className="fas fa-check-circle text-success me-2"></i><span className="text-success fw-bold">{status_counts.HEALTHY || 0}</span> healthy</div>
              <div><i className="fas fa-exclamation-triangle text-warning me-2"></i><span className="text-warning fw-bold">{status_counts.DEGRADED || 0}</span> degraded</div>
              <div><i className="fas fa-times-circle text-danger me-2"></i><span className="text-danger fw-bold">{status_counts.DOWN || 0}</span> down</div>
            </div>
            <div className="text-end">
              <div className="h4">{uptime_percentage.toFixed(1)}%</div>
              <div className="text-muted"><i className="fas fa-clock me-1"></i>Uptime</div>
            </div>
          </div>
        </Card.Body>
      </Card>
    );
  };

  // Render cluster status
  const renderClusterStatus = () => {
    if (!clusterStatus) {
      return <Alert variant="info"><i className="fas fa-spinner fa-spin me-2"></i>Loading cluster status...</Alert>;
    }

    const { nodes = [], pods = [] } = clusterStatus;

    return (
      <>
        <h4 className="mb-3"><i className="fas fa-server me-2"></i>Node Status</h4>
        <Row className="row-cols-1 row-cols-md-2 g-4 mb-4">
          {nodes.map((node, idx) => (
            <Col key={idx}>
              <Card className={`h-100 status-${(node.status || '').toLowerCase()}`}>
                <Card.Body>
                  <Card.Title><i className="fas fa-server me-2"></i>{node.name}</Card.Title>
                  <div className="d-flex justify-content-between">
                    <div>Status: {getStatusBadge(node.status || 'UNKNOWN')}</div>
                    <div>Ready: {node.ready ? <span className="text-success"><i className="fas fa-check me-1"></i>Yes</span> : <span className="text-danger"><i className="fas fa-times me-1"></i>No</span>}</div>
                  </div>
                  <hr />
                  <div className="small">
                    <div><i className="fas fa-microchip me-2"></i><strong>CPU:</strong> {node.cpu_percent || 'N/A'}%</div>
                    <div><i className="fas fa-memory me-2"></i><strong>Memory:</strong> {node.memory_percent || 'N/A'}%</div>
                    <div><i className="fas fa-cube me-2"></i><strong>Pods:</strong> {node.pods || 'N/A'}</div>
                  </div>
                </Card.Body>
              </Card>
            </Col>
          ))}
        </Row>

        <h4 className="mb-3"><i className="fas fa-cubes me-2"></i>Pod Status</h4>
        <div className="table-responsive">
          <table className="table table-sm table-striped">
            <thead>
              <tr>
                <th><i className="fas fa-project-diagram me-2"></i>Namespace</th>
                <th><i className="fas fa-cube me-2"></i>Name</th>
                <th><i className="fas fa-check-circle me-2"></i>Ready</th>
                <th><i className="fas fa-info-circle me-2"></i>Status</th>
                <th><i className="fas fa-sync me-2"></i>Restarts</th>
                <th><i className="fas fa-clock me-2"></i>Age</th>
              </tr>
            </thead>
            <tbody>
              {pods.map((pod, idx) => (
                <tr key={idx}>
                  <td>{pod.namespace || 'default'}</td>
                  <td>{pod.name || 'unknown'}</td>
                  <td>{pod.ready || '0/0'}</td>
                  <td>
                    <span className={`badge bg-${(pod.status === 'Running' ? 'success' : pod.status === 'Pending' ? 'warning' : 'danger')}`}>
                      {pod.status === 'Running' ? <i className="fas fa-play-circle me-1"></i> :
                       pod.status === 'Pending' ? <i className="fas fa-clock me-1"></i> :
                       <i className="fas fa-stop-circle me-1"></i>}
                      {pod.status || 'Unknown'}
                    </span>
                  </td>
                  <td>{pod.restarts || '0'}</td>
                  <td>{pod.age || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    );
  };

  return (
    <Container fluid>
      <h1 className="my-4"><i className="fas fa-robot me-2"></i>Chaos Monkey Overseer</h1>

      <Tabs defaultActiveKey="dashboard" className="mb-4">
        <Tab eventKey="dashboard" title={<span><i className="fas fa-tachometer-alt me-2"></i>Dashboard</span>}>
          <Row>
            <Col md={12}>
              <Row>
                <Col md={6}>
                  <Card className="mb-4">
                    <Card.Body>
                      <Card.Title><i className="fas fa-heartbeat me-2"></i>Service Status</Card.Title>
                      <div className="d-flex align-items-center">
                        <h3 className="me-2">{getStatusBadge(status.status)}</h3>
                      </div>
                      <p>{status.message}</p>
                      {status.timestamp && (
                        <small className="text-muted">
                          <i className="fas fa-clock me-1"></i>Last updated: {new Date(status.timestamp).toLocaleString()}
                        </small>
                      )}
                    </Card.Body>
                  </Card>
                </Col>
                <Col md={6}>
                  {renderOverview()}
                </Col>
              </Row>

              <div className="d-flex justify-content-between align-items-center mb-3">
                <h4 className="mb-0"><i className="fas fa-terminal me-2"></i>Agent Logs</h4>
                <Form.Check
                  type="switch"
                  id="auto-scroll-switch"
                  label={<span><i className="fas fa-scroll me-2"></i>Auto-scroll to new logs</span>}
                  checked={autoScroll}
                  onChange={e => setAutoScroll(e.target.checked)}
                  className="mb-0"
                />
              </div>

              <Tabs defaultActiveKey="blue" className="mb-3">
                <Tab eventKey="blue" title={<span className="text-primary"><i className="fas fa-shield-alt me-2"></i>Blue Agent (Defense)</span>}>
                  <Card className="mb-4">
                    <Card.Body className="p-0">
                      <Terminal
                        logs={blueAgentLogs}
                        title={<span><i className="fas fa-shield-alt me-2"></i>Blue Agent Terminal</span>}
                        autoScroll={autoScroll}
                        agentType="blue"
                      />
                    </Card.Body>
                  </Card>
                </Tab>
                <Tab eventKey="red" title={<span className="text-danger"><i className="fas fa-skull-crossbones me-2"></i>Red Agent (Offense)</span>}>
                  <Card className="mb-4">
                    <Card.Body className="p-0">
                      <Terminal
                        logs={redAgentLogs}
                        title={<span><i className="fas fa-skull-crossbones me-2"></i>Red Agent Terminal</span>}
                        autoScroll={autoScroll}
                        agentType="red"
                      />
                    </Card.Body>
                  </Card>
                </Tab>
                <Tab eventKey="both" title={<span><i className="fas fa-columns me-2"></i>Side-by-Side</span>}>
                  <Row>
                    <Col md={6}>
                      <Card className="mb-4">
                        <Card.Header className="text-primary"><i className="fas fa-shield-alt me-2"></i>Blue Agent</Card.Header>
                        <Card.Body className="p-0">
                          <Terminal
                            logs={blueAgentLogs.slice(-100)}
                            title="Blue Agent"
                            autoScroll={autoScroll}
                            agentType="blue"
                          />
                        </Card.Body>
                      </Card>
                    </Col>
                    <Col md={6}>
                      <Card className="mb-4">
                        <Card.Header className="text-danger"><i className="fas fa-skull-crossbones me-2"></i>Red Agent</Card.Header>
                        <Card.Body className="p-0">
                          <Terminal
                            logs={redAgentLogs.slice(-100)}
                            title="Red Agent"
                            autoScroll={autoScroll}
                            agentType="red"
                          />
                        </Card.Body>
                      </Card>
                    </Col>
                  </Row>
                </Tab>
              </Tabs>
            </Col>
          </Row>
        </Tab>

        <Tab eventKey="cluster" title={<span><i className="fas fa-project-diagram me-2"></i>Cluster Status</span>}>
          <Card>
            <Card.Body>
              {renderClusterStatus()}
            </Card.Body>
          </Card>
        </Tab>
      </Tabs>

      <footer className="my-4 pt-3 text-muted border-top">
        <i className="far fa-copyright me-1"></i> 2025 Daniel Klein | <a href="https://github.com/othercriteria/vibectl" target="_blank" rel="noreferrer"><i className="fab fa-github me-1"></i>vibectl on GitHub</a>
      </footer>
    </Container>
  );
}

export default App;
