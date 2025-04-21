import React from 'react';
import { Card, Alert } from 'react-bootstrap';

const ServiceOverview = ({ overview }) => {
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

export default ServiceOverview;
