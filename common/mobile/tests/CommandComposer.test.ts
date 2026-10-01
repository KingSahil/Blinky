import { expect, test } from 'bun:test';
import { fileURLToPath } from 'node:url';

// The composer case mocks React hooks; run it in a separate Bun process so
// those module mocks cannot replace the WebSocket hook suite's React mock.
test('composer offers four chat attachments without a separate transfer action', () => {
  const run = Bun.spawnSync({
    cmd: [process.execPath, 'test', fileURLToPath(new URL('./CommandComposer.case.tsx', import.meta.url))],
    stdout: 'pipe',
    stderr: 'pipe',
  });
  const output = `${new TextDecoder().decode(run.stdout)}\n${new TextDecoder().decode(run.stderr)}`;
  expect(run.exitCode, output).toBe(0);
});
