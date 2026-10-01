/** Credentials encoded in the PC app's "Connect Mobile" QR code. */
export interface QrPairingPayload {
  v: number;
  ip: string;
  ws?: number;
  disc?: number;
  token?: string;
  pin?: string | null;
  mode?: string;
}

/**
 * Parses a scanned QR string into pairing credentials.
 * Accepts raw JSON from the PC app, optionally wrapped as
 * `blinky://connect/<json>` or `blinky://pair#<json>`.
 * Returns null when the code is not a Blinky pairing code.
 */
export function parsePairingQr(data: string): QrPairingPayload | null {
  try {
    let text = data.trim();
    const schemeMatch = text.match(/^blinky:\/\/[^#]*#(.+)$/s)
      || text.match(/^blinky:\/\/[^/]*\/(.+)$/s);
    if (schemeMatch) {
      text = decodeURIComponent(schemeMatch[1]);
    }
    const obj = JSON.parse(text);
    if (typeof obj !== 'object' || obj === null) return null;
    if (typeof obj.ip !== 'string' || !obj.ip.trim()) return null;

    const pin = typeof obj.pin === 'string' && obj.pin.trim()
      ? obj.pin.trim()
      : typeof obj.certificate_pin === 'string' && obj.certificate_pin.trim()
      ? obj.certificate_pin.trim()
      : null;

    const token = typeof obj.token === 'string' && obj.token.trim()
      ? obj.token.trim()
      : undefined;

    return {
      v: typeof obj.v === 'number' ? obj.v : 1,
      ip: obj.ip.trim(),
      ws: typeof obj.ws === 'number' ? obj.ws : (typeof obj.ws_port === 'number' ? obj.ws_port : 9001),
      disc: typeof obj.disc === 'number' ? obj.disc : (typeof obj.discovery_port === 'number' ? obj.discovery_port : 9004),
      token,
      pin,
      mode: typeof obj.mode === 'string' ? obj.mode : (pin ? 'release' : undefined),
    };
  } catch {
    return null;
  }
}
