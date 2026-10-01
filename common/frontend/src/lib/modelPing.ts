export interface PingResult {
  ok: boolean;
  provider: string;
  model: string;
  latency_ms: number;
  status_code: number;
  error?: string;
  details?: string;
}

/**
 * Executes a 1-token health check probe against the selected AI provider.
 * Catches decommissioned models (404), invalid keys (401), and rate limits (429) in real time.
 */
export async function pingModel(
  provider: string,
  apiKey: string,
  model?: string,
  customUrl?: string
): Promise<PingResult> {
  const t0 = Date.now();
  const prov = (provider || 'groq').toLowerCase().trim();

  try {
    if (prov === 'groq') {
      const activeModel = model || 'qwen/qwen3.8-27b';
      if (!apiKey?.trim()) {
        return {
          ok: false,
          provider: prov,
          model: activeModel,
          latency_ms: 0,
          status_code: 401,
          error: 'Missing Groq API Key',
          details: 'Please paste your Groq API key.',
        };
      }

      const res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${apiKey.trim()}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: activeModel,
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 1,
        }),
      });

      const latency = Date.now() - t0;
      const data = await res.json().catch(() => ({}));

      if (res.ok) {
        return {
          ok: true,
          provider: prov,
          model: activeModel,
          latency_ms: latency,
          status_code: 200,
          details: `Online (${latency}ms)`,
        };
      }

      const errMsg = data?.error?.message || `HTTP ${res.status}`;
      return {
        ok: false,
        provider: prov,
        model: activeModel,
        latency_ms: latency,
        status_code: res.status,
        error: errMsg,
        details: res.status === 404 ? `Model decommissioned or not found (${activeModel})` : errMsg,
      };
    }

    if (prov === 'deepseek') {
      const activeModel = model || 'deepseek-chat';
      if (!apiKey?.trim()) {
        return {
          ok: false,
          provider: prov,
          model: activeModel,
          latency_ms: 0,
          status_code: 401,
          error: 'Missing DeepSeek API Key',
          details: 'Please paste your DeepSeek API key.',
        };
      }

      const res = await fetch('https://api.deepseek.com/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${apiKey.trim()}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: activeModel,
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 1,
        }),
      });

      const latency = Date.now() - t0;
      const data = await res.json().catch(() => ({}));

      if (res.ok) {
        return {
          ok: true,
          provider: prov,
          model: activeModel,
          latency_ms: latency,
          status_code: 200,
          details: `Online (${latency}ms)`,
        };
      }

      const errMsg = data?.error?.message || `HTTP ${res.status}`;
      return {
        ok: false,
        provider: prov,
        model: activeModel,
        latency_ms: latency,
        status_code: res.status,
        error: errMsg,
        details: errMsg,
      };
    }

    if (prov === 'custom') {
      const activeModel = model || 'default';
      const base = (customUrl || '').replace(/\/+$/, '');
      if (!base) {
        return {
          ok: false,
          provider: prov,
          model: activeModel,
          latency_ms: 0,
          status_code: 400,
          error: 'Missing Custom URL',
          details: 'Please enter custom endpoint URL.',
        };
      }

      const url = base.endsWith('/chat/completions') ? base : `${base}/chat/completions`;
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (apiKey?.trim()) {
        headers['Authorization'] = `Bearer ${apiKey.trim()}`;
      }

      const res = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model: activeModel,
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 1,
        }),
      });

      const latency = Date.now() - t0;
      if (res.ok) {
        return {
          ok: true,
          provider: prov,
          model: activeModel,
          latency_ms: latency,
          status_code: 200,
          details: `Online (${latency}ms)`,
        };
      }

      return {
        ok: false,
        provider: prov,
        model: activeModel,
        latency_ms: latency,
        status_code: res.status,
        error: `HTTP ${res.status}`,
        details: `Endpoint returned HTTP ${res.status}`,
      };
    }

    if (prov === 'gemini') {
      const activeModel = model || 'gemini-2.5-flash';
      if (!apiKey?.trim()) {
        return {
          ok: false,
          provider: prov,
          model: activeModel,
          latency_ms: 0,
          status_code: 401,
          error: 'Missing Gemini API Key',
          details: 'Please paste your Google Gemini API key.',
        };
      }

      const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(activeModel)}:generateContent?key=${encodeURIComponent(apiKey.trim())}`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: 'ping' }] }],
          generationConfig: { maxOutputTokens: 1, temperature: 0.0 },
        }),
      });

      const latency = Date.now() - t0;
      const data = await res.json().catch(() => ({}));

      if (res.ok) {
        return {
          ok: true,
          provider: prov,
          model: activeModel,
          latency_ms: latency,
          status_code: 200,
          details: `Online (${latency}ms)`,
        };
      }

      const errMsg = data?.error?.message || `HTTP ${res.status}`;
      return {
        ok: false,
        provider: prov,
        model: activeModel,
        latency_ms: latency,
        status_code: res.status,
        error: errMsg,
        details: res.status === 404 ? `Model not found or unavailable (${activeModel})` : errMsg,
      };
    }

    return {
      ok: false,
      provider: prov,
      model: model || 'unknown',
      latency_ms: 0,
      status_code: 400,
      error: `Unsupported provider: ${provider}`,
      details: 'Supported: groq, gemini, deepseek, custom',
    };
  } catch (err: any) {
    return {
      ok: false,
      provider: prov,
      model: model || 'unknown',
      latency_ms: Date.now() - t0,
      status_code: 0,
      error: err?.message || 'Network error',
      details: `Failed to connect: ${err?.message || 'Check network connection'}`,
    };
  }
}
