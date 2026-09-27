import { describe, expect, test } from 'bun:test';
import { runWebActionThenScreenGuidance } from '../src/lib/webGuidance';
import type { TutorResult } from '../src/lib/types';

function result(summary: string, steps: TutorResult['steps'] = []): TutorResult {
  return {
    summary,
    steps,
    active_app: { title: '', process: '', supported: false },
    ocr: { count: 0, items: [] },
    elapsed_ms: 0,
    warnings: [],
  };
}

describe('runWebActionThenScreenGuidance', () => {
  test('runs the browser action before screen guidance', async () => {
    const calls: string[] = [];
    const screenResult = result('Click the Blinkit search result.', [
      {
        step: 1,
        instruction: 'Click the Blinkit search result.',
        target_text: 'Blinkit',
        match: {
          text: 'Blinkit',
          x: 10,
          y: 20,
          width: 100,
          height: 30,
          confidence: 0.9,
        },
      },
    ]);

    const output = await runWebActionThenScreenGuidance({
      query: 'give me gaming chair from blinkit',
      previousQuestion: undefined,
      progress: { completed_targets: [], completed_instructions: [] },
      conversationHistory: [],
      runAgentQuery: async () => {
        calls.push('agent');
        return result('Opened web search for gaming chair on blinkit.');
      },
      runTutor: async () => {
        calls.push('screen');
        return screenResult;
      },
    });

    expect(calls).toEqual(['agent', 'screen']);
    expect(output).toBe(screenResult);
  });

  test('falls back to the browser result if screen guidance fails', async () => {
    const browserResult = result('Opened web search for gaming chair on blinkit.');

    const output = await runWebActionThenScreenGuidance({
      query: 'give me gaming chair from blinkit',
      previousQuestion: undefined,
      progress: { completed_targets: [], completed_instructions: [] },
      conversationHistory: [],
      runAgentQuery: async () => browserResult,
      runTutor: async () => {
        throw new Error('screen capture failed');
      },
    });

    expect(output).toBe(browserResult);
  });
});
