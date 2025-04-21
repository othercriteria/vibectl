import React from 'react';
import { Card, Badge } from 'react-bootstrap';

const ServiceStatus = ({ status }) => {
  // Helper function to get status badge styling
  const getStatusBadge = (status) => {
    switch (status) {
      case 'HEALTHY':
        return <Badge bg="success"><i className="fas fa-check-circle me-1"></i>HEALTHY</Badge>;
      case 'DEGRADED':
        return <Badge bg="warning"><i className="fas fa-exclamation-triangle me-1"></i>DEGRADED</Badge>;
      case 'DOWN':
        return <Badge bg="danger"><i className="fas fa-times-circle me-1"></i>DOWN</Badge>;
      case 'LOADING':
        return <Badge bg="secondary"><i className="fas fa-spinner fa-spin me-1"></i>LOADING</Badge>;
      default:
        return <Badge bg="secondary"><i className="fas fa-question-circle me-1"></i>{status}</Badge>;
    }
  };

  return (
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
  );
};

export default ServiceStatus;
