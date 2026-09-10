import { expect, test } from 'bun:test';
import { disconnectedConnectionState } from '../connectionState';

test('disconnecting after authentication failure preserves the error state', () => {
  expect(disconnectedConnectionState('The PC rejected the remote token.')).toEqual({
    status: 'error',
    errorMsg: 'The PC rejected the remote token.',
    latestResponse: null,
  });
});
