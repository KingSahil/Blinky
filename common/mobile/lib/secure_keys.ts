import AsyncStorage from '@react-native-async-storage/async-storage';

export const SECURE_KEYS_STORAGE_KEY = '@blinky_mobile_api_keys';

export interface SyncedApiKeys {
  groq_key?: string;
  openai_key?: string;
  gemini_key?: string;
  deepseek_key?: string;
}

/**
 * Persists API keys transferred from PC Blinky into mobile storage.
 */
export async function saveSyncedApiKeys(keys: SyncedApiKeys): Promise<void> {
  try {
    const payload = JSON.stringify(keys);
    await AsyncStorage.setItem(SECURE_KEYS_STORAGE_KEY, payload);
    console.log('[SecureKeys] API Keys successfully synced and saved on mobile.');
  } catch (err) {
    console.warn('[SecureKeys] Error saving API keys on mobile:', err);
  }
}

/**
 * Retrieves the stored API keys for standalone mobile execution (PC offline).
 */
export async function getSyncedApiKeys(): Promise<SyncedApiKeys> {
  try {
    const data = await AsyncStorage.getItem(SECURE_KEYS_STORAGE_KEY);
    if (!data) return {};
    return JSON.parse(data) as SyncedApiKeys;
  } catch (err) {
    console.warn('[SecureKeys] Error loading API keys on mobile:', err);
    return {};
  }
}

/**
 * Checks if at least one valid cloud API key is available for offline mobile queries.
 */
export async function hasSyncedApiKeys(): Promise<boolean> {
  const keys = await getSyncedApiKeys();
  return Boolean(keys.groq_key || keys.openai_key || keys.gemini_key || keys.deepseek_key);
}
