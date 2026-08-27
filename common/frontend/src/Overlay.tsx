import { emit, listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { getHighlightSteps } from './lib/guidance';
import type { TutorResult } from './lib/types';
import { logDebugMessage, setAgentCursorVisibility } from './lib/tauri';

interface GlobalClick {
  x: number;
  y: number;
  overlay_x: number;
  overlay_y: number;
  scale_factor: number;
}

interface HighlightFrame {
  key: string;
  left: number;
  top: number;
  width: number;
  height: number;
  compact: boolean;
  step: number;
  targetText: string;
  instruction: string;
}

export function Overlay() {
  const [result, setResult] = useState<TutorResult | null>(null);
  const [dismissedKeys, setDismissedKeys] = useState<Set<string>>(() => new Set());
  const [offsets, setOffsets] = useState({ x: 0, y: 0 });
  const offsetsRef = useRef({ x: 0, y: 0 });

  const [agentCursorVisible, setAgentCursorVisible] = useState(false);
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [isClicking, setIsClicking] = useState(false);
  const cursorRef = useRef<HTMLDivElement>(null);
  const isAgentActingRef = useRef(false);
  const actingTimeoutRef = useRef<any>(null);
  const lastNativePosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const isVoiceActiveRef = useRef(false);
  const hideVoiceTimeoutRef = useRef<any>(null);

  const glowContainerRef = useRef<HTMLDivElement>(null);

  const isWindows = typeof navigator !== 'undefined' && navigator.userAgent.includes('Windows');
  const pixelRatio = typeof window !== 'undefined' && isWindows ? window.devicePixelRatio || 1 : 1;

  // Window offsets initialization and tracking
  const updateOffsets = useCallback(async () => {
    try {
      const appWindow = getCurrentWindow();
      const pos = await appWindow.outerPosition();
      const factor = await appWindow.scaleFactor();
      const newOffsets = {
        x: pos.x / factor,
        y: pos.y / factor,
      };
      setOffsets(newOffsets);
      offsetsRef.current = newOffsets;
    } catch (err) {
      console.error('Failed to get window offsets:', err);
    }
  }, []);

  useEffect(() => {
    void updateOffsets();
    window.addEventListener('resize', updateOffsets);
    return () => window.removeEventListener('resize', updateOffsets);
  }, [updateOffsets]);

  // Sync native cursor blanking with AI cursor visibility (tradeoff A: hide native only when AI visible)
  useEffect(() => {
    void setAgentCursorVisibility(agentCursorVisible);
  }, [agentCursorVisible]);

  useEffect(() => {
    isVoiceActiveRef.current = isVoiceActive;
    // When voice becomes active, morph native -> AI (no double cursor)
    if (isVoiceActive) {
      if (hideVoiceTimeoutRef.current) {
        clearTimeout(hideVoiceTimeoutRef.current);
        hideVoiceTimeoutRef.current = null;
      }
      // Place AI at last native pos instantly then fade in
      if (cursorRef.current) {
        const cssX = (lastNativePosRef.current.x / pixelRatio) - offsetsRef.current.x;
        const cssY = (lastNativePosRef.current.y / pixelRatio) - offsetsRef.current.y;
        cursorRef.current.classList.remove('agent-acting');
        cursorRef.current.classList.add('voice-following');
        cursorRef.current.style.transform = `translate3d(${cssX}px, ${cssY}px, 0)`;
      }
      setAgentCursorVisible(true);
    } else {
      // Delay hide to avoid flicker on brief pauses, but hide if not agent acting
      if (hideVoiceTimeoutRef.current) clearTimeout(hideVoiceTimeoutRef.current);
      hideVoiceTimeoutRef.current = setTimeout(() => {
        if (!isAgentActingRef.current) {
          setAgentCursorVisible(false);
          if (cursorRef.current) {
            cursorRef.current.classList.remove('voice-following');
            cursorRef.current.style.transform = 'translate3d(-100px, -100px, 0)';
          }
        }
      }, 600);
    }
  }, [isVoiceActive, pixelRatio]);

  useEffect(() => {
    const unlistenVad = listen<{ volume: number }>('blinky://vad-update', (event) => {
      if (glowContainerRef.current) {
        const volume = event.payload.volume;
        glowContainerRef.current.style.setProperty('--vad-opacity', volume > 0 ? (0.2 + volume * 0.8).toString() : '0');
        glowContainerRef.current.style.setProperty('--glow-scale', (1 + volume * 0.2).toString());
        glowContainerRef.current.style.setProperty('--glow-speed', `${4 - volume * 2.5}s`);
        if (volume > 0.05) {
          setIsVoiceActive(true);
        }
      }
    });

    const unlistenVoice = listen<{ active: boolean }>('blinky://voice-active', (event) => {
      setIsVoiceActive(event.payload.active);
    });

    const unlistenVis = listen<{ visible: boolean }>('blinky://agent-cursor-visibility', (event) => {
      setAgentCursorVisible(event.payload.visible);
      if (!event.payload.visible) {
        isAgentActingRef.current = false;
        isVoiceActiveRef.current = false;
        if (cursorRef.current) {
          cursorRef.current.classList.remove('agent-acting', 'voice-following');
          cursorRef.current.style.transform = 'translate3d(-100px, -100px, 0)';
        }
      } else if (cursorRef.current) {
        // Morph from native position
        const cssX = (lastNativePosRef.current.x / pixelRatio) - offsetsRef.current.x;
        const cssY = (lastNativePosRef.current.y / pixelRatio) - offsetsRef.current.y;
        cursorRef.current.style.transform = `translate3d(${cssX}px, ${cssY}px, 0)`;
      }
    });


    const unlistenNativeMove = listen<{ x: number, y: number }>('blinky://native-cursor-move', (event) => {
      lastNativePosRef.current = { x: event.payload.x, y: event.payload.y };
      // Only follow native when AI is visible for voice and not busy acting (tradeoff A: smooth morph, no double cursor)
      if (isVoiceActiveRef.current && !isAgentActingRef.current && cursorRef.current) {
        const cssX = (event.payload.x / pixelRatio) - offsetsRef.current.x;
        const cssY = (event.payload.y / pixelRatio) - offsetsRef.current.y;
        cursorRef.current.style.transform = `translate3d(${cssX}px, ${cssY}px, 0)`;
      }
    });

    const unlistenAgentMove = listen<{ x: number, y: number, instruction?: string }>('blinky://agent-cursor-move', (event) => {
      // Morph native -> AI: show at last native pos first if hidden (no double cursor)
      if (cursorRef.current) {
        const wasActing = isAgentActingRef.current;
        if (!wasActing) {
          const startX = (lastNativePosRef.current.x / pixelRatio) - offsetsRef.current.x;
          const startY = (lastNativePosRef.current.y / pixelRatio) - offsetsRef.current.y;
          cursorRef.current.classList.remove('voice-following');
          // Place instantly at native before glide (transition: none briefly)
          cursorRef.current.style.transition = 'none';
          cursorRef.current.style.transform = `translate3d(${startX}px, ${startY}px, 0)`;
          // Force reflow then restore transition for glide
          void cursorRef.current.offsetWidth;
          cursorRef.current.style.transition = '';
        }
      }
      setAgentCursorVisible(true);
      isAgentActingRef.current = true;
      if (actingTimeoutRef.current) {
        clearTimeout(actingTimeoutRef.current);
      }
      if (hideVoiceTimeoutRef.current) {
        clearTimeout(hideVoiceTimeoutRef.current);
        hideVoiceTimeoutRef.current = null;
      }

      if (cursorRef.current) {
        cursorRef.current.classList.remove('voice-following', 'following-user');
        cursorRef.current.classList.add('agent-acting');
        const cssX = (event.payload.x / pixelRatio) - offsetsRef.current.x;
        const cssY = (event.payload.y / pixelRatio) - offsetsRef.current.y;
        cursorRef.current.style.transform = `translate3d(${cssX}px, ${cssY}px, 0)`;
      }

      // Trigger click pulse ring after gliding to target
      setTimeout(() => {
        setIsClicking(true);
        setTimeout(() => setIsClicking(false), 300);
      }, 360);

      // Hide AI and restore native after grace period unless voice still active
      actingTimeoutRef.current = setTimeout(() => {
        isAgentActingRef.current = false;
        if (cursorRef.current) {
          cursorRef.current.classList.remove('agent-acting');
        }
        if (!isVoiceActiveRef.current) {
          setAgentCursorVisible(false);
          if (cursorRef.current) {
            cursorRef.current.style.transform = 'translate3d(-100px, -100px, 0)';
          }
        } else if (cursorRef.current) {
          // Return to voice-following mode
          cursorRef.current.classList.add('voice-following');
          const cssX = (lastNativePosRef.current.x / pixelRatio) - offsetsRef.current.x;
          const cssY = (lastNativePosRef.current.y / pixelRatio) - offsetsRef.current.y;
          cursorRef.current.style.transform = `translate3d(${cssX}px, ${cssY}px, 0)`;
        }
      }, 2500);
    });

    return () => {
      unlistenVad.then((dispose) => dispose());
      unlistenVoice.then((dispose) => dispose());
      unlistenVis.then((dispose) => dispose());
      unlistenNativeMove.then((dispose) => dispose());
      unlistenAgentMove.then((dispose) => dispose());
      if (actingTimeoutRef.current) {
        clearTimeout(actingTimeoutRef.current);
      }
      if (hideVoiceTimeoutRef.current) {
        clearTimeout(hideVoiceTimeoutRef.current);
      }
    };
  }, [pixelRatio]);


  useEffect(() => {
    let timeoutId: any = null;

    const unlisten = listen<TutorResult>('blinky://guidance', (event) => {
      setResult(event.payload);
      setDismissedKeys(new Set());

      if (timeoutId) {
        clearTimeout(timeoutId);
      }

      // Auto-dismiss highlights after 8 seconds on non-Windows platforms (fallback for missing global click hook)
      if (!navigator.userAgent.includes('Windows')) {
        timeoutId = setTimeout(() => {
          setResult(null);
        }, 8000);
      }
    });

    return () => {
      unlisten.then((dispose) => dispose());
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, []);


  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1920;
  const viewportHeight = typeof window !== 'undefined' ? window.innerHeight : 1080;
  const screenshotWidth = result?.screenshot?.width || viewportWidth * pixelRatio;
  const screenshotHeight = result?.screenshot?.height || viewportHeight * pixelRatio;

  const physicalScaleX = (viewportWidth * pixelRatio) / screenshotWidth;
  const physicalScaleY = (viewportHeight * pixelRatio) / screenshotHeight;
  const scaleX = physicalScaleX / pixelRatio;
  const scaleY = physicalScaleY / pixelRatio;

  useEffect(() => {
    if (!result) return;
    void logDebugMessage(JSON.stringify({
      type: 'overlay_render',
      viewportWidth,
      viewportHeight,
      devicePixelRatio: window.devicePixelRatio,
      pixelRatio,
      screenshotWidth,
      screenshotHeight,
      scaleX,
      scaleY,
      offsets,
      steps: result?.steps,
    }, null, 2));
  }, [result, scaleX, scaleY, viewportWidth, viewportHeight, offsets]);

  const frames = useMemo<HighlightFrame[]>(() => {
    return (
      getHighlightSteps(result?.steps || [])
        .map((step) => {
          const match = step.match;
          if (!match) return null;

          const key = `${step.step}-${step.target_text}-${match.x}-${match.y}`;

          const scaledW = match.width * scaleX;
          const scaledH = match.height * scaleY;
          
          const textStr = match.text ? String(match.text).trim() : '';
          const controlType = String(match.control_type || '').toLowerCase();
          const isIcon = 
            match.control_type === 'Image' ||
            (scaledW <= 40 && scaledH <= 40) ||
            (scaledW <= 48 && scaledH <= 48 && textStr.length <= 1);
          const isWindowsSidebarIcon =
            isWindows &&
            ['button', 'image', 'tabitem', 'menuitem', 'custom'].includes(controlType) &&
            match.x * scaleX <= 8 &&
            scaledW >= 24 &&
            scaledW <= 70 &&
            scaledH >= 24 &&
            scaledH <= 80;
          const useIconFrame = isIcon || isWindowsSidebarIcon;

          const paddingX = useIconFrame ? 4 : 20; 
          const paddingY = useIconFrame ? 4 : 8;  

          const rawLeft = Math.round(match.x * scaleX) - Math.round(paddingX / 2) - offsets.x;
          let rawTop = Math.round(match.y * scaleY) - Math.round(paddingY / 2) - offsets.y;


          const rawWidth = Math.max(8, Math.round(match.width * scaleX)) + paddingX;
          const rawHeight = Math.max(8, Math.round(match.height * scaleY)) + paddingY;

          // Cap to MAX_BOX, keeping the element center fixed
          // EXCEPT for wide elements (like sidebar lists) where we align to the left edge (with a small margin)
          // where the folder icon and text are actually situated!
          const MAX_BOX_WIDTH = useIconFrame ? 100 : 140;
          const MAX_BOX_HEIGHT = useIconFrame ? 40 : 44;

          // Enforce a minimum size of 36px for all highlights to ensure they are easily visible,
          // particularly for small icons and dots!
          const MIN_BOX_SIZE = 36;
          let displayHeight = Math.min(Math.max(MIN_BOX_SIZE, rawHeight), MAX_BOX_HEIGHT);

          const isInput =
            match.control_type === 'Edit' ||
            match.control_type === 'TextBox' ||
            match.control_type === 'ComboBox';

          let displayWidth = Math.min(Math.max(MIN_BOX_SIZE, rawWidth), MAX_BOX_WIDTH);
          let displayLeft = rawLeft;

          if (isWindowsSidebarIcon) {
            const iconBoxSize = 30;
            const iconCenterX = rawLeft + Math.min(rawWidth / 2, 24);
            const iconCenterY = rawTop + rawHeight / 2;
            displayWidth = iconBoxSize;
            displayHeight = iconBoxSize;
            displayLeft = Math.round(iconCenterX - iconBoxSize / 2);
            rawTop = Math.round(iconCenterY - iconBoxSize / 2 - (rawHeight - displayHeight) / 2);
          } else if (isInput) {
            // Keep the exact input field width and bounds
            displayWidth = rawWidth;
            displayLeft = rawLeft;
          } else if (!useIconFrame && rawWidth > 140) {
            // Wide elements (likely list/sidebar rows):
            // Fit the width comfortably by estimating character length
            const textLength = match.text ? String(match.text).length : 8;
            const estimatedWidth = 24 + textLength * 7.2 + 28;
            
            displayWidth = Math.min(rawWidth, Math.max(55, Math.round(estimatedWidth)));
            
            // Wide elements: align to the left (shifted 20px right to cover text comfortably)
            displayLeft = rawLeft + 20;
          } else {
            // Normal elements: center them
            displayLeft = rawLeft + Math.round((rawWidth - displayWidth) / 2);
          }
          const displayTop = rawTop + Math.round((rawHeight - displayHeight) / 2);
          const clamped = clampFrame(
            displayLeft,
            displayTop,
            displayWidth,
            displayHeight,
            viewportWidth,
            viewportHeight,
          );

          void logDebugMessage(JSON.stringify({
            type: 'frame_math',
            target: step.target_text,
            matchX: match.x,
            matchY: match.y,
            scaleX,
            scaleY,
            offsets,
            rawLeft,
            rawTop,
            displayLeft,
            displayTop,
            clamped,
          }));

          return {
            key,
            left: clamped.left,
            top: clamped.top,
            width: clamped.width,
            height: clamped.height,
            compact: isWindowsSidebarIcon,
            step: step.step,
            targetText: step.target_text,
            instruction: step.instruction,
          };
        })
        .filter((frame): frame is HighlightFrame => Boolean(frame)) || []
    );
  }, [result, scaleX, scaleY, viewportWidth, viewportHeight, offsets]);

  useEffect(() => {
    const unlisten = listen<GlobalClick>('blinky://global-click', (event) => {
      const clickedFrame = frames.find((frame) => containsClick(frame, event.payload, scaleX, scaleY));
      if (!clickedFrame) return;

      setDismissedKeys((current) => {
        const next = new Set(current);
        next.add(clickedFrame.key);
        return next;
      });
      void emit('blinky://target-clicked', {
        key: clickedFrame.key,
        step: clickedFrame.step,
        target_text: clickedFrame.targetText,
        instruction: clickedFrame.instruction,
      });
    });

    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, [frames, scaleX, scaleY]);

  return (
    <main className="overlay-root">
      <div className="fullscreen-edge-lighting-container" ref={glowContainerRef}>
        <div className="fullscreen-edge-lighting-gradient" />
      </div>

      {agentCursorVisible && (
        <div 
          ref={cursorRef}
          className="agent-cursor-wrapper"
        >
          {isClicking && <div className="agent-cursor-click-ring" />}
          <svg className="agent-cursor" viewBox="0 0 24 24" width="28" height="28" fill="var(--accent-strong)" xmlns="http://www.w3.org/2000/svg">
            <path d="M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 0 1 .35-.15h6.87c.45 0 .67-.54.35-.85L6.35 2.86a.5.5 0 0 0-.85.35Z"/>
          </svg>
          {isVoiceActive && (
            <div className="agent-visualizer">
              <div className="bar" />
              <div className="bar" />
              <div className="bar" />
            </div>
          )}
        </div>
      )}



      {frames.map((frame) => {
        if (dismissedKeys.has(frame.key)) return null;
        return (
          <div
            className={`target-frame ${frame.compact ? 'target-frame-compact' : ''}`}
            key={frame.key}
            style={{
              left: frame.left,
              top: frame.top,
              width: frame.width,
              height: frame.height,
            }}
          >
            <div className="target-pulse" />
          </div>
        );
      })}
    </main>
  );
}

function clampFrame(left: number, top: number, width: number, height: number, viewportWidth: number, viewportHeight: number) {
  const frameMargin = 0;
  const pulseInset = 6;
  const clampedWidth = Math.min(width, Math.max(8, viewportWidth - pulseInset * 2));
  const clampedHeight = Math.min(height, Math.max(8, viewportHeight - pulseInset * 2));
  const maxLeft = Math.max(frameMargin, viewportWidth - clampedWidth - pulseInset);
  const maxTop = Math.max(frameMargin, viewportHeight - clampedHeight - pulseInset);

  return {
    left: Math.min(Math.max(frameMargin, left), maxLeft),
    top: Math.min(Math.max(frameMargin, top), maxTop),
    width: clampedWidth,
    height: clampedHeight,
  };
}

function containsClick(frame: HighlightFrame, click: GlobalClick, scaleX: number, scaleY: number) {
  const clickTolerance = 10;
  const scaleFactor = click.scale_factor || window.devicePixelRatio || 1;
  const localX = (click.x - click.overlay_x) / scaleFactor;
  const localY = (click.y - click.overlay_y) / scaleFactor;
  const candidates = [
    {
      x: localX,
      y: localY,
    },
    {
      x: localX * scaleX,
      y: localY * scaleY,
    },
  ];

  return candidates.some(
    ({ x, y }) =>
      x >= frame.left - clickTolerance &&
      x <= frame.left + frame.width + clickTolerance &&
      y >= frame.top - clickTolerance &&
      y <= frame.top + frame.height + clickTolerance,
  );
}
