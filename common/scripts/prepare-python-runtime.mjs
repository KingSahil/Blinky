import { existsSync } from 'fs';
import { cp, mkdir, readFile, rm } from 'fs/promises';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';
import path from 'path';

if (process.platform !== 'win32') {
  process.exit(0);
}

const scriptPath = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(scriptPath), '..', '..');
const venvCfgPath = path.join(repoRoot, '.venv', 'pyvenv.cfg');

if (!existsSync(venvCfgPath)) {
  console.error(`Missing venv config at ${venvCfgPath}`);
  process.exit(1);
}

const venvCfg = await readFile(venvCfgPath, 'utf8');
const homeMatch = venvCfg.match(/^home\s*=\s*(.+)$/m);

if (!homeMatch) {
  console.error(`Could not determine Python home from ${venvCfgPath}`);
  process.exit(1);
}

const pythonHome = homeMatch[1].trim();
const runtimeRoot = path.join(repoRoot, 'common', 'python_runtime');
const runtimeDir = path.join(runtimeRoot, 'Python313');
const runtimePython = path.join(runtimeDir, 'python.exe');
const requirementsPath = path.join(repoRoot, 'windows', 'requirements.txt');

await rm(runtimeDir, { recursive: true, force: true });
await mkdir(runtimeRoot, { recursive: true });

console.log(`Copying Python from ${pythonHome} to ${runtimeDir} using Robocopy...`);
try {
  execFileSync('robocopy', [pythonHome, runtimeDir, '/E', '/R:3', '/W:1'], { stdio: 'inherit' });
} catch (err) {
  if (err.status === undefined || err.status >= 8) {
    console.error(`Robocopy failed with exit code ${err.status}`);
    throw err;
  }
}

// Clean up bloated site-packages before installing dependencies
const sitePackages = path.join(runtimeDir, 'Lib', 'site-packages');
await rm(sitePackages, { recursive: true, force: true });
await mkdir(sitePackages, { recursive: true });

if (!existsSync(runtimePython)) {
  console.error(`Portable Python was not created at ${runtimePython}`);
  process.exit(1);
}

execFileSync(runtimePython, ['-m', 'ensurepip', '--default-pip'], {
  stdio: 'inherit',
});

execFileSync(runtimePython, ['-m', 'pip', 'install', '--upgrade', 'pip'], {
  stdio: 'inherit',
});

execFileSync(runtimePython, ['-m', 'pip', 'install', '-r', requirementsPath], {
  stdio: 'inherit',
});

console.log(`Portable Python runtime prepared at ${runtimeDir}`);