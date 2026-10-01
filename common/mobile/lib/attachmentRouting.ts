type Attachment = { name: string; type?: string; mimeType?: string };
export type AttachmentRoute = 'transfer' | 'analyze-image' | 'unsupported';
type Pending = { resolve: (action: AttachmentRoute) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> };

/** Ask the authenticated PC AI to select a tool before sending any file bytes. */
export class AttachmentPlanner {
  private pending = new Map<string, Pending>();

  request(prompt: string, files: readonly Attachment[], send: (message: Record<string, unknown>) => boolean): Promise<AttachmentRoute> {
    if (!prompt.trim()) return Promise.resolve('transfer');
    const requestId = `attachment-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new Error('The PC AI took too long to choose an attachment action. Please try again.'));
      }, 65000);
      this.pending.set(requestId, { resolve, reject, timer });
      try {
        if (send({ type: 'file_route', requestId, instruction: prompt,
          files: files.map(({ name, type, mimeType }) => ({ name, type, mimeType })) })) return;
        throw new Error('Could not reach the PC to plan this attachment.');
      } catch (error) {
        clearTimeout(timer);
        this.pending.delete(requestId);
        reject(error instanceof Error ? error : new Error('Could not reach the PC to plan this attachment.'));
      }
    });
  }

  handle(message: { type?: string; requestId?: string; action?: unknown; message?: string }): boolean {
    const routeReply = message.type === 'file_route_result' || message.type === 'file_route_error';
    if (!message.requestId || (!routeReply && message.type !== 'file_error')) return routeReply;
    const pending = this.pending.get(message.requestId);
    if (!pending) return routeReply;
    clearTimeout(pending.timer);
    this.pending.delete(message.requestId);
    if (message.type !== 'file_route_result' || typeof message.action !== 'string' || !['transfer', 'analyze-image', 'unsupported'].includes(message.action)) {
      pending.reject(new Error(message.message || 'The PC AI could not choose an attachment action.'));
    } else {
      pending.resolve(message.action as AttachmentRoute);
    }
    return true;
  }

  cancel() {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(new Error('PC connection closed before the attachment action was decided.'));
    }
    this.pending.clear();
  }
}
