import { listen } from '@tauri-apps/api/event';
import { useEffect, useMemo, useState } from 'react';
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
}

export function Overlay() {
  const [result, setResult] = useState<TutorResult | null>(null);
  const [dismissedKeys, setDismissedKeys] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    const unlisten = listen<TutorResult>('blinky://guidance', (event) => {
      setResult(event.payload);
      setDismissedKeys(new Set());
    });

    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, []);

  const screenshotWidth = result?.screenshot?.width || window.innerWidth;
  const screenshotHeight = result?.screenshot?.height || window.innerHeight;
  const scaleX = window.innerWidth / screenshotWidth;
  const scaleY = window.innerHeight / screenshotHeight;
  const frames = useMemo<HighlightFrame[]>(() => {
    return (
      result?.steps
        .map((step) => {
          const match = step.match;
          if (!match) return null;

          const key = `${step.step}-${step.target_text}-${match.x}-${match.y}`;

          // Raw dimensions in overlay CSS pixels
          const rawLeft = Math.round(match.x * scaleX);
          const rawTop = Math.round(match.y * scaleY);
          const rawWidth = Math.max(8, Math.round(match.width * scaleX));
          const rawHeight = Math.max(8, Math.round(match.height * scaleY));

          // Cap to MAX_BOX, keeping the element center fixed
          // EXCEPT for wide elements (like sidebar lists) where we align to the left edge (with a small margin)
          // where the folder icon and text are actually situated!
          const MAX_BOX_WIDTH = 120;
          const MAX_BOX_HEIGHT = 40;
          const displayHeight = Math.min(rawHeight, MAX_BOX_HEIGHT);

          let displayWidth = Math.min(rawWidth, MAX_BOX_WIDTH);
          let displayLeft = rawLeft;

          if (rawWidth > 120) {
            // Wide elements (likely list/sidebar rows):
            // Snugly fit the width by estimating character length (icon offset + chars * 7px + padding)
            const textLength = match.text ? String(match.text).length : 8;
            const estimatedWidth = 24 + textLength * 7.2 + 16;
            
            displayWidth = Math.min(rawWidth, Math.max(45, Math.round(estimatedWidth)));
            
            // Wide elements: align to the left (shifted 28px right to cover text snugly instead of expand arrows)
            displayLeft = rawLeft + 28;
          } else {
            // Normal elements: center them
            displayLeft = rawLeft + Math.round((rawWidth - displayWidth) / 2);
          }
          const displayTop = rawTop + Math.round((rawHeight - displayHeight) / 2);

          return {
            key,
            left: displayLeft,
            top: displayTop,
            width: displayWidth,
            height: displayHeight,
          };
        })
        .filter((frame): frame is HighlightFrame => Boolean(frame)) || []
    );
  }, [result, scaleX, scaleY]);

  useEffect(() => {
    const unlisten = listen<GlobalClick>('blinky://global-click', (event) => {
      const clickedFrame = frames.find((frame) => containsClick(frame, event.payload, scaleX, scaleY));
      if (!clickedFrame) return;

      setDismissedKeys((current) => {
        const next = new Set(current);
        next.add(clickedFrame.key);
        return next;
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
            className="target-frame"
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
