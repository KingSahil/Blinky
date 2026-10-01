import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography } from '../theme/theme';
import { TabScreen } from '../types';
import * as Haptics from 'expo-haptics';

interface BottomNavigationProps {
  activeTab: TabScreen;
  onTabChange: (tab: TabScreen) => void;
  isPcLocked?: boolean;
}

const TABS: { id: TabScreen; icon: keyof typeof Ionicons.glyphMap; label: string }[] = [
  { id: 'Chat', icon: 'chatbubbles-outline', label: 'Chat' },
  { id: 'Actions', icon: 'flash-outline', label: 'Actions' },
  { id: 'Notebook', icon: 'book-outline', label: 'Notebook' },
  { id: 'Files', icon: 'folder-outline', label: 'Files' },
  { id: 'PC', icon: 'grid-outline', label: 'PC' },
];

export function BottomNavigation({ activeTab, onTabChange, isPcLocked = false }: BottomNavigationProps) {
  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const showLock = tab.id === 'PC' && isPcLocked;
          return (
            <TouchableOpacity
              key={tab.id}
              style={styles.tab}
              onPress={() => {
                if (!isActive) {
                  Haptics.selectionAsync();
                  onTabChange(tab.id);
                }
              }}
              activeOpacity={0.7}
            >
              <View style={styles.iconWrapper}>
                <Ionicons
                  name={isActive ? tab.icon.replace('-outline', '') as any : tab.icon}
                  size={24}
                  color={isActive ? colors.accent : colors.textMuted}
                />
                {showLock && (
                  <View style={styles.lockBadge}>
                    <Ionicons name="lock-closed" size={9} color={colors.accent} />
                  </View>
                )}
              </View>
              <Text style={[styles.label, isActive && styles.labelActive]}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: colors.background,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  container: {
    flexDirection: 'row',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: Platform.OS === 'ios' ? 0 : spacing.sm,
    backgroundColor: colors.background,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    ...typography.label,
    fontSize: 10,
    marginTop: 4,
    color: colors.textMuted,
  },
  labelActive: {
    color: colors.accent,
  },
  iconWrapper: {
    position: 'relative',
    alignItems: 'center',
    justifyContent: 'center',
  },
  lockBadge: {
    position: 'absolute',
    top: -3,
    right: -8,
    backgroundColor: '#181920',
    borderRadius: 6,
    paddingHorizontal: 2,
    paddingVertical: 1,
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.45)',
  },
});
