import { existsSync } from 'fs';
import { mkdir, readFile, rm, copyFile } from 'fs/promises';
import { execFileSync, spawnSync } from 'child_process';
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

// ── 1. Copy the base Python install ──────────────────────────────────────────
console.log(`Copying Python from ${pythonHome} to ${runtimeDir} using Robocopy...`);
try {
  execFileSync('robocopy', [pythonHome, runtimeDir, '/E', '/R:3', '/W:1'], { stdio: 'inherit' });
} catch (err) {
  if (err.status === undefined || err.status >= 8) {
    console.error(`Robocopy failed with exit code ${err.status}`);
    throw err;
  }
}

if (!existsSync(runtimePython)) {
  console.error(`Portable Python was not created at ${runtimePython}`);
  process.exit(1);
}

// ── 1.1 Copy System C++ Runtime DLLs (MSVC Redistributable) ──────────────────
// This ensures C++ compiled extensions like winrt and cv2 load successfully
// on clean target machines that don't have Visual C++ Redistributables installed.
console.log('Copying MSVC runtime DLLs (msvcp140.dll/msvcp140_1.dll)...');
const system32Dir = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32');
const msvcDlls = ['msvcp140.dll', 'msvcp140_1.dll'];
for (const dll of msvcDlls) {
  const srcPath = path.join(system32Dir, dll);
  const destPath = path.join(runtimeDir, dll);
  if (existsSync(srcPath)) {
    try {
      await copyFile(srcPath, destPath);
      console.log(`  Copied ${dll} to python root.`);
    } catch (err) {
      console.warn(`  Failed to copy ${dll}: ${err.message}`);
    }
  } else {
    console.warn(`  Warning: System DLL ${dll} not found in System32!`);
  }
}


// ── 2. Wipe pre-existing site-packages (from system Python) ──────────────────
const libDir = path.join(runtimeDir, 'Lib');
const sitePackages = path.join(libDir, 'site-packages');
await rm(sitePackages, { recursive: true, force: true });
await mkdir(sitePackages, { recursive: true });

// ── 3. Bootstrap pip BEFORE we prune (ensurepip is still present here) ────────
console.log('Bootstrapping pip...');
execFileSync(runtimePython, ['-m', 'ensurepip', '--default-pip'], { stdio: 'inherit' });
execFileSync(runtimePython, ['-m', 'pip', 'install', '--upgrade', 'pip'], { stdio: 'inherit' });

// ── 4. Install production dependencies ───────────────────────────────────────
console.log('Installing production dependencies...');
execFileSync(runtimePython, [
  '-m', 'pip', 'install',
  '--no-warn-script-location',
  '-r', requirementsPath,
], { stdio: 'inherit' });

// ── 5. Prune stdlib bloat (NOW it's safe to remove ensurepip etc.) ─────────────
console.log('Pruning stdlib bloat...');
const stdlibPruneList = [
  path.join(libDir, 'test'),          // Python's own test suite (~28 MB)
  path.join(libDir, 'idlelib'),       // IDLE IDE (~2.5 MB)
  path.join(libDir, 'ensurepip'),     // bundled pip wheels — no longer needed (~1.7 MB)
  path.join(libDir, 'pydoc_data'),    // HTML templates for pydoc server (~1 MB)
  path.join(libDir, 'turtledemo'),    // Turtle graphics demo
  path.join(libDir, 'lib2to3'),       // Python 2->3 converter
  path.join(runtimeDir, 'Doc'),       // Python documentation (~58 MB)
  path.join(runtimeDir, 'images'),    // Misc images
  path.join(runtimeDir, 'NEWS.txt'),  // Changelog (~1.9 MB)
  path.join(runtimeDir, 'include'),   // C headers (only needed for building extensions)
  path.join(runtimeDir, 'libs'),      // .lib files (only needed for building extensions)
  path.join(runtimeDir, 'share'),
  path.join(runtimeDir, 'etc'),
  // NOTE: tcl/ is intentionally kept — tkinter (used by post_install.py) requires Tcl/Tk
];
for (const p of stdlibPruneList) {
  await rm(p, { recursive: true, force: true });
}

// ── 6. Prune site-packages bloat ─────────────────────────────────────────────
console.log('Pruning site-packages bloat...');

// Remove Playwright browser binaries (~100 MB) — post_install.py downloads them on first run
const playwrightBrowsers = path.join(sitePackages, 'playwright', 'driver', 'package', '.local-browsers');
await rm(playwrightBrowsers, { recursive: true, force: true });
console.log('  Removed Playwright bundled browsers.');

// Remove test directories recursively from all packages
const { readdirSync, statSync } = await import('fs');
const testDirNames = new Set(['test', 'tests', '_test', '__tests__', 'testing']);

function pruneTestDirs(dir) {
  let entries;
  try { entries = readdirSync(dir); } catch { return; }
  for (const entry of entries) {
    const fullPath = path.join(dir, entry);
    const stat = statSync(fullPath, { throwIfNoEntry: false });
    if (!stat?.isDirectory()) continue;
    if (testDirNames.has(entry.toLowerCase())) {
      // Schedule for deletion (synchronous rm is fine here since we await after loop)
      fs.rmSync(fullPath, { recursive: true, force: true });
    } else {
      pruneTestDirs(fullPath); // recurse into non-test subdirs
    }
  }
}

const fs = (await import('fs'));
const siteEntries = readdirSync(sitePackages);
for (const entry of siteEntries) {
  const entryPath = path.join(sitePackages, entry);
  const stat = statSync(entryPath, { throwIfNoEntry: false });
  if (!stat?.isDirectory()) continue;
  pruneTestDirs(entryPath);
}

// Remove specific known-bloat files
await rm(path.join(sitePackages, 'PyWin32.chm'), { force: true });    // Win32 help file (~2.5 MB)
await rm(path.join(sitePackages, 'pip'), { recursive: true, force: true }); // pip itself (~10 MB)
await rm(path.join(sitePackages, '_pytest'), { recursive: true, force: true }); // pytest internals

console.log(`\nPortable Python runtime prepared at ${runtimeDir}`);