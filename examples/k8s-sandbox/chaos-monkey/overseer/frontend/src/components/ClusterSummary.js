import React from 'react';
import { Card, Alert, Badge } from 'react-bootstrap';

const ClusterSummary = ({ clusterStatus }) => {
  return (
    <Card className="mb-4">
      <Card.Body>
        <Card.Title>
          <i className="fas fa-project-diagram me-2"></i>Kubernetes Status
        </Card.Title>
        <div>
          {clusterStatus ? (
            <>
              <p>
                <i className="fas fa-check-circle text-success me-2"></i>
                <strong>Control Plane:</strong> {
                  clusterStatus.nodes?.filter(node => node.ready).length || 0
                } of {clusterStatus.nodes?.length || 0} nodes ready
                {(() => {
                  // Calculate control plane health
                  let controlPlaneReady = 0;
                  let controlPlaneTotal = 0;

                  clusterStatus.pods?.forEach(namespace => {
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
                      }
                    });
                  });

                  let healthStatus = 'Unknown';
                  if (controlPlaneTotal > 0) {
                    if (controlPlaneReady === controlPlaneTotal) {
                      healthStatus = 'Healthy';
                    } else if (controlPlaneReady > 0) {
                      healthStatus = 'Degraded';
                    } else {
                      healthStatus = 'Unhealthy';
                    }
                  }

                  return (
                    <Badge bg={
                      healthStatus === 'Healthy' ? 'success' :
                      healthStatus === 'Degraded' ? 'warning' :
                      healthStatus === 'Unhealthy' ? 'danger' : 'secondary'
                    } className="ms-2">
                      {healthStatus}
                    </Badge>
                  );
                })()}
              </p>
              <p>
                <i className="fas fa-cubes text-info me-2"></i>
                <strong>Pods:</strong> {
                  (() => {
                    // Count all pods in the cluster
                    let totalPods = 0;
                    let runningPods = 0;
                    clusterStatus.pods?.forEach(ns => {
                      ns.pods.forEach(pod => {
                        totalPods++;
                        if (pod.status === 'Running' || pod.status === 'Ready') {
                          runningPods++;
                        }
                      });
                    });
                    return `${runningPods} of ${totalPods} running`;
                  })()
                }
              </p>
            </>
          ) : (
            <Alert variant="info">
              <i className="fas fa-spinner fa-spin me-2"></i>Loading cluster information...
            </Alert>
          )}
        </div>
      </Card.Body>
    </Card>
  );
};

export default ClusterSummary;
