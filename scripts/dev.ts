import { spawn, type Subprocess } from "bun";
import { existsSync } from "fs";

const args = Bun.argv.slice(2);
const noDocker = args.includes("--no-docker");
const noMobile = args.includes("--no-mobile");

function getDockerPath(): string {
  if (process.platform !== "win32") {
    return "docker";
  }
  const defaultPath = "C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe";
  try {
    // Test if 'docker' is in PATH. spawn throws synchronously if the executable is not found
    const proc = spawn(["docker", "--version"]);
    proc.kill();
    return "docker";
  } catch (err) {
    if (existsSync(defaultPath)) {
      console.log(`Docker command not found in PATH. Using default installation fallback: ${defaultPath}`);
      return defaultPath;
    }
  }
  return "docker";
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
    const output = await new Response(proc.stdout).text();
    await proc.exited;

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
    await rev1.exited;
    const rev2 = spawn([adb, "reverse", "tcp:8081", "tcp:8081"]);
    await rev2.exited;

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

    // Attempt to launch on device (Expo Go or custom package)
    setTimeout(async () => {
      try {
        const launchExpo = spawn([adb, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", "exp://127.0.0.1:8081", "host.exp.exponent"]);
        await launchExpo.exited;
      } catch {
        try {
          const launchCustom = spawn([adb, "shell", "am", "start", "-n", "com.technerds.blinkyremote/.MainActivity"]);
          await launchCustom.exited;
        } catch {}
      }
    }, 1500);

    return mobileProc;
  } catch (err: any) {
    console.warn(`[Mobile] USB mobile check encountered an error: ${err?.message || err}`);
    return null;
  }
}

if (!noDocker) {
  console.log("Starting SearXNG via Docker Compose...");
  const dockerPath = getDockerPath();
  try {
    const dockerCompose = spawn([dockerPath, "compose", "-f", "common/docker-compose.yml", "up", "-d"], {
      stdout: "inherit",
      stderr: "inherit",
    });
    const exitCode = await dockerCompose.exited;
    if (exitCode !== 0) {
      console.error("Warning: Failed to start SearXNG via Docker Compose. Continuing anyway...");
    }
  } catch (err) {
    console.warn("Warning: Docker was not found or is not running. Skipping SearXNG (web search functionality will be disabled).");
  }
}

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

console.log("Starting Tauri Development Server...");
const tauriDev = spawn(["bun", "tauri", "dev"], {
  stdout: "inherit",
  stderr: "inherit",
  stdin: "ignore",
});

const cleanup = () => {
  if (mobileProcess) {
    try {
      mobileProcess.kill();
    } catch {}
  }
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
        cleanup();
        try { tauriDev.kill(); } catch {}
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

process.on("SIGINT", cleanup);
process.on("SIGTERM", cleanup);
process.on("exit", cleanup);

// Wait for Tauri dev process to exit
const exitCode = await tauriDev.exited;
cleanup();
process.exit(exitCode);
