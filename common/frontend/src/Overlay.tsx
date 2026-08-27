import { emit, listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { getHighlightSteps } from './lib/guidance';
import type { TutorResult } from './lib/types';
import { getCursorPosition, logDebugMessage, setAgentCursorVisibility } from './lib/tauri';

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

  const cursorRef = useRef<HTMLDivElement>(null);
  const currentPosRef = useRef<{ x: number; y: number }>({ x: -100, y: -100 });
  const activeGlideAnimRef = useRef<Animation | null>(null);

  const [agentCursorVisible, setAgentCursorVisible] = useState(false);
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [isClicking, setIsClicking] = useState(false);

  const isAgentActingRef = useRef(false);
  const actingTimeoutRef = useRef<any>(null);
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

  // Initialize native cursor position on mount
  useEffect(() => {
    void getCursorPosition().then((pos) => {
      if (pos.x !== 0 || pos.y !== 0) {
        const cssX = (pos.x / pixelRatio) - offsetsRef.current.x;
        const cssY = (pos.y / pixelRatio) - offsetsRef.current.y;
        currentPosRef.current = { x: cssX, y: cssY };
        if (cursorRef.current) {
          cursorRef.current.style.transform = `translate3d(${cssX}px, ${cssY}px, 0)`;
        }
      }
    });
  }, [pixelRatio]);

  // Sync native cursor blanking with AI cursor visibility
  useEffect(() => {
    void setAgentCursorVisibility(agentCursorVisible);
  }, [agentCursorVisible]);

  useEffect(() => {
    isVoiceActiveRef.current = isVoiceActive;
    if (isVoiceActive) {
      if (hideVoiceTimeoutRef.current) {
        clearTimeout(hideVoiceTimeoutRef.current);
        hideVoiceTimeoutRef.current = null;
      }
      setAgentCursorVisible(true);
      if (cursorRef.current && !isAgentActingRef.current) {
        cursorRef.current.style.opacity = '1';
      }
    } else {
      if (hideVoiceTimeoutRef.current) clearTimeout(hideVoiceTimeoutRef.current);
      hideVoiceTimeoutRef.current = setTimeout(() => {
        if (!isAgentActingRef.current) {
          setAgentCursorVisible(false);
          if (cursorRef.current) {
            cursorRef.current.style.opacity = '0';
          }
        }
      }, 500);
    }
  }, [isVoiceActive]);

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
          cursorRef.current.style.opacity = '0';
        }
      }
    });

    const unlistenNativeMove = listen<{ x: number, y: number }>('blinky://native-cursor-move', (event) => {
      const cssX = (event.payload.x / pixelRatio) - offsetsRef.current.x;
      const cssY = (event.payload.y / pixelRatio) - offsetsRef.current.y;
      currentPosRef.current = { x: cssX, y: cssY };
      
      // Update DOM transform directly when not actively gliding
      if (!isAgentActingRef.current && cursorRef.current) {
        cursorRef.current.style.transform = `translate3d(${cssX}px, ${cssY}px, 0)`;
      }
    });

    const unlistenAgentMove = listen<{ x: number, y: number, instruction?: string }>('blinky://agent-cursor-move', (event) => {
      if (actingTimeoutRef.current) {
        clearTimeout(actingTimeoutRef.current);
        actingTimeoutRef.current = null;
      }
      if (hideVoiceTimeoutRef.current) {
        clearTimeout(hideVoiceTimeoutRef.current);
        hideVoiceTimeoutRef.current = null;
      }
      if (activeGlideAnimRef.current) {
        activeGlideAnimRef.current.cancel();
        activeGlideAnimRef.current = null;
      }

      isAgentActingRef.current = true;

      const startCssX = currentPosRef.current.x;
      const startCssY = currentPosRef.current.y;
      const targetCssX = (event.payload.x / pixelRatio) - offsetsRef.current.x;
      const targetCssY = (event.payload.y / pixelRatio) - offsetsRef.current.y;

      const el = cursorRef.current;
      if (el) {
        // Place AI cursor at start position and make visible
        el.style.transform = `translate3d(${startCssX}px, ${startCssY}px, 0)`;
        el.style.opacity = '1';
        setAgentCursorVisible(true);

        // Hardware GPU glide animation from start to target
        const anim = el.animate(
          [
            { transform: `translate3d(${startCssX}px, ${startCssY}px, 0)` },
            { transform: `translate3d(${targetCssX}px, ${targetCssY}px, 0)` }
          ],
          {
            duration: 600,
            easing: 'cubic-bezier(0.2, 0.85, 0.25, 1)',
            fill: 'forwards'
          }
        );
        activeGlideAnimRef.current = anim;

        anim.onfinish = () => {
          el.style.transform = `translate3d(${targetCssX}px, ${targetCssY}px, 0)`;
          currentPosRef.current = { x: targetCssX, y: targetCssY };
          try {
            anim.cancel();
          } catch {}
          activeGlideAnimRef.current = null;

          // Trigger click ripple ring
          setIsClicking(true);
          setTimeout(() => setIsClicking(false), 350);
        };
      }

      // Grace period before restoring native cursor
      actingTimeoutRef.current = setTimeout(() => {
        isAgentActingRef.current = false;
        if (!isVoiceActiveRef.current) {
          setAgentCursorVisible(false);
          if (cursorRef.current) {
            cursorRef.current.style.opacity = '0';
          }
        }
      }, 1200);
    });

    const unlistenAgentDone = listen('blinky://agent-cursor-done', () => {
      if (actingTimeoutRef.current) {
        clearTimeout(actingTimeoutRef.current);
        actingTimeoutRef.current = null;
      }
      actingTimeoutRef.current = setTimeout(() => {
        isAgentActingRef.current = false;
        if (!isVoiceActiveRef.current) {
          setAgentCursorVisible(false);
          if (cursorRef.current) {
            cursorRef.current.style.opacity = '0';
          }
        }
      }, 350);
    });

    return () => {
      unlistenVad.then((dispose) => dispose());
      unlistenVoice.then((dispose) => dispose());
      unlistenVis.then((dispose) => dispose());
      unlistenNativeMove.then((dispose) => dispose());
      unlistenAgentMove.then((dispose) => dispose());
      unlistenAgentDone.then((dispose) => dispose());
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

      <div 
        ref={cursorRef}
        className="agent-cursor-wrapper"
        style={{
          opacity: agentCursorVisible ? 1 : 0,
          transform: `translate3d(${currentPosRef.current.x}px, ${currentPosRef.current.y}px, 0)`,
        }}
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
