export interface DynamicModelItem {
  id: string;
  name: string;
  desc?: string;
  badge?: string;
  isCustom?: boolean;
}

const DECOMMISSIONED_GROQ_MODELS = new Set([
  'llama-3.3-70b-versatile',
  'llama-3.2-90b-vision-preview',
  'llama-3.2-11b-vision-preview',
  'meta-llama/llama-4-scout-17b-16e-instruct',
  'qwen/qwen3.6-27b',
]);

export const DEFAULT_GROQ_CATALOG: DynamicModelItem[] = [
  { id: 'qwen/qwen3.8-27b', name: 'Qwen 3.8 27B', badge: 'Recommended Actuator', desc: 'Fast vision & OS computer-use actuator' },
  { id: 'openai/gpt-oss-120b', name: 'GPT-OSS 120B', badge: 'Deep Reasoning', desc: 'Ultra-high reasoning capacity & coding' },
  { id: 'openai/gpt-oss-20b', name: 'GPT-OSS 20B', badge: 'Ultra-Fast', desc: 'Sub-300ms speed for rapid actions' },
  { id: 'llama-3.1-8b-instant', name: 'Llama 3.1 8B Instant', badge: 'Fast', desc: 'Low-latency small model' },
  { id: 'deepseek-r1-distill-llama-70b', name: 'DeepSeek R1 Distill 70B', badge: 'Thinking', desc: 'DeepSeek reasoning distilled on Groq' },
];

export const DEFAULT_GEMINI_CATALOG: DynamicModelItem[] = [
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', badge: 'Recommended RAG', desc: 'Fast multimodal reasoning & high-volume RAG' },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', badge: 'Deep Context', desc: 'Complex reasoning across 2M token context window' },
  { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash', badge: 'Fast Synthesis', desc: 'Ultra-responsive document chunk synthesis' },
  { id: 'gemini-2.0-flash-lite', name: 'Gemini 2.0 Flash Lite', badge: 'Lite', desc: 'Lightweight & quota-friendly' },
  { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash', badge: 'Stable', desc: 'Proven long-context workhorse' },
  { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', badge: 'Pro Reasoning', desc: 'High capability multi-turn analysis' },
  { id: 'gemini-flash-latest', name: 'Gemini Flash Latest', badge: 'Auto-Update', desc: 'Always points to the latest active Flash release' },
];

export const DEFAULT_OLLAMA_CATALOG: DynamicModelItem[] = [
  { id: 'qwen2.5:7b', name: 'Qwen 2.5 7B', badge: 'Recommended', desc: 'Local instruction-following model' },
  { id: 'llama3.2:latest', name: 'Llama 3.2', badge: 'Fast Local', desc: 'Lightweight local model' },
  { id: 'deepseek-r1:8b', name: 'DeepSeek R1 8B', badge: 'Local Reasoning', desc: 'Local reasoning model' },
  { id: 'mistral:latest', name: 'Mistral 7B', badge: 'Stable', desc: 'Fast general-purpose local model' },
  { id: 'llava:latest', name: 'LLaVA', badge: 'Vision', desc: 'Local multimodal vision model' },
];

export const DEFAULT_DEEPSEEK_CATALOG: DynamicModelItem[] = [
  { id: 'deepseek-chat', name: 'DeepSeek-V3 (Chat)', badge: 'Recommended', desc: 'General conversation & code execution' },
  { id: 'deepseek-reasoner', name: 'DeepSeek-R1 (Reasoner)', badge: 'Thinking', desc: 'Deep chain-of-thought reasoning' },
];

export const DEFAULT_MIMO_CATALOG: DynamicModelItem[] = [
  { id: 'mimo-v1', name: 'Mimo v1', badge: 'Active', desc: 'Fast agent action model' },
];

export async function fetchDynamicModels(
  provider: string,
  apiKey?: string,
  customUrl?: string
): Promise<{ models: DynamicModelItem[]; error?: string; isLive: boolean }> {
  const prov = (provider || 'groq').toLowerCase().trim();

  // 1. Google Gemini
  if (prov === 'gemini') {
    if (!apiKey?.trim()) {
      return { models: DEFAULT_GEMINI_CATALOG, isLive: false };
    }
    try {
      const url = `https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(apiKey.trim())}`;
      const res = await fetch(url);
      if (!res.ok) {
        return {
          models: DEFAULT_GEMINI_CATALOG,
          error: `Google API error ${res.status}`,
          isLive: false,
        };
      }
      const data = await res.json();
      const rawList = Array.isArray(data.models) ? data.models : [];
      const filtered = rawList
        .filter((m: any) => {
          const methods = m.supportedGenerationMethods || [];
          return methods.includes('generateContent');
        })
        .map((m: any) => {
          const cleanId = (m.name || '').replace(/^models\//, '');
          const isFlash = cleanId.toLowerCase().includes('flash');
          const isPro = cleanId.toLowerCase().includes('pro');
          return {
            id: cleanId,
            name: m.displayName || cleanId,
            desc: m.description ? m.description.slice(0, 85) + (m.description.length > 85 ? '...' : '') : 'Google Gemini model',
            badge: isFlash ? 'Flash' : isPro ? 'Pro' : 'Gemini',
          };
        });

      if (filtered.length === 0) {
        return { models: DEFAULT_GEMINI_CATALOG, isLive: false };
      }
      return { models: filtered, isLive: true };
    } catch (err: any) {
      return {
        models: DEFAULT_GEMINI_CATALOG,
        error: err?.message || 'Network error fetching Gemini models',
        isLive: false,
      };
    }
  }

  // 2. Groq
  if (prov === 'groq') {
    if (!apiKey?.trim()) {
      return { models: DEFAULT_GROQ_CATALOG, isLive: false };
    }
    try {
      const res = await fetch('https://api.groq.com/openai/v1/models', {
        headers: { Authorization: `Bearer ${apiKey.trim()}` },
      });
      if (!res.ok) {
        return {
          models: DEFAULT_GROQ_CATALOG,
          error: `Groq API error ${res.status}`,
          isLive: false,
        };
      }
      const data = await res.json();
      const rawList = Array.isArray(data.data) ? data.data : [];
      const liveModels: DynamicModelItem[] = rawList
        .filter((m: any) => m.id && !DECOMMISSIONED_GROQ_MODELS.has(m.id))
        .map((m: any) => {
          const id = m.id as string;
          const isQwen = id.toLowerCase().includes('qwen');
          const isGpt = id.toLowerCase().includes('gpt-oss');
          const isLlama = id.toLowerCase().includes('llama');
          const isR1 = id.toLowerCase().includes('r1');
          return {
            id,
            name: id,
            desc: `Groq fast inference endpoint (owned by ${m.owned_by || 'groq'})`,
            badge: isQwen ? 'Actuator' : isGpt ? 'Reasoning' : isR1 ? 'Thinking' : isLlama ? 'Llama' : 'Groq',
          };
        });

      // Sort so recommended actuator models appear first
      liveModels.sort((a, b) => {
        const aScore = a.id.includes('qwen3.8') ? 10 : a.id.includes('gpt-oss') ? 8 : a.id.includes('llama-3.1') ? 6 : 1;
        const bScore = b.id.includes('qwen3.8') ? 10 : b.id.includes('gpt-oss') ? 8 : b.id.includes('llama-3.1') ? 6 : 1;
        return bScore - aScore;
      });

      return { models: liveModels.length > 0 ? liveModels : DEFAULT_GROQ_CATALOG, isLive: true };
    } catch (err: any) {
      return {
        models: DEFAULT_GROQ_CATALOG,
        error: err?.message || 'Network error fetching Groq models',
        isLive: false,
      };
    }
  }

  // 3. Ollama (local endpoint)
  if (prov === 'ollama') {
    try {
      const res = await fetch('http://localhost:11434/api/tags');
      if (res.ok) {
        const data = await res.json();
        const rawList = Array.isArray(data.models) ? data.models : [];
        const models: DynamicModelItem[] = rawList.map((m: any) => ({
          id: m.name || m.model,
          name: m.name || m.model,
          desc: `Local Ollama model (${Math.round((m.size || 0) / (1024 * 1024))} MB)`,
          badge: 'Local',
        }));
        if (models.length > 0) return { models, isLive: true };
      }
    } catch {
      // Fallback
    }
    return { models: DEFAULT_OLLAMA_CATALOG, isLive: false };
  }

  // 4. DeepSeek
  if (prov === 'deepseek') {
    if (!apiKey?.trim()) {
      return { models: DEFAULT_DEEPSEEK_CATALOG, isLive: false };
    }
    try {
      const res = await fetch('https://api.deepseek.com/models', {
        headers: { Authorization: `Bearer ${apiKey.trim()}` },
      });
      if (res.ok) {
        const data = await res.json();
        const rawList = Array.isArray(data.data) ? data.data : [];
        const models: DynamicModelItem[] = rawList.map((m: any) => ({
          id: m.id,
          name: m.id,
          desc: 'DeepSeek model',
          badge: m.id.includes('reasoner') ? 'Thinking' : 'Chat',
        }));
        if (models.length > 0) return { models, isLive: true };
      }
    } catch {
      // Fallback
    }
    return { models: DEFAULT_DEEPSEEK_CATALOG, isLive: false };
  }

  // 5. Mimo
  if (prov === 'mimo') {
    return { models: DEFAULT_MIMO_CATALOG, isLive: false };
  }

  // 6. Custom OpenAI compatible
  if (prov === 'custom') {
    const base = (customUrl || '').replace(/\/+$/, '');
    if (base) {
      try {
        const url = base.endsWith('/models') ? base : `${base}/models`;
        const headers: Record<string, string> = {};
        if (apiKey?.trim()) headers['Authorization'] = `Bearer ${apiKey.trim()}`;
        const res = await fetch(url, { headers });
        if (res.ok) {
          const data = await res.json();
          const rawList = Array.isArray(data.data) ? data.data : [];
          const models: DynamicModelItem[] = rawList.map((m: any) => ({
            id: m.id,
            name: m.id,
            desc: 'Custom OpenAI-compatible model',
            badge: 'Custom',
          }));
          if (models.length > 0) return { models, isLive: true };
        }
      } catch {
        // Fallback
      }
    }
    return {
      models: [{ id: 'default', name: 'Custom Default', desc: 'Custom OpenAI endpoint default model', badge: 'Custom' }],
      isLive: false,
    };
  }

  return { models: DEFAULT_GROQ_CATALOG, isLive: false };
}
