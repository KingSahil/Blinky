# WorkBuddy AI (workbuddyai.exe)

## App Overview
WorkBuddy AI is an AI-powered desktop assistant and code editor environment. It supports a wide range of built-in models for reasoning, multimodal tasks, and image processing, as well as custom model configurations.

## Standard Behaviors
- **AI Interaction**: Supports streaming replies, thinking/tool-call visualizations, and context-aware chat.
- **Model Management**: Users can switch between built-in models or configure custom models via settings.
- **Integration**: Capable of interacting with local files, notes (e.g., Obsidian references), and external APIs (WeCom, etc.).

## Navigation & Shortcuts
- **Settings/Configuration**:
  - Access via the main menu or profile icon to manage **Model Configuration**.
  - Look for tabs or sections labeled "Models" or "Custom Models" to adjust reasoning/multimodal capabilities.
- **Help & Support**:
  - Check the **Help** menu or documentation links within the app for keyboard shortcuts and technical details.
  - For advanced configuration, refer to the **Environment Variables Reference** (e.g., `CODEBUDDY_GATEWAY_*` keys) if using local CLI or API integrations.
- **Common Actions**:
  - **Chat**: Main interface for interacting with the AI agent.
  - **Skills/Templates**: Access curated agent skills or design templates (if available in the current version) via the skills or templates panel.
  - **Keyboard Navigation**: Use standard keyboard shortcuts for navigation; specific shortcuts may vary by version, so consult the in-app Help section for the latest list.

## Notes for Blinky
- When guiding users, prioritize showing them how to **select or change the active AI model** first, as this is a core feature.
- If users report connectivity issues, check if they are using custom environment variables or API tokens.
- The app may have a PWA-like interface in some contexts, but the desktop executable (`workbuddyai.exe`) is the primary focus here.