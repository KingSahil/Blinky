# Open With (openwith.exe)

## Overview
`openwith.exe` is a system process in Windows responsible for managing file associations. It allows users to select a specific program to open a file, overriding the default application if necessary.

## Standard Behaviors
- **Trigger**: Typically invoked when a user right-clicks a file and selects "Open with" or presses `Ctrl` + `Shift` + `F10` (or the context menu key) followed by the appropriate menu navigation.
- **Function**: Displays a list of installed applications capable of opening the selected file type.
- **Persistence**: Can set the chosen application as the new default for that file type.

## Navigation & Shortcuts
- **Access via Context Menu**:
  1. Right-click the target file.
  2. Hover over **Open with**.
  3. Select **Choose another app** (or a specific app from the list).
- **Keyboard Access**:
  - Press `Ctrl` + `Shift` + `F10` (or the Menu key) to open the context menu for the selected file.
  - Use `Tab` and `Arrow Keys` to navigate the "Open with" submenu.
  - Press `Enter` to select an application.
- **Settings Integration**:
  - To change default apps globally, go to **Settings** > **Apps** > **Default Apps**.

## Troubleshooting
- If the dialog fails to appear, ensure the file type has at least one associated program installed.
- Errors in `openwith.exe` may indicate corrupted file associations; resetting defaults in Settings often resolves this.