import { listen } from '@tauri-apps/api/event';
import { useEffect, useState } from 'react';
import type { TutorResult } from './lib/types';

export function Overlay() {
  const [result, setResult] = useState<TutorResult | null>(null);

  useEffect(() => {
    const unlisten = listen<TutorResult>('clicky://guidance', (event) => {
      setResult(event.payload);
    });

    return () => {
      unlisten.then((dispose) => dispose());
    };
  }, []);

  const matches =
    result?.steps
      .map((step) => ({ step, match: step.match }))
      .filter((entry) => Boolean(entry.match)) || [];

  const screenshotWidth = result?.screenshot?.width || window.innerWidth;
  const screenshotHeight = result?.screenshot?.height || window.innerHeight;
  const scaleX = window.innerWidth / screenshotWidth;
  const scaleY = window.innerHeight / screenshotHeight;

  return (
    <main className="overlay-root">
      {matches.map(({ step, match }) => {
        if (!match) return null;
        const left = Math.round(match.x * scaleX);
        const top = Math.round(match.y * scaleY);
        const width = Math.max(8, Math.round(match.width * scaleX));
        const height = Math.max(8, Math.round(match.height * scaleY));
        return (
          <div
            className="target-frame"
            key={`${step.step}-${step.target_text}-${match.x}-${match.y}`}
            style={{
              left,
              top,
              width,
              height,
            }}
          >
            <div className="target-pulse" />
          </div>
        );
      })}
    </main>
  );
}
