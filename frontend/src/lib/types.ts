export interface OcrItem {
  ref?: string;
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
  control_type?: string;
  source?: string;
  clickable?: boolean;
  input?: boolean;
  automation_id?: string;
  ai_label?: string;
  match_method?: 'ref' | 'text';
  score?: number;
  text_similarity?: number;
  is_exact_text?: boolean;
  ambiguous_candidate_count?: number;
}

export interface TutorStep {
  step: number;
  instruction: string;
  target_ref?: string;
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
    screen_width?: number;
    screen_height?: number;
    path: string;
  };
  elapsed_ms: number;
  provider?: string;
  warnings: string[];
  is_continuation?: boolean;
  app_context?: string;
  agent_action?: {
    success: boolean;
    tool: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface TutorProgress {
  completed_targets: string[];
  completed_instructions: string[];
}

export interface TutorConversationMessage {
  role: 'student' | 'blinky';
  content: string;
}

export interface ChatMessage {
  id: string;
  role: 'student' | 'blinky';
  content: string;
  result?: TutorResult;
}
