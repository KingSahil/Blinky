import { useState, useEffect, useRef, useCallback } from 'react';

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export function usePCWebSocket() {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [latestResponse, setLatestResponse] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('disconnected');
    setErrorMsg(null);
    setLatestResponse(null);
  }, []);

  const connect = useCallback((ipAddress: string) => {
    disconnect();
    
    // Clean IP Address and default to port 9001 if no port is specified
    let formattedIp = ipAddress.trim();
    if (!formattedIp) {
      setStatus('error');
      setErrorMsg('IP Address cannot be empty');
      return;
    }

    if (!formattedIp.includes(':')) {
      formattedIp = `${formattedIp}:9001`;
    }

    const wsUrl = `ws://${formattedIp}`;
    setStatus('connecting');
    setErrorMsg(null);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (wsRef.current === ws) {
          setStatus('connected');
          setErrorMsg(null);
        }
      };

      ws.onmessage = (e) => {
        if (wsRef.current === ws) {
          try {
            const parsed = JSON.parse(e.data);
            setLatestResponse(parsed);
          } catch (err) {
            console.log('Received raw websocket message:', e.data);
          }
        }
      };

      ws.onclose = (e) => {
        if (wsRef.current === ws) {
          setStatus('disconnected');
          wsRef.current = null;
        }
      };

      ws.onerror = (e) => {
        if (wsRef.current === ws) {
          setStatus('error');
          setErrorMsg('Failed to connect. Check IP and firewall.');
          wsRef.current = null;
        }
      };
    } catch (err: any) {
      setStatus('error');
      setErrorMsg(err?.message || 'WebSocket creation failed');
      wsRef.current = null;
    }
  }, [disconnect]);

  const sendCommand = useCallback((command: 'power_off' | 'restart' | 'sleep') => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(command);
      return true;
    }
    return false;
  }, []);

  const sendQuery = useCallback((query: string, requestId: string, webSearchEnabled?: boolean) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const payload = JSON.stringify({ requestId, query, webSearchEnabled });
      wsRef.current.send(payload);
      return true;
    }
    return false;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    status,
    errorMsg,
    latestResponse,
    connect,
    disconnect,
    sendCommand,
    sendQuery,
  };
}

