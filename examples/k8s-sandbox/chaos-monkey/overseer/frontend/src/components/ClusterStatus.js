import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Table, Badge, Accordion } from 'react-bootstrap';
import apiService from '../services/ApiService';
import { useSocket } from '../hooks/useSocket';

const ClusterStatus = () => {
  const clusterData = useSocket('cluster_update', null);
  const [initialDataLoaded, setInitialDataLoaded] = useState(false);

  // Fetch initial data
  useEffect(() => {
    const fetchData = async () => {
      if (!initialDataLoaded && !clusterData) {
        const data = await apiService.getClusterStatus();
        if (data) {
          setInitialDataLoaded(true);
        }
      }
    };

    fetchData();
  }, [initialDataLoaded, clusterData]);

  if (!clusterData) {
    return (
      <div className="text-center py-5">
        <h2>Loading cluster status...</h2>
        <p>This may take a few moments as we gather data from the Kubernetes cluster.</p>
      </div>
    );
  }

  const getStatusBadge = (status, additionalText = '') => {
    let variant;
    if (typeof status === 'boolean') {
      variant = status ? 'success' : 'danger';
      status = status ? 'Ready' : 'Not Ready';
    } else {
      variant = status === 'Running' || status === 'Active' ? 'success' : 
              status === 'Pending' ? 'warning' : 
              status === 'Error' || status === 'Failed' ? 'danger' : 'secondary';
    }
    
    return (
      <Badge bg={variant} className="me-1">
        {status} {additionalText}
      </Badge>
    );
  };

  return (
    <div>
      <h1 className="mb-4">Kubernetes Cluster Status</h1>
      
      <Row className="mb-4">
        <Col md={12}>
          <Card className="shadow-sm">
            <Card.Body>
              <Card.Title>Node Status</Card.Title>
              <Table responsive striped hover>
                <thead>
                  <tr>
                    <th>Node Name</th>
                    <th>Status</th>
                    <th>CPU</th>
                    <th>Memory</th>
                  </tr>
                </thead>
                <tbody>
                  {clusterData.nodes && clusterData.nodes.length > 0 ? (
                    clusterData.nodes.map((node, index) => (
                      <tr key={index}>
                        <td>{node.name}</td>
                        <td>{getStatusBadge(node.ready)}</td>
                        <td>{node.cpu}</td>
                        <td>{node.memory}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="4" className="text-center">No nodes found</td>
                    </tr>
                  )}
                </tbody>
              </Table>
            </Card.Body>
          </Card>
        </Col>
      </Row>
      
      <Row>
        <Col md={12}>
          <Card className="shadow-sm">
            <Card.Body>
              <Card.Title>Pods by Namespace</Card.Title>
              <Accordion defaultActiveKey="0">
                {clusterData.pods && clusterData.pods.length > 0 ? (
                  clusterData.pods.map((namespaceData, nsIndex) => (
                    <Accordion.Item eventKey={nsIndex.toString()} key={nsIndex}>
                      <Accordion.Header>
                        <span className="me-2">Namespace: {namespaceData.namespace}</span>
                        {getStatusBadge(namespaceData.status)}
                        <span className="ms-2">
                          ({namespaceData.pods.length} pods)
                        </span>
                      </Accordion.Header>
                      <Accordion.Body>
                        <Table responsive striped hover>
                          <thead>
                            <tr>
                              <th>Pod Name</th>
                              <th>Status</th>
                              <th>Ready</th>
                              <th>Resources</th>
                            </tr>
                          </thead>
                          <tbody>
                            {namespaceData.pods.map((pod, podIndex) => (
                              <tr key={podIndex}>
                                <td>{pod.name}</td>
                                <td>{getStatusBadge(pod.phase)}</td>
                                <td>{pod.ready}</td>
                                <td>
                                  {pod.resources && pod.resources.cpu && (
                                    <span className="me-2">CPU: {pod.resources.cpu}</span>
                                  )}
                                  {pod.resources && pod.resources.memory && (
                                    <span>Memory: {pod.resources.memory}</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </Table>
                      </Accordion.Body>
                    </Accordion.Item>
                  ))
                ) : (
                  <div className="text-center p-4">No pod data available</div>
                )}
              </Accordion>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default ClusterStatus; 