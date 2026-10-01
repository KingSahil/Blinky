import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, typography, radius, spacing } from '../theme/theme';

interface ActionItem {
  id: string;
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  command: string;
}

const QUICK_ACTIONS: ActionItem[] = [
  { id: 'music', title: 'Play/Pause', icon: 'play', color: '#10B981', command: 'media_play_pause' },
  { id: 'volume_up', title: 'Volume Up', icon: 'volume-high', color: '#38BDF8', command: 'volume_up' },
  { id: 'volume_down', title: 'Volume Down', icon: 'volume-low', color: '#818CF8', command: 'volume_down' },
  { id: 'mute', title: 'Mute Audio', icon: 'volume-mute', color: '#EF4444', command: 'volume_mute' },
  { id: 'screenshot', title: 'Screenshot', icon: 'camera', color: '#3B82F6', command: 'screenshot' },
  { id: 'chrome', title: 'Open Browser', icon: 'globe', color: '#06B6D4', command: 'open_browser' },
  { id: 'lights', title: 'Toggle Lights', icon: 'bulb', color: '#FCD34D', command: 'toggle_lights' },
  { id: 'terminal', title: 'Terminal', icon: 'terminal', color: '#6B7280', command: 'open_terminal' },
];

interface ActionsScreenProps {
  onExecuteAction: (command: string) => void;
  isConnected: boolean;
  isLightOn?: boolean;
}

export function ActionsScreen({ onExecuteAction, isConnected, isLightOn }: ActionsScreenProps) {
  const handleAction = (command: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    onExecuteAction(command);
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.headerTitle}>Quick Actions</Text>
      <Text style={styles.headerSubtitle}>Tap to execute commands instantly on your PC.</Text>
      
      <View style={styles.grid}>
        {QUICK_ACTIONS.map((action) => {
          const isLightsCard = action.id === 'lights';
          const cardTitle = isLightsCard
            ? (isLightOn ? 'Turn Off Light' : 'Toggle Lights')
            : action.title;
          const iconColor = isLightsCard && isLightOn ? '#FBBF24' : action.color;
          const iconBg = isLightsCard && isLightOn ? '#FBBF2435' : `${action.color}15`;
          const iconBorder = isLightsCard && isLightOn ? '#FBBF2480' : `${action.color}30`;

          return (
            <TouchableOpacity 
              key={action.id} 
              style={[
                styles.card,
                isLightsCard && isLightOn && styles.cardActiveLight,
                !isConnected && styles.cardDisabled
              ]}
              disabled={!isConnected}
              activeOpacity={0.7}
              onPress={() => handleAction(action.command)}
            >
              <View style={[styles.iconBox, { backgroundColor: iconBg, borderColor: iconBorder }]}>
                <Ionicons name={action.icon} size={28} color={iconColor} />
              </View>
              <Text style={[styles.cardTitle, isLightsCard && isLightOn && styles.cardTitleActive]}>
                {cardTitle}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    padding: spacing.md,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xxxl,
  },
  headerTitle: {
    ...typography.heading2,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  headerSubtitle: {
    ...typography.bodyMedium,
    color: colors.textMuted,
    marginBottom: spacing.xl,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    justifyContent: 'space-between',
  },
  card: {
    width: '47%',
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.borderLight,
    marginBottom: spacing.xs,
  },
  cardDisabled: {
    opacity: 0.5,
  },
  iconBox: {
    width: 60,
    height: 60,
    borderRadius: 30,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
    borderWidth: 1,
  },
  cardTitle: {
    ...typography.bodyMedium,
    color: colors.textPrimary,
    fontWeight: '600',
    textAlign: 'center',
  },
  cardActiveLight: {
    borderColor: '#FBBF2460',
    backgroundColor: '#1E1B13',
  },
  cardTitleActive: {
    color: '#FDE68A',
  },
});
