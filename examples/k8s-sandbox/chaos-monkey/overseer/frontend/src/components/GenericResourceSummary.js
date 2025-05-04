import React from 'react';
import { Card, ProgressBar } from 'react-bootstrap';

// Helper function to format bytes
const formatBytes = (bytes) => {
  if (bytes === undefined || bytes === null) return 'N/A';
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KiB', 'MiB', 'GiB', 'TiB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = parseFloat((bytes / Math.pow(k, i)).toFixed(1));
  return isNaN(value) ? 'N/A' : `${value} ${sizes[i]}`;
};

// Helper function to format CPU (cores to milliCPUs for display)
const formatCpu = (cores) => {
  if (cores === undefined || cores === null) return 'N/A';
  if (cores === 0) return '0m';
  return `${Math.round(cores * 1000)}m`;
};

// Helper to get progress bar variant based on usage percentage
const getVariant = (percentage) => {
  if (percentage === undefined || percentage === null || isNaN(percentage)) return 'info'; // Default variant
  if (percentage > 90) return 'danger';
  if (percentage > 75) return 'warning';
  return 'success';
};

// Helper to parse numeric resource value, returning undefined if invalid
const parseNumeric = (value) => {
  const num = parseFloat(value);
  return isNaN(num) ? undefined : num;
};

const GenericResourceSummary = ({ title, resourceData }) => {

  // Early return if data is not yet available
  if (!resourceData) {
    return (
      <Card className="mb-4 h-100">
        <Card.Body>
          <Card.Title>
            <i className="fas fa-server me-2"></i>{title}
          </Card.Title>
          <div><i className="fas fa-spinner fa-spin me-2"></i>Loading resource data...</div>
        </Card.Body>
      </Card>
    );
  }

  // Extract data directly from the passed resourceData prop
  const cpuUsed = resourceData?.cpu_used;
  const memUsed = resourceData?.memory_used;
  const numCpuUsed = parseNumeric(cpuUsed);
  const numMemUsed = parseNumeric(memUsed);
  const numCpuRequest = parseNumeric(resourceData?.cpu_request);
  const numMemRequest = parseNumeric(resourceData?.memory_request);
  const numCpuLimit = parseNumeric(resourceData?.cpu_limit);
  const numMemLimit = parseNumeric(resourceData?.memory_limit);

  // Calculate percentages for ProgressBar and Request marker
  const calculatePercent = (value, limit) => {
    if (limit === undefined || limit === null || limit <= 0 || value === undefined || value === null) {
      return undefined; // Cannot calculate percentage
    }
    return Math.max(0, Math.min(100, (value / limit) * 100));
  };

  const cpuUsagePercent = calculatePercent(numCpuUsed, numCpuLimit);
  const memUsagePercent = calculatePercent(numMemUsed, numMemLimit);
  const cpuRequestPercent = calculatePercent(numCpuRequest, numCpuLimit);
  const memRequestPercent = calculatePercent(numMemRequest, numMemLimit);

  return (
    <Card className="mb-4 h-100">
      <Card.Body>
        <Card.Title>
          <i className="fas fa-server me-2"></i>{title} {/* Use dynamic title */}
        </Card.Title>
        {resourceData ? (
          <div className="d-flex flex-column align-items-center">
            <div className="w-100 mb-3 text-center">
              <i className="fas fa-microchip me-2"></i>CPU: {formatCpu(numCpuUsed)} / {formatCpu(numCpuRequest)} / {numCpuLimit !== undefined ? formatCpu(numCpuLimit) : 'None'}
              <div style={{ position: 'relative', width: '100%', height: '10px' }} className="mt-1">
                <ProgressBar
                  now={cpuUsagePercent ?? 0}
                  variant={getVariant(cpuUsagePercent)}
                  style={{ height: '100%' }}
                />
                {/* Request Marker Overlay */}
                {(cpuRequestPercent !== undefined && cpuRequestPercent <= 100) && (
                  <div
                    style={{
                      position: 'absolute',
                      left: `${cpuRequestPercent}%`,
                      top: '-2px', // Adjust for visibility
                      bottom: '-2px',
                      width: '2px',
                      backgroundColor: 'rgba(0, 0, 0, 0.6)', // Dark marker
                      zIndex: 1, // Ensure it's above the progress bar segments
                    }}
                    title={`Request: ${formatCpu(numCpuRequest)}`}
                  ></div>
                )}
              </div>
              {(cpuUsagePercent === undefined) && (
                <small className="text-muted">Usage/Limit N/A</small>
              )}
            </div>
            <div className="w-100 text-center">
              <i className="fas fa-memory me-2"></i>Memory: {formatBytes(numMemUsed)} / {formatBytes(numMemRequest)} / {numMemLimit !== undefined ? formatBytes(numMemLimit) : 'None'}
              <div style={{ position: 'relative', width: '100%', height: '10px' }} className="mt-1">
                <ProgressBar
                  now={memUsagePercent ?? 0}
                  variant={getVariant(memUsagePercent)}
                  style={{ height: '100%' }}
                />
                {/* Request Marker Overlay */}
                {(memRequestPercent !== undefined && memRequestPercent <= 100) && (
                  <div
                    style={{
                      position: 'absolute',
                      left: `${memRequestPercent}%`,
                      top: '-2px', // Adjust for visibility
                      bottom: '-2px',
                      width: '2px',
                      backgroundColor: 'rgba(0, 0, 0, 0.6)', // Dark marker
                      zIndex: 1, // Ensure it's above the progress bar segments
                    }}
                    title={`Request: ${formatBytes(numMemRequest)}`}
                  ></div>
                )}
              </div>
              {(memUsagePercent === undefined) && (
                <small className="text-muted">Usage/Limit N/A</small>
              )}
            </div>
          </div>
        ) : (
          <div><i className="fas fa-spinner fa-spin me-2"></i>Waiting for resource data...</div> // Should not be reached due to early return
        )}
      </Card.Body>
    </Card>
  );
};

export default GenericResourceSummary;
