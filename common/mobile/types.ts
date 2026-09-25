export type TabScreen = 'Chat' | 'Actions' | 'Files' | 'PC';

export interface Message {
  id: string;
  sender: 'user' | 'blinky';
  text: string;
  timestamp: string;
  progress?: {
    percent: number;
    statusText: string;
    duration: number;
  };
  screenshot_b64?: string;
  steps?: any[];
}

