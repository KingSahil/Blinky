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
    output_audio_codec: 'pcm',
  };
}

export interface SpeechStep {
  step?: number;
  instruction?: string;
}

export function buildSpeechContent(
  summaryText: string,
  stepsList: SpeechStep[] = [],
  options: { includeSteps?: boolean } = {},
): string {
  const summary = summaryText.trim();
  if (!options.includeSteps || stepsList.length === 0) {
    return summary;
  }

  const stepText = stepsList
    .map((step, idx) => {
      const instruction = step.instruction?.trim();
      if (!instruction) return null;
      return `Step ${step.step || idx + 1}. ${instruction}`;
    })
    .filter(Boolean)
    .join(' ');

  if (!stepText) return summary;
  if (!summary) return stepText;

  return `${summary.replace(/[.!?]+$/, '')}. Steps: ${stepText}`;
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
