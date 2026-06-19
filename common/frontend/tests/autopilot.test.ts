import { describe, expect, test } from 'bun:test';
import { getClickablePoint, getPhysicalClickablePoint, isSafeAutopilotStep, runAutopilotLoop, extractTextToType, shouldPressEnterAfterTyping, isScrollAction, getScrollDirection } from '../src/lib/autopilot';
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

function refStep(instruction: string, target = 'Gaming'): TutorStep {
  const next = step(instruction, target);
  next.target_ref = '@e1';
  next.match = {
    ...next.match!,
    ref: '@e1',
    match_method: 'ref',
  };
  return next;
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
  test('allows matched click/open/select/type/scroll steps', () => {
    expect(isSafeAutopilotStep(refStep('Click the Gaming section.'))).toBe(true);
    expect(isSafeAutopilotStep(refStep('Open Gaming.'))).toBe(true);
    expect(isSafeAutopilotStep(refStep('Select Gaming.'))).toBe(true);
    expect(isSafeAutopilotStep(refStep('Type milk into the search box.'))).toBe(true);
    expect(isSafeAutopilotStep(refStep('Scroll down on the page.'))).toBe(true);
  });

  test('rejects high-risk, install, buy, and unmatched steps', () => {
    expect(isSafeAutopilotStep(refStep('Click Buy Now.'))).toBe(false);
    expect(isSafeAutopilotStep(refStep('Click Install.'))).toBe(false);
    expect(isSafeAutopilotStep({ ...refStep('Click Gaming.'), match: null })).toBe(false);
  });

  test('rejects fuzzy non-exact matches for autopilot clicks', () => {
    const fuzzy = step('Click the Gaming section.');
    fuzzy.match = {
      ...fuzzy.match!,
      text_similarity: 0.72,
      match_method: 'text',
      is_exact_text: false,
    };

    expect(isSafeAutopilotStep(fuzzy)).toBe(false);
  });
});

describe('extractTextToType', () => {
  test('extracts text inside quotes', () => {
    expect(extractTextToType("Type 'I love pizza' in the search bar")).toBe('I love pizza');
    expect(extractTextToType('Type "milk" into search box')).toBe('milk');
  });

  test('extracts text without quotes using prepositions as boundary', () => {
    expect(extractTextToType('Type milk into the search box')).toBe('milk');
    expect(extractTextToType('Type some search query and press enter')).toBe('some search query');
    expect(extractTextToType('Search for apples in grocery app')).toBe('apples');
  });

  test('returns null if no match', () => {
    expect(extractTextToType('Click the button')).toBe(null);
  });
});

describe('shouldPressEnterAfterTyping', () => {
  test('returns true if instruction mentions enter or search', () => {
    expect(shouldPressEnterAfterTyping('Type milk and press Enter')).toBe(true);
    expect(shouldPressEnterAfterTyping('Search for apples')).toBe(true);
  });

  test('returns false otherwise', () => {
    expect(shouldPressEnterAfterTyping('Type milk')).toBe(false);
  });
});

describe('getClickablePoint', () => {
  test('returns the center of the matched target', () => {
    expect(getClickablePoint(step('Click Gaming.'))).toEqual({ x: 140, y: 220 });
  });

  test('scales optimized screenshot coordinates to physical screen coordinates', () => {
    const screen = result([step('Click Gaming.')]);
    screen.screenshot = {
      path: 'screenshots/test.jpg',
      width: 1728,
      height: 1080,
      screen_width: 2560,
      screen_height: 1600,
    };

    expect(getPhysicalClickablePoint(step('Click Gaming.'), screen)).toEqual({ x: 207, y: 326 });
  });
});

describe('runAutopilotLoop', () => {
  test('observes, clicks, then observes again until done', async () => {
    const clicked: Array<{ x: number; y: number }> = [];
    const observations = [result([refStep('Click Gaming.')]), result([], 'Done')];

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

  test('clicks physical screen coordinates when screenshot was downsampled', async () => {
    const clicked: Array<{ x: number; y: number }> = [];
    const first = result([refStep('Click Gaming.')]);
    first.screenshot = {
      path: 'screenshots/test.jpg',
      width: 1728,
      height: 1080,
      screen_width: 2560,
      screen_height: 1600,
    };
    const observations = [first, result([], 'Done')];

    await runAutopilotLoop({
      observe: async () => observations.shift()!,
      act: async (point) => clicked.push(point),
      wait: async () => {},
    });

    expect(clicked).toEqual([{ x: 207, y: 326 }]);
  });

  test('stops after five attempts', async () => {
    let observes = 0;
    const output = await runAutopilotLoop({
      maxAttempts: 5,
      observe: async () => {
        observes += 1;
        return result([refStep(`Click Gaming ${observes}.`)]);
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
        return result([refStep('Click Gaming.')]);
      },
      act: async () => {},
      wait: async () => {},
    });

    expect(output.attempts).toBe(1);
    expect(output.stopReason).toBe('unchanged_after_action');
  });

  test('can stop after one action without observing again', async () => {
    let observes = 0;
    const clicked: Array<{ x: number; y: number }> = [];

    const output = await runAutopilotLoop({
      maxAttempts: 5,
      observeAfterAction: false,
      observe: async () => {
        observes += 1;
        return result([refStep('Click Gaming.')]);
      },
      act: async (point) => clicked.push(point),
      wait: async () => {},
    });

    expect(observes).toBe(1);
    expect(clicked).toEqual([{ x: 140, y: 220 }]);
    expect(output.attempts).toBe(1);
    expect(output.stopReason).toBe('single_action');
  });
});

describe('isScrollAction', () => {
  test('returns true for actions containing scroll', () => {
    expect(isScrollAction('Scroll down')).toBe(true);
    expect(isScrollAction('Scroll up the list')).toBe(true);
    expect(isScrollAction('please scroll to find the element')).toBe(true);
  });

  test('returns false otherwise', () => {
    expect(isScrollAction('Click the list')).toBe(false);
    expect(isScrollAction('Type scroll in the input')).toBe(false);
  });
});

describe('getScrollDirection', () => {
  test('returns up if instruction mentions scroll up', () => {
    expect(getScrollDirection('scroll up')).toBe('up');
    expect(getScrollDirection('please scroll up the list')).toBe('up');
  });

  test('returns down by default or if scroll down is mentioned', () => {
    expect(getScrollDirection('scroll down')).toBe('down');
    expect(getScrollDirection('scroll')).toBe('down');
  });
});

