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
