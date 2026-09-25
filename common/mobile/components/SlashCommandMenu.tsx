import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, typography, radius, spacing } from '../theme/theme';

export interface SlashCommandDef {
  id: string;
  title: string;
  badge: string;
  description: string;
  prefix: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
}

interface SlashCommandMenuProps {
  queryText: string;
  onSelectCommand: (prefix: string) => void;
  commands: SlashCommandDef[];
}

export function SlashCommandMenu({ queryText, onSelectCommand, commands }: SlashCommandMenuProps) {
  const showSlashMenu = queryText.startsWith('/') && !queryText.includes(' ');
  if (!showSlashMenu) return null;

  const slashFilter = queryText.toLowerCase().replace('/', '');
  const filteredCommands = commands.filter(cmd =>
    !slashFilter ||
    cmd.id.includes(slashFilter) ||
    cmd.title.toLowerCase().includes(slashFilter) ||
    cmd.badge.toLowerCase().includes(slashFilter)
  );

  if (filteredCommands.length === 0) return null;

  return (
    <View style={styles.container}>
      {filteredCommands.map((cmd, idx) => (
        <TouchableOpacity
          key={cmd.id}
          style={[
            styles.menuItem,
            idx < filteredCommands.length - 1 && styles.menuItemBorder
          ]}
          onPress={() => {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            onSelectCommand(cmd.prefix);
          }}
          activeOpacity={0.7}
        >
          <View style={styles.iconContainer}>
            <Ionicons name={cmd.icon} size={16} color={colors.textPrimary} />
          </View>
          <View style={styles.content}>
            <Text style={styles.title}>{cmd.title}</Text>
            <Text style={styles.description} numberOfLines={1}>{cmd.description}</Text>
          </View>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{cmd.badge}</Text>
          </View>
        </TouchableOpacity>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    backgroundColor: '#151518',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 8,
    overflow: 'hidden',
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.md,
    backgroundColor: 'transparent',
  },
  menuItemBorder: {
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.04)',
  },
  iconContainer: {
    width: 32,
    height: 32,
    borderRadius: radius.md,
    backgroundColor: 'rgba(255,255,255,0.06)',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.02)',
  },
  content: {
    flex: 1,
  },
  title: {
    ...typography.bodyMedium,
    color: colors.textPrimary,
    fontWeight: '600',
    marginBottom: 2,
  },
  description: {
    ...typography.bodySmall,
    color: colors.textMuted,
    fontSize: 11,
  },
  badge: {
    backgroundColor: 'rgba(255,255,255,0.06)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  badgeText: {
    ...typography.label,
    color: colors.textSecondary,
    fontSize: 9,
  },
});
