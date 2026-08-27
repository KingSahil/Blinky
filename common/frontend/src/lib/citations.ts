export function linkCitationMarkers(markdown: string): string {
  const urls = extractReferenceUrls(markdown);
  if (urls.length === 0) {
    return markdown;
  }

  return markdown.replace(/(^|[^\]!])\[(\d{1,3})\](?!\()/g, (match, prefix: string, value: string) => {
    const index = Number.parseInt(value, 10) - 1;
    const url = urls[index];
    if (!url) {
      return match;
    }

    return `${prefix}[${value}](${url})`;
  });
}

export function extractReferenceUrls(markdown: string): string[] {
  const sourceMatch = markdown.match(/\b(?:References?|Sources?):\s*[\s\S]*$/i);
  const referenceSection = sourceMatch ? sourceMatch[0] : markdown;
  const matches = referenceSection.match(/https?:\/\/[^\s)]+/gi) || [];
  const urls: string[] = [];

  for (const match of matches) {
    const url = match.replace(/[.,;:]+$/g, '');
    if (!urls.includes(url)) {
      urls.push(url);
    }
  }

  return urls;
}

/**
 * Preprocesses markdown text before rendering:
 * 1. Formats inline / unseparated tables into clean GFM Markdown Tables.
 * 2. Ensures appropriate spacing before and after markdown headers and tables.
 * 3. Links citation markers [1], [2] to their reference URLs.
 */
export function preprocessMarkdown(markdown: string): string {
  if (!markdown) return '';
  let text = markdown;

  // 1. Separate table separator rows |---|---| on the same line as headers
  text = text.replace(/(\|[^\n\r]+?\|)\s*(\|(?:\s*:?-+:?\s*\|)+)/g, '$1\n$2');

  // 2. Separate data rows placed on the same line after separators
  text = text.replace(/(\|(?:\s*:?-+:?\s*\|)+)\s*(\|[^\n\r]+?\|)/g, '$1\n$2');

  // 3. Separate consecutive data rows placed on the same line
  while (/(\|[^\n\r]+?\|)\s{2,}(\|[^\n\r]+?\|)/.test(text) || /(\|[^\n\r]+?\|)\s+(\|[^\n\r]+?\|)/.test(text)) {
    const next = text.replace(/(\|[^\n\r]+?\|)\s+(\|[^\n\r]+?\|)/g, '$1\n$2');
    if (next === text) break;
    text = next;
  }

  // 4. Ensure double newline before table if immediately following regular text without a newline
  text = text.replace(/([^\n\r|])\s*(\|[^\n\r]+?\|[\r\n]+\|(?:\s*:?-+:?\s*\|)+)/g, '$1\n\n$2');

  // 5. Connect citation markers [1], [2] to sources
  text = linkCitationMarkers(text);

  return text;
}
