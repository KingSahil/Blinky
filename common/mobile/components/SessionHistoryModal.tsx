import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  FlatList,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, typography, radius, spacing } from '../theme/theme';
import { BlinkyChatSession } from '../lib/session_manager';

interface SessionHistoryModalProps {
  visible: boolean;
  onClose: () => void;
  sessions: BlinkyChatSession[];
  activeSessionId: string;
  onSelectSession: (session: BlinkyChatSession) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => void;
  onClearAllSessions: () => void;
}

export function SessionHistoryModal({
  visible,
  onClose,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  onClearAllSessions,
}: SessionHistoryModalProps) {
  if (!visible) return null;

  const formatTimestamp = (epochMs: number) => {
    const diffSec = Math.floor((Date.now() - epochMs) / 1000);
    if (diffSec < 60) return 'Just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    const d = new Date(epochMs);
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  const confirmDelete = (session: BlinkyChatSession) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    Alert.alert(
      'Delete Conversation',
      `Are you sure you want to delete "${session.title}"?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: () => onDeleteSession(session.id),
        },
      ]
    );
  };

  const confirmClearAll = () => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    Alert.alert(
      'Clear All Conversations',
      'This will delete all saved chat sessions and history from this device.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear All',
          style: 'destructive',
          onPress: onClearAllSessions,
        },
      ]
    );
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.sheetContainer}>
          {/* HEADER */}
          <View style={styles.header}>
            <View style={styles.headerTitleRow}>
              <Ionicons name="chatbubbles" size={20} color={colors.accent} />
              <Text style={styles.headerTitle}>Chat History</Text>
            </View>
            <View style={styles.headerActionRow}>
              <TouchableOpacity
                style={styles.newChatBtn}
                onPress={() => {
                  Haptics.selectionAsync();
                  onNewSession();
                  onClose();
                }}
              >
                <Ionicons name="add" size={16} color="#ffffff" />
                <Text style={styles.newChatText}>New Chat</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
                <Ionicons name="close" size={22} color={colors.textMuted} />
              </TouchableOpacity>
            </View>
          </View>

          {/* SESSIONS LIST */}
          {sessions.length === 0 ? (
            <View style={styles.emptyContainer}>
              <Ionicons name="time-outline" size={42} color={colors.textMuted} />
              <Text style={styles.emptyText}>No previous conversations</Text>
              <Text style={styles.emptySubText}>Tasks and questions you ask Blinky will be saved here.</Text>
            </View>
          ) : (
            <FlatList
              data={sessions}
              keyExtractor={(item) => item.id}
              contentContainerStyle={styles.listContent}
              renderItem={({ item }) => {
                const isActive = item.id === activeSessionId;
                return (
                  <TouchableOpacity
                    style={[styles.sessionItem, isActive && styles.sessionItemActive]}
                    activeOpacity={0.7}
                    onPress={() => {
                      Haptics.selectionAsync();
                      onSelectSession(item);
                      onClose();
                    }}
                  >
                    <View style={styles.sessionLeft}>
                      <View style={[styles.sessionIconWrapper, isActive && styles.sessionIconActive]}>
                        <Ionicons
                          name={item.mode === 'grounded' ? 'book-outline' : 'desktop-outline'}
                          size={16}
                          color={isActive ? colors.accent : colors.textMuted}
                        />
                      </View>
                      <View style={styles.sessionDetails}>
                        <Text style={[styles.sessionTitle, isActive && styles.sessionTitleActive]} numberOfLines={1}>
                          {item.title}
                        </Text>
                        <View style={styles.sessionMeta}>
                          <Text style={styles.sessionTime}>{formatTimestamp(item.updatedAt)}</Text>
                          <Text style={styles.sessionBullet}>•</Text>
                          <Text style={styles.sessionMsgCount}>
                            {item.messages.length} msg{item.messages.length !== 1 ? 's' : ''}
                          </Text>
                          {item.mode === 'grounded' && (
                            <View style={styles.groundedTag}>
                              <Text style={styles.groundedTagText}>Grounded</Text>
                            </View>
                          )}
                        </View>
                      </View>
                    </View>
                    <TouchableOpacity
                      style={styles.deleteBtn}
                      hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                      onPress={() => confirmDelete(item)}
                    >
                      <Ionicons name="trash-outline" size={17} color={colors.textMuted} />
                    </TouchableOpacity>
                  </TouchableOpacity>
                );
              }}
            />
          )}

          {/* FOOTER */}
          {sessions.length > 0 && (
            <View style={styles.footer}>
              <TouchableOpacity style={styles.clearAllBtn} onPress={confirmClearAll}>
                <Ionicons name="trash-bin-outline" size={14} color="#ef4444" />
                <Text style={styles.clearAllText}>Clear All History</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'flex-end',
  },
  sheetContainer: {
    backgroundColor: '#181b22',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '80%',
    paddingBottom: 24,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.06)',
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#ffffff',
  },
  headerActionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  newChatBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.accent,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
  },
  newChatText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '700',
  },
  closeBtn: {
    padding: 4,
  },
  listContent: {
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  sessionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 10,
    marginVertical: 3,
    backgroundColor: 'rgba(255, 255, 255, 0.03)',
  },
  sessionItemActive: {
    backgroundColor: 'rgba(255, 90, 54, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.3)',
  },
  sessionLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 10,
  },
  sessionIconWrapper: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  sessionIconActive: {
    backgroundColor: 'rgba(255, 90, 54, 0.2)',
  },
  sessionDetails: {
    flex: 1,
  },
  sessionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#e2e8f0',
  },
  sessionTitleActive: {
    color: '#ffffff',
    fontWeight: '700',
  },
  sessionMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 3,
  },
  sessionTime: {
    fontSize: 11,
    color: colors.textMuted,
  },
  sessionBullet: {
    marginHorizontal: 4,
    fontSize: 10,
    color: colors.textMuted,
  },
  sessionMsgCount: {
    fontSize: 11,
    color: colors.textMuted,
  },
  groundedTag: {
    marginLeft: 6,
    backgroundColor: 'rgba(139, 92, 246, 0.2)',
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: 4,
  },
  groundedTagText: {
    fontSize: 9,
    color: '#a78bfa',
    fontWeight: '600',
  },
  deleteBtn: {
    padding: 6,
  },
  emptyContainer: {
    paddingVertical: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: {
    marginTop: 10,
    fontSize: 14,
    fontWeight: '600',
    color: '#94a3b8',
  },
  emptySubText: {
    marginTop: 4,
    fontSize: 12,
    color: '#64748b',
    textAlign: 'center',
    paddingHorizontal: 24,
  },
  footer: {
    paddingTop: 10,
    paddingHorizontal: 16,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.06)',
    alignItems: 'center',
  },
  clearAllBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 6,
  },
  clearAllText: {
    fontSize: 12,
    color: '#ef4444',
    fontWeight: '600',
  },
});
