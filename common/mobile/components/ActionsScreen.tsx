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
  { id: 'sleep', title: 'Sleep PC', icon: 'moon', color: '#8B5CF6', command: 'Put the computer to sleep' },
  { id: 'lock', title: 'Lock Screen', icon: 'lock-closed', color: '#F59E0B', command: 'Lock the computer' },
  { id: 'music', title: 'Play/Pause', icon: 'play', color: '#10B981', command: 'Toggle media playback' },
  { id: 'mute', title: 'Mute Audio', icon: 'volume-mute', color: '#EF4444', command: 'Mute the system volume' },
  { id: 'screenshot', title: 'Screenshot', icon: 'camera', color: '#3B82F6', command: 'Take a screenshot of the desktop' },
  { id: 'chrome', title: 'Open Browser', icon: 'globe', color: '#06B6D4', command: 'Open Google Chrome' },
  { id: 'lights', title: 'Toggle Lights', icon: 'bulb', color: '#FCD34D', command: 'Toggle smart lights' },
  { id: 'terminal', title: 'Terminal', icon: 'terminal', color: '#6B7280', command: 'Open a new terminal window' },
];

interface ActionsScreenProps {
  onExecuteAction: (command: string) => void;
  isConnected: boolean;
}

export function ActionsScreen({ onExecuteAction, isConnected }: ActionsScreenProps) {
  const handleAction = (command: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    onExecuteAction(command);
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.headerTitle}>Quick Actions</Text>
      <Text style={styles.headerSubtitle}>Tap to execute commands instantly on your PC.</Text>
      
      <View style={styles.grid}>
        {QUICK_ACTIONS.map((action) => (
          <TouchableOpacity 
            key={action.id} 
            style={[styles.card, !isConnected && styles.cardDisabled]}
            disabled={!isConnected}
            activeOpacity={0.7}
            onPress={() => handleAction(action.command)}
          >
            <View style={[styles.iconBox, { backgroundColor: `${action.color}15`, borderColor: `${action.color}30` }]}>
              <Ionicons name={action.icon} size={28} color={action.color} />
            </View>
            <Text style={styles.cardTitle}>{action.title}</Text>
          </TouchableOpacity>
        ))}
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
  }
});
