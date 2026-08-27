import { invoke } from '@tauri-apps/api/core';
import type { TutorConversationMessage, TutorProgress, TutorResult } from './types';

export async function runTutor(
  question: string,
  previousQuestion?: string,
  progress?: TutorProgress,
  conversationHistory?: TutorConversationMessage[],
  webSearchEnabled?: boolean,
  agentMode?: boolean,
): Promise<TutorResult> {
  return invoke<TutorResult>('run_tutor', {
    request: {
      question,
      previous_question: previousQuestion,
      progress,
      conversation_history: conversationHistory,
      web_search_enabled: webSearchEnabled,
      agent_mode: agentMode,
    },
  });
}

export async function runAgentQuery(query: string): Promise<TutorResult> {
  return invoke<TutorResult>('run_agent_query', {
    request: {
      query,
    },
  });
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
  deepseek_api_key: string;
  custom_url: string;
  custom_model: string;
  custom_api_key: string;
}

export async function getSettings(): Promise<BlinkySettings> {
  return invoke<BlinkySettings>('get_settings');
}

export async function saveSettings(
  provider: string,
  shortcut: string,
  sarvamApiKey: string,
  groqApiKey: string,
  deepseekApiKey: string,
  customUrl: string = '',
  customModel: string = '',
  customApiKey: string = ''
): Promise<void> {
  return invoke('save_settings', { provider, shortcut, sarvamApiKey, groqApiKey, deepseekApiKey, customUrl, customModel, customApiKey });
}

export async function confirmRecipeSave(recipeId: string, save: boolean): Promise<void> {
  return invoke('confirm_recipe_save', { recipeId, save });
}

export async function openUrl(url: string): Promise<void> {
  return invoke('open_url', { url });
}

export async function clickScreenPoint(x: number, y: number): Promise<void> {
  return invoke('click_screen_point', { x, y });
}

export async function scrollAtPoint(x: number, y: number, direction: 'down' | 'up', amount: number = 3): Promise<void> {
  return invoke('scroll_at_point', { x, y, direction, amount });
}

export async function typeText(text: string, pressEnter: boolean): Promise<void> {
  return invoke('type_text', { text, pressEnter });
}

export async function logDebugMessage(message: string): Promise<void> {
  return invoke('log_debug_message', { message });
}

export async function pauseWakeWord(): Promise<void> {
  return invoke('pause_wake_word');
}

export async function resumeWakeWord(): Promise<void> {
  return invoke('resume_wake_word');
}

export async function setAgentCursorVisibility(visible: boolean): Promise<void> {
  if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
    return invoke('set_agent_cursor_visibility', { visible });
  }
}

export async function getCursorPosition(): Promise<{ x: number; y: number }> {
  if (typeof window !== 'undefined' && (window as any).__TAURI_INTERNALS__) {
    try {
      const [x, y] = await invoke<[number, number]>('get_cursor_position');
      return { x, y };
    } catch {
      return { x: 0, y: 0 };
    }
  }
  return { x: 0, y: 0 };
}

