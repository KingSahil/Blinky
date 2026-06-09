import { describe, expect, test } from 'bun:test';
import { getClickablePoint, isSafeAutopilotStep, runAutopilotLoop } from '../src/lib/autopilot';
import type { TutorResult, TutorStep } from '../src/lib/types';

function step(instruction: string, target = 'Gaming'): TutorStep {
  return {
    step: 1,
    instruction,
    target_text: target,
    match: {
      text: target,
      x: 100,
      y: 200,
      width: 80,
      height: 40,
      confidence: 0.95,
    },
  };
}

function result(steps: TutorStep[], summary = 'next'): TutorResult {
  return {
    summary,
    steps,
    active_app: { title: 'Edge', process: 'msedge.exe', supported: true },
    ocr: { count: 0, items: [] },
    elapsed_ms: 0,
    warnings: [],
  };
}

describe('isSafeAutopilotStep', () => {
  test('allows matched click/open/select steps', () => {
    expect(isSafeAutopilotStep(step('Click the Gaming section.'))).toBe(true);
    expect(isSafeAutopilotStep(step('Open Gaming.'))).toBe(true);
    expect(isSafeAutopilotStep(step('Select Gaming.'))).toBe(true);
  });

  test('rejects typing, submit, install, buy, and unmatched steps', () => {
    expect(isSafeAutopilotStep(step('Type milk into the search box.'))).toBe(false);
    expect(isSafeAutopilotStep(step('Click Buy Now.'))).toBe(false);
    expect(isSafeAutopilotStep(step('Click Install.'))).toBe(false);
    expect(isSafeAutopilotStep({ ...step('Click Gaming.'), match: null })).toBe(false);
  });
});

describe('getClickablePoint', () => {
  test('returns the center of the matched target', () => {
    expect(getClickablePoint(step('Click Gaming.'))).toEqual({ x: 140, y: 220 });
  });
});

describe('runAutopilotLoop', () => {
  test('observes, clicks, then observes again until done', async () => {
    const clicked: Array<{ x: number; y: number }> = [];
    const observations = [result([step('Click Gaming.')]), result([], 'Done')];

    const output = await runAutopilotLoop({
      maxAttempts: 5,
      observe: async () => observations.shift()!,
      act: async (point) => clicked.push(point),
      wait: async () => {},
    });

    expect(clicked).toEqual([{ x: 140, y: 220 }]);
    expect(output.finalResult.summary).toBe('Done');
    expect(output.attempts).toBe(1);
    expect(output.stopReason).toBe('complete');
  });

  test('stops after five attempts', async () => {
    let observes = 0;
    const output = await runAutopilotLoop({
      maxAttempts: 5,
      observe: async () => {
        observes += 1;
        return result([step(`Click Gaming ${observes}.`)]);
      },
      act: async () => {},
      wait: async () => {},
    });

    expect(output.attempts).toBe(5);
    expect(output.stopReason).toBe('max_attempts');
  });

  test('stops when the same target repeats after a click', async () => {
    let observes = 0;
    const output = await runAutopilotLoop({
      maxAttempts: 5,
      observe: async () => {
        observes += 1;
        return result([step('Click Gaming.')]);
      },
      act: async () => {},
      wait: async () => {},
    });

    expect(output.attempts).toBe(1);
    expect(output.stopReason).toBe('unchanged_after_action');
  });
});
