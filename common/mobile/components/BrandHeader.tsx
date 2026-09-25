import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography, radius } from '../theme/theme';
import * as Haptics from 'expo-haptics';

interface BrandHeaderProps {
  status: 'disconnected' | 'connecting' | 'connected' | 'error';
  isConnected: boolean;
  onPressConnection: () => void;
  onPressMenu: () => void;
}

export function BrandHeader({ status, isConnected, onPressConnection, onPressMenu }: BrandHeaderProps) {
  return (
    <View style={styles.header}>
      {/* Brand / Logo */}
      <View style={styles.brandContainer}>
        <Ionicons name="sparkles" size={22} color={colors.accent} style={{ marginRight: 6 }} />
        <Text style={styles.brandText}>Blinky</Text>
      </View>

      {/* Right Controls */}
      <View style={styles.controlsContainer}>
        {/* Connection Pill */}
        <TouchableOpacity
          style={styles.connectionPill}
          onPress={() => {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            onPressConnection();
          }}
          activeOpacity={0.7}
        >
          <View
            style={[
              styles.statusDot,
              {
                backgroundColor: isConnected
                  ? colors.success
                  : status === 'connecting'
                  ? colors.warning
                  : colors.danger,
              },
            ]}
          />
          <Text style={styles.connectionText}>
            {isConnected ? 'My PC' : status === 'connecting' ? 'Connecting...' : 'Disconnected'}
          </Text>
          <Ionicons name="chevron-down" size={14} color={colors.textSecondary} style={{ marginLeft: 4 }} />
        </TouchableOpacity>

        {/* Overflow Menu Button */}
        <TouchableOpacity
          style={styles.menuButton}
          onPress={() => {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            onPressMenu();
          }}
          activeOpacity={0.7}
        >
          <Ionicons name="ellipsis-horizontal" size={18} color={colors.textPrimary} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: 'transparent',
  },
  brandContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  brandText: {
    ...typography.heading3,
    fontWeight: typography.heading3.fontWeight as '600',
    color: colors.textPrimary,
    letterSpacing: -0.5,
  },
  controlsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  connectionPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  connectionText: {
    ...typography.bodySmall,
    color: colors.textPrimary,
    fontWeight: '500',
  },
  menuButton: {
    width: 32,
    height: 32,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceElevated,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
});
