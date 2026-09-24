import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as Sharing from 'expo-sharing';
import { Ionicons } from '@expo/vector-icons';
import type { FileTransferMessage } from './usePCWebSocket';

type TransferModule = typeof import('./modules/blinky-secure-socket');
type SelectedFile = { uri: string; name: string; size?: number };
type TransferPhase = 'idle' | 'hashing' | 'offering' | 'uploading' | 'resuming' | 'editing' | 'downloading' | 'error' | 'done';

type TransferSession = {
  requestId: string;
  file: SelectedFile;
  size: number;
  sha256: string;
  instruction: string;
  transferId?: string;
  token?: string;
  chunkSize?: number;
  phase: TransferPhase;
  bytes: number;
  error?: string;
  output?: { name: string; size: number; sha256: string };
  localUri?: string;
};

type Props = {
  visible: boolean;
  connected: boolean;
  hostAddress: string;
  releaseTransport: boolean;
  certificatePin: string;
  fileTransferMessage: FileTransferMessage | null;
  sendMessage(message: Record<string, unknown>): boolean;
  getNativeModule(): TransferModule | null;
  onClose(): void;
};

const CHUNK_SIZE = 16 * 1024 * 1024;

function newRequestId() {
  return `file-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatBytes(size: number) {
  if (size >= 1024 ** 3) return `${(size / 1024 ** 3).toFixed(1)} GB`;
  if (size >= 1024 ** 2) return `${(size / 1024 ** 2).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${size} bytes`;
}

function transferBaseUrl(address: string, secure: boolean) {
  let authority = address.trim().replace(/^(?:https?|wss?):\/\//i, '').replace(/\/.*$/, '');
  if (!authority) throw new Error('Enter the PC address in Local Link Setup first.');
  if (authority.startsWith('[')) {
    const close = authority.indexOf(']');
    if (close >= 0) authority = authority.slice(0, close + 1);
  } else {
    const parts = authority.split(':');
    if (parts.length === 2 && /^\d+$/.test(parts[1])) authority = parts[0];
    else if (parts.length > 2) authority = `[${authority}]`;
  }
  return `${secure ? 'https' : 'http'}://${authority}:9002`;
}

function ProgressBar({ bytes, total }: { bytes: number; total: number }) {
  const percent = total > 0 ? Math.min(100, (bytes / total) * 100) : 0;
  return (
    <View style={styles.progressWrap}>
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${percent}%` }]} />
      </View>
      <Text style={styles.progressLabel}>{Math.floor(percent)}% · {formatBytes(bytes)} / {formatBytes(total)}</Text>
    </View>
  );
}

/** Picks, uploads, resumes, edits, and receives files over the authenticated PC link. */
export function FileTransferPanel({
  visible,
  connected,
  hostAddress,
  releaseTransport,
  certificatePin,
  fileTransferMessage,
  sendMessage,
  getNativeModule,
  onClose,
}: Props) {
  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null);
  const [instruction, setInstruction] = useState('');
  const [session, setSession] = useState<TransferSession | null>(null);
  const sessionRef = useRef<TransferSession | null>(null);
  const lastMessageRef = useRef<FileTransferMessage | null>(null);
  const transferBase = useMemo(() => {
    try { return transferBaseUrl(hostAddress, releaseTransport); }
    catch { return ''; }
  }, [hostAddress, releaseTransport]);

  const updateSession = useCallback((update: (current: TransferSession) => TransferSession) => {
    const current = sessionRef.current;
    if (!current) return;
    const next = update(current);
    sessionRef.current = next;
    setSession(next);
  }, []);

  const downloadEditedFile = useCallback(async (current: TransferSession, output: { name: string; size: number; sha256: string }) => {
    const native = getNativeModule();
    if (!native || !current.transferId || !current.token) {
      updateSession(s => ({ ...s, phase: 'error', error: 'The native file transfer module is unavailable. Build and install the Blinky development or release app.' }));
      return;
    }
    updateSession(s => ({ ...s, phase: 'downloading', bytes: 0, error: undefined, output }));
    try {
      const localUri = await native.downloadFile({
        transferId: current.transferId,
        url: `${transferBase}${'/download/' + current.transferId}`,
        token: current.token,
        pin: releaseTransport ? certificatePin : undefined,
        size: output.size,
        sha256: output.sha256,
        filename: output.name,
      });
      updateSession(s => ({ ...s, phase: 'done', bytes: output.size, output, localUri }));
    } catch (error: any) {
      updateSession(s => ({ ...s, phase: 'error', output, error: error?.message || 'The edited file could not be downloaded. Resume to continue.' }));
    }
  }, [certificatePin, getNativeModule, releaseTransport, transferBase, updateSession]);

  const runUpload = useCallback(async (current: TransferSession, offset: number) => {
    const native = getNativeModule();
    if (!native || !current.transferId || !current.token) {
      updateSession(s => ({ ...s, phase: 'error', error: 'The native file transfer module is unavailable. Build and install the Blinky development or release app.' }));
      return;
    }
    updateSession(s => ({ ...s, phase: 'uploading', bytes: offset, error: undefined }));
    try {
      await native.uploadFile({
        sourceUri: current.file.uri,
        transferId: current.transferId,
        url: `${transferBase}/upload/${current.transferId}`,
        token: current.token,
        pin: releaseTransport ? certificatePin : undefined,
        size: current.size,
        chunkSize: current.chunkSize || CHUNK_SIZE,
        offset,
      });
      const latest = sessionRef.current;
      if (!latest || latest.transferId !== current.transferId) return;
      if (latest.instruction.trim()) {
        const requestId = newRequestId();
        const accepted = sendMessage({
          type: 'file_edit',
          requestId,
          transferId: latest.transferId,
          temporaryToken: latest.token,
          instruction: latest.instruction.trim(),
        });
        if (!accepted) {
          updateSession(s => ({ ...s, phase: 'error', error: 'Upload completed. Reconnect to the PC, then resume to start AiCut.' }));
          return;
        }
        updateSession(s => ({ ...s, phase: 'editing', requestId, bytes: s.size, error: undefined }));
      } else {
        updateSession(s => ({ ...s, phase: 'done', bytes: s.size, error: undefined }));
      }
    } catch (error: any) {
      updateSession(s => ({ ...s, phase: 'error', bytes: offset, error: error?.message || 'Upload paused. Resume when the PC is reachable.' }));
    }
  }, [certificatePin, getNativeModule, releaseTransport, sendMessage, transferBase, updateSession]);

  const handleServerMessage = useCallback(async (message: FileTransferMessage) => {
    const current = sessionRef.current;
    if (!current) return;
    if (message.type === 'file_offer_result' && message.requestId === current.requestId && message.transferId && message.temporaryToken) {
      const next = {
        ...current,
        phase: 'uploading' as const,
        transferId: message.transferId,
        token: message.temporaryToken,
        chunkSize: message.chunkSize || CHUNK_SIZE,
        bytes: message.uploadOffset || 0,
      };
      sessionRef.current = next;
      setSession(next);
      await runUpload(next, message.uploadOffset || 0);
      return;
    }
    if (message.transferId && message.transferId !== current.transferId) return;
    if (message.type === 'file_received' && !current.instruction.trim()) {
      updateSession(s => ({ ...s, phase: 'done', bytes: s.size, error: undefined }));
      return;
    }
    if (message.type === 'file_resume_result' && message.requestId === current.requestId) {
      if (message.edited && message.name && message.size && message.sha256) {
        await downloadEditedFile(current, { name: message.name, size: message.size, sha256: message.sha256 });
      } else if (message.editing) {
        updateSession(s => ({ ...s, phase: 'editing', error: undefined }));
      } else if (message.complete) {
        if (current.instruction.trim()) {
          const requestId = newRequestId();
          if (!sendMessage({ type: 'file_edit', requestId, transferId: current.transferId, temporaryToken: current.token, instruction: current.instruction.trim() })) {
            updateSession(s => ({ ...s, phase: 'error', error: 'The upload is saved. Reconnect to start AiCut.' }));
            return;
          }
          updateSession(s => ({ ...s, phase: 'editing', requestId, error: undefined }));
        } else {
          updateSession(s => ({ ...s, phase: 'done', bytes: s.size, error: undefined }));
        }
      } else {
        await runUpload(current, message.uploadOffset || 0);
      }
      return;
    }
    if (message.type === 'file_edit_complete' && message.name && message.size && message.sha256) {
      await downloadEditedFile(current, { name: message.name, size: message.size, sha256: message.sha256 });
      return;
    }
    if (message.type === 'file_edit_started') {
      updateSession(s => ({ ...s, phase: 'editing', error: undefined }));
      return;
    }
    if (message.type === 'file_error' || message.type === 'file_edit_error') {
      if (message.requestId !== undefined && message.requestId !== current.requestId) return;
      updateSession(s => ({ ...s, phase: 'error', error: message.message || 'The PC rejected the file transfer.' }));
    }
  }, [downloadEditedFile, runUpload, sendMessage, updateSession]);

  useEffect(() => {
    if (!fileTransferMessage || fileTransferMessage === lastMessageRef.current) return;
    lastMessageRef.current = fileTransferMessage;
    void handleServerMessage(fileTransferMessage);
  }, [fileTransferMessage, handleServerMessage]);

  useEffect(() => {
    if (!session?.transferId) return;
    const native = getNativeModule();
    if (!native) return;
    const subscription = native.addListener('onTransferProgress', event => {
      if (event.id !== session.transferId || typeof event.bytes !== 'number') return;
      updateSession(current => ({ ...current, bytes: event.bytes! }));
    });
    return () => subscription.remove();
  }, [getNativeModule, session?.transferId, updateSession]);

  const chooseFile = useCallback(async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: '*/*',
        copyToCacheDirectory: false,
        multiple: false,
        base64: false,
      });
      if (result.canceled || !result.assets?.[0]) return;
      const asset = result.assets[0];
      const nextFile = { uri: asset.uri, name: asset.name, size: asset.size };
      setSelectedFile(nextFile);
      setInstruction('');
      setSession(null);
      sessionRef.current = null;
    } catch (error: any) {
      Alert.alert('Could not open file', error?.message || 'Choose a file from the system picker and try again.');
    }
  }, []);

  const startTransfer = useCallback(async (withEdit: boolean) => {
    if (!connected) {
      Alert.alert('PC disconnected', 'Connect to Blinky before sending a file.');
      return;
    }
    if (!selectedFile || !transferBase) {
      Alert.alert('Choose a file', 'Select a file before starting a transfer.');
      return;
    }
    if (withEdit && !instruction.trim()) {
      Alert.alert('Add an edit instruction', 'Describe the AiCut change, such as trimming the video or adding captions.');
      return;
    }
    const native = getNativeModule();
    if (!native) {
      Alert.alert('Install the Blinky mobile build', 'Large file transfer needs the Blinky native module. It is unavailable in Expo Go.');
      return;
    }
    if (releaseTransport && !certificatePin.trim()) {
      Alert.alert('Certificate pin required', 'Enter the PC release certificate pin in Local Link Setup.');
      return;
    }

    const requestId = newRequestId();
    const next: TransferSession = {
      requestId,
      file: selectedFile,
      size: selectedFile.size || 0,
      sha256: '',
      instruction: withEdit ? instruction.trim() : '',
      phase: 'hashing',
      bytes: 0,
    };
    sessionRef.current = next;
    setSession(next);
    try {
      const digest = await native.hashFile(selectedFile.uri);
      if (selectedFile.size && selectedFile.size !== digest.size) {
        throw new Error('The selected file changed while it was being prepared. Choose it again.');
      }
      const offered: TransferSession = { ...next, size: digest.size, sha256: digest.sha256, phase: 'offering' };
      sessionRef.current = offered;
      setSession(offered);
      if (!sendMessage({
        type: 'file_offer',
        requestId,
        name: selectedFile.name,
        size: digest.size,
        sha256: digest.sha256,
        purpose: withEdit ? 'edit' : 'upload',
      })) {
        throw new Error('Could not send the file offer. Check the PC connection.');
      }
    } catch (error: any) {
      updateSession(s => ({ ...s, phase: 'error', error: error?.message || 'Could not prepare this file.' }));
    }
  }, [certificatePin, connected, getNativeModule, instruction, releaseTransport, selectedFile, sendMessage, transferBase, updateSession]);

  const resume = useCallback(() => {
    const current = sessionRef.current;
    if (!current) return;
    if (current.phase === 'error' && current.output && current.transferId && current.token) {
      void downloadEditedFile(current, current.output);
      return;
    }
    if (!current.transferId || !current.token || !connected) {
      updateSession(s => ({ ...s, phase: 'error', error: 'Reconnect to the PC before resuming.' }));
      return;
    }
    const requestId = newRequestId();
    updateSession(s => ({ ...s, phase: 'resuming', requestId, error: undefined }));
    if (!sendMessage({ type: 'file_resume', requestId, transferId: current.transferId, temporaryToken: current.token })) {
      updateSession(s => ({ ...s, phase: 'error', error: 'Could not check the transfer offset. Reconnect and try again.' }));
    }
  }, [connected, downloadEditedFile, sendMessage, updateSession]);

  const shareFile = useCallback(async () => {
    if (!session?.localUri) return;
    if (!(await Sharing.isAvailableAsync())) {
      Alert.alert('Sharing unavailable', 'This device does not currently provide a share sheet.');
      return;
    }
    await Sharing.shareAsync(session.localUri, { dialogTitle: session.output?.name || session.file.name });
  }, [session]);

  const phaseLabel = session?.phase === 'hashing' ? 'Checking file and calculating SHA-256…'
    : session?.phase === 'offering' ? 'Checking file size and PC storage…'
      : session?.phase === 'uploading' ? 'Uploading to PC…'
        : session?.phase === 'resuming' ? 'Checking saved transfer progress…'
          : session?.phase === 'editing' ? 'AiCut is editing on the PC…'
            : session?.phase === 'downloading' ? 'Downloading the edited file…'
              : session?.phase === 'done' ? (session.localUri ? 'Transfer complete' : 'File saved to Downloads/Blinky')
                : '';
  const busy = !!session && ['hashing', 'offering', 'uploading', 'resuming', 'editing', 'downloading'].includes(session.phase);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <View style={styles.header}>
            <View>
              <Text style={styles.title}>Send a file to PC</Text>
              <Text style={styles.subtitle}>{releaseTransport ? 'TLS-pinned, resumable transfer · 20 GiB default limit' : 'Development transfer · 20 GiB default limit'}</Text>
            </View>
            <Pressable onPress={onClose} hitSlop={12} style={styles.closeButton}>
              <Ionicons name="close" size={22} color="#D8D4E8" />
            </Pressable>
          </View>

          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
            {!connected && <Text style={styles.notice}>Connect to your Blinky PC before starting a transfer.</Text>}
            {!transferBase && <Text style={styles.notice}>Set a PC address in Local Link Setup.</Text>}
            {!releaseTransport && <Text style={styles.notice}>Development transfers use unencrypted HTTP on the local network. Use only on a trusted network; release builds use TLS pinning.</Text>}

            <Pressable style={styles.pickButton} onPress={chooseFile} disabled={busy}>
              <Ionicons name="document-attach-outline" size={20} color="#FF7254" />
              <Text style={styles.pickButtonText}>{selectedFile ? 'Choose a different file' : 'Choose file'}</Text>
            </Pressable>

            {selectedFile && (
              <View style={styles.fileCard}>
                <Ionicons name="document-text-outline" size={22} color="#B7A8FF" />
                <View style={styles.fileDetails}>
                  <Text style={styles.fileName} numberOfLines={1}>{selectedFile.name}</Text>
                  <Text style={styles.fileSize}>{selectedFile.size ? formatBytes(selectedFile.size) : 'Size checked before upload'}</Text>
                </View>
              </View>
            )}

            <Text style={styles.fieldLabel}>AiCut instruction (optional)</Text>
            <TextInput
              value={instruction}
              onChangeText={setInstruction}
              placeholder="Trim from 3 to 20 seconds, or add Instagram captions…"
              placeholderTextColor="#817C98"
              style={styles.instructionInput}
              multiline
              editable={!busy && session?.phase !== 'done'}
              autoCorrect
            />
            <Text style={styles.helpText}>Without an instruction, the file is saved to Downloads/Blinky. With an instruction, AiCut edits it on the PC and Blinky downloads the result to app storage.</Text>

            {session && busy && (
              <View style={styles.statusCard}>
                <View style={styles.statusHeading}>
                  <ActivityIndicator size="small" color="#FF7254" />
                  <Text style={styles.statusText}>{phaseLabel}</Text>
                </View>
                {(session.phase === 'uploading' || session.phase === 'downloading') && (
                  <ProgressBar bytes={session.bytes} total={session.phase === 'downloading' ? session.output?.size || 0 : session.size} />
                )}
              </View>
            )}

            {session?.phase === 'error' && (
              <View style={styles.errorCard}>
                <Text style={styles.errorText}>{session.error}</Text>
                {!!session.transferId && <Pressable style={styles.secondaryButton} onPress={resume}><Text style={styles.secondaryButtonText}>{session.output ? 'Resume download' : 'Resume transfer'}</Text></Pressable>}
              </View>
            )}

            {session?.phase === 'done' && (
              <View style={styles.doneCard}>
                <Ionicons name="checkmark-circle" size={20} color="#43D6A1" />
                <View style={styles.fileDetails}>
                  <Text style={styles.doneTitle}>Transfer complete</Text>
                  <Text style={styles.fileSize} numberOfLines={1}>{session.output?.name || selectedFile?.name}{session.localUri ? '' : ' · Saved to Downloads/Blinky'}</Text>
                </View>
                {!!session.localUri && <Pressable style={styles.shareButton} onPress={() => void shareFile()}><Ionicons name="share-outline" size={17} color="#FFFFFF" /><Text style={styles.shareText}>Share</Text></Pressable>}
              </View>
            )}
          </ScrollView>

          <View style={styles.actions}>
            <Pressable style={[styles.secondaryButton, busy && styles.disabledButton]} onPress={onClose}>
              <Text style={styles.secondaryButtonText}>Close</Text>
            </Pressable>
            <Pressable
              style={[styles.primaryButton, (!connected || !selectedFile || busy) && styles.disabledButton]}
              onPress={() => void startTransfer(!!instruction.trim())}
              disabled={!connected || !selectedFile || busy}
            >
              <Text style={styles.primaryButtonText}>{instruction.trim() ? 'Upload & edit' : 'Upload to PC'}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.72)', justifyContent: 'flex-end' },
  sheet: { maxHeight: '90%', backgroundColor: '#100D1B', borderTopLeftRadius: 24, borderTopRightRadius: 24, borderWidth: 1, borderColor: '#302942', paddingBottom: Platform.OS === 'ios' ? 30 : 18 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 22, paddingTop: 22, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: '#282338' },
  title: { color: '#FFFFFF', fontSize: 18, fontWeight: '700' },
  subtitle: { color: '#A19BB8', fontSize: 12, marginTop: 4 },
  closeButton: { width: 36, height: 36, borderRadius: 18, backgroundColor: '#211C2D', alignItems: 'center', justifyContent: 'center' },
  content: { padding: 20, gap: 14 },
  notice: { color: '#F5C76D', backgroundColor: '#362A14', borderRadius: 10, padding: 11, fontSize: 12, lineHeight: 17 },
  pickButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9, minHeight: 48, borderRadius: 12, borderWidth: 1, borderColor: '#514366', backgroundColor: '#211A30' },
  pickButtonText: { color: '#F5F2FF', fontWeight: '600' },
  fileCard: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 13, borderRadius: 12, backgroundColor: '#191527', borderWidth: 1, borderColor: '#312B42' },
  fileDetails: { flex: 1 },
  fileName: { color: '#F3F0FF', fontSize: 13, fontWeight: '600' },
  fileSize: { color: '#A19BB8', fontSize: 11, marginTop: 3 },
  fieldLabel: { color: '#E8E4F4', fontSize: 12, fontWeight: '600', marginBottom: -8 },
  instructionInput: { minHeight: 84, maxHeight: 140, color: '#FFFFFF', fontSize: 13, lineHeight: 19, backgroundColor: '#191527', borderColor: '#342E45', borderWidth: 1, borderRadius: 12, padding: 12, textAlignVertical: 'top' },
  helpText: { color: '#9791AA', fontSize: 11, lineHeight: 16, marginTop: -5 },
  statusCard: { backgroundColor: '#1A1725', borderColor: '#383149', borderWidth: 1, borderRadius: 12, padding: 13 },
  statusHeading: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  statusText: { color: '#E6E1F2', fontSize: 12, flex: 1 },
  progressWrap: { marginTop: 12 },
  progressTrack: { height: 6, borderRadius: 3, overflow: 'hidden', backgroundColor: '#363044' },
  progressFill: { height: '100%', borderRadius: 3, backgroundColor: '#FF7254' },
  progressLabel: { marginTop: 6, color: '#A19BB8', fontSize: 10 },
  errorCard: { borderWidth: 1, borderColor: '#753932', backgroundColor: '#301A1C', borderRadius: 12, padding: 13, gap: 11 },
  errorText: { color: '#FFB0A3', fontSize: 12, lineHeight: 17 },
  doneCard: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 13, borderWidth: 1, borderColor: '#285C4D', backgroundColor: '#12251F', borderRadius: 12 },
  doneTitle: { color: '#DDFBF1', fontSize: 12, fontWeight: '700' },
  shareButton: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#3C34A0', paddingHorizontal: 10, paddingVertical: 8, borderRadius: 9 },
  shareText: { color: '#FFFFFF', fontWeight: '600', fontSize: 11 },
  actions: { flexDirection: 'row', gap: 10, paddingHorizontal: 20, paddingTop: 14, borderTopWidth: 1, borderTopColor: '#282338' },
  primaryButton: { flex: 1, minHeight: 46, borderRadius: 12, backgroundColor: '#FF5A36', alignItems: 'center', justifyContent: 'center' },
  primaryButtonText: { color: '#FFFFFF', fontSize: 13, fontWeight: '700' },
  secondaryButton: { minHeight: 42, minWidth: 92, borderRadius: 11, borderWidth: 1, borderColor: '#4A435C', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
  secondaryButtonText: { color: '#E1DDEE', fontSize: 12, fontWeight: '600' },
  disabledButton: { opacity: 0.45 },
});
