import React from 'react';
import { View, Text, StyleSheet, Modal, TouchableOpacity, TextInput, ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { colors, typography, radius, spacing } from '../theme/theme';

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
  disconnect: () => void;
  discoveryProgress: string | null;
  errorMsg: string | null;
  RELEASE_TRANSPORT: boolean;
  WORKSTATION_PIN_STORAGE_KEY: string;
}

export function SettingsModal(props: SettingsModalProps) {
  if (!props.visible) return null;

  return (
    <Modal visible={props.visible} animationType="slide" transparent={true} onRequestClose={props.onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.modalOverlay}>
        <View style={styles.modalContent}>
          <View style={styles.handleBar} />
          
          <View style={styles.connectionHeaderRow}>
            <Text style={styles.connectionTitle}>Local Wi-Fi Link Setup</Text>
            <TouchableOpacity onPress={props.onClose} style={styles.closeBtn}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>
          
          <ScrollView style={styles.scrollContent} showsVerticalScrollIndicator={false}>
            <Text style={styles.connectionSubtitle}>
              {props.RELEASE_TRANSPORT
                ? 'Enter the PC IP, remote token, and the pinned certificate value from the PC release build.'
                : 'Enter your PC\'s IP (e.g. 100.122.62.2) or tap "Auto-Discover" to automatically locate and connect to Blinky.'}
            </Text>
            
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
                placeholder="Windows Account Password"
                placeholderTextColor={colors.textMuted}
                value={props.workstationPin}
                onChangeText={(val) => {
                  props.setWorkstationPin(val);
                  AsyncStorage.setItem(props.WORKSTATION_PIN_STORAGE_KEY, val).catch(() => {});
                }}
                secureTextEntry
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
            <Text style={styles.helperText}>
              Enter your Windows password (not Windows Hello PIN) to unlock remotely via the Unlock Provider.
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
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: colors.background,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xl,
    maxHeight: '90%',
    borderTopWidth: 1,
    borderColor: colors.borderLight,
  },
  handleBar: {
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.surfacePressed,
    alignSelf: 'center',
    marginBottom: spacing.md,
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
