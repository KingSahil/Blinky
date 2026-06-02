import { invoke } from '@tauri-apps/api/core';
import type { TutorProgress, TutorResult } from './types';

export async function runTutor(question: string, previousQuestion?: string, progress?: TutorProgress): Promise<TutorResult> {
  return invoke<TutorResult>('run_tutor', { request: { question, previous_question: previousQuestion, progress } });
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

export async function resizeCommandWindow(height: number): Promise<void> {
  return invoke('resize_command_window', { height });
}

export async function resizeAndMoveCommandWindow(x: number, y: number, width: number, height: number): Promise<void> {
  return invoke('resize_and_move_command_window', { x, y, width, height });
}

export interface BlinkySettings {
  provider: string;
  shortcut: string;
  sarvam_api_key: string;
  groq_api_key: string;
}

export async function getSettings(): Promise<BlinkySettings> {
  return invoke<BlinkySettings>('get_settings');
}

export async function saveSettings(provider: string, shortcut: string, sarvamApiKey: string, groqApiKey: string): Promise<void> {
  return invoke('save_settings', { provider, shortcut, sarvamApiKey, groqApiKey });
}

