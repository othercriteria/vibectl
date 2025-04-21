import React, { useEffect, useRef } from 'react';
import { Terminal as XTerm } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { WebLinksAddon } from 'xterm-addon-web-links';
import * as AnsiUp from 'ansi_up';
import 'xterm/css/xterm.css';
import './Terminal.css';

const Terminal = ({ logs = [], title = 'Terminal', autoScroll = true, agentType = 'default' }) => {
  const terminalRef = useRef(null);
  const xtermRef = useRef(null);
  const fitAddonRef = useRef(null);
  const webLinksAddonRef = useRef(null);
  const processedLogsRef = useRef([]);
  const ansiUp = useRef(new AnsiUp.default());
  const logsContainerRef = useRef(null);

  // Get agent-specific theme settings
  const getAgentTheme = () => {
    const baseTheme = {
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
    };

    // Apply agent-specific customizations
    switch (agentType) {
      case 'blue':
        return {
          ...baseTheme,
          blue: '#80b0ff', // Enhanced blue
          foreground: '#d0e0ff', // Light blue-tinted foreground
        };
      case 'red':
        return {
          ...baseTheme,
          red: '#ff8080', // Enhanced red
          foreground: '#ffe0e0', // Light red-tinted foreground
        };
      default:
        return baseTheme;
    }
  };

  // Function to strip problematic control sequences but keep colors
  const cleanAnsiCodes = (text) => {
    // Keep color codes but remove problematic control sequences
    return text
      // Remove terminal control sequences that aren't color-related
      .replace(/\u001b\[\d*[A-Z]/g, '') // Remove cursor movement sequences
      .replace(/\u001b\[\d*[a-rt-zA-RT-Z]/g, '') // Remove other control codes but keep colors (s is used in colors)
      .replace(/\u001b\[\?[0-9;]*[a-zA-Z]/g, ''); // Remove advanced terminal sequences
  };

  // Clean and normalize box-drawing characters
  const normalizeBoxDrawing = (text) => {
    return text
      // Ensure box drawing characters are preserved
      .replace(/\u2500/g, '─') // HORIZONTAL LINE
      .replace(/\u2502/g, '│') // VERTICAL LINE
      .replace(/\u250C/g, '┌') // TOP-LEFT CORNER
      .replace(/\u2510/g, '┐') // TOP-RIGHT CORNER
      .replace(/\u2514/g, '└') // BOTTOM-LEFT CORNER
      .replace(/\u2518/g, '┘') // BOTTOM-RIGHT CORNER
      .replace(/\u251C/g, '├') // LEFT TEE
      .replace(/\u2524/g, '┤') // RIGHT TEE
      .replace(/\u252C/g, '┬') // TOP TEE
      .replace(/\u2534/g, '┴') // BOTTOM TEE
      .replace(/\u253C/g, '┼') // CROSS
      .replace(/\u2550/g, '═') // DOUBLE HORIZONTAL LINE
      .replace(/\u2551/g, '║') // DOUBLE VERTICAL LINE
      .replace(/\u2554/g, '╔') // DOUBLE TOP-LEFT CORNER
      .replace(/\u2557/g, '╗') // DOUBLE TOP-RIGHT CORNER
      .replace(/\u255A/g, '╚') // DOUBLE BOTTOM-LEFT CORNER
      .replace(/\u255D/g, '╝'); // DOUBLE BOTTOM-RIGHT CORNER
  };

  // Fix kubectl table output that's split across multiple lines
  const fixKubectlTableOutput = (logs) => {
    const fixedLogs = [];
    let isPreviousLineTableHeader = false;
    let isPreviousLineTableRow = false;
    let currentTimestamp = null;

    for (let i = 0; i < logs.length; i++) {
      const log = logs[i];
      let message = log.message || '';
      const timestamp = log.timestamp;

      // Check if this is a kubectl table header (contains uppercase column names with spaces)
      const isTableHeader = message.match(/\b[A-Z]{2,}\s+[A-Z]{2,}(\s+[A-Z]{2,})*\b/);

      // Check if this is a continuation of a table row
      const isTableRowContinuation = isPreviousLineTableHeader ||
                                    (isPreviousLineTableRow && message.trim().length > 0 && !message.includes(':'));

      // If this line is a continuation of the previous table row/header
      if (isTableRowContinuation && fixedLogs.length > 0 && currentTimestamp === timestamp) {
        // Get the previous log and append this message to it
        const previousLog = fixedLogs[fixedLogs.length - 1];
        previousLog.message = `${previousLog.message} ${message.trim()}`;
      } else {
        // Track for the next iteration
        isPreviousLineTableHeader = isTableHeader ? true : false;
        isPreviousLineTableRow = isTableRowContinuation;
        currentTimestamp = timestamp;

        // Add as a new log entry
        fixedLogs.push({ ...log, message });
      }
    }

    return fixedLogs;
  };

  // Special handling for Memory Content display
  const fixMemoryContentDisplay = (message) => {
    // Replace problematic memory content format with fixed-width characters
    if (message.includes('Memory Content')) {
      // Find memory content blocks
      const memoryBlockRegex = /╭─+\s*Memory Content\s*─+╮[\s\S]*?╰─+╯/g;
      return message.replace(memoryBlockRegex, (match) => {
        // Normalize all box-drawing characters
        return normalizeBoxDrawing(match);
      });
    }
    return message;
  };

  // NOTE: Word emphasis feature removed - see TODO.md for future agent tagging plans

  // Auto-scroll the HTML log container
  useEffect(() => {
    if (logsContainerRef.current && autoScroll) {
      const container = logsContainerRef.current;
      container.scrollTop = container.scrollHeight;
    }
  }, [logs, autoScroll]);

  // Initialize xterm
  useEffect(() => {
    if (!xtermRef.current) {
      // Create xterm instance with improved options for box drawing
      xtermRef.current = new XTerm({
        cursorBlink: false,
        convertEol: true,
        fontSize: 14,
        lineHeight: 1.2,
        fontFamily: '"DejaVu Sans Mono", "Cascadia Mono", "Consolas", "Courier New", monospace',
        letterSpacing: 0,
        rendererType: 'canvas',
        disableStdin: true,
        allowProposedApi: true,
        theme: getAgentTheme(),
        scrollback: 1000, // Increase scrollback buffer
        rows: 20 // Ensure sufficient rows to fill the container
      });

      // Create and load addons
      fitAddonRef.current = new FitAddon();
      webLinksAddonRef.current = new WebLinksAddon();

      xtermRef.current.loadAddon(fitAddonRef.current);
      xtermRef.current.loadAddon(webLinksAddonRef.current);

      // Configure ansi_up
      ansiUp.current.use_classes = true;

      // Mount terminal
      if (terminalRef.current) {
        xtermRef.current.open(terminalRef.current);
        fitAddonRef.current.fit();

        // Add a small delay before fitting again to ensure proper sizing
        setTimeout(() => {
          if (fitAddonRef.current) {
            fitAddonRef.current.fit();
          }
        }, 100);
      }
    }

    // Handle window resize
    const handleResize = () => {
      if (fitAddonRef.current) {
        fitAddonRef.current.fit();

        // Re-apply fit after a short delay to handle any rendering delays
        setTimeout(() => {
          if (fitAddonRef.current) {
            fitAddonRef.current.fit();
          }
        }, 50);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [agentType]); // Added agentType as dependency

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
        // Fix kubectl table output split across multiple lines
        const fixedLogs = fixKubectlTableOutput(newLogs);

        // Process and write each new log
        fixedLogs.forEach(log => {
          const timestamp = new Date(log.timestamp).toLocaleTimeString();

          // Clean and normalize the message
          let message = log.message || '';
          message = cleanAnsiCodes(message);
          message = normalizeBoxDrawing(message);
          message = fixMemoryContentDisplay(message);

          // Write to terminal with timestamp
          xtermRef.current.writeln(`[${timestamp}] ${message}`);
        });

        // Add new logs to processed logs
        processedLogsRef.current = [...processedLogs, ...fixedLogs];

        // Auto-scroll to bottom
        if (autoScroll) {
          xtermRef.current.scrollToBottom();
        }
      }
    }
  }, [logs, autoScroll, agentType]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (xtermRef.current) {
        xtermRef.current.dispose();
        xtermRef.current = null;
      }
    };
  }, []);

  // Get CSS class based on agent type
  const getAgentClass = () => {
    switch (agentType) {
      case 'blue':
        return 'terminal-container blue-agent';
      case 'red':
        return 'terminal-container red-agent';
      default:
        return 'terminal-container';
    }
  };

  return (
    <div className={getAgentClass()}>
      <div className="terminal-header">
        <strong>{typeof title === 'string' ? title : title}</strong>
      </div>
      <div
        ref={terminalRef}
        className="terminal-content"
        style={{
          minHeight: "400px",
          width: "100%",
          backgroundColor: "#1e1e1e",
          position: "relative"
        }}
      >
        {/* Add an empty div at the bottom to ensure background color extends */}
        <div style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: "30px",
          backgroundColor: "#1e1e1e",
          zIndex: 1
        }} />
      </div>

      {/* HTML-based log rendering for regular view */}
      <div className={`log-container ${agentType === 'blue' ? 'text-blue-agent' : agentType === 'red' ? 'text-red-agent' : ''}`} ref={logsContainerRef} style={{ display: 'none' }}>
        {processedLogsRef.current.map((log, index) => {
          const timestamp = new Date(log.timestamp).toLocaleTimeString();
          return (
            <div key={index} className="log-entry">
              <span className="log-timestamp">[{timestamp}]</span>
              <span
                className="log-message"
                dangerouslySetInnerHTML={{
                  __html: ansiUp.current.ansi_to_html(log.message || '')
                }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Terminal;
