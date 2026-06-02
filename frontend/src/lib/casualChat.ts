import type { TutorStep } from './types';

interface CasualChatResponse {
  summary: string;
  steps: TutorStep[];
}

const WELLNESS_CHECKS = new Set([
  'how are you',
  'how are you doing',
  'how r u',
  'how do you do',
  'hows it going',
  'how is it going',
  'whats up',
  'what is up',
  'sup',
]);

const GREETINGS = new Set([
  'hello',
  'hi',
  'hey',
  'good morning',
  'good afternoon',
  'good evening',
]);

const IDENTITY_QUESTIONS = new Set([
  'who are you',
  'what are you',
  'what is your name',
  'tell me about yourself',
  'introduce yourself',
]);

export function getCasualChatResponse(question: string): CasualChatResponse | null {
  const normalized = normalizeQuestion(question);

  if (WELLNESS_CHECKS.has(normalized)) {
    return {
      summary: "I'm doing well. Ask me a software question when you want screen help.",
      steps: [],
    };
  }

  if (IDENTITY_QUESTIONS.has(normalized)) {
    return {
      summary: "I'm Blinky, your desktop tutor. I can chat, and I can guide you through apps when you ask for screen help.",
      steps: [],
    };
  }

  if (GREETINGS.has(normalized)) {
    return {
      summary: "Hi, I'm here. What would you like help with?",
      steps: [],
    };
  }

  return null;
}

function normalizeQuestion(question: string): string {
  return question
    .toLowerCase()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}
