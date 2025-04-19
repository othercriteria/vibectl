import React, { useEffect, useRef } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';

const Terminal = ({ logs = [], title = 'Terminal', autoScroll = true }) => {
  const terminalRef = useRef(null);
  const xtermRef = useRef(null);
  const fitAddonRef = useRef(null);
  const processedLogsRef = useRef([]);

  // Initialize xterm
  useEffect(() => {
    if (!xtermRef.current) {
      // Create xterm instance
      xtermRef.current = new XTerm({
        cursorBlink: false,
        convertEol: true,
        fontSize: 14,
        lineHeight: 1.2,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
        theme: {
          background: '#1e1e1e',
          foreground: '#f0f0f0',
          cursor: '#ffffff',
          selectionBackground: '#5DA5D533',
          black: '#000000',
          red: '#e06c75',
          green: '#98c379',
          yellow: '#e5c07b',
          blue: '#61afef',
          magenta: '#c678dd',
          cyan: '#56b6c2',
          white: '#ffffff',
        }
      });

      // Create fit addon to automatically resize terminal
      fitAddonRef.current = new FitAddon();
      xtermRef.current.loadAddon(fitAddonRef.current);

      // Mount terminal
      if (terminalRef.current) {
        xtermRef.current.open(terminalRef.current);
        fitAddonRef.current.fit();
      }
    }

    // Handle window resize
    const handleResize = () => {
      if (fitAddonRef.current) {
        fitAddonRef.current.fit();
      }
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  // Process logs when they change
  useEffect(() => {
    if (xtermRef.current && logs && logs.length > 0) {
      // Get processed logs to avoid duplicates
      const processedLogs = processedLogsRef.current;

      // Find any new logs
      const newLogs = logs.filter(log => !processedLogs.some(
        processed => processed.timestamp === log.timestamp && processed.message === log.message
      ));

      if (newLogs.length > 0) {
        // Color map for log levels
        const colorMap = {
          ERROR: '\x1b[31m', // Red
          WARNING: '\x1b[33m', // Yellow
          INFO: '\x1b[32m', // Green
          DEBUG: '\x1b[36m', // Cyan
          RESET: '\x1b[0m'
        };

        // Process and write each new log
        newLogs.forEach(log => {
          const timestamp = new Date(log.timestamp).toLocaleTimeString();
          const color = colorMap[log.level] || colorMap.INFO;
          
          // Format log entry with color
          xtermRef.current.writeln(
            `${color}[${timestamp}] ${log.level}:${colorMap.RESET} ${log.message}`
          );
        });

        // Add new logs to processed logs
        processedLogsRef.current = [...processedLogs, ...newLogs];

        // Auto-scroll to bottom
        if (autoScroll) {
          xtermRef.current.scrollToBottom();
        }
      }
    }
  }, [logs, autoScroll]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (xtermRef.current) {
        xtermRef.current.dispose();
        xtermRef.current = null;
      }
    };
  }, []);

  return (
    <div className="terminal-container">
      <div className="terminal-header p-2 bg-dark text-light">
        <strong>{title}</strong>
      </div>
      <div ref={terminalRef} className="xterm" />
    </div>
  );
};

export default Terminal; 