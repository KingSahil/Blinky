export interface OcrItem {
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
}

export interface TutorStep {
  step: number;
  instruction: string;
  target_text: string;
  match?: OcrItem | null;
}

export interface TutorResult {
  summary: string;
  steps: TutorStep[];
  active_app: {
    title: string;
    process: string;
    supported: boolean;
  };
  ocr: {
    count: number;
    items: OcrItem[];
  };
  screenshot?: {
    width: number;
    height: number;
    path: string;
  };
  elapsed_ms: number;
  warnings: string[];
}

export interface ChatMessage {
  id: string;
  role: 'student' | 'clicky';
  content: string;
  result?: TutorResult;
}
