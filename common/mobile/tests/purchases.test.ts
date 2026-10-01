import { beforeEach, describe, expect, mock, test } from 'bun:test';

// In-memory mock for AsyncStorage
const storage = new Map<string, string>();

mock.module('@react-native-async-storage/async-storage', () => ({
  default: {
    getItem: async (key: string) => storage.get(key) ?? null,
    setItem: async (key: string, value: string) => {
      storage.set(key, value);
    },
    removeItem: async (key: string) => {
      storage.delete(key);
    },
    clear: async () => {
      storage.clear();
    },
  },
}));

mock.module('react-native', () => ({
  Platform: {
    OS: 'android',
  },
}));

mock.module('react-native-purchases', () => ({
  default: {
    setLogLevel: async () => {},
    configure: () => {},
    addCustomerInfoUpdateListener: () => {},
    getCustomerInfo: async () => ({
      entitlements: { active: {} },
    }),
    restorePurchases: async () => ({
      entitlements: { active: {} },
    }),
  },
  LOG_LEVEL: { DEBUG: 'DEBUG', ERROR: 'ERROR' },
}));

mock.module('react-native-purchases-ui', () => ({
  default: {
    presentPaywallIfNeeded: async () => 'NOT_PRESENTED',
    presentPaywall: async () => 'PURCHASED',
  },
  PAYWALL_RESULT: {
    PURCHASED: 'PURCHASED',
    RESTORED: 'RESTORED',
    CANCELLED: 'CANCELLED',
    NOT_PRESENTED: 'NOT_PRESENTED',
    ERROR: 'ERROR',
  },
}));

const {
  getAllowedPromoCodes,
  redeemPromoCode,
  isPromoUnlocked,
  getRedeemedPromoCode,
  hasPcAccess,
  addPcAccessListener,
  resetPromoUnlockForDebug,
  restorePurchases,
} = await import('../lib/purchases');

describe('Monetization & Promo Code Engine (lib/purchases.ts)', () => {
  beforeEach(async () => {
    await resetPromoUnlockForDebug();
    storage.clear();
  });

  test('getAllowedPromoCodes returns default fallback codes when env is standard', () => {
    const codes = getAllowedPromoCodes();
    expect(codes).toContain('SHIPATHON');
    expect(codes).toContain('BLINKYVIP');
    expect(codes).toContain('EARLYBIRD');
  });

  test('initially user does not have PC access without a redeemed code or subscription', async () => {
    const access = await hasPcAccess();
    expect(access).toBe(false);

    const promoStatus = await isPromoUnlocked();
    expect(promoStatus).toBe(false);

    const redeemed = await getRedeemedPromoCode();
    expect(redeemed).toBeNull();
  });

  test('rejects empty or whitespace promo codes', async () => {
    const resEmpty = await redeemPromoCode('');
    expect(resEmpty.success).toBe(false);
    expect(resEmpty.message).toContain('Please enter a valid promo code');

    const resWhitespace = await redeemPromoCode('   ');
    expect(resWhitespace.success).toBe(false);
  });

  test('rejects invalid promo code without unlocking', async () => {
    const result = await redeemPromoCode('NOT_A_REAL_CODE_999');
    expect(result.success).toBe(false);
    expect(result.message).toContain('Invalid promo code');

    const access = await hasPcAccess();
    expect(access).toBe(false);
  });

  test('successfully redeems valid promo code with case and whitespace insensitivity', async () => {
    // Test lowercase and leading/trailing whitespace
    const result = await redeemPromoCode('   shipathon   ');
    expect(result.success).toBe(true);
    expect(result.message).toContain('successfully applied');

    // Verify unlocked state
    const access = await hasPcAccess();
    expect(access).toBe(true);

    const isUnlocked = await isPromoUnlocked();
    expect(isUnlocked).toBe(true);

    const redeemedCode = await getRedeemedPromoCode();
    expect(redeemedCode).toBe('SHIPATHON');
  });

  test('notifies listeners when promo code is redeemed and access status changes', async () => {
    let listenerCalledWith = false;
    const unsubscribe = addPcAccessListener((hasAccess) => {
      listenerCalledWith = hasAccess;
    });

    // Redeem code
    await redeemPromoCode('BLINKYVIP');
    expect(listenerCalledWith).toBe(true);

    // Reset via debug helper
    await resetPromoUnlockForDebug();
    expect(listenerCalledWith).toBe(false);

    // Cleanup listener
    unsubscribe();
  });

  test('restorePurchases reports unlock if promo code already applied', async () => {
    await redeemPromoCode('EARLYBIRD');
    const restoreRes = await restorePurchases();
    expect(restoreRes.success).toBe(true);
    expect(restoreRes.hasAccess).toBe(true);
    expect(restoreRes.message).toContain('already unlocked via promo code');
  });

  test('resetPromoUnlockForDebug clears persisted promo status', async () => {
    await redeemPromoCode('SHIPATHON');
    expect(await hasPcAccess()).toBe(true);

    await resetPromoUnlockForDebug();
    expect(await hasPcAccess()).toBe(false);
    expect(await isPromoUnlocked()).toBe(false);
    expect(await getRedeemedPromoCode()).toBeNull();
  });
});
