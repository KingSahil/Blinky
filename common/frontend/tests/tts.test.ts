import { describe, expect, test } from 'bun:test';
import { buildAudioDataUrl, buildSarvamTtsPayload, buildSpeechContent, getSarvamErrorMessage } from '../src/lib/tts';

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
  test('uses MP3 media type for compressed Sarvam output', () => {
    expect(buildAudioDataUrl('SUQz')).toBe('data:audio/mpeg;base64,SUQz');
  });
});

describe('buildSarvamTtsPayload', () => {
  test('uses a compact Bulbul v3 MP3 payload compatible with English readback', () => {
    expect(buildSarvamTtsPayload('Hello')).toEqual({
      text: 'Hello',
      model: 'bulbul:v3',
      target_language_code: 'en-IN',
      speaker: 'ratan',
      pace: 1.05,
      speech_sample_rate: 16000,
      output_audio_codec: 'mp3',
    });
  });
});

describe('buildSpeechContent', () => {
  test('keeps automatic voice readback short and natural', () => {
    expect(
      buildSpeechContent('Open Extensions from the sidebar.', [
        { step: 1, instruction: 'Click Extensions.' },
        { step: 2, instruction: 'Search Python.' },
      ]),
    ).toBe('Open Extensions from the sidebar.');
  });

  test('strips robotic Step 1 prefixes from summary or instructions', () => {
    expect(
      buildSpeechContent('Step 1: click reddit', []),
    ).toBe('Click reddit');

    expect(
      buildSpeechContent('Step 1. Click on the Reddit icon.', []),
    ).toBe('Click on the Reddit icon.');
  });

  test('speaks fallback step cleanly without step numbers when summary is empty', () => {
    expect(
      buildSpeechContent(
        '',
        [{ step: 3, instruction: 'Step 3: Click the Install button for the extension.' }],
      ),
    ).toBe('Click the Install button for the extension.');
  });
});
