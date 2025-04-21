import React from 'react';
import { Row, Col, Card, Badge, Alert } from 'react-bootstrap';

const ClusterStatus = ({ clusterStatus }) => {
  if (!clusterStatus) {
    return <Alert variant="info"><i className="fas fa-spinner fa-spin me-2"></i>Loading cluster status...</Alert>;
  }

  const { nodes = [], pods = [] } = clusterStatus;

  // Calculate control plane health stats
  const controlPlanePods = [];
  let controlPlaneReady = 0;
  let controlPlaneTotal = 0;

  // Extract all pods related to control plane
  pods.forEach(namespace => {
    namespace.pods.forEach(pod => {
      if (pod.name && (
        pod.name.includes('control-plane') ||
        pod.name.includes('kube-') ||
        pod.namespace === 'kube-system'
      )) {
        controlPlaneTotal++;
        if (pod.status === 'Ready' || pod.status === 'Running') {
          controlPlaneReady++;
        }
        controlPlanePods.push(pod);
      }
    });
  });

  // For debugging, show data about control plane health
  const controlPlaneHealth = controlPlaneTotal > 0
    ? Math.round((controlPlaneReady / controlPlaneTotal) * 100)
    : 0;

  // Determine overall control plane status
  let controlPlaneStatus = 'Unknown';
  if (controlPlaneTotal > 0) {
    if (controlPlaneReady === controlPlaneTotal) {
      controlPlaneStatus = 'Healthy';
    } else if (controlPlaneReady > 0) {
      controlPlaneStatus = 'Degraded';
    } else {
      controlPlaneStatus = 'Unhealthy';
    }
  }

  // Helper function to get status badge styling
  const getStatusBadge = (status) => {
    switch (status) {
      case 'HEALTHY':
        return <Badge bg="success"><i className="fas fa-check-circle me-1"></i>HEALTHY</Badge>;
      case 'DEGRADED':
        return <Badge bg="warning"><i className="fas fa-exclamation-triangle me-1"></i>DEGRADED</Badge>;
      case 'DOWN':
        return <Badge bg="danger"><i className="fas fa-times-circle me-1"></i>DOWN</Badge>;
      case 'Ready':
        return <Badge bg="success"><i className="fas fa-check-circle me-1"></i>Ready</Badge>;
      case 'NotReady':
        return <Badge bg="danger"><i className="fas fa-times-circle me-1"></i>Not Ready</Badge>;
      case 'Running':
        return <Badge bg="success"><i className="fas fa-play-circle me-1"></i>Running</Badge>;
      case 'Pending':
        return <Badge bg="warning"><i className="fas fa-clock me-1"></i>Pending</Badge>;
      default:
        return <Badge bg="secondary"><i className="fas fa-question-circle me-1"></i>{status}</Badge>;
    }
  };

  return (
    <>
      <Card className="mb-4">
        <Card.Body>
          <Card.Title><i className="fas fa-server me-2"></i>Control Plane Status</Card.Title>
          <Alert variant={controlPlaneStatus === 'Healthy' ? 'success' :
                         controlPlaneStatus === 'Degraded' ? 'warning' : 'danger'}>
            <h5>
              <i className={`fas fa-${controlPlaneStatus === 'Healthy' ? 'check-circle' :
                             controlPlaneStatus === 'Degraded' ? 'exclamation-triangle' :
                             'times-circle'} me-2`}></i>
              {controlPlaneStatus}
            </h5>
            <div className="mt-2">
              <div><strong>Control Plane Components:</strong> {controlPlaneReady}/{controlPlaneTotal} ready</div>
              <div><strong>Health:</strong> {controlPlaneHealth}%</div>
            </div>
          </Alert>
          {clusterStatus.last_updated && (
            <div className="text-muted small mt-2">
              <i className="fas fa-clock me-1"></i>
              Last updated: {new Date(clusterStatus.last_updated).toLocaleString()}
            </div>
          )}
        </Card.Body>
      </Card>

      <h4 className="mb-3"><i className="fas fa-server me-2"></i>Node Status</h4>
      <Row className="row-cols-1 row-cols-md-2 g-4 mb-4">
        {nodes.map((node, idx) => (
          <Col key={idx}>
            <Card className={`h-100 ${node.ready ? 'border-success' : 'border-danger'}`}>
              <Card.Body>
                <Card.Title><i className="fas fa-server me-2"></i>{node.name}</Card.Title>
                <div className="d-flex justify-content-between">
                  <div>Status: {getStatusBadge(node.status || 'UNKNOWN')}</div>
                  <div>Ready: {node.ready ? <span className="text-success"><i className="fas fa-check me-1"></i>Yes</span> : <span className="text-danger"><i className="fas fa-times me-1"></i>No</span>}</div>
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
            {pods.flatMap((ns) =>
              ns.pods.map((pod, idx) => (
                <tr key={`${ns.namespace}-${idx}`}>
                  <td>{ns.namespace || 'default'}</td>
                  <td>{pod.name || 'unknown'}</td>
                  <td>{pod.ready || '0/0'}</td>
                  <td>
                    <span className={`badge bg-${(pod.status === 'Running' || pod.status === 'Ready' ? 'success' : pod.status === 'Pending' ? 'warning' : 'danger')}`}>
                      {pod.status === 'Running' || pod.status === 'Ready' ? <i className="fas fa-play-circle me-1"></i> :
                       pod.status === 'Pending' ? <i className="fas fa-clock me-1"></i> :
                       <i className="fas fa-stop-circle me-1"></i>}
                      {pod.status || 'Unknown'}
                    </span>
                  </td>
                  <td>{pod.restarts || '0'}</td>
                  <td>{pod.age || 'N/A'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
};

export default ClusterStatus;
