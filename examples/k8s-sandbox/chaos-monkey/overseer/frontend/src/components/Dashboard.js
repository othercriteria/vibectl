import React from 'react';
import { Row, Col, Card, Alert, ProgressBar, Container } from 'react-bootstrap';
import ClusterSummary from './ClusterSummary';
import AgentLogs from './AgentLogs';
import ServiceHistoryChart from './ServiceHistoryChart';
import ServiceStatus from './ServiceStatus';
import ServiceOverview from './ServiceOverview';
import GenericResourceSummary from './GenericResourceSummary';

const Dashboard = ({
  clusterStatus,
  overview,
  currentStatus,
  history,
  blueAgentLogs,
  redAgentLogs,
  autoScroll,
  onAutoScrollChange
}) => {

  return (
    <Container fluid className="pt-3">
      {/* Row 1: Cluster Level Cards */}
      <Row className="mb-4">
         <Col md={6}><ClusterSummary clusterStatus={clusterStatus} /></Col>
         <Col md={6}>
            <GenericResourceSummary
              title="System Resource Quota (kube-system)"
              resourceData={clusterStatus?.resources?.quotas?.['kube-system']}
            />
         </Col>
      </Row>

      {/* Row 2: Demo Service Level Cards */}
      <Row className="mb-4">
         <Col md={4}><ServiceStatus status={currentStatus} /></Col>
         <Col md={4}><ServiceOverview overview={overview} /></Col>
         <Col md={4}>
            <GenericResourceSummary
              title="Demo Service Usage (services)"
              resourceData={clusterStatus?.resources?.quotas?.services}
            />
         </Col>
      </Row>

      {/* Row 3: History Chart */}
      <Row className="mb-4">
         <Col md={12}><ServiceHistoryChart history={history} /></Col>
      </Row>

      {/* Row 4: Agent Logs */}
      <Row>
         <Col md={12}>
           <AgentLogs
             blueAgentLogs={blueAgentLogs}
             redAgentLogs={redAgentLogs}
             autoScroll={autoScroll}
             onAutoScrollChange={onAutoScrollChange}
           />
         </Col>
      </Row>
    </Container>
  );
};

export default Dashboard;
