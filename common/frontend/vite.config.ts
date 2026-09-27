import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import * as dotenv from 'dotenv';
import * as path from 'path';

dotenv.config({ path: path.resolve(__dirname, '../../.env') });

const port = process.env.PORT ? parseInt(process.env.PORT, 10) : 5173;
const aaiKey = process.env.ASSEMBLY_AI_API_KEY || process.env.ASSEMBLYAI_API_KEY || '';

export default defineConfig({
  root: 'common/frontend',
  envDir: '../../',
  define: {
    'import.meta.env.VITE_ASSEMBLY_AI_API_KEY': JSON.stringify(aaiKey),
  },
  plugins: [react()],
  clearScreen: false,
  server: {
    port,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});

