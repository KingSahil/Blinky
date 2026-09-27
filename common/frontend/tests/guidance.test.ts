import { describe, expect, test } from 'bun:test';
import {
  getCurrentGuideSteps,
  getDisplaySteps,
  getHighlightSteps,
  getPendingSteps,
  getWorkflowContinuationReadback,
  mergeGuideHistory,
  shouldCompleteStepOnHighlightClick,
  shouldShowSummaryBubble,
} from '../src/lib/guidance';

describe('getDisplaySteps', () => {
  test('keeps unmatched future workflow steps in the action guide', () => {
    const steps = [
      {
        step: 1,
        instruction: 'Click Extensions in the left activity bar.',
        target_text: 'Extensions',
        match: {
          text: 'Extensions',
          x: 20,
          y: 80,
          width: 100,
          height: 24,
          confidence: 0.9,
        },
      },
      {
        step: 2,
        instruction: 'Search for the extension by name.',
        target_text: '',
        match: null,
      },
    ];

    expect(getDisplaySteps(steps)).toEqual(steps);
  });
});

describe('getHighlightSteps', () => {
  test('removes steps without an exact target', () => {
    expect(
      getHighlightSteps([
        {
          step: 1,
          instruction: 'Open the relevant panel or menu and ask again.',
          target_text: '',
          match: {
            text: 'Settings',
            x: 10,
            y: 10,
            width: 20,
            height: 20,
            confidence: 0.8,
            control_type: 'Image',
          },
        },
      ]),
    ).toEqual([]);
  });

  test('keeps matched app-control guidance', () => {
    const steps = [
      {
        step: 1,
        instruction: 'Click Extensions in the left activity bar.',
        target_text: 'Extensions',
        match: {
          text: 'Extensions',
          x: 20,
          y: 80,
          width: 100,
          height: 24,
          confidence: 0.9,
        },
      },
    ];

    expect(getHighlightSteps(steps)).toEqual(steps);
  });

  test('keeps ref-only matched guidance', () => {
    const steps = [
      {
        step: 1,
        instruction: 'Click the sidebar button.',
        target_ref: '@e4',
        target_text: '',
        match: {
          ref: '@e4',
          text: '',
          x: 16,
          y: 170,
          width: 24,
          height: 24,
          confidence: 1,
          match_method: 'ref' as const,
        },
      },
    ];

    expect(getHighlightSteps(steps)).toEqual(steps);
  });

  test('highlights only the next matched step in a workflow', () => {
    const steps = [
      {
        step: 1,
        instruction: 'Click Extensions in the left activity bar.',
        target_text: 'Extensions',
        match: {
          text: 'Extensions',
          x: 20,
          y: 80,
          width: 24,
          height: 24,
          confidence: 0.9,
        },
      },
      {
        step: 2,
        instruction: 'Click Install.',
        target_text: 'Install',
        match: {
          text: 'Install',
          x: 380,
          y: 220,
          width: 68,
          height: 28,
          confidence: 0.9,
        },
      },
    ];

    expect(getHighlightSteps(steps)).toEqual([steps[0]]);
  });
});

describe('getPendingSteps', () => {
  test('removes steps whose target was already completed', () => {
    const steps = [
      {
        step: 1,
        instruction: 'Click the Extensions button on the left sidebar.',
        target_text: 'Extensions',
        match: {
          text: 'Extensions',
          x: 20,
          y: 80,
          width: 24,
          height: 24,
          confidence: 0.9,
        },
      },
      {
        step: 2,
        instruction: 'Click Install.',
        target_text: 'Install',
        match: {
          text: 'Install',
          x: 380,
          y: 220,
          width: 68,
          height: 28,
          confidence: 0.9,
        },
      },
    ];

    expect(
      getPendingSteps(steps, {
        completed_targets: ['Extensions'],
        completed_instructions: [],
      }),
    ).toEqual([steps[1]]);
  });
});

describe('getCurrentGuideSteps', () => {
  test('shows only the next uncompleted step', () => {
    const steps = [
      { step: 1, instruction: 'Open the panel.', target_text: '', match: null },
      { step: 2, instruction: 'Search for the item.', target_text: '', match: null },
    ];

    expect(
      getCurrentGuideSteps(steps, {
        completed_targets: [],
        completed_instructions: [],
      }),
    ).toEqual([steps[0]]);
  });

  test('does not skip an earlier pending step just because a later target is visible', () => {
    const steps = [
      {
        step: 1,
        instruction: 'Click the Extensions button on the left sidebar.',
        target_text: 'Extensions',
        match: {
          text: 'Extensions',
          x: 20,
          y: 80,
          width: 24,
          height: 24,
          confidence: 0.9,
        },
      },
      {
        step: 2,
        instruction: 'Search for code runner.',
        target_text: '',
        match: null,
      },
      {
        step: 3,
        instruction: 'Click Install.',
        target_text: 'Install',
        match: {
          text: 'Install',
          x: 380,
          y: 220,
          width: 68,
          height: 28,
          confidence: 0.9,
        },
      },
    ];

    expect(
      getCurrentGuideSteps(steps, {
        completed_targets: ['Extensions'],
        completed_instructions: ['Click the Extensions button on the left sidebar.'],
      }),
    ).toEqual([steps[1]]);
  });
});

describe('mergeGuideHistory', () => {
  test('keeps completed guide steps and appends the freshly-read next step', () => {
    const completedStep = {
      step: 1,
      instruction: 'Click the Extensions button on the left sidebar.',
      target_text: 'Extensions',
      match: {
        text: 'Extensions',
        x: 18,
        y: 170,
        width: 26,
        height: 26,
        confidence: 0.8,
      },
    };
    const nextStep = {
      step: 1,
      instruction: "Type 'Code Runner' in the Extensions Marketplace search bar.",
      target_text: 'Search Extensions in Marketplace',
      match: {
        text: 'Search Extensions in Marketplace',
        x: 80,
        y: 90,
        width: 300,
        height: 30,
        confidence: 0.95,
      },
    };

    expect(
      mergeGuideHistory([completedStep], [nextStep], {
        completed_targets: ['Extensions'],
        completed_instructions: ['Click the Extensions button on the left sidebar.'],
      }),
    ).toEqual([completedStep, nextStep]);
  });

  test('does not duplicate the same current step across refreshes', () => {
    const currentStep = {
      step: 1,
      instruction: "Type 'Code Runner' in the Extensions Marketplace search bar.",
      target_text: 'Search Extensions in Marketplace',
      match: null,
    };

    expect(
      mergeGuideHistory([currentStep], [currentStep], {
        completed_targets: [],
        completed_instructions: [],
      }),
    ).toEqual([currentStep]);
  });
});

describe('shouldShowSummaryBubble', () => {
  test('hides summary for actionable task guides', () => {
    expect(
      shouldShowSummaryBubble({
        isRunning: false,
        status: 'Use the active app extension workflow.',
        defaultStatus: 'Ask anything on your screen',
        steps: [{ step: 1, instruction: 'Click Extensions.', target_text: 'Extensions' }],
      }),
    ).toBe(false);
  });

  test('can show a completion summary while retaining guide history', () => {
    expect(
      shouldShowSummaryBubble({
        isRunning: false,
        status: 'The requested action is complete.',
        defaultStatus: 'Ask anything on your screen',
        steps: [{ step: 1, instruction: 'Click Install.', target_text: 'Install' }],
        forceShow: true,
      }),
    ).toBe(true);
  });

  test('shows summary for informational responses and loading state', () => {
    expect(
      shouldShowSummaryBubble({
        isRunning: false,
        status: 'Hi, I am ready to help.',
        defaultStatus: 'Ask anything on your screen',
        steps: [],
      }),
    ).toBe(true);

    expect(
      shouldShowSummaryBubble({
        isRunning: true,
        status: 'Thinking...',
        defaultStatus: 'Ask anything on your screen',
        steps: [],
      }),
    ).toBe(true);
  });
});

describe('getWorkflowContinuationReadback', () => {
  test('keeps typed workflows silent when a highlighted target is clicked', () => {
    expect(getWorkflowContinuationReadback(false)).toBe(false);
  });

  test('continues voice readback for workflows that started with spoken input', () => {
    expect(getWorkflowContinuationReadback(true)).toBe(true);
  });
});

describe('shouldCompleteStepOnHighlightClick', () => {
  test('does not complete text-entry steps just because the input highlight was clicked', () => {
    expect(
      shouldCompleteStepOnHighlightClick({
        step: 2,
        instruction: "Type 'Code Runner' in the Extensions Marketplace search bar.",
        target_text: 'Search Extensions in Marketplace',
        match: {
          text: 'Search Extensions in Marketplace',
          x: 80,
          y: 90,
          width: 300,
          height: 30,
          confidence: 0.95,
          control_type: 'Edit',
        },
      }),
    ).toBe(false);
  });

  test('completes click-only steps when the highlighted target is clicked', () => {
    expect(
      shouldCompleteStepOnHighlightClick({
        step: 1,
        instruction: 'Click the Extensions button on the left sidebar.',
        target_text: 'Extensions',
        match: {
          text: 'Extensions',
          x: 18,
          y: 170,
          width: 26,
          height: 26,
          confidence: 0.9,
          control_type: 'Button',
        },
      }),
    ).toBe(true);
  });

  test('does not complete locator-only highlight steps', () => {
    expect(
      shouldCompleteStepOnHighlightClick({
        step: 1,
        instruction: 'Show me where the Extensions button is on the left sidebar.',
        target_text: 'Extensions',
        match: {
          text: 'Extensions',
          x: 18,
          y: 170,
          width: 26,
          height: 26,
          confidence: 0.9,
          control_type: 'Button',
        },
      }),
    ).toBe(false);
  });

  test('does not complete click steps for locator-only user questions', () => {
    expect(
      shouldCompleteStepOnHighlightClick(
        {
          step: 1,
          instruction: 'Click the Extensions icon on the left sidebar.',
          target_text: 'Extensions',
          match: {
            text: 'Extensions',
            x: 18,
            y: 170,
            width: 26,
            height: 26,
            confidence: 0.9,
            control_type: 'Button',
          },
        },
        'where is the extension button',
      ),
    ).toBe(false);
  });

  test('keeps click steps completable for workflow user questions', () => {
    expect(
      shouldCompleteStepOnHighlightClick(
        {
          step: 1,
          instruction: 'Click the Extensions icon on the left sidebar.',
          target_text: 'Extensions',
          match: {
            text: 'Extensions',
            x: 18,
            y: 170,
            width: 26,
            height: 26,
            confidence: 0.9,
            control_type: 'Button',
          },
        },
        'how to install code runner extension',
      ),
    ).toBe(true);
  });
});
