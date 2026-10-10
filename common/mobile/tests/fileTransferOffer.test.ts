import { expect, test } from 'bun:test';
import { buildFileOffer, findTransferItem, transferIntent, extractTransferEdit } from '../lib/fileTransferOffer';

test('a mixed batch without instruction remains an upload', () => {
  expect(transferIntent('')).toBe('upload');
  expect(buildFileOffer({
    requestId: 'offer-1', name: 'notes.pdf', size: 12, sha256: 'a'.repeat(64),
    instruction: '', destinationPath: '/home/user/Projects',
  })).toEqual({
    type: 'file_offer', requestId: 'offer-1', name: 'notes.pdf', size: 12,
    sha256: 'a'.repeat(64), purpose: 'upload', destinationPath: '/home/user/Projects',
  });
});

test('an explicit edit instruction marks every file offer for an AiCut batch', () => {
  expect(transferIntent('  merge these videos  ')).toBe('edit');
  expect(buildFileOffer({
    requestId: 'offer-2', name: 'clip.mp4', size: 50, sha256: 'b'.repeat(64),
    instruction: 'trim from 1 to 3 seconds', destinationPath: ' ',
    destinationHint: 'send this to downloads/blinky folder and trim to 2 seconds',
  })).toEqual({
    type: 'file_offer', requestId: 'offer-2', name: 'clip.mp4', size: 50,
    sha256: 'b'.repeat(64), purpose: 'edit',
    destinationHint: 'send this to downloads/blinky folder and trim to 2 seconds',
  });
});

test('file-card status follows file identity after transfer priority reorders items', () => {
  const pdf = { uri: 'content://notes', name: 'notes.pdf' };
  const audio = { uri: 'content://beat', name: 'beat.wav' };
  const items = [
    { file: audio, phase: 'uploading' },
    { file: pdf, phase: 'pending' },
  ];
  expect(findTransferItem(items, pdf)?.phase).toBe('pending');
  expect(findTransferItem(items, audio)?.phase).toBe('uploading');
});

test('extractTransferEdit identifies silence removal instructions', () => {
  expect(extractTransferEdit('remove silence')).toBe('remove silence');
  expect(extractTransferEdit('remove silence from video')).toBe('remove silence from video');
  expect(extractTransferEdit('cut the silence from this clip')).toBe('cut the silence from this clip');
  expect(extractTransferEdit('jump cut this video')).toBe('jump cut this video');
  expect(extractTransferEdit('remove silence and save to PC')).toBe('remove silence');
  expect(extractTransferEdit('put this in videos and remove silence')).toBe('remove silence');
});

test('extractTransferEdit preserves standard media edits and ignores pure destinations', () => {
  expect(extractTransferEdit('trim from 1 to 3 seconds')).toBe('trim from 1 to 3 seconds');
  expect(extractTransferEdit('add subtitles with instagram preset')).toBe('add subtitles with instagram preset');
  expect(extractTransferEdit('save to Downloads/Blinky')).toBe('');
  expect(extractTransferEdit('put these in my receipts folder')).toBe('');
});
