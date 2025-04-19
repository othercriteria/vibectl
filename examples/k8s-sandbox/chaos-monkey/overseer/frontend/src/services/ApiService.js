import axios from 'axios';

// Create axios instance with base URL for API calls
const apiClient = axios.create({
  baseURL: process.env.NODE_ENV === 'development' ? 'http://localhost:8080/api' : '/api',
  headers: {
    'Content-Type': 'application/json'
  }
});

class ApiService {
  // Get current service status
  async getStatus() {
    try {
      const response = await apiClient.get('/status');
      return response.data;
    } catch (error) {
      console.error('Error fetching status:', error);
      return { status: 'ERROR', message: 'Failed to fetch status data' };
    }
  }

  // Get service history
  async getHistory() {
    try {
      const response = await apiClient.get('/history');
      return response.data;
    } catch (error) {
      console.error('Error fetching history:', error);
      return [];
    }
  }

  // Get agent logs
  async getLogs(agentRole) {
    try {
      const response = await apiClient.get(`/logs/${agentRole}`);
      return response.data;
    } catch (error) {
      console.error(`Error fetching ${agentRole} logs:`, error);
      return [];
    }
  }

  // Get system overview
  async getOverview() {
    try {
      const response = await apiClient.get('/overview');
      return response.data;
    } catch (error) {
      console.error('Error fetching overview:', error);
      return { status_counts: {}, uptime_percentage: 0 };
    }
  }

  // Get cluster status
  async getClusterStatus() {
    try {
      const response = await apiClient.get('/cluster');
      return response.data;
    } catch (error) {
      console.error('Error fetching cluster status:', error);
      return { nodes: [], pods: [] };
    }
  }
}

// Create a singleton instance
const apiService = new ApiService();

export default apiService; 