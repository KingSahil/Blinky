import AsyncStorage from '@react-native-async-storage/async-storage';

export const MOBILE_NOTEBOOKS_STORAGE_KEY = '@blinky_mobile_notebooks_db';

export interface MobileSource {
  id: string;
  source_name: string;
  file_type: string;
  word_count: number;
  content: string;
  okf_block: string;
  active: boolean;
  created_at: number;
}

export interface MobileNotebook {
  id: string;
  title: string;
  description: string;
  created_at: number;
  updated_at: number;
  sources: MobileSource[];
}

/**
 * Loads all mobile notebooks from Android device storage.
 */
export async function listMobileNotebooks(): Promise<MobileNotebook[]> {
  try {
    const raw = await AsyncStorage.getItem(MOBILE_NOTEBOOKS_STORAGE_KEY);
    if (!raw) {
      // Default sample notebook
      const defaultNb: MobileNotebook = {
        id: 'mb_default',
        title: 'Mobile Companion Hub',
        description: 'Documents and notes stored on your phone',
        created_at: Date.now(),
        updated_at: Date.now(),
        sources: [
          {
            id: 'ms_1',
            source_name: 'Getting_Started.md',
            file_type: 'md',
            word_count: 220,
            content: 'Blinky Mobile companion allows document research and PC remote control.',
            okf_block: '### SOURCE: Getting_Started.md\nType: MD\n\nBlinky Mobile companion allows document research and PC remote control.\n',
            active: true,
            created_at: Date.now(),
          },
        ],
      };
      await saveMobileNotebooks([defaultNb]);
      return [defaultNb];
    }
    return JSON.parse(raw) as MobileNotebook[];
  } catch (err) {
    console.warn('[MobileRAG] Error listing mobile notebooks:', err);
    return [];
  }
}

/**
 * Saves updated mobile notebooks array to Android storage.
 */
export async function saveMobileNotebooks(notebooks: MobileNotebook[]): Promise<void> {
  try {
    await AsyncStorage.setItem(MOBILE_NOTEBOOKS_STORAGE_KEY, JSON.stringify(notebooks));
  } catch (err) {
    console.warn('[MobileRAG] Error saving mobile notebooks:', err);
  }
}

/**
 * Creates a new notebook on the mobile device.
 */
export async function createMobileNotebook(title: string, description: string = ''): Promise<MobileNotebook> {
  const notebooks = await listMobileNotebooks();
  const newNb: MobileNotebook = {
    id: `mb_${Date.now()}`,
    title: title.trim() || 'Untitled Notebook',
    description: description.strip ? description.strip() : description,
    created_at: Date.now(),
    updated_at: Date.now(),
    sources: [],
  };
  const updated = [newNb, ...notebooks];
  await saveMobileNotebooks(updated);
  return newNb;
}

/**
 * Adds and indexes a document source into a mobile notebook.
 */
export async function addSourceToMobileNotebook(
  notebookId: string,
  fileName: string,
  rawContent: string,
  fileType: string = 'txt'
): Promise<MobileSource | null> {
  const notebooks = await listMobileNotebooks();
  const nbIndex = notebooks.findIndex((n) => n.id === notebookId);
  if (nbIndex === -1) return null;

  const ext = fileType || fileName.split('.').pop()?.toLowerCase() || 'txt';
  const cleanContent = rawContent.trim();
  const wordCount = Math.round(cleanContent.length / 5);

  const okfBlock = `### SOURCE: ${fileName}\nType: ${ext.toUpperCase()}\n\n${cleanContent}\n`;

  const newSource: MobileSource = {
    id: `msrc_${Date.now()}`,
    source_name: fileName,
    file_type: ext,
    word_count: wordCount,
    content: cleanContent,
    okf_block: okfBlock,
    active: true,
    created_at: Date.now(),
  };

  notebooks[nbIndex].sources = [
    ...notebooks[nbIndex].sources.filter((s) => s.source_name !== fileName),
    newSource,
  ];
  notebooks[nbIndex].updated_at = Date.now();

  await saveMobileNotebooks(notebooks);
  return newSource;
}

/**
 * Builds grounded LLM context payload from active mobile document sources.
 */
export function buildMobileOkfContext(notebook: MobileNotebook, query: string): { systemPrompt: string; userPrompt: string } {
  const activeSources = notebook.sources.filter((s) => s.active);
  const okfBlocks = activeSources.map((s) => s.okf_block).join('\n\n');

  const systemPrompt =
    'You are Blinky Mobile AI, a grounded research assistant.\n' +
    'Answer queries strictly using the provided Mobile Notebook Document Sources.\n' +
    'Cite your sources using exact inline badges: [Source: filename.pdf].\n';

  const userPrompt =
    `--- MOBILE NOTEBOOK SOURCES ---\n${okfBlocks || '[No active sources]'}\n\n` +
    `--- USER QUERY ---\n${query.trim()}`;

  return { systemPrompt, userPrompt };
}
