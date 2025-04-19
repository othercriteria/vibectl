import { useEffect, useState } from 'react';
import socketService from '../services/SocketService';

export function useSocket(event, initialValue = null) {
  const [data, setData] = useState(initialValue);

  useEffect(() => {
    // Connect to socket on mount
    socketService.connect();

    // Subscribe to the event
    const unsubscribe = socketService.on(event, (newData) => {
      setData(newData);
    });

    // Cleanup on unmount
    return () => {
      unsubscribe();
    };
  }, [event]);

  return data;
}

export function useMultipleEvents(events) {
  const [data, setData] = useState({});

  useEffect(() => {
    // Connect to socket on mount
    socketService.connect();

    // Array to hold all unsubscribe functions
    const unsubscribeFunctions = [];

    // Subscribe to each event
    events.forEach(event => {
      const unsubscribe = socketService.on(event, (newData) => {
        setData(prevData => ({
          ...prevData,
          [event]: newData
        }));
      });
      unsubscribeFunctions.push(unsubscribe);
    });

    // Cleanup on unmount
    return () => {
      unsubscribeFunctions.forEach(unsubscribe => unsubscribe());
    };
  }, [events]);

  return data;
} 