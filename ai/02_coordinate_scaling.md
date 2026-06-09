# Blinky — Coordinate Scaling & Resolution Normalization Guide

This document describes the mathematical formulas, scale transitions, and layout constraints used to map physical coordinate spaces to virtual overlay dimensions across process boundaries.

---

## 1. Physical vs. Downsampled Screenshot Space

Screenshots can be captured at any physical desktop resolution (e.g., $2560 \times 1600$, $3840 \times 2160$). To optimize local OCR execution speeds and keep LLM input context within token budgets, `capture/screen.py` downsamples screenshots using Lanczos interpolation:

$$\text{Max Width} = 1920 \text{ px}, \quad \text{Max Height} = 1080 \text{ px}$$

The aspect ratio is strictly preserved.
* **Example**: A physical screen of $2560 \times 1600$ (16:10 aspect ratio) downsamples to a screenshot of $1728 \times 1080$ pixels.
* **Dataclass Representation**: The [Screenshot](file:///c:/projects/Jarvis/python/capture/screen.py) dataclass maintains both:
  * `width` / `height`: Downsampled screenshot dimensions.
  * `screen_width` / `screen_height`: Original physical desktop dimensions.

---

## 2. UIA Coordinate Normalization

Windows UI Automation (UIA) returns control bounding rectangles in physical desktop coordinates (relative to the full display). WinRT OCR and pytesseract OCR results are extracted directly from the downsampled screenshot buffer, meaning they are already in downsampled screenshot-space.

To align both coordinate systems in the same space, [main.py](file:///c:/projects/Jarvis/python/main.py) maps UIA bounds to screenshot-space bounds:

### Scale Factors
$$s_x = \frac{\text{screenshot.width}}{\text{screenshot.screen\_width}}$$

$$s_y = \frac{\text{screenshot.height}}{\text{screenshot.screen\_height}}$$

### Normalization Mapping
For any coordinate pair $(x_{\text{uia}}, y_{\text{uia}})$:

$$x_{\text{ss}} = \lfloor x_{\text{uia}} \times s_x \rceil$$

$$y_{\text{ss}} = \lfloor y_{\text{uia}} \times s_y \rceil$$

This scaling ensures that fuzzy matching and text calibration operate on identical pixel scales.

---

## 3. Overlay Viewport Display Scaling

When the React frontend renders [Overlay.tsx](file:///c:/projects/Jarvis/frontend/src/Overlay.tsx), it must map screenshot-space coordinates back to CSS pixels matching the browser's viewport.

### Viewport Ratios
$$\text{scale}_x = \frac{\text{window.innerWidth}}{\text{screenshot.width}}$$

$$\text{scale}_y = \frac{\text{window.innerHeight}}{\text{screenshot.height}}$$

### Render Calculations
$$\text{frame.left} = \text{round}(x_{\text{ss}} \times \text{scale}_x)$$

$$\text{frame.top} = \text{round}(y_{\text{ss}} \times \text{scale}_y)$$

$$\text{frame.width} = \text{round}(\text{width}_{\text{ss}} \times \text{scale}_x)$$

$$\text{frame.height} = \text{round}(\text{height}_{\text{ss}} \times \text{scale}_y)$$

---

## 3.5 Linux Viewport Coordinate Shifting (GNOME Shell vs KDE/Plasma)

Under Linux (GNOME/Wayland), standard frameless full-screen windows hide the system top panel. To prevent this, **Blinky dynamically detects the desktop environment at runtime**:
* **GNOME**: Spawns the native overlay window exactly below the GNOME status bar (physically positioned at $y = 32 \times \text{scale\_factor}$).
* **KDE / Plasma / Others**: Spawns the overlay window at $y = 0$ with full screen dimensions (as system panels are usually placed at the bottom or sides and do not trigger full-screen hiding).

To maintain absolute coordinate precision across all platforms, resolutions, and desktop setups, **the vertical offset is resolved dynamically at runtime** inside `Overlay.tsx`.

### Dynamic Offset Calculation
The frontend queries the Tauri window shell's native screen coordinates:

$$\text{y\_offset} = \frac{\text{appWindow.outerPosition().y}}{\text{appWindow.scaleFactor()}}$$

Consequently, the OCR vertical coordinates are shifted relative to the overlay's dynamic window position before scaling and rendering:

$$y_{\text{shifted}} = y_{\text{ss}} - \text{y\_offset}$$

$$\text{frame.top} = \text{round}(y_{\text{shifted}} \times \text{scale}_y)$$

* **On GNOME**: `y_offset` dynamically evaluates to `32` (or the corresponding scaled panel height), aligning overlay frames perfectly with underlying elements.
* **On KDE / Plasma / Windows**: The window is positioned at `y: 0`, so `y_offset` evaluates to `0`, resulting in a zero-offset rendering.

This dynamic shift guarantees that graphical highlights overlay target items with pixel-perfect accuracy on all display types (1080p, 2K, 4K) and all desktop environments.

---

## 4. Autopilot Click Scaling

The screen tutor and matcher always return `step.match` boxes in downsampled screenshot-space. This is correct for the overlay and for LLM reasoning, but native mouse clicks need physical desktop coordinates.

`python/main.py` includes both coordinate spaces in every result:

```json
"screenshot": {
  "width": 1728,
  "height": 1080,
  "screen_width": 2560,
  "screen_height": 1600
}
```

`frontend/src/lib/autopilot.ts` first takes the center of the matched screenshot-space box:

$$x_{\text{center}} = x_{\text{ss}} + \frac{w_{\text{ss}}}{2}$$

$$y_{\text{center}} = y_{\text{ss}} + \frac{h_{\text{ss}}}{2}$$

Then it maps that point back to physical desktop coordinates before calling Rust:

$$x_{\text{physical}} = \text{round}\left(x_{\text{center}} \times \frac{\text{screen\_width}}{\text{screenshot.width}}\right)$$

$$y_{\text{physical}} = \text{round}\left(y_{\text{center}} \times \frac{\text{screen\_height}}{\text{screenshot.height}}\right)$$

`src-tauri/src/lib.rs` receives the physical point in `click_screen_point` and sends a Windows `SendInput` click. If physical dimensions are absent, the frontend falls back to screenshot-space coordinates for backward compatibility.

---

## 5. Highlight Box Sizing & Capping

To prevent large highlight boxes from cluttering the screen or looking unpolished, [Overlay.tsx](file:///c:/projects/Jarvis/frontend/src/Overlay.tsx) applies custom sizing restrictions based on the control type:

### Standard / Non-Input Controls
For text, buttons, and icons, bounds are capped:
```typescript
const MAX_BOX_WIDTH = isIcon ? 100 : 140;
const MAX_BOX_HEIGHT = isIcon ? 40 : 44;
const MIN_BOX_SIZE = 36;

const displayWidth = Math.min(Math.max(MIN_BOX_SIZE, rawWidth), MAX_BOX_WIDTH);
const displayHeight = Math.min(Math.max(MIN_BOX_SIZE, rawHeight), MAX_BOX_HEIGHT);
```
*Standard elements are center-aligned when width/height constraints are active.*

### Input Control Full-Width Bypass
If the matched element is an input control (e.g. `Edit`, `TextBox`, `ComboBox`), the capping logic is bypassed to highlight the entire text input field:
```typescript
if (isInput) {
  displayWidth = rawWidth;   // Use full element width
  displayLeft = rawLeft;     // Bypasses centering shift offsets
}
```

---

## Related Guides & Files
- [01 System Architecture](file:///c:/projects/Jarvis/ai/01_architecture.md)
- [Overlay Frontend Component](file:///c:/projects/Jarvis/frontend/src/Overlay.tsx)
- [Screen Capture Engine](file:///c:/projects/Jarvis/python/capture/screen.py)
