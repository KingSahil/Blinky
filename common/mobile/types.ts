export type TabScreen = 'Chat' | 'Actions' | 'Files' | 'PC' | 'Notebook';

export interface AttachedFile {
  uri: string;
  name: string;
  type?: string;
  size?: number;
  mimeType?: string;
  base64?: string;
}

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
  attachedFile?: AttachedFile;
  attachedFiles?: AttachedFile[];
  steps?: any[];
}

