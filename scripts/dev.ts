import { spawn, type Subprocess } from "bun";
import { existsSync } from "fs";

const args = Bun.argv.slice(2);
const noDocker = args.includes("--no-docker");
const noMobile = args.includes("--no-mobile");

function getDockerPath(): string {
  if (process.platform !== "win32") {
    return "docker";
  }
  const progFiles = process.env.ProgramFiles || "C:\\Program Files";
  const progFilesX86 = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)";
  const candidates = [
    "docker",
    `${progFiles}\\Docker\\Docker\\resources\\bin\\docker.exe`,
    `${progFilesX86}\\Docker\\Docker\\resources\\bin\\docker.exe`,
    "C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe",
  ];
  for (const c of candidates) {
    if (c === "docker") {
      try {
        const proc = spawn(["docker", "--version"]);
        proc.kill();
        return "docker";
      } catch {}
    } else if (existsSync(c)) {
      return c;
    }
  }
  return "docker";
}

function getDockerDesktopPath(): string | null {
  if (process.platform === "win32") {
    const progFiles = process.env.ProgramFiles || "C:\\Program Files";
    const progFilesX86 = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)";
    const localAppData = process.env.LOCALAPPDATA || "";
    const candidates = [
      `${progFiles}\\Docker\\Docker\\Docker Desktop.exe`,
      "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe",
      `${progFilesX86}\\Docker\\Docker\\Docker Desktop.exe`,
      `${localAppData}\\Programs\\Docker\\Docker\\Docker Desktop.exe`,
      `${localAppData}\\Docker\\Docker Desktop.exe`,
    ];
    for (const c of candidates) {
      if (c && existsSync(c)) {
        return c;
      }
    }
  } else if (process.platform === "darwin") {
    if (existsSync("/Applications/Docker.app")) {
      return "/Applications/Docker.app";
    }
  }
  return null;
}

async function isDockerDaemonRunning(dockerPath: string): Promise<boolean> {
  try {
    const proc = spawn([dockerPath, "info"], {
      stdout: "pipe",
      stderr: "pipe",
    });
    const exitCodePromise = proc.exited;
    const timeoutPromise = new Promise<number>((resolve) => setTimeout(() => resolve(1), 3500));
    const exitCode = await Promise.race([exitCodePromise, timeoutPromise]);
    if (exitCode === 0) {
      return true;
    }
    try {
      proc.kill();
    } catch {}
    return false;
  } catch {
    return false;
  }
}

async function tryStartDockerDaemon(dockerPath: string): Promise<boolean> {
  if (await isDockerDaemonRunning(dockerPath)) {
    return true;
  }

  if (process.platform === "win32") {
    const desktopExe = getDockerDesktopPath();
    if (desktopExe) {
      console.log(`[Docker] 🐳 Docker is installed but daemon is not running. Launching Docker Desktop (${desktopExe})...`);
      try {
        const startProc = spawn(["cmd.exe", "/c", "start", "", desktopExe], {
          detached: true,
          stdio: ["ignore", "ignore", "ignore"],
        });
        startProc.unref();
      } catch (err: any) {
        console.warn(`[Docker] Failed to launch Docker Desktop: ${err?.message || err}`);
        return false;
      }
    } else {
      console.log("[Docker] 🐳 Docker Desktop executable not found at standard paths. Trying com.docker.service...");
      try {
        const netStart = spawn(["powershell", "-NoProfile", "-Command", "Start-Service com.docker.service -ErrorAction SilentlyContinue"]);
        await Promise.race([netStart.exited, new Promise((r) => setTimeout(r, 4000))]);
      } catch {}
    }
  } else if (process.platform === "darwin") {
    console.log("[Docker] 🐳 Docker daemon is not running. Launching Docker.app...");
    try {
      const startProc = spawn(["open", "-a", "Docker"], {
        detached: true,
        stdio: ["ignore", "ignore", "ignore"],
      });
      startProc.unref();
    } catch (err: any) {
      console.warn(`[Docker] Failed to launch Docker.app: ${err?.message || err}`);
      return false;
    }
  } else {
    // Linux
    console.log("[Docker] 🐳 Attempting to start Docker daemon service...");
    try {
      const startProc = spawn(["systemctl", "--user", "start", "docker"], { stdio: "ignore" });
      await Promise.race([startProc.exited, new Promise((r) => setTimeout(r, 3000))]);
    } catch {
      try {
        const sysStart = spawn(["sudo", "systemctl", "start", "docker"], { stdio: "ignore" });
        await Promise.race([sysStart.exited, new Promise((r) => setTimeout(r, 3000))]);
      } catch {}
    }
  }

  // Poll until the Docker daemon is ready (up to 45 seconds)
  const maxWaitSeconds = 45;
  const pollIntervalMs = 2000;
  const startTime = Date.now();

  console.log(`[Docker] ⏳ Waiting for Docker engine to become ready (max ${maxWaitSeconds}s)...`);
  while ((Date.now() - startTime) < maxWaitSeconds * 1000) {
    await new Promise((r) => setTimeout(r, pollIntervalMs));
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    if (await isDockerDaemonRunning(dockerPath)) {
      console.log(`[Docker] ✨ Docker daemon is now online and ready (took ${elapsed}s)!`);
      return true;
    }
    if (elapsed % 6 === 0) {
      console.log(`[Docker] ⏳ Still waiting for Docker engine to initialize (${elapsed}s / ${maxWaitSeconds}s)...`);
    }
  }

  console.warn(`[Docker] ⚠️ Docker daemon did not become ready within ${maxWaitSeconds} seconds.`);
  return false;
}

async function ensureSearXNGStarted(): Promise<void> {
  if (noDocker) {
    console.log("[Docker] Skipping SearXNG (--no-docker flag specified).");
    return;
  }

  const dockerPath = getDockerPath();
  let isRunning = await isDockerDaemonRunning(dockerPath);

  if (!isRunning) {
    console.log("[Docker] Docker daemon is not active. Attempting to start it automatically...");
    isRunning = await tryStartDockerDaemon(dockerPath);
  }

  if (!isRunning) {
    console.warn("Warning: Docker was not found or failed to start. Skipping SearXNG (web search functionality will be disabled).");
    console.warn("💡 Tip: You can start Docker Desktop manually anytime and SearXNG will connect.");
    return;
  }

  console.log("Starting SearXNG via Docker Compose...");
  try {
    const dockerCompose = spawn([dockerPath, "compose", "-f", "common/docker-compose.yml", "up", "-d"], {
      stdout: "inherit",
      stderr: "inherit",
    });
    const exitCode = await dockerCompose.exited;
    if (exitCode !== 0) {
      console.error("Warning: Failed to start SearXNG via Docker Compose. Continuing anyway...");
    } else {
      console.log("[Docker] ✅ SearXNG service is ready on http://localhost:8888");
    }
  } catch (err: any) {
    console.warn(`Warning: Docker Compose error (${err?.message || err}). Skipping SearXNG.`);
  }
}

function getAdbPath(): string | null {
  if (process.platform === "win32") {
    const localAppData = process.env.LOCALAPPDATA || "";
    const androidHome = process.env.ANDROID_HOME || "";
    const candidates = [
      "adb",
      `${localAppData}\\Android\\platform-tools\\adb.exe`,
      `${localAppData}\\Android\\Sdk\\platform-tools\\adb.exe`,
      `${androidHome}\\platform-tools\\adb.exe`,
      "C:\\Program Files\\Android\\Android Studio\\platform-tools\\adb.exe",
    ];
    for (const c of candidates) {
      if (c === "adb") {
        try {
          const test = spawn(["adb", "version"]);
          test.kill();
          return "adb";
        } catch {}
      } else if (existsSync(c)) {
        return c;
      }
    }
  } else {
    try {
      const test = spawn(["adb", "version"]);
      test.kill();
      return "adb";
    } catch {}
  }
  return null;
}

async function checkAndStartMobileIfUsbConnected(): Promise<Subprocess | null> {
  const adb = getAdbPath();
  if (!adb) {
    console.log("[Mobile] adb not found. Skipping USB mobile check.");
    return null;
  }

  try {
    const proc = spawn([adb, "devices", "-l"], { stdout: "pipe" });
    const outputPromise = new Response(proc.stdout).text();
    const timeoutPromise = new Promise<string>((resolve) => setTimeout(() => resolve(""), 2500));
    const output = await Promise.race([outputPromise, timeoutPromise]);

    // Parse connected devices in 'device' state
    const lines = output.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    const connectedDevices = lines.filter(l => !l.startsWith("List of") && l.includes("device") && !l.includes("offline") && !l.includes("unauthorized"));

    if (connectedDevices.length === 0) {
      console.log("[Mobile] No USB-connected Android devices detected.");
      return null;
    }

    console.log(`[Mobile] 📱 Detected ${connectedDevices.length} USB-connected Android device(s):`);
    for (const dev of connectedDevices) {
      console.log(`  - ${dev}`);
    }

    console.log("[Mobile] Setting up USB reverse port forwarding (tcp:9001, tcp:8081)...");
    const rev1 = spawn([adb, "reverse", "tcp:9001", "tcp:9001"]);
    await Promise.race([rev1.exited, new Promise(r => setTimeout(r, 1500))]);
    const rev2 = spawn([adb, "reverse", "tcp:8081", "tcp:8081"]);
    await Promise.race([rev2.exited, new Promise(r => setTimeout(r, 1500))]);

    // Check if Metro bundler is already running
    let mobileProc: Subprocess | null = null;
    let isRunning = false;
    try {
      const res = await fetch("http://localhost:8081", { signal: AbortSignal.timeout(1000) });
      isRunning = res.status === 200 || res.status === 404;
    } catch {}

    if (isRunning) {
      console.log("[Mobile] ⚡ Metro bundler is already running on port 8081.");
    } else {
      if (process.platform === "win32") {
        try {
          const killProc = spawn(["powershell", "-Command", "Get-NetTCPConnection -LocalPort 8081 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"]);
          await killProc.exited;
        } catch {}
      }

      console.log("[Mobile] 🚀 Starting Expo mobile development server on port 8081...");
      mobileProc = spawn(["bun", "run", "start"], {
        cwd: "common/mobile",
        stdout: "inherit",
        stderr: "inherit",
        stdin: "pipe",
        env: {
          ...process.env,
          EXPO_NO_TELEMETRY: "1",
        },
      });

    }

    // Wait for Metro packager to be ready before opening the app on device
    (async () => {
      const maxAttempts = 40;
      let ready = false;
      for (let i = 0; i < maxAttempts; i++) {
        try {
          const res = await fetch("http://localhost:8081/status", { signal: AbortSignal.timeout(1000) });
          if (res.status === 200) {
            ready = true;
            break;
          }
        } catch {}
        await new Promise(r => setTimeout(r, 500));
      }

      if (ready) {
        console.log("[Mobile] 📱 Metro is ready. Opening app on device...");
      } else {
        console.warn("[Mobile] ⚠️ Metro bundler readiness check timed out. Attempting launch anyway...");
      }

      try {
        const launchExpo = spawn([adb, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "exp://127.0.0.1:8081", "host.exp.exponent"]);
        await launchExpo.exited;
      } catch {
        try {
          const launchCustom = spawn([adb, "shell", "am", "start", "-n", "com.technerds.blinkyremote/.MainActivity"]);
          await launchCustom.exited;
        } catch {}
      }
    })();

    return mobileProc;
  } catch (err: any) {
    console.warn(`[Mobile] USB mobile check encountered an error: ${err?.message || err}`);
    return null;
  }
}

await ensureSearXNGStarted();


let mobileProcess: Subprocess | null = null;
if (!noMobile) {
  mobileProcess = await checkAndStartMobileIfUsbConnected();
}

if (process.platform === "win32" && !existsSync("common/python_runtime/Python313")) {
  console.log("Preparing Python runtime...");
  const prepProc = spawn(["bun", "common/scripts/prepare-python-runtime.mjs"], {
    stdout: "inherit",
    stderr: "inherit",
  });
  const exitCode = await prepProc.exited;
  if (exitCode !== 0) {
    console.error("Warning: Python runtime preparation returned non-zero exit code.");
  }
}

const killWindowsProcessTree = (pid?: number) => {
  if (process.platform !== "win32") return;
  try {
    if (pid) {
      Bun.spawnSync(["taskkill", "/F", "/T", "/PID", String(pid)]);
    }
    Bun.spawnSync(["taskkill", "/F", "/T", "/IM", "blinky.exe"]);
    Bun.spawnSync(["powershell", "-NoProfile", "-Command", "Get-NetTCPConnection -LocalPort 5173,9001 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"]);
  } catch {}
};

const restoreWindowsSystemCursor = () => {
  if (process.platform === "win32") {
    try {
      const { dlopen, FFIType } = require("bun:ffi");
      const user32 = dlopen("user32.dll", {
        SystemParametersInfoW: {
          args: [FFIType.u32, FFIType.u32, FFIType.ptr, FFIType.u32],
          returns: FFIType.bool,
        },
      });
      user32.symbols.SystemParametersInfoW(0x0057 /* SPI_SETCURSORS */, 0, null, 0);
    } catch {
      try {
        Bun.spawnSync(["powershell", "-NoProfile", "-Command", "rundll32.exe user32.dll,UpdatePerUserSystemParameters 1, True"]);
      } catch {}
    }
  }
};

// Pre-flight cleanup to ensure port 5173 and 9001 are free and native cursor is active
restoreWindowsSystemCursor();
killWindowsProcessTree();

console.log("Starting Tauri Development Server...");
const tauriDev = spawn(["bun", "tauri", "dev"], {
  stdout: "inherit",
  stderr: "inherit",
  stdin: "ignore",
});

const cleanup = () => {
  restoreWindowsSystemCursor();
  if (mobileProcess) {
    try {
      mobileProcess.kill();
    } catch {}
  }
  try {
    tauriDev.kill();
  } catch {}

  killWindowsProcessTree(tauriDev.pid);
  restoreWindowsSystemCursor();
};


const adbCmd = getAdbPath();
if (process.stdin.isTTY) {
  try {
    process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.setEncoding("utf8");

    process.stdin.on("data", (key: string) => {
      // Handle Ctrl+C
      if (key === "\u0003") {
        console.log("\n[Blinky] 🛑 Shutting down dev servers and closing Blinky PC app...");
        cleanup();
        process.exit(0);
      }

      // Forward keystroke to Metro process stdin
      if (mobileProcess && mobileProcess.stdin) {
        try {
          (mobileProcess.stdin as any).write(key);
        } catch {}
      }

      // Handle direct adb mobile actions
      const k = key.toLowerCase();
      if (adbCmd) {
        if (k === "r") {
          console.log("\n[Mobile] 🔄 Reloading app on connected device...");
          spawn([adbCmd, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "exp://127.0.0.1:8081", "host.exp.exponent"]);
        } else if (k === "m") {
          console.log("\n[Mobile] 📱 Toggling developer menu on device...");
          spawn([adbCmd, "shell", "input", "keyevent", "82"]);
        } else if (k === "a") {
          console.log("\n[Mobile] 📱 Opening Expo Go on device...");
          spawn([adbCmd, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "exp://127.0.0.1:8081", "host.exp.exponent"]);
        }
      }
    });
  } catch {}
}

process.on("SIGINT", () => {
  cleanup();
  process.exit(0);
});
process.on("SIGTERM", () => {
  cleanup();
  process.exit(0);
});
process.on("exit", cleanup);

// Wait for Tauri dev process to exit
const exitCode = await tauriDev.exited;
cleanup();
process.exit(exitCode);
