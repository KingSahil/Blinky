import { invoke } from '@tauri-apps/api/core';
import type { TutorResult } from './types';

export async function runTutor(question: string): Promise<TutorResult> {
  return invoke<TutorResult>('run_tutor', { request: { question } });
}

export async function showOverlay(): Promise<void> {
  return invoke('show_overlay');
}

export async function hideOverlay(): Promise<void> {
  return invoke('hide_overlay');
}

export async function showCommandBar(): Promise<void> {
  return invoke('show_command_bar');
}
