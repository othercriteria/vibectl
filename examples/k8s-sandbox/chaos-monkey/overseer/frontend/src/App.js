import React, { useState, useEffect } from 'react';
import { Tabs, Tab, Container, Row, Col, Alert } from 'react-bootstrap';
import { io } from 'socket.io-client';
import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';

// Import components
import ClusterStatus from './components/ClusterStatus';
import Dashboard from './components/Dashboard';

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
  const [history, setHistory] = useState([]);
  const [isStale, setIsStale] = useState(false);

  useEffect(() => {
    const updateStatus = (data) => setStatus(data);
    const updateBlueLogs = (logs) => setBlueAgentLogs((prevLogs) => [...prevLogs, ...logs].slice(-200));
    const updateRedLogs = (logs) => setRedAgentLogs((prevLogs) => [...prevLogs, ...logs].slice(-200));
    const updateClusterStatus = (data) => setClusterStatus(data);
    const updateOverview = (data) => setOverview(data);
    const updateHistory = (data) => setHistory(data);

    socket.on('connect', () => {
      console.log('Connected to server');
    });

    socket.on('status_update', updateStatus);
    socket.on('blue_log_update', updateBlueLogs);
    socket.on('red_log_update', updateRedLogs);
    socket.on('cluster_update', updateClusterStatus);
    socket.on('service_overview_update', updateOverview);

    socket.on('staleness_update', ({ isStale }) => {
        console.log(`Received staleness update: ${isStale}`);
        setIsStale(isStale);
    });

    socket.on('history_append', (newEntry) => {
        setHistory(prevHistory => {
            const updatedHistory = [...prevHistory, newEntry];
            return updatedHistory.length > 1000 ? updatedHistory.slice(-1000) : updatedHistory;
        });
    });

    fetch('/api/status').then(r => r.json()).then(updateStatus).catch(e => console.error('Error loading initial status:', e));
    fetch('/api/logs/blue').then(r => r.json()).then(updateBlueLogs).catch(e => console.error('Error loading initial blue logs:', e));
    fetch('/api/logs/red').then(r => r.json()).then(updateRedLogs).catch(e => console.error('Error loading initial red logs:', e));
    fetch('/api/overview').then(r => r.json()).then(updateOverview).catch(e => console.error('Error loading initial overview:', e));
    fetch('/api/cluster').then(r => r.json()).then(updateClusterStatus).catch(e => console.error('Error loading initial cluster status:', e));
    fetch('/api/history').then(r => r.json()).then(updateHistory).catch(e => console.error('Error loading initial history:', e));

    return () => {
      socket.off('connect');
      socket.off('status_update');
      socket.off('blue_log_update');
      socket.off('red_log_update');
      socket.off('cluster_update');
      socket.off('service_overview_update');
      socket.off('staleness_update');
      socket.off('history_append');
    };
  }, []);

  return (
    <Container fluid>
      {/* Stale Data Warning Banner */}
      {isStale && (
        <Alert variant="warning" className="mt-3">
          <i className="fas fa-exclamation-triangle me-2"></i>
          Warning: UI data may be stale. No updates received since {new Date(Date.now()).toLocaleString()}.
        </Alert>
      )}

      <h1 className="my-4"><i className="fas fa-robot me-2"></i>Chaos Monkey Overseer</h1>

      <Tabs
        activeKey={activeTab}
        onSelect={(k) => setActiveTab(k)}
        className="mb-4"
        id="main-tabs"
      >
        <Tab eventKey="dashboard" title={<span><i className="fas fa-tachometer-alt me-2"></i>Dashboard</span>}>
          <Dashboard
            clusterStatus={clusterStatus}
            overview={overview}
            currentStatus={status}
            history={history}
            blueAgentLogs={blueAgentLogs}
            redAgentLogs={redAgentLogs}
            autoScroll={autoScroll}
            onAutoScrollChange={setAutoScroll}
          />
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
