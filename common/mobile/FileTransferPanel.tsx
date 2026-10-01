import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
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
import { buildFileOffer, findTransferItem, transferIntent } from './lib/fileTransferOffer';

type TransferModule = typeof import('./modules/blinky-secure-socket');

export type SelectedFile = {
  uri: string;
  name: string;
  size?: number;
};

export type FileTransferItem = {
  id: string;
  file: SelectedFile;
  size: number;
  sha256: string;
  transferId?: string;
  token?: string;
  bytes: number;
  phase: 'pending' | 'hashing' | 'offering' | 'uploading' | 'uploaded' | 'error';
  error?: string;
};

export type BatchTransferPhase =
  | 'idle'
  | 'preparing'
  | 'uploading'
  | 'editing'
  | 'downloading'
  | 'done'
  | 'error';

export type TransferSession = {
  requestId: string;
  items: FileTransferItem[];
  currentIndex: number;
  instruction: string;
  destinationPath: string;
  isEdit: boolean;
  phase: BatchTransferPhase;
  totalBytes: number;
  primaryTransferId?: string;
  primaryToken?: string;
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
  /** Called with a human-readable status string while a chat-triggered transfer is running. */
  onTransferStatusChange?: (status: string | null) => void;
  /** Called when a chat-triggered transfer completes (done or error). */
  onTransferDone?: (success: boolean, message: string) => void;
};

export type FileTransferPanelRef = {
  /**
   * Start a transfer programmatically (e.g. from the chat bar).
   * The panel does NOT need to be visible — it runs silently in the background.
   */
  startTransfer(files: SelectedFile[], instruction: string, destination?: string, destinationHint?: string): void;
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

function getMediaType(name: string): 'video' | 'audio' | 'image' | 'other' {
  const ext = name.toLowerCase().split('.').pop() || '';
  if (['mp4', 'mov', 'mkv', 'avi', 'webm', 'flv', 'wmv', 'm4v'].includes(ext)) return 'video';
  if (['mp3', 'wav', 'aac', 'm4a', 'flac', 'ogg', 'wma'].includes(ext)) return 'audio';
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'].includes(ext)) return 'image';
  return 'other';
}

function getFileIcon(name: string): keyof typeof Ionicons.glyphMap {
  const type = getMediaType(name);
  if (type === 'video') return 'videocam-outline';
  if (type === 'audio') return 'musical-notes-outline';
  if (type === 'image') return 'image-outline';
  return 'document-text-outline';
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

/** Picks, uploads, merges/edits, and receives multiple files over the authenticated PC link. */
export const FileTransferPanel = forwardRef<FileTransferPanelRef, Props>(function FileTransferPanel({
  visible,
  connected,
  hostAddress,
  releaseTransport,
  certificatePin,
  fileTransferMessage,
  sendMessage,
  getNativeModule,
  onClose,
  onTransferStatusChange,
  onTransferDone,
}: Props, ref) {
  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([]);
  const [instruction, setInstruction] = useState('');
  const [destinationPath, setDestinationPath] = useState('');
  const [session, setSession] = useState<TransferSession | null>(null);
  const sessionRef = useRef<TransferSession | null>(null);
  const lastMessageRef = useRef<FileTransferMessage | null>(null);

  const pendingOfferResolvers = useRef<Map<string, (msg: FileTransferMessage) => void>>(new Map());
  const editCompleteResolver = useRef<((msg: FileTransferMessage) => void) | null>(null);
  const abortRef = useRef<boolean>(false);

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

  const totalRawSize = useMemo(() => {
    return selectedFiles.reduce((acc, f) => acc + (f.size || 0), 0);
  }, [selectedFiles]);

  // Handle incoming websocket messages from the PC
  const handleServerMessage = useCallback((message: FileTransferMessage) => {
    if ((message.type === 'file_offer_result' || message.type === 'file_error') && message.requestId) {
      const resolver = pendingOfferResolvers.current.get(message.requestId);
      if (resolver) {
        pendingOfferResolvers.current.delete(message.requestId);
        resolver(message);
        return;
      }
    }

    if (message.type === 'file_edit_complete' || message.type === 'file_edit_error' ||
        (message.type === 'file_error' && sessionRef.current?.phase === 'editing')) {
      if (editCompleteResolver.current) {
        const resolver = editCompleteResolver.current;
        editCompleteResolver.current = null;
        resolver(message);
        return;
      }
    }

    if (message.type === 'file_error') {
      const current = sessionRef.current;
      if (current) {
        updateSession(s => ({ ...s, phase: 'error', error: message.message || 'The PC reported a transfer error.' }));
      }
    }
  }, [updateSession]);

  useEffect(() => {
    if (!fileTransferMessage || fileTransferMessage === lastMessageRef.current) return;
    lastMessageRef.current = fileTransferMessage;
    handleServerMessage(fileTransferMessage);
  }, [fileTransferMessage, handleServerMessage]);

  // Listen to transfer progress events across all active transfers
  useEffect(() => {
    // The chat transfer panel is mounted invisibly. Do not load the custom
    // native socket module during app startup; initialize it only when the
    // panel is opened or a chat transfer has created a session.
    if (!visible && !sessionRef.current) return;
    const native = getNativeModule();
    if (!native) return;
    const subscription = native.addListener('onTransferProgress', event => {
      if (typeof event.bytes !== 'number') return;
      updateSession(curr => {
        if (!curr) return curr;
        if (curr.phase === 'downloading') {
          return {
            ...curr,
            items: curr.items.map((it, idx) => (idx === 0 ? { ...it, bytes: event.bytes! } : it)),
          };
        }
        const updatedItems = curr.items.map(it => {
          if (it.transferId === event.id) {
            return { ...it, bytes: event.bytes! };
          }
          return it;
        });
        return { ...curr, items: updatedItems };
      });
    });
    return () => subscription.remove();
  }, [getNativeModule, updateSession, visible, session?.phase]);

  const chatTransferQueueRef = useRef<{ files: SelectedFile[]; instruction: string; destination: string; destinationHint: string } | null>(null);
  // Stable ref so that useImperativeHandle can call the latest startBatchTransferDirect
  const startBatchTransferDirectRef = useRef<typeof startBatchTransferDirect | null>(null);

  const chooseFiles = useCallback(async (append = false) => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: '*/*',
        copyToCacheDirectory: false,
        multiple: true,
        base64: false,
      });
      if (result.canceled || !result.assets?.length) return;
      const newFiles: SelectedFile[] = result.assets.map(asset => ({
        uri: asset.uri,
        name: asset.name,
        size: asset.size,
      }));

      setSelectedFiles(prev => {
        if (!append) return newFiles;
        const existingUris = new Set(prev.map(f => f.uri));
        const filteredNew = newFiles.filter(f => !existingUris.has(f.uri));
        return [...prev, ...filteredNew];
      });
      setSession(null);
      sessionRef.current = null;
    } catch (error: any) {
      Alert.alert('Could not open files', error?.message || 'Choose files from the system picker and try again.');
    }
  }, []);

  const removeFile = useCallback((index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
    setSession(null);
    sessionRef.current = null;
  }, []);

  const clearFiles = useCallback(() => {
    setSelectedFiles([]);
    setSession(null);
    sessionRef.current = null;
  }, []);

  /**
   * Core transfer logic shared between the UI "Upload" button and the
   * chat-bar triggered path.  When called from chat, files/instruction/destination
   * are passed directly so we don't depend on React state being flushed.
   */
  const startBatchTransferDirect = useCallback(async (
    filesToSend: SelectedFile[],
    instructionText: string,
    destPath: string,
    destinationHint = '',
  ) => {
    if (!connected) {
      if (onTransferDone) onTransferDone(false, 'Not connected to PC.');
      else Alert.alert('PC disconnected', 'Connect to Blinky before sending files.');
      return;
    }
    if (filesToSend.length === 0 || !transferBase) {
      if (onTransferDone) onTransferDone(false, 'No files selected.');
      else Alert.alert('Choose files', 'Select one or more files before starting a transfer.');
      return;
    }
    const native = getNativeModule();
    if (!native) {
      if (onTransferDone) onTransferDone(false, 'File transfer is not supported on this device.');
      else Alert.alert('Transfer Unavailable', 'File transfer is not supported on this device.');
      return;
    }
    if (releaseTransport && !certificatePin.trim()) {
      if (onTransferDone) onTransferDone(false, 'Certificate pin required.');
      else Alert.alert('Certificate pin required', 'Enter the PC release certificate pin in Local Link Setup.');
      return;
    }

    const withEdit = transferIntent(instructionText) === 'edit';
    let batchDestination = destPath.trim();
    let destinationWarning = '';

    abortRef.current = false;

    const sortedFiles = [...filesToSend].sort((a, b) => {
      const priority = (name: string) => {
        const type = getMediaType(name);
        return type === 'video' ? 0 : type === 'audio' ? 1 : 2;
      };
      return priority(a.name) - priority(b.name);
    });

    const initialItems: FileTransferItem[] = sortedFiles.map((f, i) => ({
      id: `item-${i}-${f.name}`,
      file: f,
      size: f.size || 0,
      sha256: '',
      bytes: 0,
      phase: 'pending',
    }));

    const totalRaw = sortedFiles.reduce((acc, f) => acc + (f.size || 0), 0);

    const sessionData: TransferSession = {
      requestId: newRequestId(),
      items: initialItems,
      currentIndex: 0,
      instruction: instructionText.trim(),
      destinationPath: batchDestination || 'Downloads/Blinky',
      isEdit: withEdit,
      phase: 'preparing',
      totalBytes: totalRaw,
    };
    sessionRef.current = sessionData;
    setSession(sessionData);

    const notifyStatus = (msg: string) => onTransferStatusChange?.(msg);

    try {
      for (let i = 0; i < initialItems.length; i++) {
        if (abortRef.current) break;

        const currentItem = initialItems[i];
        updateSession(curr => ({
          ...curr,
          currentIndex: i,
          phase: 'preparing',
          items: curr.items.map((it, idx) => (idx === i ? { ...it, phase: 'hashing' } : it)),
        }));
        notifyStatus(`Verifying ${currentItem.file.name}…`);

        const digest = await native.hashFile(currentItem.file.uri);
        if (abortRef.current) break;

        currentItem.size = digest.size;
        currentItem.sha256 = digest.sha256;

        updateSession(curr => {
          const updatedItems = curr.items.map((it, idx) =>
            idx === i ? { ...it, size: digest.size, sha256: digest.sha256, phase: 'offering' as const } : it
          );
          const newTotal = updatedItems.reduce((acc, it) => acc + it.size, 0);
          return { ...curr, items: updatedItems, totalBytes: newTotal };
        });

        const offerReqId = newRequestId();
        const offerPromise = new Promise<FileTransferMessage>((resolve, reject) => {
          const timer = setTimeout(() => {
            pendingOfferResolvers.current.delete(offerReqId);
            reject(new Error(`Timed out waiting for PC to accept ${currentItem.file.name}.`));
          }, 75000);
          pendingOfferResolvers.current.set(offerReqId, msg => {
            clearTimeout(timer);
            resolve(msg);
          });
        });

        const sent = sendMessage(buildFileOffer({
          requestId: offerReqId,
          name: currentItem.file.name,
          size: digest.size,
          sha256: digest.sha256,
          instruction: instructionText,
          destinationPath: batchDestination,
          destinationHint,
        }));
        if (!sent) throw new Error('Could not send file offer. Check PC connection.');

        notifyStatus(`Offering ${currentItem.file.name} to PC…`);
        const offerResult = await offerPromise;
        if (offerResult.destinationPath) {
          updateSession(curr => ({ ...curr, destinationPath: offerResult.destinationPath! }));
          batchDestination = offerResult.destinationPath;
        }
        if (offerResult.destinationWarning) destinationWarning = offerResult.destinationWarning;
        if (!offerResult.transferId || !offerResult.temporaryToken) {
          throw new Error(offerResult.message || `PC rejected transfer of ${currentItem.file.name}.`);
        }

        currentItem.transferId = offerResult.transferId;
        currentItem.token = offerResult.temporaryToken;
        currentItem.phase = 'uploading';

        if (i === 0) {
          sessionData.primaryTransferId = offerResult.transferId;
          sessionData.primaryToken = offerResult.temporaryToken;
        }

        updateSession(curr => ({
          ...curr,
          phase: 'uploading',
          primaryTransferId: i === 0 ? offerResult.transferId : curr.primaryTransferId,
          primaryToken: i === 0 ? offerResult.temporaryToken : curr.primaryToken,
          items: curr.items.map((it, idx) =>
            idx === i
              ? { ...it, transferId: offerResult.transferId, token: offerResult.temporaryToken, phase: 'uploading' }
              : it
          ),
        }));

        notifyStatus(`Uploading ${currentItem.file.name} (${i + 1}/${initialItems.length})…`);

        await native.uploadFile({
          sourceUri: currentItem.file.uri,
          transferId: offerResult.transferId,
          url: `${transferBase}/upload/${offerResult.transferId}`,
          token: offerResult.temporaryToken,
          pin: releaseTransport ? certificatePin : undefined,
          size: digest.size,
          chunkSize: offerResult.chunkSize || CHUNK_SIZE,
          offset: offerResult.uploadOffset || 0,
        });

        if (abortRef.current) break;

        currentItem.phase = 'uploaded';
        currentItem.bytes = digest.size;
        updateSession(curr => ({
          ...curr,
          items: curr.items.map((it, idx) =>
            idx === i ? { ...it, phase: 'uploaded', bytes: digest.size } : it
          ),
        }));
      }

      if (abortRef.current) return;

      if (withEdit) {
        const latestSession = sessionRef.current;
        if (!latestSession || !latestSession.primaryTransferId || !latestSession.primaryToken) {
          throw new Error('Transfer session details missing.');
        }

        updateSession(s => ({ ...s, phase: 'editing', error: undefined }));
        notifyStatus('AiCut is processing on PC…');

        const editReqId = newRequestId();
        const primaryId = latestSession.primaryTransferId;
        const primaryTok = latestSession.primaryToken;
        const allTransferIds = latestSession.items.map(it => it.transferId!).filter(Boolean);
        const additionalTransferIds = allTransferIds.filter(id => id !== primaryId);

        const editPromise = new Promise<FileTransferMessage>((resolve, reject) => {
          const timer = setTimeout(() => {
            editCompleteResolver.current = null;
            reject(new Error('AiCut is taking longer than usual.'));
          }, 6 * 3600 * 1000);
          editCompleteResolver.current = msg => {
            clearTimeout(timer);
            resolve(msg);
          };
        });

        const sent = sendMessage({
          type: 'file_edit',
          requestId: editReqId,
          transferId: primaryId,
          temporaryToken: primaryTok,
          additionalTransferIds,
          transferIds: allTransferIds,
          instruction: instructionText.trim(),
        });
        if (!sent) throw new Error('Upload completed, but could not request AiCut edit from the PC.');

        const editResult = await editPromise;
        if (editResult.type === 'file_edit_error' || editResult.type === 'file_error') {
          throw new Error(editResult.message || 'AiCut could not complete the edit.');
        }
        if (!editResult.name || !editResult.size || !editResult.sha256) {
          throw new Error('AiCut completed without returning output file details.');
        }

        const outputMeta = { name: editResult.name, size: editResult.size, sha256: editResult.sha256 };

        updateSession(s => ({
          ...s,
          phase: 'downloading',
          output: outputMeta,
          items: s.items.map((it, idx) => (idx === 0 ? { ...it, bytes: 0 } : it)),
        }));
        notifyStatus('Downloading edited result…');

        const localUri = await native.downloadFile({
          transferId: primaryId,
          url: `${transferBase}/download/${primaryId}`,
          token: primaryTok,
          pin: releaseTransport ? certificatePin : undefined,
          size: outputMeta.size,
          sha256: outputMeta.sha256,
          filename: outputMeta.name,
        });

        updateSession(s => ({ ...s, phase: 'done', output: outputMeta, localUri, error: undefined }));
        onTransferStatusChange?.(null);
        onTransferDone?.(true, `✅ Transfer & edit complete — ${outputMeta.name} saved on PC in ${sessionRef.current?.destinationPath || batchDestination} and copied to your device.${destinationWarning ? ` ${destinationWarning}` : ''}`);
      } else {
        updateSession(s => ({ ...s, phase: 'done', error: undefined }));
        onTransferStatusChange?.(null);
        const dest = sessionRef.current?.destinationPath || batchDestination || 'Downloads/Blinky';
        const label = filesToSend.length > 1
          ? `✅ ${filesToSend.length} files sent to PC (${dest})`
          : `✅ ${filesToSend[0]?.name} sent to PC (${dest})`;
        onTransferDone?.(true, destinationWarning ? `${label}. ${destinationWarning}` : label);
      }
    } catch (err: any) {
      updateSession(s => ({ ...s, phase: 'error', error: err?.message || 'Transfer failed.' }));
      onTransferStatusChange?.(null);
      onTransferDone?.(false, `❌ Transfer failed: ${err?.message || 'unknown error'}`);
    }
  }, [
    certificatePin,
    connected,
    getNativeModule,
    releaseTransport,
    sendMessage,
    transferBase,
    updateSession,
    onTransferStatusChange,
    onTransferDone,
  ]);

  const startBatchTransfer = useCallback(async () => {
    // Delegate to the unified core transfer, passing current UI state
    return startBatchTransferDirect(selectedFiles, instruction, destinationPath);
  }, [startBatchTransferDirect, selectedFiles, instruction, destinationPath]);

  // Keep stable ref in sync with the latest startBatchTransferDirect so the
  // imperative handle can call it without stale-closure issues.
  startBatchTransferDirectRef.current = startBatchTransferDirect;

  // Expose imperative startTransfer for chat-bar triggered transfers.
  // The panel does NOT need to be visible — the transfer runs silently.
  useImperativeHandle(ref, () => ({
    startTransfer(files: SelectedFile[], instruction: string, destination?: string, destinationHint = '') {
      if (!files.length) return;
      setSelectedFiles(files);
      setInstruction(instruction);
      setDestinationPath(destination || '');
      setSession(null);
      sessionRef.current = null;
      // Enqueue the transfer data and kick it off after React flushes state
      chatTransferQueueRef.current = { files, instruction, destination: destination || '', destinationHint };
      setTimeout(() => {
        const q = chatTransferQueueRef.current;
        if (q) {
          chatTransferQueueRef.current = null;
          void startBatchTransferDirectRef.current?.(q.files, q.instruction, q.destination, q.destinationHint);
        }
      }, 0);
    },
  }), []);

  const shareFile = useCallback(async () => {
    if (!session?.localUri) return;
    if (!(await Sharing.isAvailableAsync())) {
      Alert.alert('Sharing unavailable', 'This device does not currently provide a share sheet.');
      return;
    }
    await Sharing.shareAsync(session.localUri, {
      dialogTitle: session.output?.name || 'Blinky Media',
    });
  }, [session]);

  const busy = !!session && ['preparing', 'uploading', 'editing', 'downloading'].includes(session.phase);

  // Dynamic status heading & label
  const phaseLabel = useMemo(() => {
    if (!session) return '';
    const currentItem = session.items[session.currentIndex];
    const totalCount = session.items.length;
    const currentNum = session.currentIndex + 1;

    if (session.phase === 'preparing') {
      if (currentItem?.phase === 'hashing') {
        return `Verifying file ${currentNum} of ${totalCount}: ${currentItem.file.name}…`;
      }
      return `Preparing file ${currentNum} of ${totalCount} on PC…`;
    }
    if (session.phase === 'uploading') {
      return `Uploading file ${currentNum} of ${totalCount}: ${currentItem?.file.name}…`;
    }
    if (session.phase === 'editing') {
      return 'AiCut is processing your edit on the PC…';
    }
    if (session.phase === 'downloading') {
      return 'Downloading edited result to your device…';
    }
    if (session.phase === 'done') {
      if (session.localUri) return 'Transfer & edit complete';
      return session.items.length > 1
        ? `All ${session.items.length} files saved to ${session.destinationPath}`
        : `File saved to ${session.destinationPath}`;
    }
    return '';
  }, [session]);

  // Overall bytes transferred across all items
  const totalTransferredBytes = useMemo(() => {
    if (!session) return 0;
    if (session.phase === 'downloading') {
      return session.items[0]?.bytes || 0;
    }
    return session.items.reduce((acc, it) => acc + (it.bytes || 0), 0);
  }, [session]);

  const totalTargetBytes = useMemo(() => {
    if (!session) return totalRawSize;
    if (session.phase === 'downloading') {
      return session.output?.size || 1;
    }
    return session.totalBytes || totalRawSize || 1;
  }, [session, totalRawSize]);

  const primaryButtonLabel = useMemo(() => {
    if (transferIntent(instruction) === 'edit') {
      return selectedFiles.length > 1 ? 'Upload & run edit' : 'Upload & edit';
    }
    return 'Upload to PC';
  }, [instruction, selectedFiles.length]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <View style={styles.header}>
            <View style={styles.headerTitleWrap}>
              <Text style={styles.title}>Send files to PC</Text>
              <Text style={styles.subtitle}>
                {releaseTransport
                  ? 'TLS-pinned, multi-file transfer · 20 GiB limit'
                  : 'Development transfer · 20 GiB default limit'}
              </Text>
            </View>
            <Pressable onPress={onClose} hitSlop={12} style={styles.closeButton}>
              <Ionicons name="close" size={22} color="#D8D4E8" />
            </Pressable>
          </View>

          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
            {!connected && <Text style={styles.notice}>Connect to your Blinky PC before starting a transfer.</Text>}
            {!transferBase && <Text style={styles.notice}>Set a PC address in Local Link Setup.</Text>}
            {!releaseTransport && (
              <Text style={styles.notice}>
                Development mode: unencrypted local network transfer. Release builds use TLS certificate pinning.
              </Text>
            )}

            {/* File Selection Controls */}
            {selectedFiles.length === 0 ? (
              <Pressable style={styles.pickButton} onPress={() => void chooseFiles(false)} disabled={busy}>
                <Ionicons name="document-attach-outline" size={22} color="#FF7254" />
                <Text style={styles.pickButtonText}>Choose files (videos, audios, etc.)</Text>
              </Pressable>
            ) : (
              <View style={styles.selectedFilesContainer}>
                <View style={styles.selectedFilesHeader}>
                  <Text style={styles.selectedFilesCount}>
                    Selected files ({selectedFiles.length}) · {formatBytes(totalRawSize)}
                  </Text>
                  {!busy && (
                    <Pressable onPress={clearFiles} hitSlop={8}>
                      <Text style={styles.clearAllText}>Clear all</Text>
                    </Pressable>
                  )}
                </View>

                <View style={styles.fileList}>
                  {selectedFiles.map((file, index) => {
                    const sessionItem = findTransferItem(session?.items, file);
                    return (
                      <View key={`${file.uri}-${index}`} style={styles.fileCard}>
                        <Ionicons name={getFileIcon(file.name)} size={22} color="#B7A8FF" />
                        <View style={styles.fileDetails}>
                          <Text style={styles.fileName} numberOfLines={1}>
                            {file.name}
                          </Text>
                          <Text style={styles.fileSize}>
                            {file.size ? formatBytes(file.size) : 'Size checked before upload'}
                          </Text>
                        </View>

                        {/* Status icon or remove button */}
                        {busy ? (
                          <View style={styles.itemStatus}>
                            {sessionItem?.phase === 'uploaded' ? (
                              <Ionicons name="checkmark-circle" size={18} color="#43D6A1" />
                            ) : sessionItem?.phase === 'uploading' ? (
                              <ActivityIndicator size="small" color="#FF7254" />
                            ) : sessionItem?.phase === 'hashing' || sessionItem?.phase === 'offering' ? (
                              <ActivityIndicator size="small" color="#B7A8FF" />
                            ) : (
                              <Ionicons name="time-outline" size={16} color="#7A748E" />
                            )}
                          </View>
                        ) : (
                          <Pressable
                            onPress={() => removeFile(index)}
                            hitSlop={8}
                            style={styles.removeFileBtn}
                          >
                            <Ionicons name="close-circle" size={19} color="#7B7490" />
                          </Pressable>
                        )}
                      </View>
                    );
                  })}
                </View>

                {!busy && (
                  <Pressable
                    style={styles.addMoreButton}
                    onPress={() => void chooseFiles(true)}
                  >
                    <Ionicons name="add-circle-outline" size={18} color="#B7A8FF" />
                    <Text style={styles.addMoreText}>Add more files</Text>
                  </Pressable>
                )}
              </View>
            )}

            <Text style={styles.fieldLabel}>PC destination folder</Text>
            <TextInput
              value={destinationPath}
              onChangeText={setDestinationPath}
              placeholder="Downloads/Blinky (default) or absolute PC folder path"
              placeholderTextColor="#817C98"
              style={styles.instructionInput}
              editable={!busy}
              autoCapitalize="none"
              autoCorrect={false}
              accessibilityLabel="PC destination folder"
            />
            <Text style={styles.helpText}>Enter an existing writable folder path on your PC. Leave blank for Downloads/Blinky.</Text>

            {/* Instruction input */}
            <Text style={styles.fieldLabel}>AiCut instruction (optional)</Text>
            <TextInput
              value={instruction}
              onChangeText={setInstruction}
              placeholder={
                selectedFiles.length >= 2
                  ? 'e.g. merge these videos, add background music at 25% volume, add captions…'
                  : 'e.g. trim from 3 to 20 seconds, or add Instagram captions…'
              }
              placeholderTextColor="#817C98"
              style={styles.instructionInput}
              multiline
              editable={!busy && session?.phase !== 'done'}
              autoCorrect
            />
            <Text style={styles.helpText}>Leave blank to upload every selected file. Enter a merge, trim, audio, or captions request to run AiCut on uploaded media. PDFs and images are still transferred.</Text>

            {/* Progress Card */}
            {session && busy && (
              <View style={styles.statusCard}>
                <View style={styles.statusHeading}>
                  <ActivityIndicator size="small" color="#FF7254" />
                  <Text style={styles.statusText}>{phaseLabel}</Text>
                </View>
                {(session.phase === 'uploading' || session.phase === 'downloading') && (
                  <ProgressBar bytes={totalTransferredBytes} total={totalTargetBytes} />
                )}
              </View>
            )}

            {/* Error Card */}
            {session?.phase === 'error' && (
              <View style={styles.errorCard}>
                <Text style={styles.errorText}>{session.error}</Text>
                <Pressable
                  style={styles.secondaryButton}
                  onPress={() => void startBatchTransfer()}
                >
                  <Text style={styles.secondaryButtonText}>Retry transfer</Text>
                </Pressable>
              </View>
            )}

            {/* Done Card */}
            {session?.phase === 'done' && (
              <View style={styles.doneCard}>
                <Ionicons name="checkmark-circle" size={24} color="#43D6A1" />
                <View style={styles.fileDetails}>
                  <Text style={styles.doneTitle}>Transfer complete</Text>
                  <Text style={styles.fileSize} numberOfLines={1}>
                    {session.output?.name ||
                      (selectedFiles.length > 1
                        ? `${selectedFiles.length} files saved to ${session.destinationPath}`
                        : `${selectedFiles[0]?.name} · Saved to ${session.destinationPath}`)}
                  </Text>
                </View>
                {!!session.localUri && (
                  <Pressable style={styles.shareButton} onPress={() => void shareFile()}>
                    <Ionicons name="share-outline" size={17} color="#FFFFFF" />
                    <Text style={styles.shareText}>Share</Text>
                  </Pressable>
                )}
              </View>
            )}
          </ScrollView>

          {/* Action Footer */}
          <View style={styles.actions}>
            <Pressable style={[styles.secondaryButton, busy && styles.disabledButton]} onPress={onClose}>
              <Text style={styles.secondaryButtonText}>Close</Text>
            </Pressable>

            <Pressable
              style={[
                styles.primaryButton,
                (!connected || selectedFiles.length === 0 || busy) && styles.disabledButton,
              ]}
              onPress={() => void startBatchTransfer()}
              disabled={!connected || selectedFiles.length === 0 || busy}
            >
              <Text style={styles.primaryButtonText}>{primaryButtonLabel}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
});

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.72)', justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '90%',
    backgroundColor: '#100D1B',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    borderWidth: 1,
    borderColor: '#302942',
    paddingBottom: Platform.OS === 'ios' ? 30 : 18,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 22,
    paddingTop: 22,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#282338',
  },
  headerTitleWrap: { flex: 1, marginRight: 10 },
  title: { color: '#FFFFFF', fontSize: 18, fontWeight: '700' },
  subtitle: { color: '#A19BB8', fontSize: 12, marginTop: 4 },
  closeButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#211C2D',
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: { padding: 20, gap: 14 },
  notice: {
    color: '#F5C76D',
    backgroundColor: '#362A14',
    borderRadius: 10,
    padding: 11,
    fontSize: 12,
    lineHeight: 17,
  },
  pickButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 9,
    minHeight: 48,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#514366',
    backgroundColor: '#211A30',
  },
  pickButtonText: { color: '#F5F2FF', fontWeight: '600', fontSize: 13 },
  selectedFilesContainer: { gap: 8 },
  selectedFilesHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 2,
  },
  selectedFilesCount: { color: '#B7A8FF', fontSize: 12, fontWeight: '600' },
  clearAllText: { color: '#FF7254', fontSize: 12, fontWeight: '600' },
  fileList: { gap: 8, maxHeight: 210 },
  fileCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 11,
    borderRadius: 12,
    backgroundColor: '#191527',
    borderWidth: 1,
    borderColor: '#312B42',
  },
  fileDetails: { flex: 1 },
  fileName: { color: '#F3F0FF', fontSize: 13, fontWeight: '600' },
  fileSize: { color: '#A19BB8', fontSize: 11, marginTop: 3 },
  itemStatus: { width: 24, alignItems: 'center', justifyContent: 'center' },
  removeFileBtn: { padding: 4 },
  addMoreButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 9,
    borderRadius: 10,
    backgroundColor: '#1E182D',
    borderWidth: 1,
    borderColor: '#382F4E',
  },
  addMoreText: { color: '#B7A8FF', fontSize: 12, fontWeight: '600' },
  fieldLabel: { color: '#E8E4F4', fontSize: 12, fontWeight: '600', marginBottom: -8 },
  instructionInput: {
    minHeight: 76,
    maxHeight: 130,
    color: '#FFFFFF',
    fontSize: 13,
    lineHeight: 19,
    backgroundColor: '#191527',
    borderColor: '#342E45',
    borderWidth: 1,
    borderRadius: 12,
    padding: 12,
    textAlignVertical: 'top',
  },
  helpText: { color: '#9791AA', fontSize: 11, lineHeight: 16, marginTop: -5 },
  statusCard: {
    backgroundColor: '#1A1725',
    borderColor: '#383149',
    borderWidth: 1,
    borderRadius: 12,
    padding: 13,
  },
  statusHeading: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  statusText: { color: '#E6E1F2', fontSize: 12, flex: 1 },
  progressWrap: { marginTop: 12 },
  progressTrack: { height: 6, borderRadius: 3, overflow: 'hidden', backgroundColor: '#363044' },
  progressFill: { height: '100%', borderRadius: 3, backgroundColor: '#FF7254' },
  progressLabel: { marginTop: 6, color: '#A19BB8', fontSize: 10 },
  errorCard: {
    borderWidth: 1,
    borderColor: '#753932',
    backgroundColor: '#301A1C',
    borderRadius: 12,
    padding: 13,
    gap: 11,
  },
  errorText: { color: '#FFB0A3', fontSize: 12, lineHeight: 17 },
  doneCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 13,
    borderWidth: 1,
    borderColor: '#285C4D',
    backgroundColor: '#12251F',
    borderRadius: 12,
  },
  doneTitle: { color: '#DDFBF1', fontSize: 12, fontWeight: '700' },
  shareButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: '#3C34A0',
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 9,
  },
  shareText: { color: '#FFFFFF', fontWeight: '600', fontSize: 11 },
  actions: {
    flexDirection: 'row',
    gap: 10,
    paddingHorizontal: 20,
    paddingTop: 14,
    borderTopWidth: 1,
    borderTopColor: '#282338',
  },
  primaryButton: {
    flex: 1,
    minHeight: 46,
    borderRadius: 12,
    backgroundColor: '#FF5A36',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  primaryButtonText: { color: '#FFFFFF', fontSize: 13, fontWeight: '700' },
  secondaryButton: {
    minHeight: 42,
    minWidth: 84,
    borderRadius: 11,
    borderWidth: 1,
    borderColor: '#4A435C',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  secondaryButtonText: { color: '#E1DDEE', fontSize: 12, fontWeight: '600' },
  disabledButton: { opacity: 0.45 },
});
