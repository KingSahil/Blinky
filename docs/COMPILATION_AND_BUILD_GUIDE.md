# Blinky Build, Compilation & Markdown Authoring Guide

This guide provides end-to-end instructions for:
1. **Compiling the Desktop Windows App (`.exe` / `.msi`)**
2. **Compiling the Mobile Android App (`.apk`)**
3. **Step-by-Step Guide on Creating and Editing Markdown (`.md`) Files**
4. **Fixing Audio & Microphone Routing on Windows**

---

## 1. How to Compile the Desktop Windows Executable (`.exe`)

Blinky Desktop is built using [Tauri v2](https://v2.tauri.app/) (Rust backend) with a React/TypeScript frontend (bundled via Vite and Bun).

### Prerequisites
- **Bun runtime**: Installed and on system PATH (`bun --version`).
- **Rust toolchain**: Installed via `rustup` (`rustc --version`, `cargo --version`).
- **Visual Studio C++ Build Tools**: C++ build environment with Windows 10/11 SDK.
- **Node/Python runtimes**: Bundled automatically by the build script.

### Steps to Build `.exe`

#### Option A: One-Command Production Build (Recommended)
From the root repository directory (`c:\Users\khann\Projects\Blinky`):

```bash
bun run build:release
```

#### Option B: Direct Tauri Build Command
```bash
# 1. Typecheck the frontend
bun run typecheck

# 2. Compile frontend assets into dist/
bun run build

# 3. Compile the native Rust binary and Windows installer
bun run tauri:build
```

### Where to Find the Output Files
Once the build completes successfully:
- **Standalone Portable `.exe`**:
  `common\src-tauri\target\release\blinky.exe`
- **Windows MSI Installer (`.msi`)**:
  `common\src-tauri\target\release\bundle\msi\Blinky_0.1.0_x64_en-US.msi`
- **Windows NSIS Setup (`.exe` installer)**:
  `common\src-tauri\target\release\bundle\nsis\Blinky_0.1.0_x64-setup.exe`

---

## 2. How to Compile the Mobile Android Application (`.apk`)

The mobile companion app is located inside `common/mobile/` and is built using [Expo 57](https://expo.dev) / React Native with EAS.

### Method 1: Build Standalone APK Locally (Offline with Android Studio / Gradle)

If you have Android Studio and the Android SDK installed:

1. **Navigate to the mobile directory**:
   ```bash
   cd common/mobile
   ```

2. **Generate Native Android Project**:
   ```bash
   bunx expo prebuild -p android
   ```

3. **Compile the APK with Gradle**:
   ```powershell
   cd android
   .\gradlew assembleRelease
   ```
   *(On Linux/macOS: `./gradlew assembleRelease`)*

4. **Where to Find the `.apk`**:
   `common\mobile\android\app\build\outputs\apk\release\app-release.apk`
   You can copy this file directly to any Android phone via USB or WhatsApp and install it.

---

### Method 2: Cloud Build Standalone APK (EAS CLI - No Android Studio Required)

If you do not have Android SDK configured locally:

1. **Install EAS CLI**:
   ```bash
   bun add -g eas-cli
   ```

2. **Log into Expo** (free account):
   ```bash
   eas login
   ```

3. **Trigger the Preview APK Build**:
   ```bash
   cd common/mobile
   eas build -p android --profile preview
   ```
   *Note: The `preview` profile in `common/mobile/eas.json` is pre-configured with `"buildType": "apk"`.*

4. **Download the APK**:
   EAS will generate a direct download link and QR code in your terminal. Open the link on your phone to download `blinky-companion.apk`.

---

## 3. Step-by-Step Guide on How to Create and Manage `.md` (Markdown) Files

A Markdown (`.md`) file is a lightweight plain-text file formatted using simple punctuation marks to render structured headings, code blocks, tables, and links.

### Step 1: Create the `.md` File
You can create a `.md` file anywhere in your workspace using your editor or terminal:

**In PowerShell / CMD:**
```powershell
New-Item -Path "docs\my-new-feature.md" -ItemType File
```

**In VS Code / Antigravity IDE:**
1. Right-click any folder in the Explorer sidebar.
2. Click **New File**.
3. Type the filename ending in `.md` (e.g. `NOTES.md` or `GUIDE.md`) and press <kbd>Enter</kbd>.

---

### Step 2: Write Common Markdown Elements

Here is a standard template showing essential markdown syntax:

```markdown
# Level 1 Heading (Document Title)
## Level 2 Heading (Major Section)
### Level 3 Heading (Subsection)

This is a regular paragraph. You can format text as **bold**, *italic*, or `inline code`.

### Bulleted and Numbered Lists
- First bullet item
- Second bullet item
  - Nested sub-item
1. Numbered step 1
2. Numbered step 2

### Hyperlinks and File References
[Visit Blinky Repo](https://github.com/KingSahil/Blinky)
[Open Tauri Config](file:///c:/Users/khann/Projects/Blinky/common/src-tauri/tauri.conf.json)

### Code Blocks with Syntax Highlighting
```python
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

```powershell
# PowerShell script block
bun run dev
```

### Tables
| Feature | Status | Provider |
| :--- | :---: | :--- |
| STT Transcription | Active | Groq / Sarvam |
| Wake Word Detection | Active | OpenWakeWord ONNX |
| Desktop Automation | Active | Windows UIA / Tauri |

### Alerts & Callouts
> [!NOTE]
> This is a helpful tip or contextual note.

> [!WARNING]
> This is an important warning.
```

---

### Step 3: Preview the Markdown File
In **VS Code** or **Antigravity IDE**:
- Press <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>V</kbd> to open the live Markdown preview.
- Or press <kbd>Ctrl</kbd> + <kbd>K</kbd> then <kbd>V</kbd> to open the preview side-by-side with your code.

---

## 4. Troubleshooting Windows Microphone & Wake Word

If your microphone button in Blinky says *"Could not hear anything clearly"* or if the wake word doesn't react:

### Root Cause
On many Windows laptops with Realtek Audio drivers, **Stereo Mix** is configured as the active recording device. Stereo Mix captures PC speaker audio (internal loopback), resulting in total digital silence (0.0 volume) when speaking into the room.

### How to Fix:
1. Press <kbd>Win</kbd> + <kbd>R</kbd>, type `mmsys.cpl` and press <kbd>Enter</kbd>.
2. Go to the **Recording** tab.
3. Right-click in the empty space and check both:
   - **Show Disabled Devices**
   - **Show Disconnected Devices**
4. Locate **Microphone** or **Microphone Array (Realtek Audio)**:
   - Right-click it and click **Enable**.
   - Right-click it and click **Set as Default Device** and **Set as Default Communication Device**.
5. Right-click **Stereo Mix** and click **Disable** (so Windows apps don't accidentally prioritize it over your voice).
6. Verify your hardware microphone mute hotkey (often <kbd>Fn</kbd> + <kbd>F4</kbd> or <kbd>F4</kbd>) is not active.
