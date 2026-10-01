# Security, safety, and review findings

This is a source-based development risk register, not a claim that the product has completed a security audit. Prior `docs/SECURITY-REMEDIATION.md` contains useful intent, but several recommendations are not present in current code.

## Trust boundaries

| Boundary | Sensitive capability/data |
|---|---|
| React -> Tauri invoke | native clicks, typing, URLs, settings/secrets, window control |
| Rust -> Python | screenshots, accessibility text, user requests, arbitrary tool execution paths |
| LAN client -> port 9001 | power/media/lock, screenshots, assistant queries, Sarvam key retrieval |
| LAN client -> port 9002 | uploaded user files, temporary transfer capabilities, edited output downloads |
| Python -> model/search providers | user text, sometimes screenshots/UI content, acquired web content |
| WhatsApp session -> local service/model | messages, chat metadata, media, summary memory, browser auth |
| Generated tool/recipe persistence | executable Python source and reusable action sequences |
| AiCut -> filesystem/FFmpeg | user media paths, output overwrite/creation, external processes |

## Critical/high-priority findings

### Development remote authentication is optional; release is fail-closed

`common/src-tauri/src/websocket.rs` binds `0.0.0.0:9001`. Development preserves the legacy behavior where an unset `BLINKY_REMOTE_TOKEN` trusts LAN peers. The release transport variant uses WSS and requires a JSON token auth frame for every non-loopback peer; an unset token therefore leaves remote peers unable to authenticate. Configure a strong token before building release or using development on an untrusted network.

Action: use `bun run build:release`, configure a strong token, and enter the displayed certificate pin in the mobile release build. Rate limiting, request size/time limits, short-lived pairing, and server-side confirmation remain follow-up work.

### Release WSS identity and pinning

Release Rust generates a persistent P-256 self-signed identity under the OS app-data `tls/` directory. The desktop Tauri bridge trusts that identity for local WSS and checks its `sha256/<SPKI>` pin. Android's local Expo secure-socket module verifies the self-signed leaf certificate's SHA-256 public-key pin directly during the TLS handshake and uses Android Keystore for saved credentials; iOS uses URLSession public-key pinning and Keychain. Hostname verification is intentionally replaced by the pin check because the desktop certificate has stable localhost names while its LAN IP can change. Deleting the identity rotates the certificate and invalidates the old mobile pin. The pin is public identity material whose integrity must be protected and verified through a trusted channel; the remote token is the confidential pairing secret.

### Remote commands have no server-side confirmation

Power off, restart, sleep, volume, mute, lock, screenshot, and Sarvam-key requests run directly in Rust. Mobile confirms some power actions locally, but another protocol client can bypass that UI. Authorization and confirmation are different controls.

Action: classify command risk server-side and require a short-lived confirmation capability for destructive or sensitive commands. Do not return raw provider keys to remote clients; proxy speech consistently.

### Mobile file-transfer boundary

The file listener binds `0.0.0.0:9002`. Release `file_offer` requires a configured `BLINKY_REMOTE_TOKEN` and authenticated WebSocket; development currently permits an empty token for legacy LAN behavior. Rust then issues a random transfer ID and 256-bit temporary bearer token whose SHA-256 digest is stored in memory. Upload and download requests require that capability. The listener uses the same P-256 identity as WSS in release; the mobile module pins HTTPS and rejects HTTP whenever a pin is configured. Development builds use unencrypted HTTP and show an explicit local-network warning; use them only on trusted networks. Release builds use TLS pinning.

The HTTP parser caps request headers at 16 KiB, applies a header deadline and upload read-idle timeout, and limits concurrent connections to 32. Oversized, stalled, or excess connections are rejected or dropped before they can accumulate unbounded parser memory or tasks. A per-transfer write reservation protects chunk offsets while file I/O runs outside the global session lock.

Offers validate the filename, an optional absolute destination folder, file-size cap, available disk space, chunk offsets, and final SHA-256. A destination must already exist and be writable. Authenticated remote clients may choose any such PC folder, so protect the remote token and grant it only to trusted devices. Upload data stays under `Downloads/Blinky/.staging` until complete. AiCut receives only uploaded paths with an empty Explorer context and writes output to the chosen folder. The process-local transfer state expires after 24 hours and is lost on either process restart. The temporary token is sent only over the WebSocket and native file requests; do not log it or expose it to unrelated UI state.

Operational limit: a client with a valid temporary capability can hold one of the bounded connection slots by trickling upload data or not reading a download response. The listener is reachable on the LAN, so keep the release token confidential, protect the certificate pin against modification, and use development transport only on trusted networks. On destinations without hard-link support, the copy fallback reserves a unique final name before writing; a partially copied file can be visible until finalization succeeds or error cleanup removes it.

### Generated tools are executable source mutation

`agent_router.py`/`utils/generalizer.py` can produce Python files and update `tools/registry.json`. Model-produced code may access the filesystem/network and later run as a normal tool.

Action: keep candidates outside the source tree, enforce an allowlisted runtime/sandbox, validate imports/network domains/arguments, require human diff approval, sign accepted registry entries, and make rollback explicit.

### WhatsApp command authorization is broad

In the normal path, `WaUserSession.js` permits any participant in a group and any sender in a direct chat to invoke recognized message commands. `ALLOW_PUBLIC_COMMANDS` is mainly a fallback when chat context is unavailable, not a strict allowlist.

Action: require an owner/admin/sender allowlist, default deny group commands, log authorization decisions without message content, and add tests for group/direct/unknown chat cases.

## Other important findings

### Development connection values remain less protected

`.env` holds credentials and Rust returns them to renderer settings. Development mobile builds keep connection values in AsyncStorage for Expo Go compatibility. Release mobile builds store the remote token and certificate pin through the local module's Android Keystore/iOS Keychain APIs. Mobile can request `SARVAM_API_KEY`, and WhatsApp persists service-specific settings in ignored JSON.

Action: minimize renderer/mobile exposure, keep provider operations proxied where possible, mask readbacks, and scrub logs/errors. Ensure `.env`, WhatsApp data, mobile backups, and support bundles remain excluded.

### Autopilot safety is keyword-based

Current allowed hints include type, enter, search, and submit. Blocked hints cover install, enable, deletion/removal, purchase/payment, and sign-in/login. Keyword classification can miss semantic equivalents, multilingual instructions, indirect consequences, or a safe-looking button with destructive behavior.

Action: add structured action risk from Python, require confirmation based on target/control/context, enforce domain-specific rules at execution, and retain fresh-match/confidence checks. Update older docs rather than relying on their stricter obsolete list.

### Cancellation is incomplete

Frontend/mobile stop state does not reliably cancel the one-shot worker, persistent daemon query, network request, or direct OS action.

Action: propagate request IDs and cancellation from UI through Rust to Python/tasks, make tools cancellation-aware, and report terminal cancelled status.

### Network/provider privacy is mode-dependent

“Offline-first” does not mean offline-only. Groq, DeepSeek, MiMo/custom endpoints, Sarvam, public SearXNG, direct page acquisition, WhatsApp/Groq, location lookup, and generated scraping tools can transmit user data. Vision providers may receive screenshots.

Action: show active provider/network mode, obtain explicit consent for screen upload, redact/filter sensitive regions, and record which external service received which data class.

### Browser persistence expands state and attack surface

Playwright uses a persistent visible browser and WhatsApp uses a persistent authenticated Chromium profile. Acquired pages and browser automation interact with untrusted content.

Action: isolate profiles, restrict downloads/file URLs/custom protocols, bound navigation and content sizes, update browser binaries, and treat page text as untrusted prompt input.

### SearXNG development secret and exposure

The container settings use `blinky_secret_key_change_me` and bind inside the container to all interfaces; Docker publishes port 8888. Exposure depends on host/firewall configuration.

Action: replace the secret and explicitly bind/publish loopback for local-only development.

### CSP/capabilities and URL handling need regression review

Tauri limits capabilities and `open_url` accepts HTTP/HTTPS, which are useful controls. However the renderer still has privileged invokes and external speech/browser connections; capability changes can silently expand access.

Action: keep the invoke allowlist narrow, validate every URL at the privileged layer, and add security review for new capabilities/CSP sources.

### Runtime artifacts contain sensitive UI data

Screenshots, parsed UI maps, logs, recipes, app context, WhatsApp summaries, and browser/session profiles can expose application state or messages. Most are ignored, but tracked `app_context/*.md` can be runtime-enriched.

Action: define retention/deletion, redact logs, avoid committing generated app observations, and provide a user-visible data reset.

## Reliability/design debt that affects safety

- `CommandBar.tsx` (~2.6k lines), `main.py` (~1.7k), `websocket.rs` (~1k), `WaUserSession.js` (~1.5k), and computer-use tools (~2.5k) concentrate policy and lifecycle state.
- Saved shortcut defaults and actual registered shortcuts diverge.
- Linux runtime support and Windows-only bundle target diverge.
- The legacy result JSON schema is not the current contract.
- Development mobile marks socket-open as connected before explicit authentication success. Release requires a strict positive JSON authentication acknowledgement within the connection deadline.
- `App.tsx`/mobile command types lag the full Rust command set and use casts.
- WhatsApp session header validation helpers exist but the effective service is single-session/default-session.
- Provider/model defaults differ across tutor, WIL/agent, WhatsApp, setup docs, and UI.
- Provider auto-resolution can select Groq/MiMo from a key when `BLINKY_AI_PROVIDER` is unset, while `has_vision_capability()` checks only the explicit provider value; computer-use vision can therefore be reported unavailable under an otherwise auto-selected vision provider.
- The frontend tests are present but not runnable through project scripts.

These are not all vulnerabilities, but they raise the chance of inconsistent enforcement. Prefer extracting shared protocol/policy modules before adding new modes.

## Stale or misleading documentation found

- `common/ai_docs` references nonexistent `capture/screen.py`, `ocr/extract.py`, and old UIA paths.
- Old autopilot docs say typing/search/submission are blocked; source allows them.
- Old provider docs omit DeepSeek, MiMo, and custom endpoints and use retired model defaults.
- `common/mobile/APP-FLOW.md` overstates mandatory LAN token authentication.
- Root/product docs describe agent mode as capture-free and the app as Windows-centric; current source differs.
- `common/aicut/README.md` contains malformed/stale content.
- `common/.envexample` contains malformed duplicate assignments and old `CLICKY_*` keys.

Keep those files for history unless intentionally replacing them, but do not use them to decide current behavior.

## Security checklist for changes

- Does a new route cross process, LAN, provider, browser, filesystem, or OS-action boundaries?
- Is authentication fail-closed and separate from confirmation/authorization?
- Are request sizes, timeouts, retries, concurrency, and cancellation bounded?
- Are URLs/paths/protocols allowlisted and normalized at the privileged layer?
- Could the change upload screenshots, messages, location, or secrets?
- Does any model output become executable code, a shell argument, a browser action, or a saved recipe?
- Are logs and persisted artifacts free of secrets/sensitive content and covered by deletion/retention?
- Are Windows, Hyprland, GNOME, and KDE failure paths safe?
- Are protocol, safety, and authorization tests included?
