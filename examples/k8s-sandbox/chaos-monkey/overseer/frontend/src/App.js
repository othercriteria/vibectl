import React, { useState, useEffect } from 'react';
import { Tabs, Tab, Container, Row, Col } from 'react-bootstrap';
import { io } from 'socket.io-client';
import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';

// Import components
import ServiceStatus from './components/ServiceStatus';
import ServiceOverview from './components/ServiceOverview';
import ClusterStatus from './components/ClusterStatus';
import ClusterSummary from './components/ClusterSummary';
import AgentLogs from './components/AgentLogs';
import HealthStatusGraph from './components/HealthStatusGraph';

// Initialize socket connection
const socket = io();

function App() {
  const [status, setStatus] = useState({ status: 'LOADING', message: 'Connecting to service...' });
  const [blueAgentLogs, setBlueAgentLogs] = useState([]);
  const [redAgentLogs, setRedAgentLogs] = useState([]);
  const [clusterStatus, setClusterStatus] = useState(null);
  const [overview, setOverview] = useState(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard');

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

    // Handle service overview updates
    socket.on('service_overview_update', (data) => {
      setOverview(data);
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
      socket.off('service_overview_update');
    };
  }, []);

  return (
    <Container fluid>
      <h1 className="my-4"><i className="fas fa-robot me-2"></i>Chaos Monkey Overseer</h1>

      <Tabs
        activeKey={activeTab}
        onSelect={(k) => setActiveTab(k)}
        className="mb-4"
        id="main-tabs"
      >
        <Tab eventKey="dashboard" title={<span><i className="fas fa-tachometer-alt me-2"></i>Dashboard</span>}>
          <Row>
            <Col md={12}>
              <Row>
                <Col md={12}>
                  <ClusterSummary clusterStatus={clusterStatus} />
                </Col>
              </Row>

              <Row>
                <Col md={6}>
                  <ServiceStatus status={status} />
                </Col>
                <Col md={6}>
                  <ServiceOverview overview={overview} />
                </Col>
              </Row>

              <Row>
                <Col md={12}>
                  <div className="mb-4">
                    <HealthStatusGraph history={status} overview={overview} />
                  </div>
                </Col>
              </Row>

              <AgentLogs
                blueAgentLogs={blueAgentLogs}
                redAgentLogs={redAgentLogs}
                autoScroll={autoScroll}
                onAutoScrollChange={setAutoScroll}
              />
            </Col>
          </Row>
        </Tab>

        <Tab eventKey="cluster" title={<span><i className="fas fa-project-diagram me-2"></i>Cluster Status</span>}>
          <ClusterStatus clusterStatus={clusterStatus} />
        </Tab>
      </Tabs>

      <footer className="my-4 pt-3 text-muted border-top">
        <i className="far fa-copyright me-1"></i> 2025 Daniel Klein | <a href="https://github.com/othercriteria/vibectl" target="_blank" rel="noreferrer"><i className="fab fa-github me-1"></i>vibectl on GitHub</a>
      </footer>
    </Container>
  );
}

export default App;
