import { describe, expect, test } from 'bun:test';
import { getCasualChatResponse } from '../src/lib/casualChat';

describe('getCasualChatResponse', () => {
  test('answers casual wellness checks without screen guidance', () => {
    const result = getCasualChatResponse('how r u');

    expect(result?.steps).toEqual([]);
    expect(result?.summary.toLowerCase()).toContain('doing well');
  });

  test('answers identity questions without screen guidance', () => {
    const result = getCasualChatResponse('who are you?');

    expect(result?.steps).toEqual([]);
    expect(result?.summary).toContain('Blinky');
  });

  test('does not intercept screen guidance requests', () => {
    expect(getCasualChatResponse('how do I install the Python extension in VS Code?')).toBeNull();
  });
});
