import React, { useState, useRef, useEffect } from 'react';
import { 
  View, 
  Text, 
  TextInput, 
  TouchableOpacity, 
  StyleSheet, 
  Animated, 
  Keyboard, 
  Platform,
  LayoutAnimation,
  UIManager
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, typography, radius, spacing } from '../theme/theme';

// LayoutAnimation works automatically on Android Fabric (New Architecture)

interface AttachedFile {
  uri: string;
  name: string;
  type?: string;
  size?: number;
}

interface CommandComposerProps {
  queryText: string;
  setQueryText: (text: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  status: 'idle' | 'processing' | 'success' | 'error';
  isConnected: boolean;
  
  // Voice recording
  isVoiceRecording: boolean;
  isVoiceTranscribing: boolean;
  onToggleVoice: () => void;
  recordingDuration?: number; // optionally pass in seconds
}

export function CommandComposer({
  queryText,
  setQueryText,
  onSubmit,
  onStop,
  status,
  isConnected,
  isVoiceRecording,
  isVoiceTranscribing,
  onToggleVoice
}: CommandComposerProps) {
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [attachedFile, setAttachedFile] = useState<AttachedFile | null>(null);
  const [recordingDuration, setRecordingDuration] = useState(0);

  const attachAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.spring(attachAnim, {
      toValue: showAttachMenu ? 1 : 0,
      useNativeDriver: true,
      friction: 9,
      tension: 70
    }).start();
  }, [showAttachMenu]);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isVoiceRecording) {
      setRecordingDuration(0);
      interval = setInterval(() => {
        setRecordingDuration(prev => prev + 1);
      }, 1000);
    } else {
      setRecordingDuration(0);
    }
    return () => clearInterval(interval);
  }, [isVoiceRecording]);

  const handleToggleAttach = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setShowAttachMenu(!showAttachMenu);
  };

  const handleAttachOption = (option: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setShowAttachMenu(false);
    // Mock attachment for now based on prompt
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setAttachedFile({
      uri: 'mock-uri',
      name: option === 'File' ? 'Project_Proposal.pdf' : `Attached_${option}.jpg`,
      size: 1.2
    });
  };

  const handleRemoveAttachment = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setAttachedFile(null);
  };

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <View style={styles.wrapper}>
      {/* Attachment Menu Popup */}
      {showAttachMenu && (
        <Animated.View 
          style={[
            styles.attachMenu, 
            {
              opacity: attachAnim,
              transform: [
                {
                  translateY: attachAnim.interpolate({
                    inputRange: [0, 1],
                    outputRange: [10, 0]
                  })
                },
                {
                  scale: attachAnim.interpolate({
                    inputRange: [0, 1],
                    outputRange: [0.94, 1]
                  })
                }
              ]
            }
          ]}
        >
          <View style={styles.attachMenuRow}>
            <AttachOption icon="document-text-outline" label="File" sublabel="PDF, DOC, etc." onPress={() => handleAttachOption('File')} />
            <AttachOption icon="image-outline" label="Image" sublabel="JPG, PNG, etc." onPress={() => handleAttachOption('Image')} />
            <AttachOption icon="camera-outline" label="Camera" sublabel="Take a photo" onPress={() => handleAttachOption('Camera')} />
            <AttachOption icon="desktop-outline" label="Screenshot" sublabel="Capture screen" onPress={() => handleAttachOption('Screenshot')} />
          </View>
        </Animated.View>
      )}

      {/* Main Composer Box */}
      <View style={[
        styles.composerBox, 
        !isConnected && styles.composerDisabled,
        isVoiceRecording && styles.composerRecording
      ]}>
        
        {/* Attachment Preview (if any) */}
        {attachedFile && !isVoiceRecording && (
          <View style={styles.attachmentPreview}>
            <View style={styles.attachmentIconBox}>
              <Ionicons name="document-text" size={20} color={colors.accent} />
            </View>
            <View style={styles.attachmentDetails}>
              <Text style={styles.attachmentName} numberOfLines={1}>{attachedFile.name}</Text>
              {attachedFile.size && <Text style={styles.attachmentSize}>{attachedFile.size} MB</Text>}
            </View>
            <TouchableOpacity onPress={handleRemoveAttachment} style={styles.attachmentRemove}>
              <Ionicons name="close" size={16} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>
        )}

        <View style={styles.inputRow}>
          {/* Left: Microphone */}
          <TouchableOpacity
            style={styles.micBtn}
            onPress={onToggleVoice}
            disabled={!isConnected || status === 'processing'}
            activeOpacity={0.7}
          >
            {isVoiceTranscribing ? (
              <Ionicons name="sync" size={20} color={colors.accent} style={{ opacity: 0.7 }} />
            ) : (
              <Ionicons 
                name={isVoiceRecording ? "mic" : "mic"} 
                size={22} 
                color={isVoiceRecording ? colors.danger : colors.textSecondary} 
              />
            )}
          </TouchableOpacity>

          {/* Center: Input or Recording UI */}
          <View style={styles.centerSection}>
            {isVoiceRecording ? (
              <View style={styles.recordingUI}>
                <Text style={styles.recordingTime}>{formatDuration(recordingDuration)}</Text>
                <View style={styles.waveformMock}>
                  {/* Mock animated waveform lines */}
                  {[1, 2, 3, 4, 3, 2, 1, 3, 5, 4, 2, 1].map((h, i) => (
                    <View key={i} style={[styles.waveLine, { height: h * 3 }]} />
                  ))}
                </View>
                <Text style={styles.recordingHint}>Slide to cancel &gt;</Text>
              </View>
            ) : (
              <TextInput
                style={[styles.textInput, { color: '#FFFFFF' }]}
                placeholder="Message Blinky or /agy <prompt>"
                placeholderTextColor="rgba(255, 255, 255, 0.7)"
                value={queryText}
                onChangeText={setQueryText}
                editable={isConnected && status !== 'processing'}
                autoCapitalize="none"
                autoCorrect={false}
                multiline
                maxLength={2000}
                onFocus={() => setShowAttachMenu(false)}
                keyboardAppearance="dark"
                cursorColor={colors.accent}
                selectionColor="rgba(255, 90, 54, 0.3)"
              />
            )}
          </View>

          {/* Right: Attach & Send/Stop */}
          {!isVoiceRecording && (
            <View style={styles.rightActions}>
              {queryText.length === 0 && (
                <TouchableOpacity 
                  style={styles.attachBtn} 
                  onPress={handleToggleAttach}
                  activeOpacity={0.7}
                >
                  <Ionicons name="attach-outline" size={24} color={colors.textSecondary} style={{ transform: [{ rotate: '45deg' }] }} />
                </TouchableOpacity>
              )}

              {status === 'processing' ? (
                <TouchableOpacity 
                  style={styles.stopBtn} 
                  onPress={onStop}
                  activeOpacity={0.7}
                >
                  <View style={styles.stopSquare} />
                </TouchableOpacity>
              ) : (
                <TouchableOpacity 
                  style={[
                    styles.sendBtn,
                    (!isConnected || (!queryText.trim() && !attachedFile)) && styles.sendBtnDisabled
                  ]}
                  onPress={() => {
                    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    onSubmit();
                  }}
                  disabled={!isConnected || (!queryText.trim() && !attachedFile)}
                  activeOpacity={0.7}
                >
                  <Ionicons name="arrow-up" size={20} color={(!isConnected || (!queryText.trim() && !attachedFile)) ? colors.accent : "#FFFFFF"} />
                </TouchableOpacity>
              )}
            </View>
          )}

          {isVoiceRecording && (
            <TouchableOpacity 
              style={styles.recordingStopBtn} 
              onPress={onToggleVoice}
              activeOpacity={0.7}
            >
              <View style={styles.recordingStopSquare} />
            </TouchableOpacity>
          )}
        </View>
      </View>
    </View>
  );
}

function AttachOption({ icon, label, sublabel, onPress }: { icon: any, label: string, sublabel: string, onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.attachOption} onPress={onPress} activeOpacity={0.7}>
      <View style={styles.attachOptionIcon}>
        <Ionicons name={icon} size={22} color={colors.textPrimary} />
      </View>
      <Text style={styles.attachOptionLabel}>{label}</Text>
      <Text style={styles.attachOptionSublabel} numberOfLines={1}>{sublabel}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.xs,
    paddingBottom: spacing.md, // Add bottom padding for safety
    backgroundColor: colors.background,
  },
  composerBox: {
    backgroundColor: '#111114',
    borderRadius: 30,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    overflow: 'hidden',
    padding: 6,
  },
  composerRecording: {
    backgroundColor: 'rgba(239, 68, 68, 0.05)',
    borderColor: 'rgba(239, 68, 68, 0.2)',
  },
  composerDisabled: {
    opacity: 0.5,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    minHeight: 48,
  },
  micBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.03)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  centerSection: {
    flex: 1,
    marginHorizontal: 8,
    justifyContent: 'center',
    minHeight: 44,
    paddingVertical: 4,
  },
  textInput: {
    ...typography.bodyLarge,
    fontSize: 16,
    color: colors.textPrimary,
    maxHeight: 120,
    paddingTop: 8,
    paddingBottom: 8,
  },
  rightActions: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  attachBtn: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 4,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: {
    backgroundColor: 'rgba(255, 90, 54, 0.15)',
  },
  stopBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.1)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stopSquare: {
    width: 14,
    height: 14,
    backgroundColor: colors.textPrimary,
    borderRadius: 3,
  },
  recordingUI: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flex: 1,
  },
  recordingTime: {
    ...typography.bodySmall,
    color: colors.danger,
    fontVariant: ['tabular-nums'],
  },
  waveformMock: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    marginHorizontal: 8,
  },
  waveLine: {
    width: 2,
    backgroundColor: colors.danger,
    borderRadius: 1,
  },
  recordingHint: {
    ...typography.bodySmall,
    color: colors.textMuted,
    fontSize: 11,
  },
  recordingStopBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.3)',
    marginBottom: 2,
  },
  recordingStopSquare: {
    width: 14,
    height: 14,
    backgroundColor: colors.danger,
    borderRadius: 3,
  },
  attachMenu: {
    position: 'absolute',
    bottom: '100%',
    right: spacing.md,
    marginBottom: spacing.xs,
    backgroundColor: '#151518',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 8,
    padding: spacing.sm,
    zIndex: 100,
  },
  attachMenuRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  attachOption: {
    alignItems: 'center',
    width: 72,
    padding: spacing.xs,
    borderRadius: radius.md,
  },
  attachOptionIcon: {
    width: 44,
    height: 44,
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.04)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 6,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.02)',
  },
  attachOptionLabel: {
    ...typography.bodySmall,
    color: colors.textPrimary,
    fontSize: 11,
    marginBottom: 2,
  },
  attachOptionSublabel: {
    ...typography.bodySmall,
    color: colors.textMuted,
    fontSize: 9,
  },
  attachmentPreview: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.03)',
    marginHorizontal: 8,
    marginTop: 8,
    marginBottom: 4,
    padding: 8,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.05)',
  },
  attachmentIconBox: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: 'rgba(255, 90, 54, 0.1)',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  attachmentDetails: {
    flex: 1,
  },
  attachmentName: {
    ...typography.bodySmall,
    color: colors.textPrimary,
  },
  attachmentSize: {
    ...typography.bodySmall,
    color: colors.textMuted,
    fontSize: 10,
    marginTop: 2,
  },
  attachmentRemove: {
    padding: 4,
  },
});
