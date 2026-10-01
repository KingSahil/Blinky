import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Purchases, { CustomerInfo, LOG_LEVEL } from 'react-native-purchases';
import RevenueCatUI, { PAYWALL_RESULT } from 'react-native-purchases-ui';

export const PROMO_UNLOCKED_STORAGE_KEY = '@blinky_pc_promo_unlocked';
export const PROMO_CODE_STORAGE_KEY = '@blinky_pc_redeemed_code';

export const PC_ENTITLEMENT_ID =
  process.env.EXPO_PUBLIC_REVENUECAT_ENTITLEMENT_ID || 'pc_access';

const DEFAULT_PROMO_CODES = ['SHIPATHON', 'BLINKYVIP', 'EARLYBIRD'];

/**
 * Returns the list of valid promo codes parsed from the environment variable or defaults.
 */
export function getAllowedPromoCodes(): string[] {
  const envCodes = process.env.EXPO_PUBLIC_PROMO_CODES;
  if (!envCodes) {
    return DEFAULT_PROMO_CODES;
  }
  const parsed = envCodes
    .split(',')
    .map((c: string) => c.trim().toUpperCase())
    .filter(Boolean);
  return parsed.length > 0 ? parsed : DEFAULT_PROMO_CODES;
}

let isConfigured = false;
const pcAccessListeners: Set<(hasAccess: boolean) => void> = new Set();

/**
 * Notify all subscribed listeners when PC access state changes.
 */
function notifyListeners(hasAccess: boolean) {
  pcAccessListeners.forEach((listener) => {
    try {
      listener(hasAccess);
    } catch (err) {
      console.warn('[Purchases] Error in PC access listener:', err);
    }
  });
}

/**
 * Subscribes a callback to changes in PC access state.
 * Returns an unsubscribe cleanup function.
 */
export function addPcAccessListener(listener: (hasAccess: boolean) => void): () => void {
  pcAccessListeners.add(listener);
  return () => {
    pcAccessListeners.delete(listener);
  };
}

/**
 * Safely initializes RevenueCat Purchases SDK on native platforms.
 * Handles missing keys and unsupported environments gracefully.
 */
export async function initializePurchases(): Promise<boolean> {
  if (isConfigured) return true;

  if (Platform.OS === 'web') {
    console.log('[Purchases] Running on web, RevenueCat native SDK skipped.');
    return false;
  }

  const apiKey =
    Platform.OS === 'android'
      ? process.env.EXPO_PUBLIC_REVENUECAT_GOOGLE_KEY
      : process.env.EXPO_PUBLIC_REVENUECAT_APPLE_KEY;

  if (!apiKey || apiKey === 'goog_your_public_api_key_here') {
    console.warn(
      '[Purchases] No valid RevenueCat API key configured in environment. In-app purchases disabled, promo code bypass remains active.'
    );
    return false;
  }

  try {
    if (__DEV__) {
      await Purchases.setLogLevel(LOG_LEVEL.DEBUG);
    }

    Purchases.configure({ apiKey });
    isConfigured = true;

    // Listen for real-time customer info changes (renewals, external purchases, cancels)
    Purchases.addCustomerInfoUpdateListener(async (info: CustomerInfo) => {
      const active = info.entitlements.active[PC_ENTITLEMENT_ID] !== undefined;
      const promoActive = await isPromoUnlocked();
      notifyListeners(active || promoActive);
    });

    console.log('[Purchases] RevenueCat initialized successfully.');
    return true;
  } catch (error) {
    console.warn('[Purchases] Failed to initialize RevenueCat (likely Expo Go or missing native link):', error);
    isConfigured = false;
    return false;
  }
}

/**
 * Checks whether the user has previously redeemed a valid promo code.
 */
export async function isPromoUnlocked(): Promise<boolean> {
  try {
    const val = await AsyncStorage.getItem(PROMO_UNLOCKED_STORAGE_KEY);
    return val === 'true';
  } catch {
    return false;
  }
}

/**
 * Returns the currently redeemed promo code, if any.
 */
export async function getRedeemedPromoCode(): Promise<string | null> {
  try {
    return await AsyncStorage.getItem(PROMO_CODE_STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Unified entitlement checker.
 * Returns true if the user has an active RevenueCat entitlement OR a redeemed promo code.
 */
export async function hasPcAccess(): Promise<boolean> {
  // 1. Check local promo code unlock first (fastest)
  const promo = await isPromoUnlocked();
  if (promo) return true;

  // 2. Check RevenueCat active entitlements if SDK is configured
  if (isConfigured) {
    try {
      const customerInfo = await Purchases.getCustomerInfo();
      const hasEntitlement =
        customerInfo.entitlements.active[PC_ENTITLEMENT_ID] !== undefined;
      return hasEntitlement;
    } catch (e) {
      console.warn('[Purchases] Error checking customer info:', e);
    }
  }

  return false;
}

export interface PromoRedemptionResult {
  success: boolean;
  message: string;
}

/**
 * Validates and redeems a promotional voucher code.
 * Persists the unlock locally and notifies all active listeners immediately.
 */
export async function redeemPromoCode(code: string): Promise<PromoRedemptionResult> {
  const cleanCode = (code || '').trim().toUpperCase();

  if (!cleanCode) {
    return {
      success: false,
      message: 'Please enter a valid promo code.',
    };
  }

  const allowedCodes = getAllowedPromoCodes();
  const isMatch = allowedCodes.includes(cleanCode);

  if (!isMatch) {
    return {
      success: false,
      message: 'Invalid promo code. Please check and try again.',
    };
  }

  try {
    await AsyncStorage.setItem(PROMO_UNLOCKED_STORAGE_KEY, 'true');
    await AsyncStorage.setItem(PROMO_CODE_STORAGE_KEY, cleanCode);
    notifyListeners(true);
    return {
      success: true,
      message: `Promo code "${cleanCode}" successfully applied! PC Controls are now unlocked.`,
    };
  } catch (err) {
    console.error('[Purchases] Error persisting promo code:', err);
    return {
      success: false,
      message: 'Failed to save promo code status. Please try again.',
    };
  }
}

/**
 * Restores past purchases from Google Play / App Store.
 */
export async function restorePurchases(): Promise<{
  success: boolean;
  hasAccess: boolean;
  message: string;
}> {
  // If already unlocked via promo code
  if (await isPromoUnlocked()) {
    return {
      success: true,
      hasAccess: true,
      message: 'PC Controls are already unlocked via promo code.',
    };
  }

  if (!isConfigured) {
    return {
      success: false,
      hasAccess: false,
      message:
        'Store purchase restoration is not available in this environment. If you have a promo code, please redeem it directly.',
    };
  }

  try {
    const customerInfo = await Purchases.restorePurchases();
    const hasAccess =
      customerInfo.entitlements.active[PC_ENTITLEMENT_ID] !== undefined;
    notifyListeners(hasAccess);

    if (hasAccess) {
      return {
        success: true,
        hasAccess: true,
        message: 'Your past purchase was restored successfully! PC Controls are unlocked.',
      };
    } else {
      return {
        success: true,
        hasAccess: false,
        message: 'No active subscription or lifetime purchase found for this store account.',
      };
    }
  } catch (error: any) {
    console.error('[Purchases] Restore error:', error);
    return {
      success: false,
      hasAccess: false,
      message: error?.message || 'Failed to restore purchases. Please try again later.',
    };
  }
}

/**
 * Presents the RevenueCat Paywall UI if the user does not have PC access.
 */
export async function presentPcPaywall(): Promise<{
  success: boolean;
  result?: string;
  error?: string;
}> {
  // Check if already entitled
  if (await hasPcAccess()) {
    return { success: true, result: 'ALREADY_UNLOCKED' };
  }

  if (!isConfigured) {
    return {
      success: false,
      error: 'In-app purchases are not configured. Please use a promo code to unlock.',
    };
  }

  try {
    const paywallResult = await RevenueCatUI.presentPaywallIfNeeded({
      requiredEntitlementIdentifier: PC_ENTITLEMENT_ID,
      displayCloseButton: true,
    });

    const accessNow = await hasPcAccess();
    notifyListeners(accessNow);

    return {
      success:
        paywallResult === PAYWALL_RESULT.PURCHASED ||
        paywallResult === PAYWALL_RESULT.RESTORED,
      result: paywallResult,
    };
  } catch (error: any) {
    console.error('[Purchases] Present paywall error:', error);
    return {
      success: false,
      error: error?.message || 'Could not display paywall.',
    };
  }
}

/**
 * Debug utility to reset local promo unlocks for testing paywall behavior.
 */
export async function resetPromoUnlockForDebug(): Promise<void> {
  try {
    await AsyncStorage.removeItem(PROMO_UNLOCKED_STORAGE_KEY);
    await AsyncStorage.removeItem(PROMO_CODE_STORAGE_KEY);
    const access = await hasPcAccess();
    notifyListeners(access);
    console.log('[Purchases] Reset local promo unlock. Current access:', access);
  } catch (err) {
    console.error('[Purchases] Failed to reset promo unlock:', err);
  }
}
