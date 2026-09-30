import React from 'react';
import { View, Text, TouchableOpacity, Image, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { MarkdownRenderer } from '../MarkdownRenderer';
import { colors, typography, radius, spacing } from '../theme/theme';
import { Message } from '../types';
import * as Haptics from 'expo-haptics';

interface MessageBubbleProps {
  message: Message;
  formatTime: (ms: number) => string;
  onEnlargeScreenshot: (uri: string) => void;
}

export function MessageBubble({ message, formatTime, onEnlargeScreenshot }: MessageBubbleProps) {
  const isUser = message.sender === 'user';
  const attachedFiles = message.attachedFiles || (message.attachedFile ? [message.attachedFile] : []);

  return (
    <View style={isUser ? styles.userRow : styles.blinkyRow}>
      {!isUser && (
        <View style={styles.avatar}>
          <Ionicons name="sparkles" size={14} color={colors.accent} />
        </View>
      )}

      <View style={isUser ? styles.userBubble : styles.blinkyBubble}>
        {/* Attached File/Photo Preview */}
        {attachedFiles.map((attachedFile, index) => (
          <TouchableOpacity
            key={`${attachedFile.uri}-${index}`}
            style={styles.attachedCard}
            activeOpacity={attachedFile.type === 'image' || attachedFile.mimeType?.startsWith('image') ? 0.8 : 1}
            onPress={() => {
              if (attachedFile.type === 'image' || attachedFile.mimeType?.startsWith('image')) {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                onEnlargeScreenshot(attachedFile.uri);
              }
            }}
          >
            {attachedFile.type === 'image' || attachedFile.mimeType?.startsWith('image') ? (
              <View style={styles.attachedImageContainer}>
                <Image source={{ uri: attachedFile.uri }} style={styles.attachedImage} />
                <View style={styles.attachedImageOverlay}>
                  <Ionicons name="expand-outline" size={12} color="#FFFFFF" style={{ marginRight: 4 }} />
                  <Text style={styles.attachedImageText}>Tap to peek</Text>
                </View>
              </View>
            ) : (
              <View style={styles.attachedFileRow}>
                <Ionicons name="document-text" size={18} color={isUser ? "#FFFFFF" : colors.accent} style={{ marginRight: 6 }} />
                <Text style={[styles.attachedFileName, isUser && { color: "#FFFFFF" }]} numberOfLines={1}>
                  {attachedFile.name}
                </Text>
                {attachedFile.size ? (
                  <Text style={[styles.attachedFileSize, isUser && { color: "rgba(255,255,255,0.7)" }]}>
                    ({attachedFile.size} MB)
                  </Text>
                ) : null}
              </View>
            )}
          </TouchableOpacity>
        ))}

        <MarkdownRenderer content={message.text} isUser={isUser} />

        {/* Active Progress Card */}
        {!isUser && message.progress && (
          <View style={styles.progressCard}>
            <View style={styles.progressRow}>
              <View style={styles.progressBarWrapper}>
                <View style={[styles.progressBarFill, { width: `${message.progress.percent}%` }]} />
              </View>
              <Text style={styles.progressPercent}>{message.progress.percent}%</Text>
            </View>

            <View style={styles.statusRow}>
              <View style={styles.statusDot} />
              <Text style={styles.statusText} numberOfLines={2}>
                {message.progress.statusText}
              </Text>
            </View>

            <View style={styles.timerRow}>
              <Ionicons name="time-outline" size={14} color={colors.textSecondary} style={{ marginRight: 6 }} />
              <Text style={styles.timerText}>{formatTime(message.progress.duration)}</Text>
            </View>
          </View>
        )}

        {/* Screenshot Result */}
        {!isUser && message.screenshot_b64 && (
          <TouchableOpacity
            activeOpacity={0.88}
            onPress={() => {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              onEnlargeScreenshot(`data:image/jpeg;base64,${message.screenshot_b64}`);
            }}
            style={styles.screenshotTouchable}
          >
            <Image
              source={{ uri: `data:image/jpeg;base64,${message.screenshot_b64}` }}
              style={styles.screenshot}
            />
            <View style={styles.enlargeBadge}>
              <Ionicons name="expand-outline" size={12} color={colors.textPrimary} style={{ marginRight: 4 }} />
              <Text style={styles.enlargeText}>Tap to enlarge</Text>
            </View>
          </TouchableOpacity>
        )}

        {/* Steps trace */}
        {!isUser && message.steps && message.steps.length > 0 && (
          <View style={styles.stepsContainer}>
            {message.steps.map((step: any, index: number) => (
              <View key={index} style={styles.stepItem}>
                <View style={styles.stepBadge}>
                  <Text style={styles.stepBadgeText}>{step.step || index + 1}</Text>
                </View>
                <View style={styles.stepContent}>
                  <Text style={styles.stepText}>{step.instruction}</Text>
                  {step.target_text && (
                    <View style={styles.stepTargetBadge}>
                      <Text style={styles.stepTargetText}>{step.target_text}</Text>
                    </View>
                  )}
                </View>
              </View>
            ))}
          </View>
        )}
      </View>

      <View style={isUser ? styles.userMeta : styles.blinkyMeta}>
        <Text style={styles.timestamp}>{message.timestamp}</Text>
        {isUser && <Ionicons name="checkmark-done" size={14} color={colors.accent} style={{ marginLeft: 4 }} />}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  userRow: {
    alignSelf: 'flex-end',
    maxWidth: '80%',
    marginBottom: 16,
    alignItems: 'flex-end',
  },
  blinkyRow: {
    alignSelf: 'flex-start',
    maxWidth: '85%',
    marginBottom: 16,
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  userBubble: {
    backgroundColor: 'rgba(255, 90, 54, 0.06)',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: 20,
    borderBottomRightRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.3)',
  },
  blinkyBubble: {
    flex: 1,
    backgroundColor: '#121115',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: 20,
    borderTopLeftRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.06)',
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#1A1820',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.06)',
  },
  userMeta: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    marginTop: 6,
    paddingRight: 2,
  },
  blinkyMeta: {
    width: '100%',
    paddingLeft: 40,
    marginTop: 6,
  },
  timestamp: {
    ...typography.bodySmall,
    fontSize: 10,
    color: colors.textMuted,
  },
  progressCard: {
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceElevated,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  progressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  progressBarWrapper: {
    flex: 1,
    height: 4,
    backgroundColor: colors.surfacePressed,
    borderRadius: 2,
    marginRight: spacing.sm,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: colors.accent,
    borderRadius: 2,
  },
  progressPercent: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    fontWeight: '600',
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.accent,
    marginRight: 8,
  },
  statusText: {
    ...typography.bodySmall,
    color: colors.textPrimary,
    flex: 1,
  },
  timerRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  timerText: {
    ...typography.bodySmall,
    color: colors.textSecondary,
  },
  screenshotTouchable: {
    marginTop: spacing.md,
    borderRadius: radius.md,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  screenshot: {
    width: '100%',
    height: 180,
    resizeMode: 'cover',
  },
  enlargeBadge: {
    position: 'absolute',
    bottom: 8,
    right: 8,
    backgroundColor: 'rgba(0,0,0,0.6)',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: radius.round,
  },
  enlargeText: {
    ...typography.label,
    color: colors.textPrimary,
  },
  stepsContainer: {
    marginTop: spacing.md,
    gap: spacing.sm,
  },
  stepItem: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceElevated,
    padding: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  stepBadge: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.surfacePressed,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
  },
  stepBadgeText: {
    ...typography.label,
    color: colors.textSecondary,
    fontSize: 9,
  },
  stepContent: {
    flex: 1,
  },
  stepText: {
    ...typography.bodySmall,
    color: colors.textPrimary,
  },
  stepTargetBadge: {
    marginTop: 6,
    backgroundColor: colors.surfacePressed,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    alignSelf: 'flex-start',
  },
  stepTargetText: {
    ...typography.bodySmall,
    fontSize: 10,
    color: colors.textSecondary,
    fontFamily: 'monospace',
  },
  attachedCard: {
    marginTop: spacing.xs,
    marginBottom: spacing.xs,
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  attachedImageContainer: {
    borderRadius: radius.md,
    overflow: 'hidden',
    position: 'relative',
  },
  attachedImage: {
    width: 220,
    height: 140,
    borderRadius: radius.md,
  },
  attachedImageOverlay: {
    position: 'absolute',
    bottom: 6,
    right: 6,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: radius.round,
    flexDirection: 'row',
    alignItems: 'center',
  },
  attachedImageText: {
    ...typography.bodySmall,
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '500',
  },
  attachedFileRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.sm,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
  },
  attachedFileName: {
    ...typography.bodySmall,
    color: colors.textPrimary,
    fontWeight: '500',
    flexShrink: 1,
  },
  attachedFileSize: {
    ...typography.bodySmall,
    color: colors.textMuted,
    fontSize: 10,
    marginLeft: 4,
  },
});
