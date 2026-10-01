# Blinky Mobile: Architecture Analysis, RevenueCat Verification & Android Distribution Guide

> **Scope:** Full-codebase analysis of Blinky with special focus on `common/mobile/`, verification of the RevenueCat monetization and promo-code architecture, store-independent distribution options, and instructions for porting the Expo mobile app into a standalone Android package (`.apk`).

---

## 1. Project Architecture & State Analysis

Blinky is a cross-platform AI desktop tutor, computer-use automation engine, and remote workstation companion. It is divided into three core pillars:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                             BLINKY ECOSYSTEM                               │
└────────────────────────────────────────────────────────────────────────────┘
      │
      ├─► 1. DESKTOP CORE (Tauri 2 + React 19 + Python Daemon)
      │     ├─ Rust Tauri Shell: System tray, overlay window, secure WebSocket gateway (:9001).
      │     ├─ Python AI Daemon: Local WinRT OCR, Ollama (gemma4:e4b), Groq (llama-3.3-70b-versatile).
      │     ├─ Voice Engine: Sarvam AI saaras:v3 (STT) + bulbul:v3 (TTS) with word-by-word sync.
      │     └─ Computer-Use Actuator: Background OS automation via cua-driver 0.28.1 (Hermes engine)
      │        and native SendInput/pywinauto fallbacks.
      │
      ├─► 2. MOBILE REMOTE COMPANION (common/mobile - Expo SDK 57 / React Native 0.86)
      │     ├─ WebSocket Client: Authenticated streaming with ?token= handshake and auto-discovery.
      │     ├─ Chat & Voice Interface: Real-time agent status, progress bars, audio recording (expo-audio).
      │     ├─ Remote PC Telemetry: Live CPU, RAM, battery, network status, Wake-on-LAN (react-native-wol).
      │     ├─ Remote File Browser: Browse, download, and send files to desktop agent (FilesScreen).
      │     └─ IDE Bridge: Antigravity IDE terminal session watcher and one-tap action approvals.
      │
      └─► 3. HARDWARE & WEB EXTENSIONS
            ├─ ESP32 Micro-Daemon: Ambient LED control and physical input triggers.
            └─ Base44 Landing Front: blinky.base44.app interactive showcase.
```

---

## 2. RevenueCat Implementation Verification

### Codebase Audit
The monetization implementation spans three main layers in `common/mobile/`:
1. **Core Service & State:** [`lib/purchases.ts`](file:///c:/Users/khann/Projects/Blinky/common/mobile/lib/purchases.ts)
2. **UI Screens & Modals:** [`components/SystemScreen.tsx`](file:///c:/Users/khann/Projects/Blinky/common/mobile/components/SystemScreen.tsx) & [`components/PromoCodeModal.tsx`](file:///c:/Users/khann/Projects/Blinky/common/mobile/components/PromoCodeModal.tsx)
3. **Application Integration & Navigation:** [`App.tsx`](file:///c:/Users/khann/Projects/Blinky/common/mobile/App.tsx) & [`components/BottomNavigation.tsx`](file:///c:/Users/khann/Projects/Blinky/common/mobile/components/BottomNavigation.tsx)

### Verification Checklist

| Component | Status | Details |
| :--- | :---: | :--- |
| **Dependencies** | ✅ Verified | `react-native-purchases@^10.10.2` & `react-native-purchases-ui@^10.10.2` installed in `package.json`. |
| **Expo Config Plugin** | ✅ Verified | Registered in `app.json` `plugins` array to automatically add `com.android.vending.BILLING` permissions during prebuild. |
| **Safe Startup Lifecycle** | ✅ Verified | `initializePurchases()` gracefully skips initialization on Web and non-configured environments without crashing. |
| **Entitlement Checking** | ✅ Verified | `hasPcAccess()` executes a unified check: local promo code bypass first, followed by active RevenueCat entitlement `pc_access`. |
| **Real-time Listener** | ✅ Verified | Subscribed to `Purchases.addCustomerInfoUpdateListener` to update React state across components on renewal or external purchases. |
| **Paywall & Restore** | ✅ Verified | `presentPcPaywall()` triggers `RevenueCatUI.presentPaywallIfNeeded`; `restorePurchases()` calls `Purchases.restorePurchases()`. |
| **Promo Code Engine** | ✅ Verified | Local fallback engine with `AsyncStorage` persistence, case-insensitive whitespace stripping, and instant UI listener dispatch. |
| **Automated Tests** | ✅ Verified | 8 tests in `common/mobile/tests/purchases.test.ts` passing with 26 assertions validated under Bun. |

### What Is Missing / Needs Configuration:
1. **Placeholder API Key in Environment:**
   In [`common/mobile/.env`](file:///c:/Users/khann/Projects/Blinky/common/mobile/.env):
   ```env
   EXPO_PUBLIC_REVENUECAT_GOOGLE_KEY=goog_your_public_api_key_here
   ```
   `initializePurchases()` explicitly checks for this dummy string and disables the native store purchase flow. A real public Google SDK key (`goog_...`) generated in the RevenueCat dashboard must be provided.
2. **Expo Go Execution Boundary:**
   `react-native-purchases` contains native Android binaries (Google Play Billing Library). **It does not run inside the pre-compiled Expo Go client**. When opened in standard Expo Go, `initializePurchases()` catches the native missing module error and safely drops back to promo code bypass mode. To test native store billing, a custom development build or standalone APK is mandatory.

---

## 3. Store-Independent Compatibility (No Google Play Publishing)

Google Play's Billing Library rejects purchase queries with `BILLING_UNAVAILABLE` unless the app is uploaded to at least the Google Play Console Internal Testing track with licensed tester accounts configured.

To distribute to users **without publishing to the Google Play Store**, use one of the two strategies below:

### Approach A: Built-in Promo Code Bypass (Active & Ready Now)
The app includes a fully offline voucher engine designed for testers, judges, and direct sideload users:
1. Configure promo codes in [`common/mobile/.env`](file:///c:/Users/khann/Projects/Blinky/common/mobile/.env):
   ```env
   EXPO_PUBLIC_PROMO_CODES=SHIPATHON,BLINKYVIP,EARLYBIRD,TESTER2026
   ```
2. When any user opens the app (either in Expo or standalone APK) and navigates to the locked **PC** tab, they tap **Redeem Promo Code**.
3. Entering any listed code writes `@blinky_pc_promo_unlocked = 'true'` into device storage and permanently unlocks telemetry and power actions without requiring Google Play services.

### Approach B: RevenueCat Web Billing (Stripe Checkout)
To collect real payments without publishing on Google Play:
1. Set up **RevenueCat Web Billing** in your RevenueCat Dashboard and connect a Stripe account.
2. In [`common/mobile/lib/purchases.ts`](file:///c:/Users/khann/Projects/Blinky/common/mobile/lib/purchases.ts), route the paywall action to an external browser checkout:
   ```ts
   import * as WebBrowser from 'expo-web-browser';

   export async function openWebCheckout(appUserId: string) {
     const checkoutUrl = `https://pay.revenuecat.com/YOUR_CAMPAIGN_ID?app_user_id=${appUserId}`;
     await WebBrowser.openBrowserAsync(checkoutUrl);
   }
   ```
3. Once the customer pays on the web, RevenueCat updates their entitlement. When the app resumes, `Purchases.getCustomerInfo()` restores the active `pc_access` entitlement automatically.

---

## 4. How to Port the Expo App to a Complete Standalone Android Package (APK)

### Method 1: Local Offline Build via Prebuild & Gradle (Direct APK)

Use this method to generate a native `android/` project and build the `.apk` on your local workstation without using cloud build credits.

#### Step 1: Prebuild the Native Android Project
From the repository root or `common/mobile/`:
```bash
cd common/mobile
npx expo prebuild --platform android --clean
```
*This parses `app.json`, `app.config.js`, and config plugins, then creates the native `common/mobile/android/` directory containing Gradle build files, AndroidManifest, and linked native modules (`react-native-purchases`, `expo-audio`, etc.).*

#### Step 2: Compile the APK using Gradle
```bash
cd android
./gradlew assembleRelease
```
*(Or use `./gradlew assembleDebug` if you want a debug-signed build without configuring keystores).*

#### Step 3: Install onto Device via ADB
The compiled APK will be output at:
`common/mobile/android/app/build/outputs/apk/release/app-release.apk`
*(or `debug/app-debug.apk`)*

Use the pre-configured script in `common/mobile/`:
```cmd
install_apk.bat
```
This script automatically detects `adb.exe`, locates the generated APK, and pushes it directly to a connected Android phone over USB.

---

### Method 2: Cloud Build via EAS CLI (Recommended for Easy Distribution)

Your [`eas.json`](file:///c:/Users/khann/Projects/Blinky/common/mobile/eas.json) is already pre-configured to output standalone APK files:

```json
{
  "build": {
    "preview": {
      "distribution": "internal",
      "android": {
        "buildType": "apk"
      }
    },
    "release": {
      "distribution": "internal",
      "android": {
        "buildType": "apk"
      },
      "env": {
        "EXPO_PUBLIC_BLINKY_TRANSPORT_MODE": "release"
      }
    }
  }
}
```

#### Commands to Trigger Build:
1. Ensure EAS CLI is installed:
   ```bash
   npm install -g eas-cli
   ```
2. Log in to Expo:
   ```bash
   eas login
   ```
3. Trigger the standalone Android APK build:
   ```bash
   cd common/mobile
   bun run build:release
   # or: eas build -p android --profile release
   ```
4. EAS builds the native package in the cloud and provides a direct `.apk` download URL and QR code for installation on any Android device.

---

## 5. Summary & Action Items

| Goal | Recommended Approach | Immediate Action |
| :--- | :--- | :--- |
| **Instant Testing** | Promo code bypass | Use `SHIPATHON` or `BLINKYVIP` in `PromoCodeModal`. |
| **Real Store Billing** | Google Play track + RevenueCat | Insert actual `goog_...` key in `.env`, upload AAB to Google Play Internal Testing. |
| **Real Web Billing (No Store)** | Stripe + RevenueCat Web Billing | Link Stripe to RevenueCat; open checkout link via `WebBrowser`. |
| **Standalone Package** | Local Gradle or EAS Build | Run `npx expo prebuild` + `./gradlew assembleRelease` or `eas build -p android --profile release`. |
