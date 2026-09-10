import { useState, useEffect, useRef, useCallback } from 'react';
import {
  disconnectedConnectionState,
  type ConnectionStatus,
} from './connectionState';

export type { ConnectionStatus } from './connectionState';

type NativeSecureSocketModule = typeof import('./modules/blinky-secure-socket');
type NativeSecureSocket = {
  id: string;
  module: NativeSecureSocketModule;
  subscription: { remove(): void };
  authenticated: boolean;
};

const RELEASE_TRANSPORT = process.env.EXPO_PUBLIC_BLINKY_TRANSPORT_MODE === 'release';

function loadNativeSecureSocketModule(): NativeSecureSocketModule | null {
  try {
    // Keep this require out of the development path so Expo Go continues to
    // use the normal React Native WebSocket implementation.
    return require('./modules/blinky-secure-socket') as NativeSecureSocketModule;
  } catch {
    return null;
  }
}

export function usePCWebSocket() {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [latestResponse, setLatestResponse] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const nativeRef = useRef<NativeSecureSocket | null>(null);

  const disconnect = useCallback((errorMessage?: string) => {
    if (nativeRef.current) {
      const nativeSocket = nativeRef.current;
      nativeRef.current = null;
      nativeSocket.subscription.remove();
      void nativeSocket.module.close(nativeSocket.id).catch(() => undefined);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    const nextState = disconnectedConnectionState(errorMessage);
    setStatus(nextState.status);
    setErrorMsg(nextState.errorMsg);
    setLatestResponse(nextState.latestResponse);
  }, []);

  const connect = useCallback((ipAddress: string, token?: string, certificatePin?: string) => {
    disconnect();
    
    // Clean IP Address and default to port 9001 if no port is specified
    let formattedIp = ipAddress
      .trim()
      .replace(/^https?:\/\//i, '')
      .replace(/^wss?:\/\//i, '')
      .replace(/\/+$/, '');

    if (!formattedIp) {
      setStatus('error');
      setErrorMsg('IP Address cannot be empty');
      return;
    }

    if (!formattedIp.includes(':')) {
      formattedIp = `${formattedIp}:9001`;
    }

    if (RELEASE_TRANSPORT) {
      const nativeModule = loadNativeSecureSocketModule();
      if (!nativeModule) {
        setStatus('error');
        setErrorMsg('The release secure socket module is missing. Install a release/internal development build.');
        return;
      }
      if (!certificatePin?.trim()) {
        setStatus('error');
        setErrorMsg('Certificate pin is required for the release connection.');
        return;
      }

      const socketId = `pc-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      setStatus('connecting');
      setErrorMsg(null);
      let connectTimeout: ReturnType<typeof setTimeout> | null = setTimeout(() => {
        if (nativeRef.current?.id === socketId && !nativeRef.current.authenticated) {
          disconnect(`Secure connection timed out (${formattedIp}). Check the PC address, token, and certificate pin.`);
        }
      }, 7000);

      const subscription = nativeModule.addListener('onOpen', (event) => {
        if (event.id !== socketId || nativeRef.current?.id !== socketId) return;
        if (token?.trim()) {
          void nativeModule.sendText(socketId, JSON.stringify({ type: 'auth', token: token.trim() }))
            .catch((error: any) => {
              if (nativeRef.current?.id === socketId) {
                disconnect(error?.message || 'Failed to send the remote token.');
              }
            });
        } else {
          disconnect('A remote token is required for release connections.');
        }
      });
      const messageSubscription = nativeModule.addListener('onMessage', (event) => {
        if (event.id !== socketId || nativeRef.current?.id !== socketId || !event.data) return;
        try {
          const parsed = JSON.parse(event.data);
          if (parsed.type === 'auth_result') {
            if (parsed.ok === true) {
              if (connectTimeout) clearTimeout(connectTimeout);
              nativeRef.current.authenticated = true;
              setStatus('connected');
              setErrorMsg(null);
            } else {
              disconnect('The PC rejected the remote token.');
            }
          } else if (nativeRef.current.authenticated) {
            setLatestResponse(parsed);
          }
        } catch {
          console.log('Received raw secure websocket message');
        }
      });
      const closeSubscription = nativeModule.addListener('onClose', (event) => {
        if (event.id !== socketId || nativeRef.current?.id !== socketId) return;
        disconnect(nativeRef.current.authenticated
          ? undefined
          : 'The PC closed the connection before authentication completed.');
      });
      const errorSubscription = nativeModule.addListener('onError', (event) => {
        if (event.id !== socketId || nativeRef.current?.id !== socketId) return;
        disconnect(event.error || 'Secure WebSocket connection failed.');
      });
      nativeRef.current = {
        id: socketId,
        module: nativeModule,
        authenticated: false,
        subscription: {
          remove() {
            if (connectTimeout) clearTimeout(connectTimeout);
            connectTimeout = null;
            subscription.remove();
            messageSubscription.remove();
            closeSubscription.remove();
            errorSubscription.remove();
          },
        },
      };
      void nativeModule.connect(socketId, `wss://${formattedIp}`, certificatePin.trim()).catch((error: any) => {
        if (nativeRef.current?.id !== socketId) return;
        disconnect(error?.message || 'Secure WebSocket connection failed.');
      });
      return;
    }

    const wsUrl = `ws://${formattedIp}`;
    setStatus('connecting');
    setErrorMsg(null);

    let connectTimeout: any = null;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      connectTimeout = setTimeout(() => {
        if (wsRef.current === ws && ws.readyState !== WebSocket.OPEN) {
          try { ws.close(); } catch (e) {}
          wsRef.current = null;
          setStatus('error');
          setErrorMsg(`Connection timed out (${formattedIp}). Ensure Blinky desktop app is running and port 9001 is open.`);
        }
      }, 5000);

      ws.onopen = () => {
        if (connectTimeout) clearTimeout(connectTimeout);
        if (wsRef.current === ws) {
          // Authenticate the remote connection before any commands are sent.
          // The desktop gateway denies all commands from non-loopback peers
          // unless the BLINKY_REMOTE_TOKEN is presented.
          if (token && token.trim()) {
            ws.send(`auth:${token.trim()}`);
          }
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
        if (connectTimeout) clearTimeout(connectTimeout);
        if (wsRef.current === ws) {
          setStatus('disconnected');
          wsRef.current = null;
        }
      };

      ws.onerror = (e) => {
        if (connectTimeout) clearTimeout(connectTimeout);
        if (wsRef.current === ws) {
          setStatus('error');
          setErrorMsg(`Failed to connect to ${formattedIp}. Check Wi-Fi & PC firewall.`);
          wsRef.current = null;
        }
      };
    } catch (err: any) {
      if (connectTimeout) clearTimeout(connectTimeout);
      setStatus('error');
      setErrorMsg(err?.message || 'WebSocket creation failed');
      wsRef.current = null;
    }
  }, [disconnect]);

  const sendNativeText = useCallback((data: string) => {
    const socket = nativeRef.current;
    if (!socket?.authenticated) return false;
    void socket.module.sendText(socket.id, data).catch((error: any) => {
      if (nativeRef.current === socket) {
        disconnect(error?.message || 'Failed to send the message to the PC.');
      }
    });
    return true;
  }, [disconnect]);

  const sendCommand = useCallback((command: 'power_off' | 'restart' | 'sleep' | 'volume_up' | 'volume_down' | 'volume_mute') => {
    if (RELEASE_TRANSPORT) {
      return sendNativeText(command);
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(command);
      return true;
    }
    return false;
  }, [sendNativeText]);

  const sendQuery = useCallback((query: string, requestId: string) => {
    if (RELEASE_TRANSPORT) {
      return sendNativeText(JSON.stringify({ requestId, query }));
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const payload = JSON.stringify({ requestId, query });
      wsRef.current.send(payload);
      return true;
    }
    return false;
  }, [sendNativeText]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (nativeRef.current) {
        const nativeSocket = nativeRef.current;
        nativeRef.current = null;
        nativeSocket.subscription.remove();
        void nativeSocket.module.close(nativeSocket.id).catch(() => undefined);
      }
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
