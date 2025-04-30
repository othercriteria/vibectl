import { io } from 'socket.io-client';

// Determine base URL based on environment
const getBaseUrl = () => {
  // For local development using react-scripts start (usually on port 3000)
  // connect to the backend server explicitly (usually on 8080)
  if (process.env.NODE_ENV === 'development') {
    // Construct the backend URL assuming http for local dev
    const hostname = window.location.hostname; // typically localhost
    return `http://${hostname}:8080`;
  }
  // For production or when served by Flask, use the current origin
  // which includes protocol, hostname, and port (if non-default)
  return window.location.origin;
};

class SocketService {
  constructor() {
    this.socket = null;
    this.callbacks = {
      'status_update': [],
      'history_update': [],
      'cluster_update': [],
      'blue_log_update': [],
      'red_log_update': [],
      'chaos_status_update': [],
      'service_overview_update': [],
      'dashboard_update': []
    };
  }

  connect() {
    if (this.socket) {
      return;
    }

    this.socket = io(getBaseUrl());

    // Set up event listeners
    this.socket.on('connect', () => {
      console.log('Socket connected');
    });

    this.socket.on('disconnect', () => {
      console.log('Socket disconnected');
    });

    // Set up event handlers for all our events
    Object.keys(this.callbacks).forEach(event => {
      this.socket.on(event, (data) => {
        this.callbacks[event].forEach(callback => callback(data));
      });
    });
  }

  disconnect() {
    if (!this.socket) {
      return;
    }
    this.socket.disconnect();
    this.socket = null;
  }

  on(event, callback) {
    if (!this.callbacks[event]) {
      this.callbacks[event] = [];
    }
    this.callbacks[event].push(callback);

    // If already connected, subscribe now
    if (this.socket) {
      this.socket.on(event, callback);
    }

    // Return an unsubscribe function
    return () => {
      this.callbacks[event] = this.callbacks[event].filter(cb => cb !== callback);
      if (this.socket) {
        this.socket.off(event, callback);
      }
    };
  }
}

// Singleton instance
const socketService = new SocketService();

export default socketService;
