# Concise architecture decision record

Status: accepted snapshot, 2026-09-02. This document records the architecture present in source; risks and follow-up work are in [SECURITY-AND-RISKS.md](SECURITY-AND-RISKS.md).

## ADR-001 — Layer the desktop assistant by privilege and concern

**Decision:** React owns presentation and bounded UI-loop policy; Rust/Tauri owns privileged OS/process/window/IPC operations; Python owns intent, models, screen understanding, research, and automation; platform adapters own OS-specific mechanics.

**Why:** It keeps privileged native operations out of the renderer and makes Python reasoning reusable while isolating Windows/Linux differences.

**Consequences:** Cross-layer request/result/event contracts must change atomically. Orchestration hotspots require protocol tests.

## ADR-002 — Use local process protocols instead of embedding Python

**Decision:** Spawn `main.py` per tutor request and keep `agent_router.py` as a persistent JSON-lines daemon for remote/agent queries. Stream status/chunk records and use the `__BLINKY_CAPTURED__` marker for capture lifecycle.

**Why:** One-shot work isolates tutor failures; the daemon amortizes browser/tool startup and supports streaming remote queries.

**Consequences:** stdout is a protocol, restart/cancellation/request correlation are mandatory, and settings/environment must be consistent in both paths.

## ADR-003 — Ground desktop actions in fresh observable UI state

**Decision:** Merge OCR with UIA/AT-SPI, assign stable refs, carry coordinate-space metadata, execute one bounded action, and re-observe/verify before continuing.

**Why:** Text-only plans and stale coordinates are unsafe across dynamic, scaled, multi-platform interfaces.

**Consequences:** Capture/accessibility fallbacks and coordinate conversions are core contracts; confidence/ambiguity and post-action verification must not be bypassed.

## ADR-004 — Keep platform behavior behind a backend seam

**Decision:** Use the Linux `ComputerUseBackend` implementations and Windows capture/UIA/tool modules as the OS boundary; generic routing and agents call compatibility/facade APIs.

**Why:** Wayland/X11/Windows capabilities and permissions differ materially.

**Consequences:** New generic capabilities require adapter implementations and desktop-environment-specific validation. Linux runtime support does not by itself configure Linux packaging.

## ADR-005 — Persist learned/generated automation only through reviewable artifacts

**Decision:** Stage learned recipes under `.brain` and require user approval to retain them. Treat generated Python tools/registry mutations as review-required source changes.

**Why:** Reuse improves repeated workflows, but model-derived automation can encode unsafe or brittle behavior.

**Consequences:** Recipe schemas/registry need versioning and garbage collection; generated code needs stronger sandboxing/approval than currently implemented.

## ADR-006 — Expose a LAN remote through a release-pinned WSS gateway

**Decision:** Mobile and other remote clients use port 9001 for streamed queries, direct device commands, and speech gateway paths. Development retains plain WS compatibility. Release serves WSS with a persisted P-256 self-signed identity, requires JSON token authentication with an explicit acknowledgement for non-loopback clients, and uses the certificate's `sha256/<SPKI>` pin in the native mobile module. Optional desktop speech stream classes provide a native Tauri WSS bridge; development browser WS remains supported.

**Source clarification (2026-09-10):** Current CommandBar queries use Tauri IPC and current STT/TTS calls use direct Sarvam HTTPS. CommandBar does not instantiate the optional stream classes. This corrects the previous description; switching active desktop speech to the gateway is not part of this WSS-only release review.

**Why:** A single gateway reuses desktop execution and avoids duplicating the assistant on mobile while protecting LAN traffic and preventing a private certificate from being delegated to WebView/system trust. The native mobile seam is required because Expo Go cannot contain project-local native code.

**Consequences:** This is a security boundary, not internal IPC. Development empty-token behavior remains fail-open for compatibility; release empty-token behavior makes remote authentication impossible. The identity files are managed in OS app data and deleting them rotates the mobile pin. Release mobile credentials use Android Keystore/iOS Keychain; development uses AsyncStorage for Expo Go compatibility. Sensitive commands still need server-side authorization/confirmation and cancellation.

## ADR-007 — Transfer files over a capability-protected HTTP(S) data channel

**Decision:** Mobile sends file metadata and transfer control over its authenticated port-9001 WebSocket, then streams bounded chunks over a dedicated port-9002 HTTP listener. Release wraps port 9002 in TLS using the WSS P-256 identity, and native mobile code pins the same `sha256/<SPKI>` value. Rust issues a random transfer ID and temporary bearer capability, stages uploads under `Downloads/Blinky/.staging`, verifies size and SHA-256, then moves completed uploads to an optional user-specified, existing writable absolute PC folder. A blank destination uses `Downloads/Blinky`. Each mixed batch uploads all selected files. Only an explicit edit instruction starts the structured AiCut worker for uploaded video/audio media; its result is saved in the chosen destination and downloaded into app-private storage for sharing.

**Why:** WebSocket frames and React Native JavaScript buffers are not suitable for multi-gigabyte files. A separate chunked data path supports bounded memory, offsets, integrity checks, and resumable requests while retaining the authenticated WSS session as the control plane.

**Consequences:** Authenticated remote clients can write to any existing writable PC folder, so the remote token must be shared only with trusted devices. Cross-filesystem finalization copies a verified staged file when a hard link is unavailable. PDFs and images are transferred but are not AiCut edit inputs, and selection alone does not request a merge or audio operation. The default maximum is 20 GiB, overridable in bytes through `BLINKY_FILE_TRANSFER_MAX_BYTES`. Transfer capabilities and offsets are process-local and expire after 24 hours, so Wi-Fi interruptions can resume only while the mobile app and PC process remain alive. Custom native Expo builds are required; Expo Go cannot load the local streaming module. Port 9002 must be reachable through the firewall/USB reverse setup. The Antigravity loopback hook moves from 9002 to 9003. Development uses HTTP and app config permits cleartext only in development; release uses pinned HTTPS. A global connection limit/rate limiter and process-restart recovery remain future work.
