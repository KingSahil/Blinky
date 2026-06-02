import { describe, expect, test } from 'bun:test';
import { buildAudioDataUrl, buildSarvamTtsPayload, getSarvamErrorMessage } from '../src/lib/tts';

describe('getSarvamErrorMessage', () => {
  test('extracts nested Sarvam error messages', () => {
    expect(
      getSarvamErrorMessage({
        error: {
          message: 'Invalid API key. Check your credentials.',
          code: 'invalid_api_key_error',
        },
      }, 403),
    ).toBe('Invalid API key. Check your credentials.');
  });

  test('falls back to a useful code and status instead of object text', () => {
    expect(
      getSarvamErrorMessage({
        error: {
          code: 'insufficient_quota_error',
        },
      }, 429),
    ).toBe('Sarvam TTS failed with status 429: insufficient_quota_error');
  });
});

describe('buildAudioDataUrl', () => {
  test('uses Sarvam default WAV media type', () => {
    expect(buildAudioDataUrl('UklGRg==')).toBe('data:audio/wav;base64,UklGRg==');
  });
});

describe('buildSarvamTtsPayload', () => {
  test('uses a Bulbul v3 speaker compatible with English readback', () => {
    expect(buildSarvamTtsPayload('Hello')).toEqual({
      text: 'Hello',
      model: 'bulbul:v3',
      target_language_code: 'en-IN',
      speaker: 'ratan',
      pace: 1.05,
    });
  });
});
