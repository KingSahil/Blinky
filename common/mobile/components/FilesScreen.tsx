import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, typography, radius, spacing } from '../theme/theme';

interface FilesScreenProps {
  isConnected: boolean;
  onOpenFile?: (path: string) => void;
}

const MOCK_FOLDERS = [
  { id: 'desktop', name: 'Desktop', icon: 'desktop-outline', count: '12 items' },
  { id: 'downloads', name: 'Downloads', icon: 'download-outline', count: '45 items' },
  { id: 'documents', name: 'Documents', icon: 'document-text-outline', count: '128 items' },
  { id: 'pictures', name: 'Pictures', icon: 'image-outline', count: '304 items' },
];

const MOCK_RECENT = [
  { id: '1', name: 'Project_Proposal.pdf', size: '2.4 MB', type: 'pdf', date: 'Today, 2:30 PM' },
  { id: '2', name: 'screenshot_12.png', size: '840 KB', type: 'image', date: 'Yesterday' },
  { id: '3', name: 'App.tsx', size: '12 KB', type: 'code', date: 'Yesterday' },
  { id: '4', name: 'budget_2024.xlsx', size: '1.1 MB', type: 'excel', date: 'Oct 12' },
];

export function FilesScreen({ isConnected, onOpenFile }: FilesScreenProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const handlePressItem = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    // In a real app, this would request the file over WebSocket or trigger PC to open it
  };

  const getFileIcon = (type: string) => {
    switch(type) {
      case 'pdf': return 'document-outline';
      case 'image': return 'image-outline';
      case 'code': return 'code-slash-outline';
      case 'excel': return 'stats-chart-outline';
      default: return 'document-outline';
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>PC Files</Text>
        <TouchableOpacity style={styles.headerBtn}>
          <Ionicons name="filter" size={20} color={colors.textSecondary} />
        </TouchableOpacity>
      </View>

      <View style={styles.searchContainer}>
        <Ionicons name="search" size={20} color={colors.textMuted} style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          placeholder="Search files on PC..."
          placeholderTextColor={colors.textMuted}
          value={searchQuery}
          onChangeText={setSearchQuery}
          editable={isConnected}
        />
      </View>

      {!isConnected ? (
        <View style={styles.emptyState}>
          <Ionicons name="cloud-offline-outline" size={48} color={colors.textMuted} style={{ marginBottom: spacing.md }} />
          <Text style={styles.emptyTitle}>PC Disconnected</Text>
          <Text style={styles.emptySubtitle}>Connect to your desktop to browse its file system remotely.</Text>
        </View>
      ) : (
        <ScrollView style={styles.scrollArea} showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: spacing.xxxl }}>
          
          <Text style={styles.sectionTitle}>QUICK ACCESS</Text>
          <View style={styles.grid}>
            {MOCK_FOLDERS.map((folder) => (
              <TouchableOpacity key={folder.id} style={styles.folderCard} onPress={handlePressItem} activeOpacity={0.7}>
                <View style={styles.folderIconBox}>
                  <Ionicons name={folder.icon as any} size={24} color={colors.accent} />
                </View>
                <Text style={styles.folderName}>{folder.name}</Text>
                <Text style={styles.folderCount}>{folder.count}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[styles.sectionTitle, { marginTop: spacing.xl }]}>RECENT FILES</Text>
          <View style={styles.list}>
            {MOCK_RECENT.map((file) => (
              <TouchableOpacity key={file.id} style={styles.listItem} onPress={handlePressItem} activeOpacity={0.7}>
                <View style={styles.fileIconBox}>
                  <Ionicons name={getFileIcon(file.type)} size={22} color={colors.textSecondary} />
                </View>
                <View style={styles.fileDetails}>
                  <Text style={styles.fileName} numberOfLines={1}>{file.name}</Text>
                  <Text style={styles.fileMeta}>{file.size} • {file.date}</Text>
                </View>
                <Ionicons name="chevron-forward" size={16} color={colors.borderLight} />
              </TouchableOpacity>
            ))}
          </View>

        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.lg,
    paddingBottom: spacing.sm,
  },
  headerTitle: {
    ...typography.heading2,
    color: colors.textPrimary,
  },
  headerBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    marginHorizontal: spacing.md,
    marginBottom: spacing.md,
    borderRadius: radius.round,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  searchIcon: {
    marginRight: spacing.sm,
  },
  searchInput: {
    flex: 1,
    ...typography.bodyMedium,
    color: colors.textPrimary,
    paddingVertical: 12,
  },
  emptyState: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  emptyTitle: {
    ...typography.heading3,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  emptySubtitle: {
    ...typography.bodyMedium,
    color: colors.textMuted,
    textAlign: 'center',
    lineHeight: 22,
  },
  scrollArea: {
    flex: 1,
  },
  sectionTitle: {
    ...typography.label,
    color: colors.textMuted,
    marginLeft: spacing.md,
    marginBottom: spacing.sm,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: spacing.md,
    gap: spacing.md,
    justifyContent: 'space-between',
  },
  folderCard: {
    width: '47%',
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  folderIconBox: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: 'rgba(255, 90, 54, 0.1)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  folderName: {
    ...typography.bodyMedium,
    color: colors.textPrimary,
    fontWeight: '600',
    marginBottom: 4,
  },
  folderCount: {
    ...typography.bodySmall,
    color: colors.textMuted,
  },
  list: {
    paddingHorizontal: spacing.md,
  },
  listItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
  },
  fileIconBox: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceElevated,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  fileDetails: {
    flex: 1,
    marginRight: spacing.sm,
  },
  fileName: {
    ...typography.bodyMedium,
    color: colors.textPrimary,
    fontWeight: '500',
    marginBottom: 4,
  },
  fileMeta: {
    ...typography.bodySmall,
    color: colors.textMuted,
  }
});
