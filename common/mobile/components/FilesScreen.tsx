import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  RefreshControl,
  ActivityIndicator,
  Modal,
  Animated,
  PanResponder,
  Platform,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import * as IntentLauncher from 'expo-intent-launcher';
import { colors, typography, radius, spacing } from '../theme/theme';
import { QuickAccessFolder, FsEntry, FsDirContents, FsFileData } from '../usePCWebSocket';

interface FilesScreenProps {
  isConnected: boolean;
  quickAccessFolders?: QuickAccessFolder[];
  currentDirectory?: FsDirContents | null;
  recentFiles?: FsEntry[];
  searchResults?: FsEntry[];
  isLoading?: boolean;
  fsError?: string | null;
  fsFileData?: FsFileData | null;
  onFetchQuickAccess?: () => void;
  onListDirectory?: (path?: string) => void;
  onFetchRecentFiles?: () => void;
  onSearch?: (query: string, path?: string) => void;
  onOpenFileOnPC?: (path: string) => void;
  onOpenFileOnMobile?: (path: string) => void;
  onClearFsFileData?: () => void;
  onResetDirectory?: () => void;
  onPreviewImage?: (uri: string) => void;
  onAskBlinky?: (file: FsEntry) => void;
}

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico'];
const TEXT_EXTENSIONS = [
  'txt', 'md', 'json', 'py', 'js', 'ts', 'jsx', 'tsx', 'html', 'css',
  'scss', 'rs', 'sh', 'bat', 'ps1', 'xml', 'yaml', 'yml', 'toml',
  'ini', 'cfg', 'log', 'sql', 'c', 'cpp', 'h', 'java', 'kt'
];

function isImageFile(ext: string): boolean {
  return IMAGE_EXTENSIONS.includes((ext || '').toLowerCase());
}

function isTextFile(ext: string): boolean {
  return TEXT_EXTENSIONS.includes((ext || '').toLowerCase());
}

function isViewableFile(ext: string): boolean {
  const clean = (ext || '').toLowerCase();
  return isImageFile(clean) || isTextFile(clean) || clean === 'pdf';
}

function getMimeType(ext: string): string {
  const clean = (ext || '').toLowerCase();
  switch (clean) {
    case 'pdf': return 'application/pdf';
    case 'png': return 'image/png';
    case 'jpg':
    case 'jpeg': return 'image/jpeg';
    case 'gif': return 'image/gif';
    case 'webp': return 'image/webp';
    case 'svg': return 'image/svg+xml';
    case 'bmp': return 'image/bmp';
    case 'txt':
    case 'log': return 'text/plain';
    case 'json': return 'application/json';
    case 'html': return 'text/html';
    case 'css': return 'text/css';
    case 'js': return 'application/javascript';
    case 'ts': return 'application/typescript';
    case 'mp4': return 'video/mp4';
    case 'mkv': return 'video/x-matroska';
    case 'mov': return 'video/quicktime';
    case 'mp3': return 'audio/mpeg';
    case 'wav': return 'audio/wav';
    case 'doc': return 'application/msword';
    case 'docx': return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    case 'xls': return 'application/vnd.ms-excel';
    case 'xlsx': return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    case 'ppt': return 'application/vnd.ms-powerpoint';
    case 'pptx': return 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
    case 'zip': return 'application/zip';
    default: return '*/*';
  }
}

const FALLBACK_FOLDERS: QuickAccessFolder[] = [
  { id: 'desktop', name: 'Desktop', path: '', icon: 'desktop-outline', count: 'Synced' },
  { id: 'downloads', name: 'Downloads', path: '', icon: 'download-outline', count: 'Synced' },
  { id: 'documents', name: 'Documents', path: '', icon: 'document-text-outline', count: 'Synced' },
  { id: 'pictures', name: 'Pictures', path: '', icon: 'image-outline', count: 'Synced' },
];

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDate(ts: number): string {
  if (!ts || ts === 0) return 'Recent';
  const date = new Date(ts * 1000);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return `Today, ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  }
  if (diffDays === 1) {
    return 'Yesterday';
  }
  if (diffDays < 7) {
    return `${diffDays} days ago`;
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function getFileIcon(ext: string, is_dir?: boolean): { name: keyof typeof Ionicons.glyphMap; color: string } {
  if (is_dir) {
    return { name: 'folder', color: '#FFB020' };
  }
  const cleanExt = (ext || '').toLowerCase();
  switch (cleanExt) {
    case 'pdf':
      return { name: 'document-text', color: '#EF4444' };
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'svg':
    case 'webp':
    case 'bmp':
    case 'ico':
      return { name: 'image', color: '#3B82F6' };
    case 'mp4':
    case 'mkv':
    case 'mov':
    case 'avi':
    case 'webm':
      return { name: 'film', color: '#8B5CF6' };
    case 'mp3':
    case 'wav':
    case 'flac':
    case 'ogg':
    case 'm4a':
      return { name: 'musical-notes', color: '#10B981' };
    case 'zip':
    case 'rar':
    case '7z':
    case 'tar':
    case 'gz':
      return { name: 'archive', color: '#F59E0B' };
    case 'ts':
    case 'tsx':
    case 'js':
    case 'jsx':
    case 'py':
    case 'rs':
    case 'c':
    case 'cpp':
    case 'cs':
    case 'java':
    case 'go':
    case 'html':
    case 'css':
    case 'json':
      return { name: 'code-slash', color: '#06B6D4' };
    case 'xls':
    case 'xlsx':
    case 'csv':
      return { name: 'stats-chart', color: '#10B981' };
    case 'doc':
    case 'docx':
    case 'txt':
    case 'md':
      return { name: 'document-text', color: '#6366F1' };
    default:
      return { name: 'document', color: colors.textSecondary };
  }
}

export function FilesScreen({
  isConnected,
  quickAccessFolders = [],
  currentDirectory = null,
  recentFiles = [],
  searchResults = [],
  isLoading = false,
  fsError = null,
  fsFileData = null,
  onFetchQuickAccess,
  onListDirectory,
  onFetchRecentFiles,
  onSearch,
  onOpenFileOnPC,
  onOpenFileOnMobile,
  onClearFsFileData,
  onResetDirectory,
  onPreviewImage,
  onAskBlinky,
}: FilesScreenProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [navHistory, setNavHistory] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<FsEntry | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [mobileActionMode, setMobileActionMode] = useState<'open' | 'send' | 'save_device'>('open');
  const [textPreview, setTextPreview] = useState<{ name: string; content: string } | null>(null);
  const searchTimeoutRef = useRef<any>(null);

  // Pan gesture for sliding down bottom sheet toastbar
  const panY = useRef(new Animated.Value(0)).current;

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_, gestureState) => gestureState.dy > 5,
      onPanResponderMove: (_, gestureState) => {
        if (gestureState.dy > 0) {
          panY.setValue(gestureState.dy);
        }
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dy > 80 || gestureState.vy > 0.4) {
          Animated.timing(panY, {
            toValue: 600,
            duration: 200,
            useNativeDriver: true,
          }).start(() => {
            setSelectedFile(null);
          });
        } else {
          Animated.spring(panY, {
            toValue: 0,
            bounciness: 4,
            useNativeDriver: true,
          }).start();
        }
      },
    })
  ).current;

  const handleDismissFileModal = () => {
    Animated.timing(panY, {
      toValue: 600,
      duration: 200,
      useNativeDriver: true,
    }).start(() => {
      setSelectedFile(null);
    });
  };

  useEffect(() => {
    if (selectedFile) {
      panY.setValue(0);
    }
  }, [selectedFile]);

  // Sync initial directories on load
  useEffect(() => {
    if (isConnected) {
      onFetchQuickAccess?.();
      onFetchRecentFiles?.();
    }
  }, [isConnected]);

  // Handle incoming mobile file data and execute requested action
  useEffect(() => {
    if (fsFileData && isDownloading) {
      setIsDownloading(false);
      (async () => {
        try {
          const localUri = `${FileSystem.cacheDirectory}${fsFileData.name}`;
          await FileSystem.writeAsStringAsync(localUri, fsFileData.base64, {
            encoding: FileSystem.EncodingType.Base64,
          });

          const ext = (fsFileData.name.includes('.') ? fsFileData.name.split('.').pop() || '' : '').toLowerCase();
          const targetMode = mobileActionMode;
          setSelectedFile(null);
          onClearFsFileData?.();

          // 1. Send / Share file mode (available for all files)
          if (targetMode === 'send') {
            if (await Sharing.isAvailableAsync()) {
              await Sharing.shareAsync(localUri, {
                dialogTitle: `Send ${fsFileData.name}`,
              });
              setActionFeedback(`Shared: ${fsFileData.name}`);
            }
            return;
          }

          // 2. Save to Device / Downloads
          if (targetMode === 'save_device') {
            try {
              if (Platform.OS === 'android' && FileSystem.StorageAccessFramework) {
                const permissions = await FileSystem.StorageAccessFramework.requestDirectoryPermissionsAsync();
                if (permissions.granted) {
                  const newFileUri = await FileSystem.StorageAccessFramework.createFileAsync(
                    permissions.directoryUri,
                    fsFileData.name,
                    getMimeType(ext)
                  );
                  await FileSystem.writeAsStringAsync(newFileUri, fsFileData.base64, {
                    encoding: FileSystem.EncodingType.Base64,
                  });
                  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
                  setActionFeedback(`Saved: ${fsFileData.name}`);
                  return;
                }
              }
              // Fallback for iOS or if directory picker is dismissed
              if (await Sharing.isAvailableAsync()) {
                await Sharing.shareAsync(localUri, {
                  dialogTitle: `Save ${fsFileData.name}`,
                });
                setActionFeedback(`Saved: ${fsFileData.name}`);
              }
            } catch (saveErr: any) {
              Alert.alert('Save Failed', saveErr?.message || 'Could not save file to device.');
            }
            return;
          }

          // 3. Open Mode:
          // A. Images -> default image viewer via ACTION_VIEW
          if (isImageFile(ext)) {
            if (Platform.OS === 'android') {
              try {
                const contentUri = await FileSystem.getContentUriAsync(localUri);
                await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
                  data: contentUri,
                  flags: 1, // Intent.FLAG_GRANT_READ_URI_PERMISSION
                  type: getMimeType(ext),
                });
                setActionFeedback(`Opened in image viewer: ${fsFileData.name}`);
                return;
              } catch (launcherErr) {
                console.warn('[FilesScreen] IntentLauncher image viewer fallback:', launcherErr);
              }
            }
            if (onPreviewImage) {
              onPreviewImage(localUri);
              setActionFeedback(`Viewing image: ${fsFileData.name}`);
              return;
            }
          }

          // B. PDFs -> default PDF viewer via ACTION_VIEW
          if (ext === 'pdf') {
            if (Platform.OS === 'android') {
              try {
                const contentUri = await FileSystem.getContentUriAsync(localUri);
                await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
                  data: contentUri,
                  flags: 1,
                  type: 'application/pdf',
                });
                setActionFeedback(`Opened PDF: ${fsFileData.name}`);
                return;
              } catch (launcherErr) {
                console.warn('[FilesScreen] IntentLauncher ACTION_VIEW fallback:', launcherErr);
              }
            }
          }

          // C. Text / Code -> in-app reader modal
          if (isTextFile(ext)) {
            setActionFeedback(`Opening reader: ${fsFileData.name}`);
            const textContent = await FileSystem.readAsStringAsync(localUri, {
              encoding: FileSystem.EncodingType.UTF8,
            });
            setTextPreview({ name: fsFileData.name, content: textContent });
            return;
          }

          // D. Other files (exe, zip, etc.) -> open with external app via ACTION_VIEW or Sharing
          if (Platform.OS === 'android') {
            try {
              const contentUri = await FileSystem.getContentUriAsync(localUri);
              await IntentLauncher.startActivityAsync('android.intent.action.VIEW', {
                data: contentUri,
                flags: 1,
                type: getMimeType(ext),
              });
              setActionFeedback(`Opened: ${fsFileData.name}`);
              return;
            } catch (launcherErr) {
              console.warn('[FilesScreen] IntentLauncher open fallback:', launcherErr);
            }
          }

          if (await Sharing.isAvailableAsync()) {
            await Sharing.shareAsync(localUri, {
              dialogTitle: `Open ${fsFileData.name}`,
            });
            setActionFeedback(`Opened: ${fsFileData.name}`);
          }
        } catch (err: any) {
          setActionFeedback(`Error: ${err?.message || err}`);
        } finally {
          setTimeout(() => setActionFeedback(null), 2500);
        }
      })();
    }
  }, [fsFileData, isDownloading, mobileActionMode, onPreviewImage, onClearFsFileData]);

  // Handle live search debounce
  const handleSearchChange = (text: string) => {
    setSearchQuery(text);
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    if (!text.trim()) {
      onSearch?.('', currentDirectory?.currentPath);
      return;
    }
    searchTimeoutRef.current = setTimeout(() => {
      onSearch?.(text.trim(), currentDirectory?.currentPath);
    }, 350);
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    onSearch?.('', currentDirectory?.currentPath);
  };

  const handleOpenFolder = (path: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (currentDirectory?.currentPath) {
      setNavHistory((prev: string[]) => [...prev, currentDirectory.currentPath]);
    }
    onListDirectory?.(path);
  };

  const handleGoBack = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (navHistory.length > 0) {
      const prevPath = navHistory[navHistory.length - 1];
      setNavHistory((prev: string[]) => prev.slice(0, prev.length - 1));
      onListDirectory?.(prevPath);
    } else {
      // Exit directory back to default quick access / recent screen
      handleExitDirectory();
    }
  };

  const handleExitDirectory = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setNavHistory([]);
    setSearchQuery('');
    onResetDirectory?.();
  };

  const handlePressFile = (file: FsEntry) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setSelectedFile(file);
  };

  const handleOpenOnPC = (file: FsEntry) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    onOpenFileOnPC?.(file.path);
    setActionFeedback(`Opened on PC: ${file.name}`);
    setTimeout(() => {
      setActionFeedback(null);
      setSelectedFile(null);
    }, 1800);
  };

  const handleAction = (file: FsEntry, mode: 'open' | 'send' | 'save_device') => {
    if (!isConnected) {
      Alert.alert('Offline', 'Please connect to your PC to access this file.');
      return;
    }
    setMobileActionMode(mode);
    setIsDownloading(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    onOpenFileOnMobile?.(file.path);
  };

  const handleAskAboutFile = (file: FsEntry) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setSelectedFile(null);
    onAskBlinky?.(file);
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (currentDirectory?.currentPath) {
      onListDirectory?.(currentDirectory.currentPath);
    } else {
      onFetchQuickAccess?.();
      onFetchRecentFiles?.();
    }
    setTimeout(() => {
      setIsRefreshing(false);
    }, 700);
  };

  const displayFolders = quickAccessFolders.length > 0 ? quickAccessFolders : FALLBACK_FOLDERS;
  const isInsideDirectory = Boolean(currentDirectory && currentDirectory.currentPath);
  const isSearching = searchQuery.trim().length > 0;

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          {isInsideDirectory ? (
            <TouchableOpacity style={styles.backBtn} onPress={handleGoBack} activeOpacity={0.7}>
              <Ionicons name="arrow-back" size={20} color={colors.textPrimary} />
            </TouchableOpacity>
          ) : (
            <View style={styles.headerIconBox}>
              <Ionicons name="folder-open" size={20} color={colors.accent} />
            </View>
          )}
          <View>
            <Text style={styles.headerTitle}>
              {isInsideDirectory
                ? currentDirectory?.currentPath.split(/[\\/]/).filter(Boolean).pop() || 'Folder'
                : 'PC Files'}
            </Text>
            {isInsideDirectory && (
              <Text style={styles.headerSubPath} numberOfLines={1}>
                {currentDirectory?.currentPath}
              </Text>
            )}
          </View>
        </View>

        <View style={styles.headerRight}>
          {isInsideDirectory && (
            <TouchableOpacity
              style={styles.headerActionBtn}
              onPress={handleExitDirectory}
              activeOpacity={0.7}
            >
              <Ionicons name="home-outline" size={18} color={colors.textSecondary} />
            </TouchableOpacity>
          )}
          <TouchableOpacity
            style={styles.headerActionBtn}
            onPress={handleRefresh}
            activeOpacity={0.7}
            disabled={!isConnected}
          >
            {isLoading || isRefreshing ? (
              <ActivityIndicator size="small" color={colors.accent} />
            ) : (
              <Ionicons name="sync-outline" size={18} color={colors.textSecondary} />
            )}
          </TouchableOpacity>
        </View>
      </View>

      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <Ionicons name="search" size={18} color={colors.textMuted} style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          placeholder={
            isInsideDirectory
              ? `Search in ${currentDirectory?.currentPath.split(/[\\/]/).filter(Boolean).pop() || 'folder'}...`
              : 'Search all files on PC...'
          }
          placeholderTextColor={colors.textMuted}
          value={searchQuery}
          onChangeText={handleSearchChange}
          editable={isConnected}
          returnKeyType="search"
        />
        {searchQuery.length > 0 && (
          <TouchableOpacity onPress={handleClearSearch} style={styles.clearSearchBtn}>
            <Ionicons name="close-circle" size={18} color={colors.textMuted} />
          </TouchableOpacity>
        )}
      </View>

      {/* Feedback Toast */}
      {actionFeedback && (
        <View style={styles.toastBox}>
          <Ionicons name="checkmark-circle" size={16} color="#10B981" />
          <Text style={styles.toastText} numberOfLines={1}>
            {actionFeedback}
          </Text>
        </View>
      )}

      {/* Error Banner */}
      {fsError && (
        <View style={styles.errorBanner}>
          <Ionicons name="alert-circle" size={16} color="#EF4444" style={{ marginRight: 6 }} />
          <Text style={styles.errorBannerText} numberOfLines={2}>
            {fsError}
          </Text>
        </View>
      )}

      {!isConnected ? (
        <View style={styles.emptyState}>
          <Ionicons
            name="cloud-offline-outline"
            size={48}
            color={colors.textMuted}
            style={{ marginBottom: spacing.md }}
          />
          <Text style={styles.emptyTitle}>PC Disconnected</Text>
          <Text style={styles.emptySubtitle}>
            Connect your mobile companion to your PC to browse, search, and launch desktop files remotely.
          </Text>
        </View>
      ) : (
        <ScrollView
          style={styles.scrollArea}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{ paddingBottom: spacing.xxxl * 1.5 }}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={handleRefresh}
              tintColor={colors.accent}
              colors={[colors.accent]}
            />
          }
        >
          {/* SEARCH RESULTS VIEW */}
          {isSearching ? (
            <View style={styles.sectionContainer}>
              <View style={styles.sectionHeaderRow}>
                <Text style={styles.sectionTitle}>
                  SEARCH RESULTS ({searchResults.length})
                </Text>
                {isLoading && <ActivityIndicator size="small" color={colors.accent} />}
              </View>

              {searchResults.length === 0 && !isLoading ? (
                <View style={styles.emptyFolderBox}>
                  <Ionicons name="search-outline" size={36} color={colors.textMuted} />
                  <Text style={styles.emptyFolderTitle}>No files found</Text>
                  <Text style={styles.emptyFolderSubtitle}>Try checking your query or path.</Text>
                </View>
              ) : (
                <View style={styles.list}>
                  {searchResults.map((item, idx) => {
                    const iconInfo = getFileIcon(item.ext, item.is_dir);
                    return (
                      <TouchableOpacity
                        key={`${item.path}-${idx}`}
                        style={styles.listItem}
                        onPress={() => (item.is_dir ? handleOpenFolder(item.path) : handlePressFile(item))}
                        activeOpacity={0.7}
                      >
                        <View style={[styles.fileIconBox, { backgroundColor: `${iconInfo.color}15` }]}>
                          <Ionicons name={iconInfo.name} size={22} color={iconInfo.color} />
                        </View>
                        <View style={styles.fileDetails}>
                          <Text style={styles.fileName} numberOfLines={1}>
                            {item.name}
                          </Text>
                          <Text style={styles.fileMeta} numberOfLines={1}>
                            {item.is_dir ? 'Folder' : `${formatBytes(item.size_bytes)} • ${formatDate(item.modified_ts)}`}
                          </Text>
                          <Text style={styles.filePathTiny} numberOfLines={1}>
                            {item.path}
                          </Text>
                        </View>
                        <Ionicons
                          name={item.is_dir ? 'chevron-forward' : 'ellipsis-vertical'}
                          size={16}
                          color={colors.borderLight}
                        />
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}
            </View>
          ) : isInsideDirectory ? (
            /* DIRECTORY BROWSER VIEW */
            <View style={styles.sectionContainer}>
              <View style={styles.dirActionBar}>
                <TouchableOpacity
                  style={styles.upFolderBtn}
                  onPress={handleGoBack}
                  activeOpacity={0.7}
                >
                  <Ionicons name="arrow-up" size={16} color={colors.textSecondary} />
                  <Text style={styles.upFolderText}>Up one folder</Text>
                </TouchableOpacity>
                <Text style={styles.itemCountText}>
                  {currentDirectory?.entries.length || 0} items
                </Text>
              </View>

              {(!currentDirectory?.entries || currentDirectory.entries.length === 0) && !isLoading ? (
                <View style={styles.emptyFolderBox}>
                  <Ionicons name="folder-open-outline" size={36} color={colors.textMuted} />
                  <Text style={styles.emptyFolderTitle}>This folder is empty</Text>
                </View>
              ) : (
                <View style={styles.list}>
                  {currentDirectory?.entries.map((item, idx) => {
                    const iconInfo = getFileIcon(item.ext, item.is_dir);
                    return (
                      <TouchableOpacity
                        key={`${item.path}-${idx}`}
                        style={styles.listItem}
                        onPress={() => (item.is_dir ? handleOpenFolder(item.path) : handlePressFile(item))}
                        activeOpacity={0.7}
                      >
                        <View style={[styles.fileIconBox, { backgroundColor: `${iconInfo.color}15` }]}>
                          <Ionicons name={iconInfo.name} size={22} color={iconInfo.color} />
                        </View>
                        <View style={styles.fileDetails}>
                          <Text style={styles.fileName} numberOfLines={1}>
                            {item.name}
                          </Text>
                          <Text style={styles.fileMeta}>
                            {item.is_dir
                              ? 'Folder'
                              : `${formatBytes(item.size_bytes)} • ${formatDate(item.modified_ts)}`}
                          </Text>
                        </View>
                        <Ionicons
                          name={item.is_dir ? 'chevron-forward' : 'ellipsis-vertical'}
                          size={16}
                          color={colors.borderLight}
                        />
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}
            </View>
          ) : (
            /* HOME QUICK ACCESS + RECENT FILES VIEW */
            <>
              <View style={styles.sectionHeaderRow}>
                <Text style={styles.sectionTitle}>QUICK ACCESS</Text>
                <TouchableOpacity onPress={handleRefresh} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
                  <Text style={styles.sectionActionText}>Sync</Text>
                </TouchableOpacity>
              </View>

              <View style={styles.grid}>
                {displayFolders.map((folder) => (
                  <TouchableOpacity
                    key={folder.id}
                    style={styles.folderCard}
                    onPress={() => (folder.path ? handleOpenFolder(folder.path) : null)}
                    activeOpacity={0.7}
                  >
                    <View style={styles.folderIconBox}>
                      <Ionicons name={folder.icon as any} size={24} color={colors.accent} />
                    </View>
                    <Text style={styles.folderName} numberOfLines={1}>
                      {folder.name}
                    </Text>
                    <Text style={styles.folderCount}>{folder.count}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={[styles.sectionHeaderRow, { marginTop: spacing.xl }]}>
                <Text style={styles.sectionTitle}>RECENT FILES</Text>
                <Text style={styles.sectionSubText}>{recentFiles.length} files</Text>
              </View>

              {recentFiles.length === 0 ? (
                <View style={styles.emptyRecentBox}>
                  <Text style={styles.emptyFolderSubtitle}>Pull down to sync recent files from PC</Text>
                </View>
              ) : (
                <View style={styles.list}>
                  {recentFiles.map((file, idx) => {
                    const iconInfo = getFileIcon(file.ext, false);
                    return (
                      <TouchableOpacity
                        key={`${file.path}-${idx}`}
                        style={styles.listItem}
                        onPress={() => handlePressFile(file)}
                        activeOpacity={0.7}
                      >
                        <View style={[styles.fileIconBox, { backgroundColor: `${iconInfo.color}15` }]}>
                          <Ionicons name={iconInfo.name} size={22} color={iconInfo.color} />
                        </View>
                        <View style={styles.fileDetails}>
                          <Text style={styles.fileName} numberOfLines={1}>
                            {file.name}
                          </Text>
                          <Text style={styles.fileMeta}>
                            {formatBytes(file.size_bytes)} • {formatDate(file.modified_ts)}
                          </Text>
                        </View>
                        <Ionicons name="ellipsis-vertical" size={16} color={colors.borderLight} />
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}
            </>
          )}
        </ScrollView>
      )}

      {/* File Action Toastbar with Slide-down to Close */}
      <Modal
        visible={Boolean(selectedFile)}
        transparent
        animationType="fade"
        onRequestClose={handleDismissFileModal}
      >
        <TouchableOpacity
          style={styles.modalBackdrop}
          activeOpacity={1}
          onPress={handleDismissFileModal}
        >
          <Animated.View
            style={[
              styles.modalContent,
              {
                transform: [{ translateY: panY }],
              },
            ]}
            onStartShouldSetResponder={() => true}
          >
            {/* Slide Down Drag Handle */}
            <View {...panResponder.panHandlers} style={styles.sheetHandleContainer}>
              <View style={styles.sheetHandleBar} />
            </View>

            {selectedFile && (
              <>
                <View style={styles.modalHeader}>
                  <View
                    style={[
                      styles.modalIconBox,
                      { backgroundColor: `${getFileIcon(selectedFile.ext, selectedFile.is_dir).color}20` },
                    ]}
                  >
                    <Ionicons
                      name={getFileIcon(selectedFile.ext, selectedFile.is_dir).name}
                      size={28}
                      color={getFileIcon(selectedFile.ext, selectedFile.is_dir).color}
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.modalFileName} numberOfLines={2}>
                      {selectedFile.name}
                    </Text>
                    <Text style={styles.modalFileMeta}>
                      {formatBytes(selectedFile.size_bytes)} • {formatDate(selectedFile.modified_ts)}
                    </Text>
                  </View>
                </View>

                <View style={styles.pathBadge}>
                  <Ionicons name="desktop-outline" size={14} color={colors.textMuted} style={{ marginRight: 6 }} />
                  <Text style={styles.pathBadgeText} numberOfLines={2}>
                    {selectedFile.path}
                  </Text>
                </View>

                <View style={styles.modalActions}>
                  {/* 1. Open Button (Available for all files) */}
                  {!selectedFile.is_dir && (
                    <TouchableOpacity
                      style={styles.mobileActionBtn}
                      onPress={() => handleAction(selectedFile, 'open')}
                      activeOpacity={0.8}
                      disabled={isDownloading}
                    >
                      {isDownloading && mobileActionMode === 'open' ? (
                        <ActivityIndicator size="small" color="#FFFFFF" style={{ marginRight: 8 }} />
                      ) : (
                        <Ionicons
                          name={
                            isImageFile(selectedFile.ext)
                              ? 'image-outline'
                              : selectedFile.ext.toLowerCase() === 'pdf'
                              ? 'document-text-outline'
                              : isTextFile(selectedFile.ext)
                              ? 'reader-outline'
                              : 'open-outline'
                          }
                          size={18}
                          color="#FFFFFF"
                          style={{ marginRight: 8 }}
                        />
                      )}
                      <Text style={styles.mobileActionBtnText}>
                        {isDownloading && mobileActionMode === 'open'
                          ? 'Opening...'
                          : isImageFile(selectedFile.ext)
                          ? 'Open in Image Viewer'
                          : selectedFile.ext.toLowerCase() === 'pdf'
                          ? 'Open PDF Directly'
                          : isTextFile(selectedFile.ext)
                          ? 'Read File Directly'
                          : 'Open File with...'}
                      </Text>
                    </TouchableOpacity>
                  )}

                  {/* 2. Send / Share File Button (Available for all files) */}
                  {!selectedFile.is_dir && (
                    <TouchableOpacity
                      style={styles.sendActionBtn}
                      onPress={() => handleAction(selectedFile, 'send')}
                      activeOpacity={0.8}
                      disabled={isDownloading}
                    >
                      {isDownloading && mobileActionMode === 'send' ? (
                        <ActivityIndicator size="small" color="#FFFFFF" style={{ marginRight: 8 }} />
                      ) : (
                        <Ionicons name="share-social-outline" size={18} color="#FFFFFF" style={{ marginRight: 8 }} />
                      )}
                      <Text style={styles.sendActionBtnText}>
                        {isDownloading && mobileActionMode === 'send' ? 'Preparing to send...' : 'Send / Share File'}
                      </Text>
                    </TouchableOpacity>
                  )}

                  {/* 3. Save to Device option for images */}
                  {!selectedFile.is_dir && isImageFile(selectedFile.ext) && (
                    <TouchableOpacity
                      style={styles.saveGalleryActionBtn}
                      onPress={() => handleAction(selectedFile, 'save_device')}
                      activeOpacity={0.8}
                      disabled={isDownloading}
                    >
                      {isDownloading && mobileActionMode === 'save_device' ? (
                        <ActivityIndicator size="small" color="#10B981" style={{ marginRight: 8 }} />
                      ) : (
                        <Ionicons name="download-outline" size={18} color="#10B981" style={{ marginRight: 8 }} />
                      )}
                      <Text style={styles.saveGalleryActionBtnText}>
                        {isDownloading && mobileActionMode === 'save_device' ? 'Saving to Device...' : 'Save to Device'}
                      </Text>
                    </TouchableOpacity>
                  )}

                  {/* Open on PC button */}
                  <TouchableOpacity
                    style={styles.primaryActionBtn}
                    onPress={() => handleOpenOnPC(selectedFile)}
                    activeOpacity={0.8}
                  >
                    <Ionicons name="open-outline" size={18} color="#FFFFFF" style={{ marginRight: 8 }} />
                    <Text style={styles.primaryActionBtnText}>Open on PC</Text>
                  </TouchableOpacity>

                  {/* Ask Blinky button */}
                  <TouchableOpacity
                    style={styles.secondaryActionBtn}
                    onPress={() => handleAskAboutFile(selectedFile)}
                    activeOpacity={0.8}
                  >
                    <Ionicons name="sparkles" size={18} color={colors.accent} style={{ marginRight: 8 }} />
                    <Text style={styles.secondaryActionBtnText}>Ask Blinky about this file</Text>
                  </TouchableOpacity>

                  {/* Cancel button */}
                  <TouchableOpacity
                    style={styles.cancelActionBtn}
                    onPress={() => setSelectedFile(null)}
                    activeOpacity={0.8}
                  >
                    <Text style={styles.cancelActionBtnText}>Cancel</Text>
                  </TouchableOpacity>
                </View>
              </>
            )}
          </Animated.View>
        </TouchableOpacity>
      </Modal>

      {/* In-app Text / Code Reader Modal */}
      <Modal
        visible={!!textPreview}
        animationType="slide"
        transparent={false}
        onRequestClose={() => setTextPreview(null)}
      >
        <View style={styles.textPreviewContainer}>
          <View style={styles.textPreviewHeader}>
            <View style={{ flex: 1, marginRight: spacing.sm }}>
              <Text style={styles.textPreviewTitle} numberOfLines={1}>{textPreview?.name}</Text>
              <Text style={styles.textPreviewSub}>In-app Reader</Text>
            </View>
            <TouchableOpacity 
              style={styles.textPreviewCloseBtn}
              onPress={() => setTextPreview(null)}
            >
              <Ionicons name="close" size={24} color={colors.textPrimary} />
            </TouchableOpacity>
          </View>
          <ScrollView style={styles.textPreviewScroll} contentContainerStyle={{ padding: spacing.md, paddingBottom: 60 }}>
            <Text style={styles.textPreviewBody} selectable={true}>
              {textPreview?.content}
            </Text>
          </ScrollView>
        </View>
      </Modal>
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
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: spacing.sm,
  },
  headerIconBox: {
    width: 38,
    height: 38,
    borderRadius: radius.md,
    backgroundColor: 'rgba(255, 90, 54, 0.12)',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
  },
  backBtn: {
    width: 38,
    height: 38,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
    borderWidth: 1,
    borderColor: colors.borderLight,
  },
  headerTitle: {
    ...typography.heading2,
    color: colors.textPrimary,
  },
  headerSubPath: {
    ...typography.bodySmall,
    color: colors.textMuted,
    maxWidth: 220,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  headerActionBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
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
    paddingVertical: 10,
  },
  clearSearchBtn: {
    padding: 4,
  },
  toastBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.3)',
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.md,
    gap: 8,
  },
  toastText: {
    ...typography.bodySmall,
    color: '#10B981',
    fontWeight: '600',
    flex: 1,
  },
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.3)',
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.md,
  },
  errorBannerText: {
    ...typography.bodySmall,
    color: '#EF4444',
    flex: 1,
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
  sectionContainer: {
    paddingHorizontal: spacing.md,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },
  sectionTitle: {
    ...typography.label,
    color: colors.textMuted,
  },
  sectionActionText: {
    ...typography.label,
    color: colors.accent,
    fontWeight: '700',
  },
  sectionSubText: {
    ...typography.bodySmall,
    color: colors.textMuted,
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
  dirActionBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
    paddingBottom: 4,
  },
  upFolderBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: 4,
  },
  upFolderText: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    fontWeight: '600',
  },
  itemCountText: {
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
    marginBottom: 3,
  },
  fileMeta: {
    ...typography.bodySmall,
    color: colors.textMuted,
  },
  filePathTiny: {
    fontSize: 10,
    color: colors.textMuted,
    marginTop: 2,
  },
  emptyFolderBox: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxl,
    gap: 8,
  },
  emptyFolderTitle: {
    ...typography.bodyMedium,
    color: colors.textSecondary,
    fontWeight: '600',
  },
  emptyFolderSubtitle: {
    ...typography.bodySmall,
    color: colors.textMuted,
    textAlign: 'center',
  },
  emptyRecentBox: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.lg,
    alignItems: 'center',
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#121216', // Solid 100% opaque dark background
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: spacing.lg,
    paddingBottom: Platform.OS === 'ios' ? spacing.xxl : spacing.xl,
    borderTopWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.12)',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: -8 },
    shadowOpacity: 0.6,
    shadowRadius: 20,
    elevation: 24,
  },
  sheetHandleContainer: {
    paddingVertical: 12,
    alignItems: 'center',
    width: '100%',
  },
  sheetHandleBar: {
    width: 44,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: 'rgba(255, 255, 255, 0.35)',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  modalIconBox: {
    width: 50,
    height: 50,
    borderRadius: radius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  modalFileName: {
    ...typography.heading3,
    color: colors.textPrimary,
    marginBottom: 4,
  },
  modalFileMeta: {
    ...typography.bodySmall,
    color: colors.textMuted,
  },
  pathBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderRadius: radius.md,
    padding: spacing.sm,
    marginBottom: spacing.lg,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  pathBadgeText: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    fontSize: 11,
    flex: 1,
  },
  modalActions: {
    gap: spacing.sm,
  },
  mobileActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#059669',
    borderRadius: radius.md,
    paddingVertical: 14,
  },
  mobileActionBtnText: {
    ...typography.bodyMedium,
    color: '#FFFFFF',
    fontWeight: '700',
  },
  saveGalleryActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(16, 185, 129, 0.12)',
    borderRadius: radius.md,
    paddingVertical: 14,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.35)',
  },
  saveGalleryActionBtnText: {
    ...typography.bodyMedium,
    color: '#10B981',
    fontWeight: '700',
  },
  sendActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#3B82F6',
    borderRadius: radius.md,
    paddingVertical: 14,
  },
  sendActionBtnText: {
    ...typography.bodyMedium,
    color: '#FFFFFF',
    fontWeight: '700',
  },
  primaryActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accent,
    borderRadius: radius.md,
    paddingVertical: 14,
  },
  primaryActionBtnText: {
    ...typography.bodyMedium,
    color: '#FFFFFF',
    fontWeight: '700',
  },
  secondaryActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255, 90, 54, 0.1)',
    borderRadius: radius.md,
    paddingVertical: 14,
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.3)',
  },
  secondaryActionBtnText: {
    ...typography.bodyMedium,
    color: colors.accent,
    fontWeight: '600',
  },
  cancelActionBtn: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
  },
  cancelActionBtnText: {
    ...typography.bodyMedium,
    color: colors.textMuted,
  },
  textPreviewContainer: {
    flex: 1,
    backgroundColor: colors.background,
    paddingTop: Platform.OS === 'android' ? 40 : 50,
  },
  textPreviewHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderLight,
    backgroundColor: colors.surface,
  },
  textPreviewTitle: {
    ...typography.heading3,
    color: colors.textPrimary,
  },
  textPreviewSub: {
    ...typography.bodySmall,
    color: colors.textMuted,
  },
  textPreviewCloseBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  textPreviewScroll: {
    flex: 1,
    backgroundColor: colors.background,
  },
  textPreviewBody: {
    ...typography.bodyMedium,
    color: colors.textPrimary,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    lineHeight: 22,
  },
});
