# Remote Desktop over WebRTC — Architecture Design

**Author:** drafted for Eddie (jaco.live)
**Status:** Draft v1 · 2026-05-16
**Scope:** personal / small-team self-use, P2P, multi-client (Web + native)

This document proposes an architecture for a WebRTC-based remote desktop
application with screen sharing, input control (keyboard/mouse), and file
transfer. It commits to opinionated technical choices and calls out where
those choices are likely to bite.

---

## 1. Goals and non-goals

### In scope
- A **macOS host** that exposes its screen, accepts remote input, and serves files.
- **Multiple client surfaces**: Web (browser), native iOS/Android, native macOS/Windows.
- **Real-time** screen streaming (target: < 100 ms glass-to-glass on LAN, < 250 ms on WAN).
- **Bidirectional control**: mouse, keyboard, scroll, modifier keys.
- **File transfer**: drag-drop, paste, chunked, resumable.
- **P2P-first** with public STUN; TURN only as escape hatch.

### Out of scope for v1
- Multi-monitor enumeration with per-monitor selection (single primary display first).
- Audio capture from host (postponed to v1.1).
- Recording / playback of sessions.
- Multi-user accounts, RBAC, billing.
- Mobile **as host** (only as client).
- Windows / Linux **as host** (only as client). Host can be ported later — the
  capture and input modules are the only platform-specific parts.

### Explicit non-goals
- **Not** a competitor to Parsec / Moonlight on latency for gaming. Their pipelines
  bypass standard WebRTC for sub-30ms input. We target productivity, not games.
- **Not** building our own codecs or signaling protocol from scratch. We use
  vanilla WebRTC + a thin signaling layer.

---

## 2. High-level architecture

```
                ┌────────────────────────────────────────────────┐
                │                  Signaling Server               │
                │    (Node + WebSocket, stateless, ephemeral)     │
                │    rooms: {roomCode -> [hostSocket, clientIds]} │
                └────────────────────────────────────────────────┘
                         ▲                       ▲
                         │  WSS (control plane)  │
                         │                       │
                ┌────────┴───────┐       ┌───────┴──────────┐
                │   Host (Mac)   │       │   Client(s)      │
                │                │       │  Web / iOS /     │
                │ ScreenCapture  │       │  Android / Mac / │
                │      Kit       │       │  Windows         │
                │ CGEvent inject │       │                  │
                │ FS access      │       │  RTCPeerConn     │
                │ RTCPeerConn    │◄──────┤  <video> render  │
                └────────┬───────┘  P2P  └──────────────────┘
                         │   DTLS-SRTP (media)
                         │   DTLS-SCTP (data channels)
                         ▼
                    STUN / TURN
```

### Why three planes
- **Control plane (signaling)** is small, JSON over WSS, only used for SDP offer/answer,
  ICE candidate exchange, and room lifecycle. Bandwidth: kilobytes per session.
- **Media plane** is the screen video, raw H.264 over SRTP, MB/s.
- **Data plane** is two DataChannels: one for input events (low latency, unreliable
  is fine for mouse moves), one for file transfer (ordered, reliable).

Separating these means we can scale the signaling server trivially (it holds no
media), and DataChannels are isolated from media congestion control.

---

## 3. Component design

### 3.1 Host (macOS)

Native Swift app, **menu-bar agent** (no dock icon).

**Modules**
1. **Capture** — `ScreenCaptureKit` (macOS 12.3+). Produces `CMSampleBuffer` at 30/60 fps.
   - Crops to a single display (primary by default; selectable).
   - Optional cursor capture (`SCStreamConfiguration.showsCursor`).
2. **Encode** — VideoToolbox H.264 hardware encoder, fed by the capture module
   via `RTCVideoSource.capturer`. Adaptive bitrate driven by WebRTC's congestion
   controller (GCC). Initial bitrate 4 Mbps, ceiling 15 Mbps, floor 500 Kbps.
3. **PeerConnection** — `WebRTC` Swift SDK (stasel/WebRTC or
   `pod 'WebRTC-SDK'`). One `RTCPeerConnection` per connected client.
4. **Input** — `CGEvent` injection. Requires **Accessibility** permission
   (System Settings → Privacy & Security → Accessibility). Capture permission
   is **Screen Recording** (separate permission, separate prompt).
5. **File service** — surface a sandboxed "shared" folder. Reads/writes via
   `FileManager`. Reuses data channel for transfer (see §3.4).
6. **Signaling client** — WebSocket, handles room registration, SDP/ICE.

**State**
- `Idle` → `Advertising(roomCode)` → `Connecting(clientId)` → `Streaming(clientId)`
- Multiple `Streaming` states concurrently allowed (one PC per client).

**Process model**
- Single process; no XPC service. ScreenCaptureKit runs in-process.
- Capture + encode on a dedicated dispatch queue.
- PC callbacks on the WebRTC worker thread (do not block).

### 3.2 Web client (primary v1 client)

Single-page app, no framework lock-in (React or plain TS — either works).
The Web client is the **lead client** because it covers Mac, Windows, Linux,
Android, and iOS Safari with one codebase.

**Modules**
1. **PeerConnection** — browser-native `RTCPeerConnection`.
2. **Video render** — `<video autoplay playsinline>` element bound to the
   incoming `MediaStream`. CSS handles scaling/letterboxing.
3. **Input capture** — DOM events on the `<video>`:
   - `pointermove`, `pointerdown`, `pointerup`, `wheel`
   - `keydown`, `keyup` (with `preventDefault` to swallow browser shortcuts;
     warn the user that `Cmd+W` will close the tab, not the remote window)
   - Map browser coordinates → host display coordinates (see §4.2)
4. **File transfer UI** — drag-drop overlay, progress bars per file.
5. **Signaling** — `WebSocket` to the signaling server.

**Constraints to design around**
- iOS Safari does not allow auto-play of streams that have no user gesture →
  show a "Connect" button.
- Browsers cannot capture **all** keys (Cmd+Tab, Cmd+Space, system shortcuts).
  Document this as a known limitation; native clients win here.

### 3.3 Native clients (phase 2)

| Platform | SDK | Why |
|---|---|---|
| iOS / iPadOS | stasel/WebRTC (SwiftPM) | Better input fidelity (Pencil pressure, system gestures), background audio, push-to-wake |
| Android | `io.github.webrtc-sdk:android` | Same — and Android browsers are inconsistent |
| macOS / Windows | Wrap the Web client in Tauri or Electron | Avoids maintaining a full native UI; native shell gives global keyboard hooks (Cmd+Tab etc.) |

**Don't write each native client from scratch in v1.** The Web client covers
everything functional. Native is for the 20% better experience that ships
after the core works.

### 3.4 Signaling server

**Stack:** Node + `ws`, ~200 LOC.

**Endpoints (single WebSocket, message-typed)**
```
{ type: "host:register",     roomCode }
{ type: "client:join",       roomCode }
{ type: "offer",   to, sdp }
{ type: "answer",  to, sdp }
{ type: "ice",     to, candidate }
{ type: "bye",     to }
```

**State:**
```
Map<roomCode, { hostSocket, clients: Map<clientId, socket> }>
```

**Lifecycle:** rooms are ephemeral, garbage-collected when host disconnects.
Room codes are 6 alphanumeric chars (~36⁶ ≈ 2 billion, plenty for personal use).

**Deployment:** single Node process behind nginx / Caddy on a $5 VPS, or
Fly.io / Railway free tier. The whole control plane should cost < $10/mo.

### 3.5 STUN / TURN

- **STUN**: `stun:stun.l.google.com:19302` — free, sufficient for most home networks.
- **TURN**: deploy coturn on the same VPS only when a peer reports ICE failure.
  Free TURN providers exist (e.g. Open Relay) but are rate-limited.

For personal/small-team use, expect **>90% of pairs to succeed with STUN-only**.
Cellular CGNAT on the client side is the main failure mode → TURN required there.

---

## 4. Data plane protocols

### 4.1 File transfer protocol

DataChannel labeled `"file"`, **ordered**, **reliable**.

```
// Header frame (JSON, UTF-8)
{ "type": "file:start",
  "id": "<uuid>", "name": "...", "size": 12345, "mime": "...", "chunks": 765 }

// Chunk frame (binary)
[ 1-byte type=0x01 | 16-byte id | 4-byte seq | payload up to 16 KB ]

// End / ack frames
{ "type": "file:end",   "id": "..." }
{ "type": "file:ack",   "id": "...", "seq": N }   // every 64 chunks for flow control
{ "type": "file:abort", "id": "...", "reason": "..." }
```

**Why 16 KB chunks:** SCTP message size limit varies; 16 KB is safe across all
WebRTC implementations and matches the recommended size for `RTCDataChannel`.

**Backpressure:** check `dataChannel.bufferedAmount` before each send; pause
when above 1 MB, resume below 256 KB. This prevents OOM on slow links.

**Resumability:** receiver acks every 64 chunks. On reconnect, sender resumes
from last ack + 1. Files larger than ~100 MB benefit from this most.

### 4.2 Input event protocol

DataChannel labeled `"input"`, **unordered**, **unreliable with retransmit**
(`maxRetransmits: 0` for mouse moves, ordered for keys).

Actually — split into two channels:

```
"input:mouse"  — unordered, maxRetransmits: 0   (loss is fine, latest wins)
"input:key"    — ordered, reliable             (every keypress matters)
```

**Coordinate mapping (critical):**
- Client knows the rendered video element's display size.
- Host's display has a different resolution.
- Send **normalized [0..1] coordinates**, not pixels — host scales to its display.
- This avoids breaking on DPI changes, multi-monitor moves, or client window resize.

```jsonc
// Mouse move
{ "t": "mm", "x": 0.5234, "y": 0.6710 }              // normalized

// Mouse button
{ "t": "mb", "btn": "L", "down": true, "x": 0.5, "y": 0.5 }

// Scroll
{ "t": "ms", "dx": 0, "dy": -3 }

// Key (ordered channel)
{ "t": "k", "code": "KeyA", "down": true, "mods": ["meta"] }
```

`code` follows the W3C `KeyboardEvent.code` spec (physical key, layout-independent).
Mods are explicit so the host doesn't have to track modifier state from key events.

---

## 5. Security

### Threats considered
1. **Eavesdropping on media/data** — mitigated by DTLS-SRTP/SCTP (WebRTC built-in,
   non-optional).
2. **MITM at signaling** — mitigated by WSS (TLS) + certificate pinning is
   overkill for v1; rely on standard CA chain.
3. **Unauthorized host access** — mitigated by 6-char room code shown on host's
   screen + optional 4-digit PIN entered on client. Room codes expire when
   host disconnects.
4. **Input injection abuse** (someone replays input frames) — out of scope for
   v1; assume the DTLS session is the security boundary.
5. **File system over-exposure** — host exposes a single "shared" folder only;
   no path traversal (canonicalize and validate every requested path).

### Permissions UX (macOS specifically)
- **Screen Recording** prompt on first capture attempt.
- **Accessibility** prompt on first input injection attempt.
- Both require system settings + app restart on first grant. Build the onboarding
  to expect this — show a "permissions needed" screen with deep links to System Settings.

### What we are NOT doing in v1
- Hardware-backed device attestation.
- 2FA on signaling join.
- Encrypted local file vault.

These are correct things to add at scale; for self-use among trusted devices
they're overengineering.

---

## 6. Key technical decisions and trade-offs

### Decision: don't build WebRTC from source
**Choice:** use prebuilt SDKs (stasel/WebRTC for Apple, official for Android,
browser-native for Web).
**Rejected:** building libwebrtc from source.
**Why:** 2h download, fragile build, no measurable benefit unless we need
custom codecs. We don't. Keep the source-build scripts (`0X_*.sh`) as an
escape hatch.

### Decision: H.264 first, not VP9/AV1
**Choice:** H.264 baseline @ 30/60 fps.
**Rejected:** VP9 / AV1.
**Why:** Hardware encoder on every Apple Silicon Mac; hardware decoder in every
modern client. AV1 has better compression but no widespread hardware decode on
iOS/Android until very recent silicon. H.264 is the only codec guaranteed to be
hardware-accelerated end-to-end today.

### Decision: Web client first
**Choice:** ship Web before native iOS/Android.
**Rejected:** native-first.
**Why:** one codebase covers 5 platforms. Input fidelity is worse than native
(Cmd+Tab can't be intercepted), but for v1 productivity that's acceptable.
Native ships later for the platforms where it actually matters.

### Decision: P2P with STUN-only by default
**Choice:** rely on STUN; add TURN only when ICE fails.
**Rejected:** TURN-always.
**Why:** TURN relays cost money (egress bandwidth) and add latency. Personal
use almost always works direct. Detect and recover when it doesn't.

### Decision: single-process host
**Choice:** menu-bar Swift app, all modules in-process.
**Rejected:** capture daemon + UI app separated by XPC.
**Why:** XPC adds complexity with no benefit at v1 scale. If we later need to
share captures across processes, XPC is a refactor, not a rewrite.

### Decision: room code in signaling, not full account system
**Choice:** ephemeral 6-char code, no accounts.
**Rejected:** OAuth + device pairing.
**Why:** matches "personal/small-team self-use" scope. Adding accounts later is
additive; starting with accounts and stripping them is wasted work.

---

## 7. Risks and open questions

### Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| `ScreenCaptureKit` permission UX is rough on first run | High | Build an onboarding screen with explicit deep links to System Settings |
| Browsers swallow system shortcuts (Cmd+Tab) on Web client | Certain | Document; native client for users who need it |
| iOS Safari restrictions on autoplay / fullscreen | Certain | Require explicit "Connect" button + fullscreen request on user gesture |
| ICE failure rate on cellular CGNAT | Medium | TURN deployment ready as a feature flag |
| H.264 patent licensing for distribution | Medium | For self-use: a non-issue. For shipped product: Cisco's openh264 binary or sign Apple's MPEG-LA license |
| HiDPI / Retina coordinate scaling bugs | High | Normalize coords end-to-end; never send pixel values across the wire |
| Clipboard sync expectations | Medium | Out of scope for v1; users will ask for it within a week of shipping |

### Open questions
1. **Audio?** Easy to add (one more SCStream stream + audio track on PC) but
   doubles permission UX complexity. Defer to v1.1.
2. **Recording sessions?** Trivially possible with MediaRecorder on client.
   Decide based on privacy posture.
3. **Multi-monitor on host?** Day-1 single display; multi-display is a v1.1
   feature with monitor enumeration in the signaling handshake.
4. **Client-to-host file sends vs host-to-client?** Initial protocol is bidirectional;
   only the UX differs. Both directions work day 1.
5. **Latency budget targets** — what is "good enough"? Suggest:
   - capture → encode: < 20 ms
   - encode → network: < 5 ms (hardware encoder)
   - network RTT: 5–60 ms typical home
   - decode → render: < 16 ms (one frame)
   - **Total: < 100 ms LAN, < 250 ms WAN** is the target.

---

## 8. Phased roadmap

### Phase 0 — Skeleton (1 week)
- Signaling server (Node + ws), room codes, in-memory state.
- Web client: connect, render incoming video, no input.
- Host: ScreenCaptureKit capture → WebRTC video track. **Verify glass-to-glass works.**
- Use a placeholder pre-shared SDP for the first day to skip signaling debugging.

### Phase 1 — Control (1–2 weeks)
- Input DataChannels (mouse, key).
- CGEvent injection on host.
- Normalized coordinate mapping.
- Modifier key handling on Web (preventDefault on relevant combos).
- Onboarding screen for macOS permissions.

### Phase 2 — Files (1 week)
- File DataChannel protocol.
- Drag-drop UI on Web client.
- Shared folder on host (sandboxed, single path).
- Resumability + backpressure.

### Phase 3 — Hardening (1–2 weeks)
- TURN deployment + ICE failure detection.
- Reconnection logic (host disconnects, room expires gracefully).
- Adaptive bitrate tuning.
- Multi-client (one host, multiple clients viewing).

### Phase 4 — Native clients (open-ended)
- iOS / iPadOS client (Swift + stasel/WebRTC).
- Tauri/Electron wrapper for Mac/Windows desktop client.
- Android (only if there's demand — Web on Android Chrome covers most cases).

---

## 9. What I'd build first, concretely

If we end up coding this together, here's the v0 that proves the riskiest assumptions
in two days:

```
~/projects/remotedesk/
├── signaling/        # Node + ws, room codes, ~150 LOC
├── host-mac/         # Xcode project, Swift, ScreenCaptureKit + stasel/WebRTC
├── client-web/       # Vite + TS, <video> + RTCPeerConnection
└── README.md
```

**The acceptance test for v0:** open the host app, open the web client on another
Mac, type the 6-char room code, see the host's screen render in the browser
within 5 seconds, with stable video, no input yet. That's the foundation —
input and files plug into the data plane after.

---

## Appendix A — WebRTC SDK quick reference

| Platform | Package | Install |
|---|---|---|
| iOS / macOS (native) | stasel/WebRTC | SwiftPM: `https://github.com/stasel/WebRTC.git` |
| iOS / macOS (Cocoapods) | WebRTC-SDK | `pod 'WebRTC-SDK', '~> 125.0'` |
| Android | webrtc-sdk | `implementation 'io.github.webrtc-sdk:android:125.+'` |
| Web | (native) | `new RTCPeerConnection(...)` |
| Windows | libdatachannel | C++, lightweight; or use Electron+web |
| Node (signaling-only) | `ws` | no WebRTC SDK needed |

## Appendix B — Capability matrix

| Capability | Web | iOS native | Mac native | Android native |
|---|:--:|:--:|:--:|:--:|
| Video receive | ✅ | ✅ | ✅ | ✅ |
| Mouse / pointer | ✅ | ✅ | ✅ | ✅ |
| Keyboard | ⚠️ (no Cmd+Tab) | n/a | ✅ (with global hook) | n/a |
| File drag-drop | ✅ | ⚠️ (limited) | ✅ | ⚠️ |
| Background | ⚠️ | ✅ | ✅ | ✅ |
| Wake host | ❌ | ✅ (silent push) | ✅ | ✅ |
| Clipboard sync | ⚠️ (user gesture required) | ✅ | ✅ | ✅ |
