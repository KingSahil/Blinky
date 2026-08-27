export interface SarvamTtsPayload {
  text: string;
  model: 'bulbul:v3';
  target_language_code: 'en-IN';
  speaker: 'ratan';
  pace: number;
  speech_sample_rate: number;
  output_audio_codec: 'mp3' | 'pcm';
}

export function buildSarvamTtsPayload(text: string): SarvamTtsPayload {
  return {
    text,
    model: 'bulbul:v3',
    target_language_code: 'en-IN',
    speaker: 'ratan',
    pace: 1.05,
    speech_sample_rate: 16000,
    output_audio_codec: 'mp3',
  };
}

export interface SpeechStep {
  step?: number;
  instruction?: string;
}

export function cleanSpokenText(text: string): string {
  let cleaned = (text || '')
    // Remove markdown links [text](url) -> text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // Remove citation markers [1], [2], etc.
    .replace(/\[\d+\]/g, '')
    // Remove markdown formatting characters (*, _, `, #)
    .replace(/[*_`#~]/g, '')
    // Remove robotic prefixes like "Step 1:", "Step 1.", "Step 2 -", "Steps:"
    .replace(/\bstep\s*\d+[\s:.-]+/gi, '')
    .replace(/\bsteps[\s:.-]+/gi, '')
    // Clean up multiple spaces and empty punctuation
    .replace(/\s+/g, ' ')
    .trim();

  if (cleaned.length > 0) {
    cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  }
  return cleaned;
}

export function buildSpeechContent(
  summaryText: string,
  stepsList: SpeechStep[] = [],
  options: { includeSteps?: boolean } = {},
): string {
  const summary = cleanSpokenText(summaryText);
  if (summary) {
    return summary;
  }

  if (stepsList.length > 0) {
    const firstValidStep = stepsList.find((s) => s.instruction?.trim());
    if (firstValidStep?.instruction) {
      return cleanSpokenText(firstValidStep.instruction);
    }
  }

  return '';
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

export function buildAudioDataUrl(base64Audio: string, mimeType = 'audio/mpeg'): string {
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
