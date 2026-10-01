import React, { useRef, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Animated,
  PanResponder,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { colors, typography, radius, spacing } from '../theme/theme';
import { QrScanner, parsePairingQr } from './QrScanner';

export type LinkTab = 'qr' | 'manual';

export interface QrConnectInfo {
  ip: string;
  token?: string;
  pin?: string;
  mode?: string;
}

export interface SettingsModalProps {
  visible: boolean;
  onClose: () => void;
  isConnected: boolean;
  status: string;
  ipAddress: string;
  setIpAddress: (val: string) => void;
  remoteToken: string;
  setRemoteToken: (val: string) => void;
  certificatePin: string;
  setCertificatePin: (val: string) => void;
  workstationPin: string;
  setWorkstationPin: (val: string) => void;
  macAddress: string;
  setMacAddress: (val: string) => void;
  systemInfo: any;
  isDiscovering: boolean;
  handleConnect: () => void;
  handleAutoDiscover: () => void;
  handleQrConnect: (qr: QrConnectInfo) => void;
  disconnect: () => void;
  onUnlink?: () => void;
  discoveryProgress: string | null;
  errorMsg: string | null;
  RELEASE_TRANSPORT: boolean;
  WORKSTATION_PIN_STORAGE_KEY: string;
}

export function SettingsModal(props: SettingsModalProps) {
  const panY = useRef(new Animated.Value(0)).current;
  const [linkTab, setLinkTab] = useState<LinkTab>('qr');
  const [qrError, setQrError] = useState<string | null>(null);
  const [showRescanScanner, setShowRescanScanner] = useState<boolean>(false);

  const isPaired = Boolean(props.remoteToken?.trim() && props.certificatePin?.trim());

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
            props.onClose();
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

  const handleDismiss = () => {
    Animated.timing(panY, {
      toValue: 600,
      duration: 200,
      useNativeDriver: true,
    }).start(() => {
      props.onClose();
    });
  };

  useEffect(() => {
    if (props.visible) {
      panY.setValue(0);
      setQrError(null);
      setShowRescanScanner(false);
    }
  }, [props.visible]);

  if (!props.visible) return null;

  const handleQrScanned = (data: string) => {
    const trimmed = data.trim();
    // The Metro bundler QR (exp://...) loads the app via Expo Go — it is not
    // a PC-link code. Point this out explicitly: the two QRs get mixed up.
    if (/^exp:\/\//i.test(trimmed)) {
      setQrError('That is the Expo loader code (for opening this app in Expo Go), not the PC link code. First open the app with Expo Go, then scan the QR shown in the Blinky PC app header (QR icon) here.');
      return;
    }
    const parsed = parsePairingQr(data);
    if (!parsed) {
      setQrError('That is not a Blinky pairing code. Open the Blinky PC app, tap the QR icon in the header, and scan that code.');
      return;
    }
    setQrError(null);
    setShowRescanScanner(false);
    props.handleQrConnect({
      ip: parsed.ip,
      token: parsed.token,
      pin: parsed.pin ?? undefined,
      mode: parsed.mode,
    });
  };

  return (
    <Modal visible={props.visible} animationType="fade" transparent={true} onRequestClose={handleDismiss}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.modalOverlay}>
        <Animated.View
          style={[
            styles.modalContent,
            {
              transform: [{ translateY: panY }],
            },
          ]}
        >
          {/* Slide Down Drag Handle */}
          <View {...panResponder.panHandlers} style={styles.sheetHandleContainer}>
            <View style={styles.handleBar} />
          </View>
          
          <View style={styles.connectionHeaderRow}>
            <Text style={styles.connectionTitle}>
              {props.RELEASE_TRANSPORT ? 'PC Link & Settings' : 'Local Link Setup'}
            </Text>
            <TouchableOpacity onPress={handleDismiss} style={styles.closeBtn}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>
          
          <ScrollView style={styles.scrollContent} showsVerticalScrollIndicator={false}>
            {props.RELEASE_TRANSPORT ? (
              // ================= RELEASE MODE: QR-FIRST & WHATSAPP WEB STYLE =================
              <View>
                {props.isConnected ? (
                  <View>
                    <View style={styles.connectedCard}>
                      <View style={styles.connectedCardHeader}>
                        <View style={styles.connectedIconCircle}>
                          <Ionicons name="desktop-outline" size={20} color={colors.success} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.connectedCardTitle}>Linked to Host PC</Text>
                          <Text style={styles.connectedCardSubtitle}>
                            {props.ipAddress ? `Host: ${props.ipAddress}` : 'Connected via Secure TLS'}
                          </Text>
                        </View>
                        <View style={styles.secureBadge}>
                          <Ionicons name="shield-checkmark" size={12} color={colors.success} style={{ marginRight: 3 }} />
                          <Text style={styles.secureBadgeText}>TLS PINNED</Text>
                        </View>
                      </View>

                      <View style={styles.connectedActionsRow}>
                        <TouchableOpacity
                          style={[styles.smallBtn, { backgroundColor: colors.surface }]}
                          onPress={() => {
                            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                            props.disconnect();
                          }}
                          activeOpacity={0.8}
                        >
                          <Ionicons name="power-outline" size={14} color={colors.textSecondary} style={{ marginRight: 4 }} />
                          <Text style={styles.smallBtnText}>Disconnect</Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                          style={[styles.smallBtn, { backgroundColor: 'rgba(239, 68, 68, 0.15)', borderColor: 'rgba(239, 68, 68, 0.3)', borderWidth: 1 }]}
                          onPress={() => {
                            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
                            props.onUnlink?.();
                          }}
                          activeOpacity={0.8}
                        >
                          <Ionicons name="trash-outline" size={14} color={colors.danger} style={{ marginRight: 4 }} />
                          <Text style={[styles.smallBtnText, { color: colors.danger }]}>Unlink PC</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  </View>
                ) : props.status === 'connecting' ? (
                  <View style={styles.progressCard}>
                    <ActivityIndicator size="small" color={colors.accent} style={{ marginRight: 10 }} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.progressTitle}>Connecting to PC...</Text>
                      <Text style={styles.progressSubtitle}>{props.ipAddress || 'Authenticating secure session'}</Text>
                    </View>
                    <TouchableOpacity
                      style={styles.cancelLinkBtn}
                      onPress={() => {
                        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                        props.disconnect();
                      }}
                    >
                      <Text style={styles.cancelLinkBtnText}>Cancel</Text>
                    </TouchableOpacity>
                  </View>
                ) : isPaired && !showRescanScanner ? (
                  <View>
                    <View style={styles.reconnectingCard}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
                        <Ionicons name="sync-outline" size={18} color={colors.warning} style={{ marginRight: 8 }} />
                        <Text style={styles.reconnectingTitle}>Disconnected from PC</Text>
                      </View>
                      <Text style={styles.reconnectingDesc}>
                        Saved credentials for {props.ipAddress || 'your PC'} are active. Blinky will auto-reconnect once the desktop app is online.
                      </Text>

                      <View style={styles.reconnectingActionsRow}>
                        <TouchableOpacity
                          style={[styles.actionBtn, { backgroundColor: colors.accent, flex: 1 }]}
                          onPress={() => {
                            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                            setShowRescanScanner(true);
                          }}
                          activeOpacity={0.8}
                        >
                          <Ionicons name="qr-code-outline" size={16} color={colors.white} style={{ marginRight: 6 }} />
                          <Text style={styles.btnText}>Scan New QR Code</Text>
                        </TouchableOpacity>

                        <TouchableOpacity
                          style={[styles.actionBtn, { backgroundColor: colors.surfaceElevated, paddingHorizontal: 14 }]}
                          onPress={() => {
                            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
                            props.onUnlink?.();
                          }}
                          activeOpacity={0.8}
                        >
                          <Ionicons name="trash-outline" size={16} color={colors.danger} />
                        </TouchableOpacity>
                      </View>
                    </View>

                    {props.errorMsg ? (
                      <View style={styles.errorContainer}>
                        <Ionicons name="alert-circle-outline" size={16} color={colors.danger} style={{ marginRight: 6 }} />
                        <Text style={styles.errorText}>{props.errorMsg}</Text>
                      </View>
                    ) : null}
                  </View>
                ) : (
                  <View>
                    <Text style={styles.connectionSubtitle}>
                      Point your camera at the QR code shown in Blinky on your PC (tap the QR icon in the desktop toolbar) to link this device.
                    </Text>
                    <QrScanner onScanned={handleQrScanned} scanActive={props.visible} />
                    {showRescanScanner && isPaired && (
                      <TouchableOpacity
                        style={[styles.smallBtn, { marginTop: 12, alignSelf: 'center', backgroundColor: colors.surface }]}
                        onPress={() => setShowRescanScanner(false)}
                      >
                        <Ionicons name="arrow-back" size={14} color={colors.textSecondary} style={{ marginRight: 4 }} />
                        <Text style={styles.smallBtnText}>Cancel & Use Saved PC</Text>
                      </TouchableOpacity>
                    )}
                    {qrError ? (
                      <View style={styles.errorContainer}>
                        <Ionicons name="alert-circle-outline" size={16} color={colors.danger} style={{ marginRight: 6 }} />
                        <Text style={styles.errorText}>{qrError}</Text>
                      </View>
                    ) : null}
                    {props.errorMsg ? (
                      <View style={styles.errorContainer}>
                        <Ionicons name="alert-circle-outline" size={16} color={colors.danger} style={{ marginRight: 6 }} />
                        <Text style={styles.errorText}>{props.errorMsg}</Text>
                      </View>
                    ) : null}
                  </View>
                )}
              </View>
            ) : (
              // ================= DEBUG MODE: MANUAL & AUTO-DISCOVER TABS =================
              <View>
                <Text style={styles.connectionSubtitle}>
                  Enter your PC's IP or tap "Auto-Discover" to automatically locate and connect to Blinky over LAN.
                </Text>

                <View style={styles.tabRow}>
                  <TouchableOpacity
                    style={[styles.tab, linkTab === 'qr' && styles.tabActive]}
                    onPress={() => {
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
                      setLinkTab('qr');
                    }}
                    activeOpacity={0.8}
                  >
                    <Ionicons
                      name="qr-code-outline"
                      size={16}
                      color={linkTab === 'qr' ? colors.white : colors.textSecondary}
                      style={{ marginRight: 6 }}
                    />
                    <Text style={[styles.tabText, linkTab === 'qr' && styles.tabTextActive]}>QR</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.tab, linkTab === 'manual' && styles.tabActive]}
                    onPress={() => {
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
                      setLinkTab('manual');
                    }}
                    activeOpacity={0.8}
                  >
                    <Ionicons
                      name="create-outline"
                      size={16}
                      color={linkTab === 'manual' ? colors.white : colors.textSecondary}
                      style={{ marginRight: 6 }}
                    />
                    <Text style={[styles.tabText, linkTab === 'manual' && styles.tabTextActive]}>Manual</Text>
                  </TouchableOpacity>
                </View>

                {linkTab === 'qr' ? (
                  props.status === 'connected' ? (
                    <View style={styles.connectedNote}>
                      <Ionicons name="checkmark-circle-outline" size={20} color={colors.success} />
                      <Text style={styles.connectedNoteText}>
                        Connected{props.ipAddress ? ` to ${props.ipAddress}` : ''}. Disconnect to pair a different PC.
                      </Text>
                    </View>
                  ) : props.status === 'connecting' ? (
                    <View style={styles.progressContainer}>
                      <ActivityIndicator size="small" color={colors.accent} style={{ marginRight: 8 }} />
                      <Text style={styles.progressText}>Connecting...</Text>
                    </View>
                  ) : (
                    <View>
                      <QrScanner onScanned={handleQrScanned} scanActive={props.visible} />
                      {qrError ? (
                        <View style={styles.errorContainer}>
                          <Text style={styles.errorText}>{qrError}</Text>
                        </View>
                      ) : null}
                      {props.errorMsg ? (
                        <View style={styles.errorContainer}>
                          <Text style={styles.errorText}>{props.errorMsg}</Text>
                        </View>
                      ) : null}
                    </View>
                  )
                ) : (
                  <View>
                    <View style={styles.inputWrapper}>
                      <Ionicons name="link-outline" size={20} color={colors.textSecondary} style={styles.inputIcon} />
                      <TextInput
                        style={[styles.input, props.isConnected && styles.inputDisabled]}
                        placeholder="Enter PC IP (e.g. 100.122.62.2)"
                        placeholderTextColor={colors.textMuted}
                        value={props.ipAddress}
                        onChangeText={props.setIpAddress}
                        editable={!props.isConnected && props.status !== 'connecting'}
                        keyboardType="numeric"
                        autoCapitalize="none"
                        autoCorrect={false}
                      />
                    </View>

                    <View style={styles.actionRow}>
                      {props.status !== 'connected' && props.status !== 'connecting' ? (
                        <>
                          <TouchableOpacity
                            style={[styles.actionBtn, { backgroundColor: props.isDiscovering ? colors.surfacePressed : colors.accent }]}
                            onPress={props.handleConnect}
                            activeOpacity={0.8}
                            disabled={props.isDiscovering}
                          >
                            <Text style={styles.btnText}>Establish Link</Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            style={[styles.actionBtn, { backgroundColor: props.isDiscovering ? colors.surfacePressed : colors.surfaceElevated }]}
                            onPress={props.handleAutoDiscover}
                            activeOpacity={0.8}
                            disabled={props.isDiscovering}
                          >
                            <Text style={styles.btnText}>Auto-Discover</Text>
                          </TouchableOpacity>
                        </>
                      ) : (
                        <TouchableOpacity
                          style={[styles.actionBtn, { backgroundColor: colors.danger, width: '100%' }]}
                          onPress={() => {
                            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
                            props.disconnect();
                          }}
                          activeOpacity={0.8}
                        >
                          <Text style={styles.btnText}>
                            {props.status === 'connecting' ? 'Cancel Connection' : 'Disconnect Link'}
                          </Text>
                        </TouchableOpacity>
                      )}
                    </View>

                    {props.discoveryProgress ? (
                      <View style={styles.progressContainer}>
                        <ActivityIndicator size="small" color={colors.accent} style={{ marginRight: 8 }} />
                        <Text style={styles.progressText}>{props.discoveryProgress}</Text>
                      </View>
                    ) : null}

                    {props.errorMsg ? (
                      <View style={styles.errorContainer}>
                        <Text style={styles.errorText}>{props.errorMsg}</Text>
                      </View>
                    ) : null}
                  </View>
                )}
              </View>
            )}

            {/* Workstation Lockscreen Password / PIN */}
            <View style={styles.sectionDivider} />
            <Text style={styles.sectionHeader}>WORKSTATION AUTO-UNLOCK</Text>
            <View style={styles.inputWrapper}>
              <Ionicons name="lock-open-outline" size={20} color={colors.textSecondary} style={styles.inputIcon} />
              <TextInput
                style={styles.input}
                placeholder="Windows Lockscreen Password or PIN"
                placeholderTextColor={colors.textMuted}
                value={props.workstationPin}
                onChangeText={(val) => {
                  props.setWorkstationPin(val);
                  AsyncStorage.setItem(props.WORKSTATION_PIN_STORAGE_KEY, val).catch(() => {});
                }}
                secureTextEntry
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="off"
                textContentType="none"
                importantForAutofill="no"
              />
            </View>
            <Text style={styles.helperText}>
              Enter your Windows password or PIN (e.g. 1750) to automatically unlock when waking PC.
            </Text>

            {/* Target MAC address for Wake-on-LAN */}
            <View style={styles.macSection}>
              <View style={styles.macHeader}>
                <Text style={styles.macTitle}>TARGET PC MAC ADDRESS</Text>
                {props.systemInfo?.network?.mac_address ? (
                  <TouchableOpacity
                    onPress={() => {
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                      props.setMacAddress(props.systemInfo.network.mac_address);
                    }}
                    style={styles.autoDetectBadge}
                  >
                    <Text style={styles.autoDetectText}>⚡ Auto-detected</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
              <View style={styles.inputWrapper}>
                <Ionicons name="hardware-chip-outline" size={18} color={colors.textSecondary} style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  placeholder={props.systemInfo?.network?.mac_address || "e.g. 68:c6:ac:a2:d2:30"}
                  placeholderTextColor={colors.textMuted}
                  value={props.macAddress}
                  onChangeText={props.setMacAddress}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>
            </View>
          </ScrollView>
        </Animated.View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#121216',
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xl,
    maxHeight: '90%',
    borderTopWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.12)',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: -8 },
    shadowOpacity: 0.6,
    shadowRadius: 20,
    elevation: 24,
  },
  sheetHandleContainer: {
    paddingVertical: 10,
    alignItems: 'center',
    width: '100%',
  },
  handleBar: {
    width: 44,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: 'rgba(255, 255, 255, 0.35)',
    alignSelf: 'center',
  },
  connectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  connectionTitle: {
    ...typography.heading2,
    color: colors.textPrimary,
  },
  closeBtn: {
    padding: 4,
  },
  scrollContent: {
    marginTop: spacing.xs,
  },
  connectionSubtitle: {
    ...typography.bodyMedium,
    color: colors.textMuted,
    marginBottom: spacing.md,
    lineHeight: 20,
  },
  connectedCard: {
    backgroundColor: 'rgba(16, 185, 129, 0.08)',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.25)',
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  connectedCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  connectedIconCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  connectedCardTitle: {
    ...typography.bodyMedium,
    color: colors.textPrimary,
    fontWeight: '700',
  },
  connectedCardSubtitle: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    marginTop: 2,
  },
  secureBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(16, 185, 129, 0.2)',
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: radius.sm,
  },
  secureBadgeText: {
    fontSize: 9.5,
    fontWeight: '800',
    color: colors.success,
    letterSpacing: 0.5,
  },
  connectedActionsRow: {
    flexDirection: 'row',
    gap: 10,
  },
  smallBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: radius.md,
  },
  smallBtnText: {
    ...typography.bodySmall,
    color: colors.textPrimary,
    fontWeight: '600',
  },
  progressCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
    marginBottom: spacing.md,
  },
  progressTitle: {
    ...typography.bodyMedium,
    color: colors.textPrimary,
    fontWeight: '600',
  },
  progressSubtitle: {
    ...typography.bodySmall,
    color: colors.textMuted,
    marginTop: 2,
  },
  cancelLinkBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
  },
  cancelLinkBtnText: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    fontWeight: '600',
  },
  reconnectingCard: {
    backgroundColor: 'rgba(245, 158, 11, 0.08)',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: 'rgba(245, 158, 11, 0.25)',
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  reconnectingTitle: {
    ...typography.bodyMedium,
    color: colors.warning,
    fontWeight: '700',
  },
  reconnectingDesc: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    lineHeight: 18,
    marginBottom: 12,
  },
  reconnectingActionsRow: {
    flexDirection: 'row',
    gap: 8,
  },
  tabRow: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
    padding: 4,
    marginBottom: spacing.md,
    gap: 4,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: radius.sm,
  },
  tabActive: {
    backgroundColor: colors.accent,
  },
  tabText: {
    ...typography.bodyMedium,
    fontWeight: '600',
    color: colors.textSecondary,
  },
  tabTextActive: {
    color: colors.white,
  },
  connectedNote: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.successMuted,
    padding: spacing.sm,
    borderRadius: radius.sm,
    borderLeftWidth: 3,
    borderLeftColor: colors.success,
    marginBottom: spacing.md,
    gap: spacing.sm,
  },
  connectedNoteText: {
    ...typography.bodySmall,
    color: colors.success,
    flex: 1,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
    paddingHorizontal: spacing.sm,
    marginBottom: spacing.sm,
  },
  inputIcon: {
    marginRight: spacing.sm,
  },
  input: {
    flex: 1,
    height: 48,
    color: colors.textPrimary,
    ...typography.bodyMedium,
  },
  inputDisabled: {
    color: colors.textMuted,
  },
  helperText: {
    ...typography.bodySmall,
    color: colors.textMuted,
    marginBottom: spacing.md,
    marginTop: -2,
    lineHeight: 16,
  },
  sectionDivider: {
    height: 1,
    backgroundColor: colors.borderLight,
    marginVertical: spacing.md,
  },
  sectionHeader: {
    fontSize: 11,
    fontWeight: '800',
    color: colors.textSecondary,
    letterSpacing: 0.8,
    marginBottom: spacing.xs,
  },
  actionRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.xs,
    marginBottom: spacing.md,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    height: 44,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnText: {
    ...typography.bodyMedium,
    fontWeight: '600',
    color: colors.white,
  },
  progressContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.md,
    gap: spacing.sm,
  },
  progressText: {
    ...typography.bodyMedium,
    color: colors.accent,
  },
  errorContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.3)',
    padding: spacing.sm,
    marginBottom: spacing.sm,
  },
  errorText: {
    ...typography.bodySmall,
    color: colors.danger,
    flex: 1,
  },
  macSection: {
    marginTop: spacing.xs,
  },
  macHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  macTitle: {
    fontSize: 11,
    fontWeight: '800',
    color: colors.textSecondary,
    letterSpacing: 0.8,
  },
  autoDetectBadge: {
    backgroundColor: 'rgba(255, 90, 54, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  autoDetectText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#FF5A36',
  },
});
