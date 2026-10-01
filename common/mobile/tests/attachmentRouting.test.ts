import { expect, test } from 'bun:test';
import { AttachmentPlanner } from '../lib/attachmentRouting';

const files = [{ name: 'screen.png', type: 'image', mimeType: 'image/png', uri: 'private://image' }];

test('blank prompt transfers without contacting AI', async () => {
  expect(await new AttachmentPlanner().request('', files, () => { throw new Error('unexpected RPC'); })).toBe('transfer');
});

test('the PC model action determines routing for natural language', async () => {
  const planner = new AttachmentPlanner();
  let request: any;
  const result = planner.request('These belong wherever I keep my receipts', files, message => { request = message; return true; });
  expect(request.instruction).toBe('These belong wherever I keep my receipts');
  expect(request.files[0].uri).toBeUndefined();
  expect(planner.handle({ type: 'file_route_result', requestId: 'other', action: 'transfer' })).toBe(true);
  planner.handle({ type: 'file_route_result', requestId: request.requestId, action: 'transfer' });
  expect(await result).toBe('transfer');
});

test('image analysis is selected from the model response', async () => {
  const planner = new AttachmentPlanner();
  let request: any;
  const result = planner.request('Summarize this', files, message => { request = message; return true; });
  planner.handle({ type: 'file_route_result', requestId: request.requestId, action: 'analyze-image' });
  expect(await result).toBe('analyze-image');
});

test('invalid action and failed sends do not fall back to transfer', async () => {
  const planner = new AttachmentPlanner();
  let request: any;
  const result = planner.request('Put it on PC', files, message => { request = message; return true; });
  planner.handle({ type: 'file_route_result', requestId: request.requestId, action: 'delete' });
  await expect(result).rejects.toThrow('could not choose');
  await expect(planner.request('Summarize', files, () => false)).rejects.toThrow('Could not reach');
});

test('cancellation rejects planning and ignores late model decisions', async () => {
  const planner = new AttachmentPlanner();
  let request: any;
  const result = planner.request('Place this on PC', files, message => { request = message; return true; });
  planner.cancel();
  await expect(result).rejects.toThrow('connection closed');
  expect(planner.handle({ type: 'file_route_result', requestId: request.requestId, action: 'transfer' })).toBe(true);
  expect(planner.handle({ type: 'file_route_error', requestId: request.requestId, message: 'Late AI error' })).toBe(true);
  expect(planner.handle({ type: 'file_error', requestId: 'actual-transfer', message: 'Transfer failed' })).toBe(false);
});

test('throwing transport releases pending request and rejects immediately', async () => {
  const planner = new AttachmentPlanner();
  let request: any;
  await expect(planner.request('Summarize', files, message => {
    request = message;
    throw new Error('Socket failed');
  })).rejects.toThrow('Socket failed');
  expect(planner.handle({ type: 'file_error', requestId: request.requestId })).toBe(false);
});

test('routing errors reject without reaching the transfer handler', async () => {
  const planner = new AttachmentPlanner();
  let request: any;
  const result = planner.request('Summarize', files, message => { request = message; return true; });
  expect(planner.handle({ type: 'file_route_error', requestId: request.requestId, message: 'AI offline' })).toBe(true);
  await expect(result).rejects.toThrow('AI offline');
});
