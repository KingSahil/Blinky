import type { TutorResult, TutorStep } from './types';

export interface ScreenPoint {
  x: number;
  y: number;
}

export interface AutopilotRunInput {
  maxAttempts?: number;
  observe: () => Promise<TutorResult>;
  act: (point: ScreenPoint, step: TutorStep) => Promise<void>;
  wait?: () => Promise<void>;
}

export interface AutopilotRunResult {
  finalResult: TutorResult;
  attempts: number;
  stopReason: 'complete' | 'unsafe_step' | 'missing_target' | 'unchanged_after_action' | 'max_attempts';
}

const SAFE_ACTION_HINTS = ['click', 'open', 'select', 'choose', 'go to'];
const BLOCKED_ACTION_HINTS = ['type', 'enter', 'search', 'submit', 'install', 'enable', 'delete', 'remove', 'buy', 'purchase', 'pay', 'sign in', 'login'];

export async function runAutopilotLoop({
  maxAttempts = 5,
  observe,
  act,
  wait = defaultWait,
}: AutopilotRunInput): Promise<AutopilotRunResult> {
  let current = await observe();
  let attempts = 0;

  while (attempts < maxAttempts) {
    const nextStep = current.steps.find((candidate) => candidate.instruction.trim());
    if (!nextStep) {
      return { finalResult: current, attempts, stopReason: 'complete' };
    }

    if (!isSafeAutopilotStep(nextStep)) {
      return {
        finalResult: current,
        attempts,
        stopReason: nextStep.match ? 'unsafe_step' : 'missing_target',
      };
    }

    const beforeSignature = getStepSignature(nextStep);
    const point = getPhysicalClickablePoint(nextStep, current);
    await act(point, nextStep);
    attempts += 1;
    await wait();

    const after = await observe();
    const afterStep = after.steps.find((candidate) => candidate.instruction.trim());
    if (afterStep && getStepSignature(afterStep) === beforeSignature) {
      return { finalResult: after, attempts, stopReason: 'unchanged_after_action' };
    }

    current = after;
  }

  return { finalResult: current, attempts, stopReason: 'max_attempts' };
}

export function isSafeAutopilotStep(step: TutorStep): boolean {
  if (!step.match) return false;

  const instruction = normalize(step.instruction);
  if (!instruction) return false;
  if (BLOCKED_ACTION_HINTS.some((hint) => instruction.includes(hint))) return false;

  return SAFE_ACTION_HINTS.some((hint) => instruction.includes(hint));
}

export function getClickablePoint(step: TutorStep): ScreenPoint {
  const match = step.match;
  if (!match) {
    throw new Error('Cannot click a step without a matched target');
  }

  return {
    x: Math.round(match.x + match.width / 2),
    y: Math.round(match.y + match.height / 2),
  };
}

export function getPhysicalClickablePoint(step: TutorStep, result: TutorResult): ScreenPoint {
  const point = getClickablePoint(step);
  const screenshot = result.screenshot;
  if (!screenshot?.screen_width || !screenshot?.screen_height) {
    return point;
  }

  return {
    x: Math.round(point.x * (screenshot.screen_width / screenshot.width)),
    y: Math.round(point.y * (screenshot.screen_height / screenshot.height)),
  };
}

function getStepSignature(step: TutorStep): string {
  const match = step.match;
  return [
    normalize(step.instruction),
    normalize(step.target_text),
    match?.x ?? '',
    match?.y ?? '',
    match?.width ?? '',
    match?.height ?? '',
  ].join('|');
}

function normalize(value: string | undefined): string {
  return (value || '').trim().toLowerCase().replace(/\s+/g, ' ');
}

function defaultWait(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, 700));
}
