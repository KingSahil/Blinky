export type FileOfferInput = {
  requestId: string;
  name: string;
  size: number;
  sha256: string;
  instruction: string;
  destinationPath: string;
  destinationHint?: string;
};

export function transferIntent(instruction: string): 'upload' | 'edit' {
  return instruction.trim() ? 'edit' : 'upload';
}

/** Match a rendered picker card to its item after the upload order changes. */
export function findTransferItem<T extends { file: { uri: string } }>(
  items: readonly T[] | undefined,
  file: { uri: string },
): T | undefined {
  return items?.find(item => item.file.uri === file.uri);
}

export function buildFileOffer(input: FileOfferInput): Record<string, unknown> {
  const destinationPath = input.destinationPath.trim();
  const pdfIntent = isPdfInstruction(input.instruction);
  return {
    type: 'file_offer',
    requestId: input.requestId,
    name: input.name,
    size: input.size,
    sha256: input.sha256,
    purpose: transferIntent(input.instruction),
    pdfAction: pdfIntent ? parsePdfAction(input.instruction) : undefined,
    ...(destinationPath ? { destinationPath } : {}),
    ...(input.destinationHint?.trim() ? { destinationHint: input.destinationHint.trim() } : {}),
  };
}

export function isPdfInstruction(instruction: string): boolean {
  const lower = instruction.toLowerCase();
  return (
    lower.includes('pdf') ||
    lower.includes('merge') ||
    lower.includes('watermark') ||
    lower.includes('extract table') ||
    lower.includes('docx to pdf') ||
    lower.includes('txt to pdf')
  );
}

export function parsePdfAction(instruction: string): string {
  const lower = instruction.toLowerCase();
  if (lower.includes('merge')) return 'merge';
  if (lower.includes('watermark')) return 'watermark';
  if (lower.includes('table') || lower.includes('csv')) return 'extract_tables';
  if (lower.includes('split') || lower.includes('extract page')) return 'split';
  if (lower.includes('rotate')) return 'rotate';
  return 'convert';
}

