import { io } from 'socket.io-client';

// Determine base URL based on environment
const getBaseUrl = () => {
  const protocol = window.location.protocol;
  const hostname = window.location.hostname;
  const port = process.env.NODE_ENV === 'development' ? ':8080' : window.location.port;
  return `${protocol}//${hostname}${port}`;
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
      'chaos_status_update': []
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
