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
  return {
    type: 'file_offer',
    requestId: input.requestId,
    name: input.name,
    size: input.size,
    sha256: input.sha256,
    purpose: transferIntent(input.instruction),
    ...(destinationPath ? { destinationPath } : {}),
    ...(input.destinationHint?.trim() ? { destinationHint: input.destinationHint.trim() } : {}),
  };
}
