export type TransportType = 'WEBTRANSPORT' | 'WEBSOCKET';

interface NetworkMetrics {
  rtt: number;
  downlink: number;
  effectiveType: string;
}

export class AdaptiveTransportManager {
  private activeTransport: any = null;
  private currentType: TransportType | null = null;
  private isChecking = false;

  constructor(
    private gatewayHttp3Url: string,
    private fallbackWsUrl: string,
    private apiKey: string,
    private onStateChange: (type: TransportType) => void
  ) {
    this.initNetworkListeners();
  }

  private initNetworkListeners() {
    window.addEventListener('online', () => {
      void this.reEvaluateConnection();
    });
    window.addEventListener('offline', () => {
      this.handleDisconnect();
    });

    const connection =
      (navigator as any).connection ||
      (navigator as any).mozConnection ||
      (navigator as any).webkitConnection;
    if (connection) {
      connection.addEventListener('change', () => {
        void this.reEvaluateConnection();
      });
    }
  }

  private async probeConnection(): Promise<NetworkMetrics> {
    const start = performance.now();
    try {
      // Use controller to abort the fetch if it times out
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);

      // Probe URL. Note: For dev/local environments, this probe verifies HTTP/3 endpoint accessibility.
      await fetch(`${this.gatewayHttp3Url.replace(/^wt:/, 'https:')}/probe`, {
        method: 'GET',
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      const rtt = performance.now() - start;
      const connectionInfo = (navigator as any).connection || {};

      return {
        rtt,
        downlink: connectionInfo.downlink || 10,
        effectiveType: connectionInfo.effectiveType || '4g',
      };
    } catch (err) {
      return { rtt: Infinity, downlink: 0, effectiveType: 'offline' };
    }
  }

  async reEvaluateConnection() {
    if (this.isChecking) return;
    this.isChecking = true;

    // Check if WebTransport is supported by browser environment
    const hasWebTransport = typeof (window as any).WebTransport !== 'undefined';
    if (!hasWebTransport) {
      console.warn("WebTransport is not supported by this browser client. Defaulting to WebSockets.");
      await this.switchToWebSocket();
      this.isChecking = false;
      return;
    }

    const metrics = await this.probeConnection();

    if (metrics.rtt === Infinity || metrics.rtt > 1500) {
      if (this.currentType !== 'WEBSOCKET') {
        await this.switchToWebSocket();
      }
    } else {
      if (this.currentType !== 'WEBTRANSPORT') {
        await this.switchToWebTransport();
      }
    }
    this.isChecking = false;
  }

  private async switchToWebTransport() {
    this.cleanupActiveConnection();
    try {
      const WebTransportClass = (window as any).WebTransport;
      const transport = new WebTransportClass(this.gatewayHttp3Url);
      await transport.ready;

      this.activeTransport = transport;
      this.currentType = 'WEBTRANSPORT';
      this.onStateChange('WEBTRANSPORT');
    } catch (e) {
      console.error("WebTransport connection failed, falling back to WebSockets.", e);
      await this.switchToWebSocket();
    }
  }

  private async switchToWebSocket() {
    this.cleanupActiveConnection();
    return new Promise<void>((resolve, reject) => {
      try {
        const ws = new WebSocket(this.fallbackWsUrl);
        ws.onopen = () => {
          this.activeTransport = ws;
          this.currentType = 'WEBSOCKET';
          this.onStateChange('WEBSOCKET');
          resolve();
        };
        ws.onerror = (err) => {
          reject(err);
        };
      } catch (e) {
        reject(e);
      }
    });
  }

  private cleanupActiveConnection() {
    if (this.activeTransport) {
      try {
        this.activeTransport.close();
      } catch {}
      this.activeTransport = null;
    }
    this.currentType = null;
  }

  private handleDisconnect() {
    this.cleanupActiveConnection();
    console.warn("Client network is offline.");
  }
}
