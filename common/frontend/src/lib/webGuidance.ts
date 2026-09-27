import type { TutorConversationMessage, TutorProgress, TutorResult } from './types';

interface WebGuidanceInput {
  query: string;
  previousQuestion?: string;
  progress: TutorProgress;
  conversationHistory: TutorConversationMessage[];
  runAgentQuery: (query: string) => Promise<TutorResult>;
  runTutor: (
    question: string,
    previousQuestion: string | undefined,
    progress: TutorProgress,
    conversationHistory: TutorConversationMessage[],
    webSearchEnabled?: boolean,
  ) => Promise<TutorResult>;
}

export async function runWebActionThenScreenGuidance({
  query,
  previousQuestion,
  progress,
  conversationHistory,
  runAgentQuery,
  runTutor,
}: WebGuidanceInput): Promise<TutorResult> {
  const browserResult = await runAgentQuery(query);

  try {
    return await runTutor(query, previousQuestion, progress, conversationHistory, true);
  } catch {
    return browserResult;
  }
}
