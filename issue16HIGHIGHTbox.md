# Highlight Box Feature: Implementation Plan

This plan details how we will implement the new "highlight box" feature that displays real-time AI step explanations right next to the cursor and voice visualizer.

## Proposed Changes

### 1. Backend: Updating AI System Prompts and Parsing

We need the AI to output exactly what it is doing at the current moment (the "step") so it can be passed down to the frontend UI.

#### [MODIFY] `common/python/prompts/agent.yaml`
- Update the `vision_planner_prompt` (and any other relevant routing prompts) to explicitly require a new JSON property: `"step_explanation": "Short, user-friendly description of this exact step (e.g. 'Clicking the Search button...')"` in addition to its standard tool and reasoning output.
- Update the system instructions to ensure this text is concise and conversational.

#### [MODIFY] `common/python/computer_use/agent.py` or `common/python/computer_use/loop.py` (depending on where the vision planner response is parsed)
- Extract the new `step_explanation` from the AI's JSON output.
- Map this `step_explanation` to the `instruction` property inside the `TutorStep` that gets dispatched over the `blinky://guidance` or `blinky://agent-cursor-move` WebSocket/Tauri events.

---

### 2. Frontend: Capturing and Rendering the Highlight Box

The frontend already has `target-frame` for highlighting the element box, and `agent-cursor-click-ring` for the click animation. We need to add the new floating text box attached to the cursor.

#### [MODIFY] `common/frontend/src/Overlay.tsx`
- **State Management**: Add a new React state `const [currentInstruction, setCurrentInstruction] = useState<string | null>(null);`.
- **Event Listeners**: 
  - Update the `blinky://agent-cursor-move` listener to set `setCurrentInstruction(event.payload.instruction || null)`.
  - Update `blinky://agent-cursor-done` to clear it (`setCurrentInstruction(null)`).
- **Rendering**: Inside the `<div className="agent-cursor-wrapper">`, directly next to the `<svg className="agent-cursor">` and the `.agent-visualizer`, add a new container for the text box:
  ```tsx
  {currentInstruction && (
    <div className="agent-instruction-box">
      {currentInstruction}
    </div>
  )}
  ```

#### [MODIFY] `common/frontend/src/styles.css`
- Add sleek, glassmorphic CSS for `.agent-instruction-box` so it matches the Ember/Pink aesthetics you've built.
- Ensure it is positioned `absolute` relative to the cursor wrapper (e.g., slightly offset to the right or bottom right) so it doesn't overlap the audio visualizer.
- Add micro-animations (like a fade-in and slide-up) when the text changes or appears.

---

## Existing Implementations

To address your notes in the prompt:
- **Click Animation**: This is already implemented in `Overlay.tsx` as `.agent-cursor-click-ring`. When a click happens, a ripple ring appears around the cursor. 
- **Tab/Button Box Highlight**: This is also already implemented as `.target-frame` and `.target-pulse`, which draws a box over the element the AI is targeting. We will leave these perfectly intact and only add the new text box!

## Verification Plan
### Manual Verification
1. Run `bun run dev` to launch Blinky.
2. Trigger the agent with a complex query (e.g., "Search for X on Google").
3. Verify that as the cursor moves to click elements, a sleek text box appears next to it saying something like *"Clicking on the Search bar..."*
4. Ensure the box disappears or updates correctly as the AI transitions to the next step.

> [!IMPORTANT]
> **User Review Required**
> Let me know if you want the text box to be styled in a specific way (e.g., dark mode only, specific font sizes) or if you approve this approach!
