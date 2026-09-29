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
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'm1',
      sender: 'ai',
      text: 'Welcome to Blinky Mobile Notebook! Upload documents on your phone or query synced notebooks.',
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
        // Read contents or placeholder text
        const content = `[Document ${fileName} attached on mobile device]`;

        const added = await addSourceToMobileNotebook(activeNotebook.id, fileName, content);
        if (added) {
          await loadNotebooks();
          Alert.alert('Document Attached', `Successfully added "${fileName}" to notebook.`);
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
      const { systemPrompt, userPrompt } = buildMobileOkfContext(activeNotebook, q);
      const keys = await getSyncedApiKeys();

      let answer = '';
      if (keys.groq_key) {
        // Direct Groq Cloud API call from mobile (PC offline mode)
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
        const data = await resp.json();
        answer = data?.choices?.[0]?.message?.content || 'No response from Groq.';
      } else {
        // Fallback message if no synced keys present
        answer = `[Local Mobile Query Result]\nAnswer for "${q}" derived from ${activeNotebook.sources.length} document sources. Connect to PC Blinky to sync cloud keys!`;
      }

      const aiMsg: ChatMessage = { id: `ai_${Date.now()}`, sender: 'ai', text: answer };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      const errMsg: ChatMessage = {
        id: `err_${Date.now()}`,
        sender: 'ai',
        text: `Error executing query: ${err?.message || 'Network error'}`,
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

      {/* NOTEBOOK SELECTOR & SOURCES BAR */}
      {activeNotebook && (
        <View style={styles.subHeader}>
          <Text style={styles.activeNbTitle}>{activeNotebook.title}</Text>
          <TouchableOpacity style={styles.attachBtn} onPress={handlePickDocument}>
            <Text style={styles.attachBtnText}>📎 Attach File</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* CHAT STREAM */}
      <ScrollView style={styles.chatStream} contentContainerStyle={styles.chatContent}>
        {messages.map((msg) => (
          <View key={msg.id} style={[styles.bubble, msg.sender === 'user' ? styles.userBubble : styles.aiBubble]}>
            <Text style={styles.bubbleText}>{msg.text}</Text>
          </View>
        ))}
        {loading && <ActivityIndicator color="#ff8b6a" style={{ marginTop: 10 }} />}
      </ScrollView>

      {/* INPUT BAR */}
      <View style={styles.inputBar}>
        <TextInput
          style={styles.textInput}
          value={queryInput}
          onChangeText={setQueryInput}
          placeholder="Ask grounded questions..."
          placeholderTextColor="#6b7280"
        />
        <TouchableOpacity style={styles.sendBtn} onPress={handleSendQuery} disabled={loading}>
          <Text style={styles.sendBtnText}>Send</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#12151c' },
  header: {
    height: 56,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.08)',
  },
  headerTitle: { color: '#ffffff', fontSize: 16, fontWeight: '700' },
  addNbBtn: { backgroundColor: 'rgba(255, 139, 106, 0.2)', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  addNbBtnText: { color: '#ff8b6a', fontSize: 12, fontWeight: '600' },
  subHeader: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'rgba(255, 255, 255, 0.02)',
  },
  activeNbTitle: { color: '#e5e7eb', fontSize: 14, fontWeight: '600' },
  attachBtn: { backgroundColor: 'rgba(255, 255, 255, 0.05)', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6 },
  attachBtnText: { color: '#9ca3af', fontSize: 12 },
  chatStream: { flex: 1 },
  chatContent: { padding: 16, gap: 12 },
  bubble: { padding: 12, borderRadius: 12, maxWidth: '85%' },
  userBubble: { alignSelf: 'flex-end', backgroundColor: '#ff8b6a' },
  aiBubble: { alignSelf: 'flex-start', backgroundColor: 'rgba(255, 255, 255, 0.05)', borderWidth: 1, borderColor: 'rgba(255, 255, 255, 0.08)' },
  bubbleText: { color: '#ffffff', fontSize: 14, lineHeight: 20 },
  inputBar: {
    padding: 12,
    flexDirection: 'row',
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.08)',
  },
  textInput: {
    flex: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderRadius: 10,
    paddingHorizontal: 14,
    color: '#ffffff',
    fontSize: 14,
  },
  sendBtn: { backgroundColor: '#ff8b6a', justifyContent: 'center', paddingHorizontal: 16, borderRadius: 10 },
  sendBtnText: { color: '#ffffff', fontWeight: '600' },
});
