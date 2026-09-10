# WSS internal-release handoff

Review/build checks: 2026-09-08. Handoff and PR preparation: 2026-09-10. Branch: `release-wss-pinning`. Intended for team review and testing before merging; not a public-production release approval.

Integration warning: this branch was built from `f5c525a` with Expo SDK 54. On September 10, upstream main was `d4ca36d` and included an Expo SDK upgrade plus overlapping mobile/WebSocket changes. Review/test this branch independently; reconcile upstream changes and rerun validation before merge. The PR is a draft for that reason.

## Scope and behavior

The release desktop serves WSS on port 9001 using a persistent self-signed P-256 identity. Android verifies its SHA-256 public-key pin, then authenticates with the remote token. Non-loopback release connections fail closed when the token is absent. Development retains WS/Expo Go compatibility; release requires a custom native app, not experimental Expo Go support.

The review tightened mobile authentication deadlines, strict acknowledgement handling, visible rejection errors, stale-connection cleanup, and send gating. Android cancellation now prevents pending sockets from reviving, and failed sends are reported. Rust serializes initial identity creation and creates private files with Unix mode 0600. Optional desktop speech bridge setup now cleans up cancelled/failed listeners and queues STT audio until open. iOS delegate wiring and CocoaPods discovery were corrected, but iOS remains unbuilt and unverified.

Current desktop queries use Tauri IPC, and CommandBar STT/TTS uses direct Sarvam HTTPS. The optional native WSS speech classes are not instantiated by CommandBar. Do not describe the current desktop speech UI as tested through WSS. Mobile-to-PC commands and queries are the primary release WSS path.

## Build and pair

From the repository root, build the desktop with `bun run build:release`. For an internal Linux executable without the checkout's missing Windows bundle resources:

```bash
TAURI_CONFIG='{"bundle":{"resources":[]}}' bun run build:release --no-bundle
```

Output: `common/src-tauri/target/release/blinky`. This is not a packaged Linux installer. Runtime Python/services still need the source-checkout dependencies. Configure a strong `BLINKY_REMOTE_TOKEN` in the ignored environment configuration or launch environment.

From `common/mobile`, `bun run build:release` uses the EAS internal APK profile. For a local Android build, generate Android with Expo prebuild if necessary, then run from `common/mobile/android` using JDK 21, Android SDK 36, NDK 27.1.12297006, and CMake 3.22.1:

```bash
EXPO_PUBLIC_BLINKY_TRANSPORT_MODE=release NODE_ENV=production ./gradlew :blinky-secure-socket:testReleaseUnitTest :blinky-secure-socket:lintRelease :app:assembleRelease --no-daemon --console=plain
```

Set `JAVA_HOME` and `ANDROID_HOME` to installed toolchains. Output: `common/mobile/android/app/build/outputs/apk/release/app-release.apk`.

The locally generated APK is signed with the Android debug certificate despite its release build variant. It is for internal testing only. Public distribution needs team-controlled release signing and platform release checks.

Pair on normal Wi-Fi using the PC's current LAN IP, the configured token, and the exact `sha256/...` pin displayed in desktop settings. Verify the pin through the trusted desktop; do not trust a pin supplied by an unknown network peer. Changing IP does not require rotating the pin; deleting the desktop identity does.

## Recorded verification

| Check | Result on 2026-09-08 | Evidence boundary |
|---|---|---|
| Mobile Bun tests | 11 passed | Real hook with mocked React/native events/timers, plus error-state helper |
| Mobile TypeScript | Passed | Compile-time contracts |
| Frontend Bun tests | 66 passed | Includes 9 mocked native speech lifecycle tests |
| Frontend production build | Passed | TypeScript + Vite |
| Rust release tests | 25 passed | Includes real loopback pinned TLS/WebSocket exchange, wrong-pin rejection, identity permissions |
| Android pin tests | 4 passed | Matching/mismatching/malformed/missing pin/certificate data |
| Android secure-socket lint | Passed | Module lint only |
| Android release APK | Built | Release vital lint passed; not full app lint |
| Linux optimized executable | Built | No-bundle build; not installer verification |
| iOS module discovery | Passed | Autolinking only, not Xcode compilation or device validation |

APK SHA-256 (rechecked 2026-09-10):

```text
0e33354f9f4cafc4087dbf08d7d61c8c9ce6f8a84ae83b35fc8d3fc4b00437f5
```

Earlier September 4 testing established a physical Wi-Fi connection with the correct pin/token and rejection of a wrong pin. Server checks rejected missing/wrong credentials, legacy/query-only release authentication, and plaintext downgrade. Those results predate the newest APK; automated mocks do not replace another physical test.

## Before approving the WSS PR

Pre-PR review found and fixed an empty-token bypass: comparing two empty tokens previously authenticated a remote peer when no server token was configured. A regression test failed before the shared comparator was changed to reject an empty configured secret. Rebuild the PC executable from this PR; the September 8 executable predates this fix. The mobile APK is unchanged.

After the fix on September 10, all 26 Rust tests passed with `BLINKY_TRANSPORT_MODE=release TAURI_CONFIG='{"bundle":{"resources":[]}}' cargo test --locked --manifest-path common/src-tauri/Cargo.toml`, including the real pinned loopback WSS round trip.

Known iOS merge blocker: socket/pin dictionaries are accessed from Expo's async queue, URLSession delegates, and main-queue receive callbacks without serialization. Fix this race and validate reconnect/concurrent discovery in Xcode/device tests before accepting the iOS implementation; autolinking success is insufficient.

- Install the newest APK and verify normal Wi-Fi pairing, a harmless volume command, and a query with streamed status/result.
- Verify bad token shows an error, bad pin fails, and correcting credentials reconnects without restarting. Reopen the app and repeat.
- Check disconnect/reconnect and timeout behavior when Wi-Fi or the PC server becomes unavailable.
- If iOS is in the release scope, compile with Xcode and test pin rejection, token rejection, saved credentials, and reconnect on a device. Otherwise mark this PR Android-validated only.
- Check Windows packaging before claiming a Windows distributable. The Arch installer attempt lacked AppIndicator; the successful Linux executable build does not resolve that installer dependency.

Full Android app lint has an Expo audio notification-permission finding; only module/vital release lint passed. Expo Doctor reported dependency/module warnings. Development Expo export was interrupted, so no completed development-bundle validation is claimed here.

This is a focused transport review, not a complete security audit. Server-side authorization/confirmation, rate and resource limits, safer pairing/token lifecycle, and avoiding provider-key delivery to clients remain separate production-hardening work.

The frontend/mobile Bun suites (66/11 tests), both TypeScript checks, and APK hash were rechecked on September 10. Other native/build results above are the recorded September 8 runs, not reruns of the latest upstream main. Existing local architecture/workflow documents and root AGENTS.md are outside this focused PR; this handoff is its standalone documentation.
