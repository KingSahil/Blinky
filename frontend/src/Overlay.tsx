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

  return (
    <main className="overlay-root">
      {matches.map(({ step, match }) => {
        if (!match) return null;
        return (
          <div
            className="target-frame"
            key={`${step.step}-${step.target_text}-${match.x}-${match.y}`}
            style={{
              left: match.x,
              top: match.y,
              width: match.width,
              height: match.height,
            }}
          >
            <div className="target-pulse" />
            <div className="target-tooltip">
              <span>{step.step}</span>
              {step.instruction}
            </div>
          </div>
        );
      })}
    </main>
  );
}
