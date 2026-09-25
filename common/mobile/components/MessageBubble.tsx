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

  return (
    <View style={isUser ? styles.userRow : styles.blinkyRow}>
      {!isUser && (
        <View style={styles.avatar}>
          <Ionicons name="sparkles" size={14} color={colors.accent} />
        </View>
      )}

      <View style={isUser ? styles.userBubble : styles.blinkyBubble}>
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
    maxWidth: '85%',
    marginBottom: spacing.lg,
  },
  blinkyRow: {
    alignSelf: 'flex-start',
    maxWidth: '90%',
    marginBottom: spacing.lg,
  },
  userBubble: {
    backgroundColor: colors.surfaceElevated,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: radius.lg,
    borderBottomRightRadius: 4,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  blinkyBubble: {
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: radius.lg,
    borderTopLeftRadius: 4,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  avatar: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: colors.surfaceElevated,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 6,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  userMeta: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    marginTop: 6,
    paddingRight: 2,
  },
  blinkyMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 6,
    paddingLeft: 2,
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
});
