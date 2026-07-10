import { emit } from '@tauri-apps/api/event';
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
  observeAfterAction?: boolean;
}

export interface AutopilotRunResult {
  finalResult: TutorResult;
  attempts: number;
  stopReason: 'complete' | 'unsafe_step' | 'missing_target' | 'single_action' | 'unchanged_after_action' | 'max_attempts';
}

const SAFE_ACTION_HINTS = ['click', 'open', 'select', 'choose', 'go to', 'type', 'enter', 'search', 'submit', 'scroll'];
const BLOCKED_ACTION_HINTS = ['install', 'enable', 'delete', 'remove', 'buy', 'purchase', 'pay', 'sign in', 'login'];

export async function runAutopilotLoop({
  maxAttempts = 5,
  observe,
  act,
  wait = defaultWait,
  observeAfterAction = true,
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
    const logicalPoint = getClickablePoint(nextStep);
    const point = getPhysicalClickablePoint(nextStep, current);
    
    // Emit cursor move event so Overlay can animate the AI cursor
    await emit('blinky://agent-cursor-move', { x: logicalPoint.x, y: logicalPoint.y, instruction: nextStep.instruction });

    await act(point, nextStep);
    attempts += 1;

    if (!observeAfterAction) {
      return { finalResult: current, attempts, stopReason: 'single_action' };
    }

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
  if (!isConfidentAutopilotMatch(step)) return false;

  const instruction = normalize(step.instruction);
  if (!instruction) return false;
  if (BLOCKED_ACTION_HINTS.some((hint) => instruction.includes(hint))) return false;

  return SAFE_ACTION_HINTS.some((hint) => instruction.includes(hint));
}

function isConfidentAutopilotMatch(step: TutorStep): boolean {
  const match = step.match;
  if (!match) return false;
  if (match.ref && step.target_ref === match.ref) {
    return true;
  }
  if (match.match_method === 'ref' && match.ref && (!step.target_ref || step.target_ref === match.ref)) {
    return true;
  }
  if (match.match_method === 'text') {
    if (isTextEntryStep(step) && isInputLikeMatch(step)) {
      const candidateCount = match.ambiguous_candidate_count ?? 1;
      const score = match.score ?? 0;
      const textSimilarity = match.text_similarity ?? 0;
      return candidateCount <= 2 && (score >= 0.62 || textSimilarity >= 0.62);
    }
    const score = match.score ?? 0;
    const textSimilarity = match.text_similarity ?? 0;
    const ambiguousCandidateCount = match.ambiguous_candidate_count ?? 1;
    return (match.is_exact_text === true && ambiguousCandidateCount <= 1) ||
           (score >= 0.82 || textSimilarity >= 0.86);
  }
  const score = match.score ?? 0;
  const textSimilarity = match.text_similarity ?? 0;
  return (match.is_exact_text === true && (match.ambiguous_candidate_count ?? 1) <= 1) ||
         (score >= 0.82 || textSimilarity >= 0.86);
}

function isTextEntryStep(step: TutorStep): boolean {
  const instruction = normalize(step.instruction);
  return ['type', 'enter', 'input', 'search for'].some((hint) => instruction.includes(hint));
}

function isInputLikeMatch(step: TutorStep): boolean {
  const match = step.match;
  if (!match) return false;

  const controlType = normalize(match.control_type);
  const targetText = normalize(step.target_text);
  const matchText = normalize(match.text);
  const instruction = normalize(step.instruction);
  const searchable = `${targetText} ${matchText} ${instruction}`;

  return (
    ['edit', 'textbox', 'combobox'].includes(controlType) ||
    ['search', 'filter', 'find', 'input', 'text field', 'search bar'].some((hint) => searchable.includes(hint))
  );
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

export function extractTextToType(instruction: string): string | null {
  const normalized = instruction.trim();
  
  // Try matching quotes first
  const quoteMatch = normalized.match(/(?:type|enter|input|search\s+for)\s+['"‘’“”]([^'"‘’“”]+)['"‘’“”]/i);
  if (quoteMatch && quoteMatch[1]) {
    return quoteMatch[1];
  }
  
  // Fallback to matching until prepositions or "and press"
  const fallbackMatch = normalized.match(/(?:type|enter|input|search\s+for)\s+(.+?)(?:\s+(?:into|in|on|to|and\s+press)\b|$)/i);
  if (fallbackMatch && fallbackMatch[1]) {
    return fallbackMatch[1].trim().replace(/^['"‘’“”]+|['"‘’“”]+$/g, '');
  }
  
  return null;
}

export function shouldPressEnterAfterTyping(instruction: string): boolean {
  const normalized = instruction.toLowerCase();
  return normalized.includes('press enter') || normalized.includes('press return') || normalized.includes('submit') || normalized.includes('search');
}

export function isScrollAction(instruction: string): boolean {
  const norm = normalize(instruction);
  if (!/\bscroll\b/.test(norm)) return false;
  const otherVerbs = ['click', 'type', 'enter', 'input', 'search', 'submit', 'select', 'choose', 'go to', 'open'];
  const startsWithOther = otherVerbs.some(verb => norm.startsWith(verb));
  return !startsWithOther;
}

export function getScrollDirection(instruction: string): 'down' | 'up' {
  const norm = normalize(instruction);
  if (norm.includes('scroll up')) {
    return 'up';
  }
  return 'down';
}

export function isClickInstruction(instruction: string): boolean {
  const norm = normalize(instruction);
  return SAFE_ACTION_HINTS.some((hint) => norm.startsWith(hint));
}
