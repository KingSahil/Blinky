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
  discoveryProgress: string | null;
  errorMsg: string | null;
  RELEASE_TRANSPORT: boolean;
  WORKSTATION_PIN_STORAGE_KEY: string;
}

export function SettingsModal(props: SettingsModalProps) {
  const panY = useRef(new Animated.Value(0)).current;
  const [linkTab, setLinkTab] = useState<LinkTab>('qr');
  const [qrError, setQrError] = useState<string | null>(null);

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
    }
  }, [props.visible]);

  if (!props.visible) return null;

  // QR pairing is a release-build feature (release APK <-> release PC,
  // wss + pinned cert). Dev builds use the manual flow below.
  const qrAvailable = props.RELEASE_TRANSPORT;

  const handleQrScanned = (data: string) => {
    const parsed = parsePairingQr(data);
    if (!parsed) {
      setQrError('That is not a Blinky pairing code. Open the Blinky PC app, tap the QR icon in its header, and scan that code.');
      return;
    }
    setQrError(null);
    props.handleQrConnect({
      ip: parsed.ip,
      token: parsed.token,
      pin: parsed.pin ?? undefined,
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
            <Text style={styles.connectionTitle}>Local Wi-Fi Link Setup</Text>
            <TouchableOpacity onPress={handleDismiss} style={styles.closeBtn}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>
          
          <ScrollView style={styles.scrollContent} showsVerticalScrollIndicator={false}>
            <Text style={styles.connectionSubtitle}>
              {props.RELEASE_TRANSPORT
                ? 'Scan the QR from the PC app, or enter the details manually below.'
                : 'Enter your PC\'s IP (e.g. 100.122.62.2) or tap "Auto-Discover" to automatically locate and connect to Blinky.'}
            </Text>

            {qrAvailable && (
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
            )}

            {qrAvailable && linkTab === 'qr' ? (
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

            {props.RELEASE_TRANSPORT && (
            <View style={styles.inputWrapper}>
              <Ionicons name="key-outline" size={20} color={colors.textSecondary} style={styles.inputIcon} />
              <TextInput
                style={[styles.input, props.isConnected && styles.inputDisabled]}
                placeholder="Remote token (BLINKY_REMOTE_TOKEN)"
                placeholderTextColor={colors.textMuted}
                value={props.remoteToken}
                onChangeText={props.setRemoteToken}
                editable={!props.isConnected && props.status !== 'connecting'}
                secureTextEntry
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
            )}
            
            {props.RELEASE_TRANSPORT && (
              <View style={styles.inputWrapper}>
                <Ionicons name="shield-checkmark-outline" size={20} color={colors.textSecondary} style={styles.inputIcon} />
                <TextInput
                  style={[styles.input, props.isConnected && styles.inputDisabled]}
                  placeholder="Certificate pin (sha256/...)"
                  placeholderTextColor={colors.textMuted}
                  value={props.certificatePin}
                  onChangeText={props.setCertificatePin}
                  editable={!props.isConnected && props.status !== 'connecting'}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>
            )}
            
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
            
            <View style={styles.actionRow}>
              {props.status !== 'connected' && props.status !== 'connecting' ? (
                <>
                  <TouchableOpacity style={[styles.actionBtn, { backgroundColor: props.isDiscovering ? colors.surfacePressed : colors.accent }]} onPress={props.handleConnect} activeOpacity={0.8} disabled={props.isDiscovering}>
                    <Text style={styles.btnText}>Establish Link</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={[styles.actionBtn, { backgroundColor: props.isDiscovering ? colors.surfacePressed : colors.surfaceElevated }]} onPress={props.handleAutoDiscover} activeOpacity={0.8} disabled={props.isDiscovering}>
                    <Text style={styles.btnText}>Auto-Discover</Text>
                  </TouchableOpacity>
                </>
              ) : (
                <TouchableOpacity style={[styles.actionBtn, { backgroundColor: colors.danger, width: '100%' }]} onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy); props.disconnect(); }} activeOpacity={0.8}>
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
    backgroundColor: '#121216', // 100% OPAQUE SOLID DARK, NO TRANSPARENCY
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
    ...typography.bodyMedium,
    color: colors.textPrimary,
    paddingVertical: 12,
    ...(Platform.OS === 'web' ? { outlineStyle: 'none' as any } : {}),
  },
  inputDisabled: {
    opacity: 0.5,
  },
  helperText: {
    ...typography.label,
    color: colors.textMuted,
    marginBottom: spacing.md,
    lineHeight: 16,
    textTransform: 'none',
  },
  actionRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 14,
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
    marginBottom: spacing.md,
  },
  progressText: {
    ...typography.bodyMedium,
    color: colors.accent,
  },
  errorContainer: {
    backgroundColor: colors.dangerMuted,
    padding: spacing.sm,
    borderRadius: radius.sm,
    borderLeftWidth: 3,
    borderLeftColor: colors.danger,
    marginBottom: spacing.md,
  },
  errorText: {
    ...typography.bodySmall,
    color: colors.danger,
  },
  macSection: {
    marginTop: spacing.sm,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.borderLight,
  },
  macHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  macTitle: {
    ...typography.label,
    color: colors.textSecondary,
  },
  autoDetectBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: radius.sm,
    backgroundColor: colors.successMuted,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.3)',
  },
  autoDetectText: {
    ...typography.label,
    color: colors.success,
  }
});
