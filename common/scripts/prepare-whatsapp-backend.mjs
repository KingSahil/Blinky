import { execSync } from 'child_process';
import { existsSync, writeFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const scriptPath = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(scriptPath), '..', '..');
const backendDir = path.join(repoRoot, 'common', 'whatsapp_backend');

const packageJsonPath = path.join(backendDir, 'package.json');
if (!existsSync(packageJsonPath)) {
  const packageJsonContent = {
    name: "blinky-whatsapp-backend",
    version: "0.1.0",
    private: true,
    type: "module",
    dependencies: {
      "axios": "^1.7.9",
      "cors": "^2.8.6",
      "dotenv": "^17.3.1",
      "express": "^5.2.1",
      "groq-sdk": "^0.37.0",
      "qrcode-terminal": "^0.12.0",
      "socket.io": "^4.8.3",
      "whatsapp-web.js": "^1.26.0"
    }
  };
  writeFileSync(packageJsonPath, JSON.stringify(packageJsonContent, null, 2), 'utf8');
  console.log('Created package.json for whatsapp_backend');
}

console.log('Installing WhatsApp backend dependencies...');
try {
  execSync('bun install --production', {
    cwd: backendDir,
    stdio: 'inherit',
    env: {
      ...process.env,
      PUPPETEER_SKIP_DOWNLOAD: 'true',
      PUPPETEER_SKIP_CHROMIUM_DOWNLOAD: 'true'
    }
  });
  console.log('WhatsApp backend dependencies installed successfully.');
} catch (err) {
  console.error('Failed to install WhatsApp backend dependencies using Bun, trying npm...', err);
  try {
    execSync('npm install --omit=dev', {
      cwd: backendDir,
      stdio: 'inherit',
      env: {
        ...process.env,
        PUPPETEER_SKIP_DOWNLOAD: 'true',
        PUPPETEER_SKIP_CHROMIUM_DOWNLOAD: 'true'
      }
    });
    console.log('WhatsApp backend dependencies installed successfully using npm.');
  } catch (npmErr) {
    console.error('Failed to install WhatsApp backend dependencies using npm:', npmErr);
    process.exit(1);
  }
}
