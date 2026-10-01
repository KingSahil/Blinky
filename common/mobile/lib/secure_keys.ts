import AsyncStorage from '@react-native-async-storage/async-storage';

let SecureStore: any = null;
try {
  SecureStore = require('expo-secure-store');
} catch (_) {}

export const SECURE_KEYS_STORAGE_KEY = 'blinky_mobile_api_keys_v2';
export const ASYNC_KEYS_FALLBACK_KEY = '@blinky_mobile_api_keys';

export interface SyncedApiKeys {
  groq_key?: string;
  openai_key?: string;
  gemini_key?: string;
  deepseek_key?: string;
}

/**
 * Persists API keys transferred from PC Blinky into hardware Android KeyStore via SecureStore.
 */
export async function saveSyncedApiKeys(keys: SyncedApiKeys): Promise<void> {
  try {
    const payload = JSON.stringify(keys);
    const isSecureAvailable = SecureStore ? await SecureStore.isAvailableAsync().catch(() => false) : false;
    
    if (isSecureAvailable) {
      await SecureStore.setItemAsync(SECURE_KEYS_STORAGE_KEY, payload, {
        keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK,
      });
      // Purge any lingering plaintext fallback copy once hardware keystore succeeds
      await AsyncStorage.removeItem(ASYNC_KEYS_FALLBACK_KEY).catch(() => {});
      console.log('[SecureKeys] API Keys securely encrypted in Android KeyStore.');
    } else {
      await AsyncStorage.setItem(ASYNC_KEYS_FALLBACK_KEY, payload);
      console.log('[SecureKeys] API Keys saved to AsyncStorage fallback.');
    }
  } catch (err) {
    console.warn('[SecureKeys] Error saving encrypted API keys on mobile:', err);
    try {
      await AsyncStorage.setItem(ASYNC_KEYS_FALLBACK_KEY, JSON.stringify(keys));
    } catch (_) {}
  }
}

/**
 * Retrieves the stored encrypted API keys for standalone mobile execution (PC offline).
 */
export async function getSyncedApiKeys(): Promise<SyncedApiKeys> {
  try {
    const isSecureAvailable = SecureStore ? await SecureStore.isAvailableAsync().catch(() => false) : false;
    let data: string | null = null;

    if (isSecureAvailable) {
      data = await SecureStore.getItemAsync(SECURE_KEYS_STORAGE_KEY).catch(() => null);
    }

    if (!data) {
      data = await AsyncStorage.getItem(ASYNC_KEYS_FALLBACK_KEY);
    }

    if (!data) return {};
    return JSON.parse(data) as SyncedApiKeys;
  } catch (err) {
    console.warn('[SecureKeys] Error loading encrypted API keys on mobile:', err);
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

/**
 * Completely purges synced API keys from both SecureStore and AsyncStorage on disconnect/logout.
 */
export async function clearSyncedApiKeys(): Promise<void> {
  try {
    const isSecureAvailable = SecureStore ? await SecureStore.isAvailableAsync().catch(() => false) : false;
    if (isSecureAvailable) {
      await SecureStore.deleteItemAsync(SECURE_KEYS_STORAGE_KEY).catch(() => {});
    }
    await AsyncStorage.removeItem(ASYNC_KEYS_FALLBACK_KEY).catch(() => {});
    console.log('[SecureKeys] Synced API keys successfully purged from mobile storage.');
  } catch (err) {
    console.warn('[SecureKeys] Error clearing synced API keys:', err);
  }
}
