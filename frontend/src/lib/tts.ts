export interface SarvamTtsPayload {
  text: string;
  model: 'bulbul:v3';
  target_language_code: 'en-IN';
  speaker: 'ratan';
  pace: number;
}

export function buildSarvamTtsPayload(text: string): SarvamTtsPayload {
  return {
    text,
    model: 'bulbul:v3',
    target_language_code: 'en-IN',
    speaker: 'ratan',
    pace: 1.05,
  };
}

export function getSarvamErrorMessage(payload: unknown, status: number): string {
  const detail = extractErrorDetail(payload);
  if (detail) {
    if (detail.kind === 'code' && status > 0) {
      return `Sarvam TTS failed with status ${status}: ${detail.text}`;
    }
    return detail.text;
  }

  return status > 0 ? `Sarvam TTS failed with status ${status}` : 'Sarvam TTS failed.';
}

export function buildAudioDataUrl(base64Audio: string, mimeType = 'audio/wav'): string {
  return `data:${mimeType};base64,${base64Audio}`;
}

function extractErrorDetail(value: unknown): { text: string; kind: 'message' | 'code' } | null {
  if (typeof value === 'string') {
    const text = value.trim();
    return text ? { text, kind: 'message' } : null;
  }

  if (!value || typeof value !== 'object') {
    return null;
  }

  const record = value as Record<string, unknown>;
  if ('error' in record) {
    const nested = extractErrorDetail(record.error);
    if (nested) return nested;
  }

  for (const key of ['message', 'detail', 'code']) {
    const field = record[key];
    if (typeof field === 'string' && field.trim()) {
      return {
        text: field.trim(),
        kind: key === 'code' ? 'code' : 'message',
      };
    }
  }

  return null;
}
