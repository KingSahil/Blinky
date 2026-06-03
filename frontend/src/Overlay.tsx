import { emit, listen } from '@tauri-apps/api/event';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { useEffect, useMemo, useState } from 'react';
import { getHighlightSteps } from './lib/guidance';
import type { TutorResult } from './lib/types';

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
  const [yOffset, setYOffset] = useState(0);

  useEffect(() => {
    const isLinux = !navigator.userAgent.includes('Windows') && !navigator.userAgent.includes('Macintosh');
    if (isLinux) {
      const fetchOffset = async () => {
        try {
          const appWindow = getCurrentWindow();
          const position = await appWindow.outerPosition();
          const scaleFactor = await appWindow.scaleFactor();
          if (scaleFactor > 0) {
            setYOffset(position.y / scaleFactor);
          }
        } catch (err) {
          console.error('Failed to resolve dynamic y-offset:', err);
        }
      };
      void fetchOffset();
      const timer = window.setTimeout(fetchOffset, 200);
      return () => window.clearTimeout(timer);
    }
  }, []);

  useEffect(() => {
    const unlisten = listen<TutorResult>('blinky://guidance', (event) => {
      setResult(event.payload);
      setDismissedKeys(new Set());
    });

    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, []);

  const isWindows = navigator.userAgent.includes('Windows');
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const pixelRatio = isWindows ? window.devicePixelRatio || 1 : 1;
  const screenshotWidth = result?.screenshot?.width || viewportWidth * pixelRatio;
  const screenshotHeight = result?.screenshot?.height || viewportHeight * pixelRatio;
  const physicalScaleX = (viewportWidth * pixelRatio) / screenshotWidth;
  const physicalScaleY = (viewportHeight * pixelRatio) / screenshotHeight;
  const scaleX = physicalScaleX / pixelRatio;
  const scaleY = physicalScaleY / pixelRatio;
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

          const rawLeft = Math.round(match.x * scaleX) - Math.round(paddingX / 2);
          let rawTop = Math.round(match.y * scaleY) - Math.round(paddingY / 2);

          const isLinux = !navigator.userAgent.includes('Windows') && !navigator.userAgent.includes('Macintosh');
          if (isLinux) {
            rawTop -= yOffset;
          }
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
  }, [result, scaleX, scaleY, yOffset, viewportWidth, viewportHeight]);

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
