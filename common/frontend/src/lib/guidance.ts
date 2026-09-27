import type { TutorStep } from './types';

export interface SummaryVisibilityInput {
  isRunning: boolean;
  status: string;
  defaultStatus: string;
  steps: Pick<TutorStep, 'instruction'>[];
  forceShow?: boolean;
}

export interface CompletedGuideProgress {
  completed_targets: string[];
  completed_instructions: string[];
}

export function getDisplaySteps(steps: TutorStep[]): TutorStep[] {
  return steps.filter((step) => step.instruction.trim());
}

export function getPendingSteps(steps: TutorStep[], progress: CompletedGuideProgress): TutorStep[] {
  return getDisplaySteps(steps).filter((step) => !isCompletedStep(step, progress));
}

export function getCurrentGuideSteps(steps: TutorStep[], progress: CompletedGuideProgress): TutorStep[] {
  const pendingSteps = getPendingSteps(steps, progress);
  if (pendingSteps.length === 0) return [];
  return [pendingSteps[0]];
}

export function getHighlightSteps(steps: TutorStep[]): TutorStep[] {
  const nextStep = steps.find((step) => {
    const hasTargetHandle = Boolean(step.target_text?.trim() || step.target_ref?.trim());
    if (!step.instruction?.trim() || !hasTargetHandle) return false;
    if (!step.match) return false;
    return true;
  });
  return nextStep ? [nextStep] : [];
}

export function getWorkflowContinuationReadback(startedWithReadback: boolean): boolean {
  return startedWithReadback;
}

export function shouldCompleteStepOnHighlightClick(step: Pick<TutorStep, 'instruction' | 'target_text' | 'match'>, originalQuery = ''): boolean {
  if (isLocatorOnlyText(originalQuery)) return false;

  const instruction = normalizeGuideText(step.instruction);
  const targetText = normalizeGuideText(step.target_text);
  const controlType = normalizeGuideText(step.match?.control_type);

  if (isLocatorOnlyText(instruction)) return false;

  const wantsTextEntry = [
    'type',
    'enter',
    'search',
    'filter',
    'find',
    'input',
    'text field',
    'search bar',
  ].some((hint) => instruction.includes(hint));
  const targetIsInput = controlType === 'edit' || controlType === 'textbox' || targetText.includes('search');

  return !(wantsTextEntry || targetIsInput);
}

export function mergeGuideHistory(
  history: TutorStep[],
  currentSteps: TutorStep[],
  progress: CompletedGuideProgress,
): TutorStep[] {
  const completedHistory = getDisplaySteps(history).filter((step) => isCompletedStep(step, progress));
  const nextStep = getDisplaySteps(currentSteps)[0];

  if (!nextStep) {
    return completedHistory;
  }

  if (completedHistory.some((step) => isSameGuideStep(step, nextStep))) {
    return completedHistory;
  }

  const currentHistory = history.find((step) => isSameGuideStep(step, nextStep));
  if (currentHistory && !isCompletedStep(currentHistory, progress)) {
    return [...completedHistory, currentHistory];
  }

  return [...completedHistory, nextStep];
}

function isCompletedStep(step: TutorStep, progress: CompletedGuideProgress): boolean {
  const targetText = normalizeGuideText(step.target_text);
  const instruction = normalizeGuideText(step.instruction);

  const hasCompletedTarget = progress.completed_targets.some((target) => {
    const completedTarget = normalizeGuideText(target);
    return Boolean(completedTarget && targetText && completedTarget === targetText);
  });
  if (hasCompletedTarget) return true;

  return progress.completed_instructions.some((completedInstruction) => {
    const completed = normalizeGuideText(completedInstruction);
    return Boolean(completed && instruction && completed === instruction);
  });
}

function normalizeGuideText(value: string | undefined): string {
  return (value || '').trim().toLowerCase().replace(/\s+/g, ' ');
}

function isLocatorOnlyText(value: string | undefined): boolean {
  const text = normalizeGuideText(value);
  return [
    'where is',
    'where are',
    'show me',
    'point to',
    'locate',
    'highlight',
    'where can i find',
    'where do i find',
  ].some((hint) => text.includes(hint));
}

function isSameGuideStep(left: TutorStep, right: TutorStep): boolean {
  const leftInstruction = normalizeGuideText(left.instruction);
  const rightInstruction = normalizeGuideText(right.instruction);
  const leftTarget = normalizeGuideText(left.target_text);
  const rightTarget = normalizeGuideText(right.target_text);

  return Boolean(leftInstruction && rightInstruction && leftInstruction === rightInstruction && leftTarget === rightTarget);
}

export function shouldShowSummaryBubble({ isRunning, status, defaultStatus, steps, forceShow }: SummaryVisibilityInput): boolean {
  if (isRunning) return true;
  if (forceShow) return status !== defaultStatus;
  if (steps.length > 0) return false;
  return status !== defaultStatus;
}
