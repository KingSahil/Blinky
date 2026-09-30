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

export interface MobileVectorMatch {
  source_name: string;
  chunk_index: number;
  content: string;
  score: number;
}

/**
 * Tokenizes text into lowercase alphanumeric words.
 */
export function simpleTokenize(text: string): string[] {
  return (text || '').toLowerCase().match(/\b\w+\b/g) || [];
}

/**
 * Calculates normalized term frequencies for a token list.
 */
export function calculateTermFrequencies(tokens: string[]): Record<string, number> {
  if (!tokens || tokens.length === 0) return {};
  const tf: Record<string, number> = {};
  for (const t of tokens) {
    tf[t] = (tf[t] || 0) + 1;
  }
  const total = tokens.length;
  for (const k in tf) {
    tf[k] = tf[k] / total;
  }
  return tf;
}

/**
 * Calculates cosine similarity between two term-frequency maps.
 */
export function calculateCosineSimilarity(tf1: Record<string, number>, tf2: Record<string, number>): number {
  if (!tf1 || !tf2) return 0;
  let dotProduct = 0;
  let mag1Sq = 0;
  let mag2Sq = 0;

  for (const k in tf1) {
    mag1Sq += tf1[k] * tf1[k];
    if (tf2[k]) {
      dotProduct += tf1[k] * tf2[k];
    }
  }
  for (const k in tf2) {
    mag2Sq += tf2[k] * tf2[k];
  }

  const mag1 = Math.sqrt(mag1Sq);
  const mag2 = Math.sqrt(mag2Sq);
  if (mag1 === 0 || mag2 === 0) return 0;
  return dotProduct / (mag1 * mag2);
}

/**
 * Loads all mobile notebooks from Android device storage.
 */
export async function listMobileNotebooks(): Promise<MobileNotebook[]> {
  try {
    const raw = await AsyncStorage.getItem(MOBILE_NOTEBOOKS_STORAGE_KEY);
    if (!raw) {
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
    description: description.trim ? description.trim() : description,
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
 * Searches active document sources in a mobile notebook using Top-K vector cosine similarity.
 */
export function searchMobileVectorChunks(
  notebook: MobileNotebook,
  query: string,
  topK: number = 5
): MobileVectorMatch[] {
  const queryTokens = simpleTokenize(query);
  if (queryTokens.length === 0) return [];
  const queryTf = calculateTermFrequencies(queryTokens);

  const matches: MobileVectorMatch[] = [];
  const activeSources = notebook.sources.filter((s) => s.active);

  for (const src of activeSources) {
    // Chunk source content into 100-word blocks for mobile RAG
    const words = src.content.split(/\s+/);
    const chunkSize = 100;
    const overlap = 20;

    let idx = 0;
    for (let i = 0; i < words.length; i += chunkSize - overlap) {
      const chunkWords = words.slice(i, i + chunkSize);
      const chunkText = chunkWords.join(' ');
      const chunkTokens = simpleTokenize(chunkText);
      const chunkTf = calculateTermFrequencies(chunkTokens);

      const sim = calculateCosineSimilarity(queryTf, chunkTf);
      if (sim > 0) {
        matches.push({
          source_name: src.source_name,
          chunk_index: idx,
          content: chunkText,
          score: Math.round(sim * 100) / 100,
        });
      }
      idx++;
      if (i + chunkSize >= words.length) break;
    }
  }

  matches.sort((a, b) => b.score - a.score);
  return matches.slice(0, topK);
}

/**
 * Builds grounded LLM context payload from active mobile document sources (or Top-K vector matches).
 */
export function buildMobileOkfContext(
  notebook: MobileNotebook,
  query: string,
  useVectorSearch: boolean = false
): { systemPrompt: string; userPrompt: string; matchCount: number } {
  const activeSources = notebook.sources.filter((s) => s.active);
  let payloadText = '';
  let matchCount = 0;

  if (useVectorSearch) {
    const vMatches = searchMobileVectorChunks(notebook, query, 5);
    matchCount = vMatches.length;
    if (vMatches.length > 0) {
      payloadText = vMatches
        .map(
          (m) =>
            `### VECTOR CHUNK: ${m.source_name} (Part ${m.chunk_index + 1}, Relevance: ${Math.round(m.score * 100)}%)\n${m.content}`
        )
        .join('\n\n');
    } else {
      payloadText = activeSources.map((s) => s.okf_block).join('\n\n');
      matchCount = activeSources.length;
    }
  } else {
    payloadText = activeSources.map((s) => s.okf_block).join('\n\n');
    matchCount = activeSources.length;
  }

  const systemPrompt =
    'You are Blinky Mobile AI, a grounded research assistant.\n' +
    'Answer queries strictly using the provided Mobile Notebook Document Sources.\n' +
    'Cite your sources using exact inline badges: [Source: filename.pdf].\n';

  const userPrompt =
    `--- MOBILE NOTEBOOK SOURCES ---\n${payloadText || '[No active sources selected]'}\n\n` +
    `--- USER QUERY ---\n${query.trim()}`;

  return { systemPrompt, userPrompt, matchCount };
}

/**
 * Syncs notebooks and sources pulled from Desktop Blinky into local device storage.
 */
export async function syncPcNotebooks(pcData: any): Promise<void> {
  try {
    if (!pcData) return;
    const existing = await listMobileNotebooks();
    const existingMap = new Map<string, MobileNotebook>();
    for (const nb of existing) {
      existingMap.set(nb.id, nb);
    }

    const pcNotebookList: any[] = Array.isArray(pcData)
      ? pcData
      : typeof pcData === 'object'
      ? Object.values(pcData)
      : [];

    for (const rawNb of pcNotebookList) {
      if (!rawNb || typeof rawNb !== 'object' || !rawNb.id) continue;

      const convertedSources: MobileSource[] = (rawNb.sources || []).map((s: any) => {
        const ext = s.file_type || (s.source_name || s.name || '').split('.').pop()?.toLowerCase() || 'txt';
        const content = s.raw_text || s.content || s.okf_content || '';
        const name = s.source_name || s.name || 'document.txt';
        return {
          id: s.id || `msrc_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
          source_name: name,
          file_type: ext,
          word_count: s.word_count || Math.round(content.length / 5),
          content: content,
          okf_block: s.okf_content || `### SOURCE: ${name}\nType: ${ext.toUpperCase()}\n\n${content}\n`,
          active: s.active !== false,
          created_at: s.created_at || Date.now(),
        };
      });

      const mergedNb: MobileNotebook = {
        id: rawNb.id,
        title: rawNb.title || 'Synced PC Hub',
        description: rawNb.description || '',
        created_at: rawNb.created_at || Date.now(),
        updated_at: rawNb.updated_at || Date.now(),
        sources: convertedSources,
      };

      existingMap.set(rawNb.id, mergedNb);
    }

    const mergedList = Array.from(existingMap.values());
    await saveMobileNotebooks(mergedList);
    console.log(`[MobileRAG] Successfully synced ${pcNotebookList.length} PC notebooks.`);
  } catch (err) {
    console.warn('[MobileRAG] Failed to sync PC notebooks:', err);
  }
}
