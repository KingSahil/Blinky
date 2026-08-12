import { spawn } from "bun";
import { existsSync } from "fs";

const args = Bun.argv.slice(2);
const noDocker = args.includes("--no-docker");

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
  stdin: "inherit",
});

// Wait for Tauri dev process to exit
const exitCode = await tauriDev.exited;
process.exit(exitCode);
