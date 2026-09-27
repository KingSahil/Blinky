import { describe, expect, test } from 'bun:test';
import { extractReferenceUrls, linkCitationMarkers } from '../src/lib/citations';

describe('citation links', () => {
  test('extracts reference URLs in display order', () => {
    const markdown = [
      'Answer with sources [1] and [2].',
      '',
      'References:',
      '- First source (https://example.com/one)',
      '- Second source (https://example.com/two).',
    ].join('\n');

    expect(extractReferenceUrls(markdown)).toEqual([
      'https://example.com/one',
      'https://example.com/two',
    ]);
  });

  test('links numeric citation markers to matching references', () => {
    const markdown = [
      'Cosmos launched recently [2], while another story matters [1].',
      '',
      'References:',
      '- First source (https://example.com/one)',
      '- Second source (https://example.com/two)',
    ].join('\n');

    expect(linkCitationMarkers(markdown)).toContain('[2](https://example.com/two)');
    expect(linkCitationMarkers(markdown)).toContain('[1](https://example.com/one)');
  });

  test('links numeric citation markers from a sources section', () => {
    const markdown = [
      'Amazon has one option [1], and EliteHubs has another [2].',
      '',
      'Sources:',
      '- [Amazon.in Gaming Mouse](https://amazon.in/example)',
      '- [EliteHubs Gaming Mouse](https://elitehubs.com/example)',
    ].join('\n');

    const linked = linkCitationMarkers(markdown);
    expect(linked).toContain('[1](https://amazon.in/example)');
    expect(linked).toContain('[2](https://elitehubs.com/example)');
  });

  test('does not rewrite existing markdown links or missing references', () => {
    const markdown = [
      'Already linked [1](https://example.com/manual) and missing [3].',
      '',
      'References:',
      '- First source (https://example.com/one)',
    ].join('\n');

    const linked = linkCitationMarkers(markdown);
    expect(linked).toContain('[1](https://example.com/manual)');
    expect(linked).toContain('missing [3]');
  });
});
