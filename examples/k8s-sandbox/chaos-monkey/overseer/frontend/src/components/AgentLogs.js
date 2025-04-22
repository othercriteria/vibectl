import React from 'react';
import { Tabs, Tab, Card, Row, Col, Form } from 'react-bootstrap';
import Terminal from './Terminal';

const AgentLogs = ({ blueAgentLogs, redAgentLogs, autoScroll, onAutoScrollChange }) => {
  return (
    <>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h4 className="mb-0"><i className="fas fa-terminal me-2"></i>Agent Logs</h4>
        <Form.Check
          type="switch"
          id="auto-scroll-switch"
          label={<span><i className="fas fa-scroll me-2"></i>Auto-scroll to new logs</span>}
          checked={autoScroll}
          onChange={e => onAutoScrollChange(e.target.checked)}
          className="mb-0"
        />
      </div>

      <Tabs defaultActiveKey="blue" className="mb-3">
        <Tab eventKey="blue" title={<span className="text-primary"><i className="fas fa-shield-alt me-2"></i>Blue Agent (Defense)</span>}>
          <Card className="mb-4">
            <Card.Body className="p-0">
              <Terminal
                logs={blueAgentLogs}
                title={<span><i className="fas fa-shield-alt me-2"></i>Blue Agent Terminal</span>}
                autoScroll={autoScroll}
                agentType="blue"
              />
            </Card.Body>
          </Card>
        </Tab>
        <Tab eventKey="red" title={<span className="text-danger"><i className="fas fa-skull-crossbones me-2"></i>Red Agent (Offense)</span>}>
          <Card className="mb-4">
            <Card.Body className="p-0">
              <Terminal
                logs={redAgentLogs}
                title={<span><i className="fas fa-skull-crossbones me-2"></i>Red Agent Terminal</span>}
                autoScroll={autoScroll}
                agentType="red"
              />
            </Card.Body>
          </Card>
        </Tab>
        <Tab eventKey="both" title={<span><i className="fas fa-columns me-2"></i>Side-by-Side</span>}>
          <Row>
            <Col md={6}>
              <Card className="mb-4">
                <Card.Header className="text-primary"><i className="fas fa-shield-alt me-2"></i>Blue Agent</Card.Header>
                <Card.Body className="p-0">
                  <Terminal
                    logs={blueAgentLogs.slice(-100)}
                    title="Blue Agent"
                    autoScroll={autoScroll}
                    agentType="blue"
                  />
                </Card.Body>
              </Card>
            </Col>
            <Col md={6}>
              <Card className="mb-4">
                <Card.Header className="text-danger"><i className="fas fa-skull-crossbones me-2"></i>Red Agent</Card.Header>
                <Card.Body className="p-0">
                  <Terminal
                    logs={redAgentLogs.slice(-100)}
                    title="Red Agent"
                    autoScroll={autoScroll}
                    agentType="red"
                  />
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </Tab>
      </Tabs>
    </>
  );
};

export default AgentLogs;
