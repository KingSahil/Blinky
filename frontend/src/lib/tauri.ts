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

export async function resizeCommandWindow(height: number): Promise<void> {
  return invoke('resize_command_window', { height });
}

export async function resizeAndMoveCommandWindow(x: number, y: number, width: number, height: number): Promise<void> {
  return invoke('resize_and_move_command_window', { x, y, width, height });
}

export interface ClickySettings {
  provider: string;
  shortcut: string;
}

export async function getSettings(): Promise<ClickySettings> {
  return invoke<ClickySettings>('get_settings');
}

export async function saveSettings(provider: string, shortcut: string): Promise<void> {
  return invoke('save_settings', { provider, shortcut });
}

