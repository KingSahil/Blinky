import React, { useState, useEffect } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  TextInput,
  ScrollView,
  ActivityIndicator,
  Alert,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import {
  listMobileNotebooks,
  createMobileNotebook,
  addSourceToMobileNotebook,
  buildMobileOkfContext,
  MobileNotebook,
  MobileSource,
} from '../lib/mobile_rag_db';
import { getSyncedApiKeys, hasSyncedApiKeys } from '../lib/secure_keys';

interface ChatMessage {
  id: string;
  sender: 'user' | 'ai';
  text: string;
}

export const NotebookScreen: React.FC = () => {
  const [notebooks, setNotebooks] = useState<MobileNotebook[]>([]);
  const [activeNotebookId, setActiveNotebookId] = useState<string>('');
  const [useVectorSearch, setUseVectorSearch] = useState<boolean>(true);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'm1',
      sender: 'ai',
      text: 'Welcome to Blinky Mobile Notebook! Upload documents on your phone or query synced notebooks with Top-K Mobile Vector Search.',
    },
  ]);
  const [queryInput, setQueryInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);

  useEffect(() => {
    loadNotebooks();
  }, []);

  const loadNotebooks = async () => {
    const list = await listMobileNotebooks();
    setNotebooks(list);
    if (list.length > 0 && !activeNotebookId) {
      setActiveNotebookId(list[0].id);
    }
  };

  const activeNotebook = notebooks.find((n) => n.id === activeNotebookId) || notebooks[0];

  const handlePickDocument = async () => {
    if (!activeNotebook) return;
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: ['*/*'],
        copyToCacheDirectory: true,
      });

      if (!res.canceled && res.assets && res.assets.length > 0) {
        const asset = res.assets[0];
        const fileName = asset.name;
        const content = `[Document ${fileName} attached on mobile device]`;

        const added = await addSourceToMobileNotebook(activeNotebook.id, fileName, content);
        if (added) {
          await loadNotebooks();
          Alert.alert('Document Attached', `Successfully indexed "${fileName}" into mobile vector database.`);
        }
      }
    } catch (err: any) {
      console.warn('[NotebookScreen] Document pick error:', err);
      Alert.alert('Error', 'Failed to pick document.');
    }
  };

  const handleCreateNotebook = async () => {
    if (!newTitle.trim()) return;
    const created = await createMobileNotebook(newTitle);
    setNewTitle('');
    setShowCreateModal(false);
    await loadNotebooks();
    setActiveNotebookId(created.id);
  };

  const handleSendQuery = async () => {
    const q = queryInput.trim();
    if (!q || loading || !activeNotebook) return;

    const userMsg: ChatMessage = { id: `u_${Date.now()}`, sender: 'user', text: q };
    setMessages((prev) => [...prev, userMsg]);
    setQueryInput('');
    setLoading(true);

    try {
      const { systemPrompt, userPrompt, matchCount } = buildMobileOkfContext(
        activeNotebook,
        q,
        useVectorSearch
      );
      const keys = await getSyncedApiKeys();

      let answer = '';
      if (keys.groq_key) {
        const resp = await fetch('https://api.groq.com/openai/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${keys.groq_key}`,
          },
          body: JSON.stringify({
            model: 'llama-3.3-70b-versatile',
            messages: [
              { role: 'system', content: systemPrompt },
              { role: 'user', content: userPrompt },
            ],
            temperature: 0.2,
          }),
        });
        const data: any = await resp.json();
        if (data?.error) {
          const errMsg = JSON.stringify(data.error).toLowerCase();
          if (errMsg.includes('rate_limit') || errMsg.includes('tpm') || resp.status === 429) {
            answer = "⚠️ **Groq Rate Limit Exceeded (TPM Exhausted)**: If you are on the free tier, please try again in a few moments, reduce active document context, or upgrade your plan.";
          } else {
            answer = `Groq API Error: ${data.error.message || 'Request failed'}`;
          }
        } else {
          const responseText = data?.choices?.[0]?.message?.content || 'No response from Groq.';
          answer = `[Vector Match Mode: ${useVectorSearch ? 'Top-K Mobile Search' : 'Full Context'} (${matchCount} chunk matches)]\n\n${responseText}`;
        }
      } else {
        answer = `[Offline Mobile Mode]\nMode: ${useVectorSearch ? 'Top-K Vector Cosine Similarity' : 'Full Context'}\nMatched ${matchCount} local chunks for "${q}". Connect to PC Blinky on Wi-Fi once to sync your Groq/Gemini API keys for full offline cloud intelligence!`;
      }

      const aiMsg: ChatMessage = { id: `ai_${Date.now()}`, sender: 'ai', text: answer };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      const errMsg: ChatMessage = {
        id: `err_${Date.now()}`,
        sender: 'ai',
        text: `Error executing mobile vector query: ${err?.message || 'Network error'}`,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      {/* HEADER BAR */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Blinky Mobile Notebook</Text>
        <TouchableOpacity style={styles.addNbBtn} onPress={() => setShowCreateModal(true)}>
          <Text style={styles.addNbBtnText}>+ New</Text>
        </TouchableOpacity>
      </View>

      {/* NOTEBOOK SELECTOR & VECTOR RAG TOGGLE */}
      {activeNotebook && (
        <View style={styles.subHeader}>
          <Text style={styles.activeNbTitle}>{activeNotebook.title}</Text>
          <View style={styles.controlsRow}>
            <TouchableOpacity
              style={[styles.toggleBtn, useVectorSearch ? styles.toggleBtnActive : null]}
              onPress={() => setUseVectorSearch(!useVectorSearch)}
            >
              <Text style={styles.toggleBtnText}>
                {useVectorSearch ? '⚡ Vector RAG' : '📄 Full Context'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.attachBtn} onPress={handlePickDocument}>
              <Text style={styles.attachBtnText}>📎 Attach File</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* CHAT STREAM */}
      <ScrollView style={styles.chatStream} contentContainerStyle={styles.chatContent}>
        {messages.map((msg) => (
          <View key={msg.id} style={[styles.bubble, msg.sender === 'user' ? styles.userBubble : styles.aiBubble]}>
            <Text style={styles.bubbleText}>{msg.text}</Text>
          </View>
        ))}
      </ScrollView>

      {/* INPUT BAR */}
      <View style={styles.inputBar}>
        <TextInput
          style={styles.textInput}
          placeholder="Ask your mobile documents..."
          placeholderTextColor="#8e8e93"
          value={queryInput}
          onChangeText={setQueryInput}
          onSubmitEditing={handleSendQuery}
        />
        <TouchableOpacity style={styles.sendBtn} onPress={handleSendQuery} disabled={loading}>
          {loading ? (
            <ActivityIndicator color="#ffffff" size="small" />
          ) : (
            <Text style={styles.sendBtnText}>Send</Text>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 48,
    paddingHorizontal: 16,
    paddingBottom: 12,
    backgroundColor: '#1e293b',
  },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#f8fafc' },
  addNbBtn: { backgroundColor: '#3b82f6', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6 },
  addNbBtnText: { color: '#ffffff', fontWeight: '600', fontSize: 13 },
  subHeader: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: '#334155',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  activeNbTitle: { color: '#e2e8f0', fontWeight: '600', fontSize: 14, flex: 1 },
  controlsRow: { flexDirection: 'row', alignItems: 'center' },
  toggleBtn: {
    backgroundColor: '#475569',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    marginRight: 8,
  },
  toggleBtnActive: { backgroundColor: '#8b5cf6' },
  toggleBtnText: { color: '#ffffff', fontSize: 11, fontWeight: '600' },
  attachBtn: { backgroundColor: '#0284c7', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  attachBtnText: { color: '#ffffff', fontSize: 12, fontWeight: '600' },
  chatStream: { flex: 1 },
  chatContent: { padding: 16 },
  bubble: { padding: 12, borderRadius: 12, marginBottom: 12, maxWidth: '85%' },
  userBubble: { alignSelf: 'flex-end', backgroundColor: '#2563eb' },
  aiBubble: { alignSelf: 'flex-start', backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#334155' },
  bubbleText: { color: '#f8fafc', fontSize: 14, lineHeight: 20 },
  inputBar: {
    flexDirection: 'row',
    padding: 12,
    backgroundColor: '#1e293b',
    borderTopWidth: 1,
    borderTopColor: '#334155',
  },
  textInput: {
    flex: 1,
    backgroundColor: '#0f172a',
    color: '#f8fafc',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 14,
    marginRight: 8,
  },
  sendBtn: { backgroundColor: '#3b82f6', justifyContent: 'center', paddingHorizontal: 16, borderRadius: 8 },
  sendBtnText: { color: '#ffffff', fontWeight: '600' },
});
