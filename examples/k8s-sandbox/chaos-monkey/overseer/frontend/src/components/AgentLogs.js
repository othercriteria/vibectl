import React, { useEffect, useState } from 'react';
import { Row, Col, Card, Tabs, Tab, Form } from 'react-bootstrap';
import Terminal from './Terminal';
import apiService from '../services/ApiService';
import { useMultipleEvents } from '../hooks/useSocket';

const AgentLogs = () => {
  const [blueLogs, setBlueLogs] = useState([]);
  const [redLogs, setRedLogs] = useState([]);
  const [autoScroll, setAutoScroll] = useState(true);
  
  // Listen for socket updates for both agent logs
  const socketData = useMultipleEvents(['blue_log_update', 'red_log_update']);

  // Fetch initial data
  useEffect(() => {
    const fetchData = async () => {
      const blueLogsData = await apiService.getLogs('blue');
      if (blueLogsData && blueLogsData.length > 0) {
        setBlueLogs(blueLogsData);
      }

      const redLogsData = await apiService.getLogs('red');
      if (redLogsData && redLogsData.length > 0) {
        setRedLogs(redLogsData);
      }
    };

    fetchData();
  }, []);

  // Update logs when socket events are received
  useEffect(() => {
    if (socketData['blue_log_update']) {
      setBlueLogs(prevLogs => {
        // Check if we got a full log update or just new entries
        const newData = socketData['blue_log_update'];
        if (Array.isArray(newData)) {
          // If a full array was provided, replace current logs
          if (newData.length > 10) {
            return newData;
          } else {
            // Otherwise append new logs, avoiding duplicates
            const updatedLogs = [...prevLogs];
            newData.forEach(log => {
              if (!updatedLogs.some(l => l.timestamp === log.timestamp && l.message === log.message)) {
                updatedLogs.push(log);
              }
            });
            return updatedLogs;
          }
        }
        return prevLogs;
      });
    }
    
    if (socketData['red_log_update']) {
      setRedLogs(prevLogs => {
        // Check if we got a full log update or just new entries
        const newData = socketData['red_log_update'];
        if (Array.isArray(newData)) {
          // If a full array was provided, replace current logs
          if (newData.length > 10) {
            return newData;
          } else {
            // Otherwise append new logs, avoiding duplicates
            const updatedLogs = [...prevLogs];
            newData.forEach(log => {
              if (!updatedLogs.some(l => l.timestamp === log.timestamp && l.message === log.message)) {
                updatedLogs.push(log);
              }
            });
            return updatedLogs;
          }
        }
        return prevLogs;
      });
    }
  }, [socketData]);

  return (
    <div>
      <h1 className="mb-4">Agent Logs</h1>
      
      <Form.Check 
        type="switch"
        id="auto-scroll-switch"
        label="Auto-scroll to new logs"
        checked={autoScroll}
        onChange={e => setAutoScroll(e.target.checked)}
        className="mb-3"
      />
      
      <Tabs defaultActiveKey="blue" className="mb-3">
        <Tab eventKey="blue" title="Blue Agent (Defense)">
          <Row>
            <Col>
              <Card className="shadow-sm mb-4">
                <Card.Body>
                  <Card.Title>Blue Agent Logs</Card.Title>
                  <Terminal 
                    logs={blueLogs} 
                    title="Blue Agent Terminal" 
                    autoScroll={autoScroll} 
                  />
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </Tab>
        
        <Tab eventKey="red" title="Red Agent (Offense)">
          <Row>
            <Col>
              <Card className="shadow-sm mb-4">
                <Card.Body>
                  <Card.Title>Red Agent Logs</Card.Title>
                  <Terminal 
                    logs={redLogs} 
                    title="Red Agent Terminal" 
                    autoScroll={autoScroll}
                  />
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </Tab>
        
        <Tab eventKey="both" title="Side-by-Side View">
          <Row>
            <Col md={6}>
              <Card className="shadow-sm mb-4">
                <Card.Body>
                  <Card.Title>Blue Agent Logs</Card.Title>
                  <Terminal 
                    logs={blueLogs} 
                    title="Blue Agent Terminal" 
                    autoScroll={autoScroll}
                  />
                </Card.Body>
              </Card>
            </Col>
            <Col md={6}>
              <Card className="shadow-sm mb-4">
                <Card.Body>
                  <Card.Title>Red Agent Logs</Card.Title>
                  <Terminal 
                    logs={redLogs} 
                    title="Red Agent Terminal" 
                    autoScroll={autoScroll}
                  />
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </Tab>
      </Tabs>
    </div>
  );
};

export default AgentLogs; 