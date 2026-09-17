import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
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

export interface SecureTransportInfo {
  mode: 'development' | 'release';
  desktop_url: string;
  certificate_pin: string | null;
}

export interface SecureSocketEvent {
  socket_id: string;
  kind: 'open' | 'text' | 'binary' | 'close' | 'error';
  data?: string;
  message?: string;
}

export function getSecureTransportInfo(): Promise<SecureTransportInfo> {
  return invoke<SecureTransportInfo>('get_secure_transport_info');
}

export function connectSecureSocket(
  socketId: string,
  url: string,
  expectedPin?: string | null,
): Promise<void> {
  return invoke('secure_socket_connect', {
    socketId,
    url,
    expectedPin: expectedPin ?? null,
  });
}

export function sendSecureSocketText(socketId: string, data: string): Promise<void> {
  return invoke('secure_socket_send', { socketId, kind: 'text', data });
}

export function sendSecureSocketBinary(socketId: string, data: ArrayBuffer): Promise<void> {
  const bytes = new Uint8Array(data);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return invoke('secure_socket_send', {
    socketId,
    kind: 'binary',
    data: btoa(binary),
  });
}

export function closeSecureSocket(socketId: string): Promise<void> {
  return invoke('secure_socket_close', { socketId });
}

export async function listenForSecureSocketEvents(
  handler: (event: SecureSocketEvent) => void,
): Promise<UnlistenFn> {
  const subscriptions: UnlistenFn[] = [];
  const cleanup = () => subscriptions.splice(0).forEach((unlisten) => unlisten());
  try {
    for (const name of ['open', 'message', 'close', 'error']) {
      subscriptions.push(await listen<SecureSocketEvent>(
        `blinky://secure-socket-${name}`, (event) => handler(event.payload),
      ));
    }
    return cleanup;
  } catch (error) {
    cleanup();
    throw error;
  }
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

/**
 * Click the element behind a screen point, preferring the background path.
 *
 * `label` is the matched target text. cua-driver uses it together with the point
 * to pick the control to invoke through UIA, which keeps the real pointer still
 * and does not require the window to be unobstructed. Falls back to the
 * point-only click on surfaces with no element tree.
 */
export async function clickElement(x: number, y: number, label: string): Promise<void> {
  return invoke('click_element', { x, y, label });
}

export async function scrollAtPoint(x: number, y: number, direction: 'down' | 'up', amount: number = 3): Promise<void> {
  return invoke('scroll_at_point', { x, y, direction, amount });
}

/**
 * Type into the window behind a screen point.
 *
 * `x`/`y` are required: the background path needs them to address the target window,
 * and cua-driver refuses a `type_text` that names no target.
 */
export async function typeText(x: number, y: number, text: string, pressEnter: boolean): Promise<void> {
  return invoke('type_text', { x, y, text, pressEnter });
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
