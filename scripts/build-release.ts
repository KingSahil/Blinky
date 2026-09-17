const child = Bun.spawn([process.execPath, 'tauri', 'build', ...process.argv.slice(2)], {
  env: {
    ...process.env,
    BLINKY_TRANSPORT_MODE: 'release',
    VITE_BLINKY_TRANSPORT_MODE: 'release',
  },
  stdout: 'inherit',
  stderr: 'inherit',
});

process.exit(await child.exited);
