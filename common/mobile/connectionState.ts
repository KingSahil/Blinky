export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export type DisconnectedConnectionState = {
  status: Extract<ConnectionStatus, 'disconnected' | 'error'>;
  errorMsg: string | null;
  latestResponse: null;
};

export function disconnectedConnectionState(errorMessage?: string): DisconnectedConnectionState {
  return {
    status: errorMessage ? 'error' : 'disconnected',
    errorMsg: errorMessage || null,
    latestResponse: null,
  };
}
