import React, { useState } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  ScrollView,
  TextInput,
  Modal,
  ActivityIndicator,
  Platform,
  StatusBar,
  Alert,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { triggerHaptic } from './lib/haptics';
import type { SystemInfo, PowerEvent } from './usePCWebSocket';

interface SentinelModalProps {
  visible: boolean;
  onClose: () => void;
  isConnected: boolean;
  systemInfo: SystemInfo | null;
  onRefresh: () => void;
  onTriggerPowerCommand: (
    command: 'hibernate' | 'power_off' | 'restart' | 'sleep' | 'lock' | 'unlock',
    label: string
  ) => void;
  macAddress: string;
  onChangeMacAddress: (mac: string) => void;
  wolBroadcastIp: string;
  onChangeWolBroadcastIp: (ip: string) => void;
  onSendWakeOnLan: () => Promise<void>;
  isSendingWol: boolean;
  wolFeedback: string | null;
  latestPowerEvent: PowerEvent | null;
}

/** Displays host telemetry, power controls, and Wake-on-LAN settings. */
export const SentinelModal: React.FC<SentinelModalProps> = ({
  visible,
  onClose,
  isConnected,
  systemInfo,
  onRefresh,
  onTriggerPowerCommand,
  macAddress,
  onChangeMacAddress,
  wolBroadcastIp,
  onChangeWolBroadcastIp,
  onSendWakeOnLan,
  isSendingWol,
  wolFeedback,
  latestPowerEvent,
}) => {
  const [showSettings, setShowSettings] = useState(false);
  const isLocked = Boolean(
    systemInfo?.is_locked ||
    (latestPowerEvent?.action === 'lock' && latestPowerEvent.status === 'triggered')
  );

  /** Formats an uptime duration as compact hours and minutes. */
  const formatUptime = (seconds: number) => {
    if (!seconds) return 'N/A';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (hrs > 0) return `${hrs}h ${mins}m`;
    return `${mins}m`;
  };

  const ramUsed = systemInfo?.memory ? (systemInfo.memory.used_mb / 1024).toFixed(1) : '0';
  const ramTotal = systemInfo?.memory ? (systemInfo.memory.total_mb / 1024).toFixed(1) : '0';
  const ramPercent = systemInfo?.memory?.percent || 0;

  const hasBattery = systemInfo?.battery?.has_battery;
  const batteryPercent = systemInfo?.battery?.percent ?? null;
  const isCharging = systemInfo?.battery?.is_charging ?? false;
  const batteryStatusText = systemInfo?.battery?.status || 'AC Mains Nominal';

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={false}
      onRequestClose={onClose}
    >
      <LinearGradient colors={['#070313', '#090710', '#05020B']} style={styles.container}>
        <StatusBar barStyle="light-content" />
        <View style={styles.safeArea}>
          {/* Header */}
          <View style={styles.header}>
            <View style={styles.headerLeft}>
              <View style={styles.boltBadge}>
                <Ionicons name="flash" size={16} color="#FF5A36" />
              </View>
              <View>
                <Text style={styles.headerTitle}>SENTINEL</Text>
                <Text style={styles.headerSubtitle}>Power & Telemetry Monitor</Text>
              </View>
            </View>
            <View style={styles.headerRight}>
              <TouchableOpacity
                style={styles.refreshBtn}
                onPress={() => {
                  triggerHaptic('light');
                  onRefresh();
                }}
                activeOpacity={0.7}
              >
                <Ionicons name="refresh-outline" size={18} color="#A78BFA" />
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.closeBtn}
                onPress={() => {
                  triggerHaptic('light');
                  onClose();
                }}
                activeOpacity={0.7}
              >
                <Ionicons name="close" size={20} color="#FFFFFF" />
              </TouchableOpacity>
            </View>
          </View>

          <ScrollView
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
          >
            {/* Host Status Pill */}
            <View style={styles.statusPillRow}>
              <View
                style={[
                  styles.statusIndicatorDot,
                  { backgroundColor: isConnected ? '#10B981' : '#EF4444' },
                ]}
              />
              <Text style={styles.statusPillText}>
                {isConnected
                  ? `HOST ONLINE • ${systemInfo?.hostname || 'Desktop'}`
                  : 'HOST OFFLINE / STANDBY'}
              </Text>
              {systemInfo?.platform && (
                <View style={styles.platformBadge}>
                  <Text style={styles.platformBadgeText}>
                    {systemInfo.platform.toUpperCase()}
                  </Text>
                </View>
              )}
            </View>

            {/* Broadcast Power Alert Banner if triggered */}
            {latestPowerEvent && (
              <View style={styles.powerEventAlertBanner}>
                <Ionicons name="notifications-outline" size={18} color="#FF5A36" style={{ marginRight: 8 }} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.powerEventTitle}>
                    {latestPowerEvent.action.toUpperCase()} TRIGGERED
                  </Text>
                  <Text style={styles.powerEventDesc}>{latestPowerEvent.message}</Text>
                </View>
              </View>
            )}

            {/* WoL feedback */}
            {wolFeedback && (
              <View style={styles.feedbackBanner}>
                <Ionicons name="wifi-outline" size={16} color="#10B981" style={{ marginRight: 8 }} />
                <Text style={styles.feedbackText}>{wolFeedback}</Text>
              </View>
            )}

            {/* Telemetry Card */}
            <View style={styles.card}>
              <Text style={styles.cardSectionTitle}>HOST TELEMETRY</Text>

              {/* OS / Desktop info */}
              <View style={styles.telemetryRow}>
                <View style={styles.telemetryItem}>
                  <Text style={styles.telemetryLabel}>OPERATING SYSTEM</Text>
                  <Text style={styles.telemetryValue} numberOfLines={1}>
                    {systemInfo?.os || (isConnected ? 'Linux / Windows' : 'Offline')}
                  </Text>
                </View>
                <View style={styles.telemetryItem}>
                  <Text style={styles.telemetryLabel}>COMPOSITOR / DE</Text>
                  <Text style={styles.telemetryValue} numberOfLines={1}>
                    {systemInfo?.compositor || 'N/A'}
                  </Text>
                </View>
              </View>

              <View style={styles.divider} />

              {/* Power / Battery source */}
              <View style={styles.telemetryRow}>
                <View style={styles.telemetryItem}>
                  <Text style={styles.telemetryLabel}>POWER SOURCE</Text>
                  <View style={styles.inlineRow}>
                    <Ionicons
                      name={hasBattery ? (isCharging ? 'battery-charging' : 'battery-half') : 'flash-outline'}
                      size={18}
                      color={hasBattery ? (isCharging ? '#10B981' : '#F59E0B') : '#10B981'}
                      style={{ marginRight: 6 }}
                    />
                    <Text style={styles.telemetryValue}>
                      {hasBattery
                        ? `${batteryPercent !== null ? `${batteryPercent}%` : ''} (${batteryStatusText})`
                        : 'AC Mains Nominal ⚡'}
                    </Text>
                  </View>
                </View>
                <View style={styles.telemetryItem}>
                  <Text style={styles.telemetryLabel}>UPTIME</Text>
                  <Text style={styles.telemetryValue}>
                    {formatUptime(systemInfo?.uptime_seconds || 0)}
                  </Text>
                </View>
              </View>

              {/* RAM Usage Progress Meter */}
              {systemInfo?.memory && systemInfo.memory.total_mb > 0 && (
                <>
                  <View style={styles.divider} />
                  <View style={styles.ramSection}>
                    <View style={styles.ramHeaderRow}>
                      <Text style={styles.telemetryLabel}>MEMORY / RAM</Text>
                      <Text style={styles.ramValuesText}>
                        {ramUsed} GB / {ramTotal} GB ({ramPercent}%)
                      </Text>
                    </View>
                    <View style={styles.ramBarTrack}>
                      <View
                        style={[
                          styles.ramBarFill,
                          {
                            width: `${Math.min(100, Math.max(2, ramPercent))}%`,
                            backgroundColor: ramPercent > 85 ? '#EF4444' : '#8B5CF6',
                          },
                        ]}
                      />
                    </View>
                  </View>
                </>
              )}
            </View>

            {/* Remote Power Actions Grid (GridWatch feature) */}
            <View style={styles.card}>
              <Text style={styles.cardSectionTitle}>REMOTE POWER ACTIONS</Text>
              <Text style={styles.cardSubtitle}>
                Control your host workstation state securely over local Wi-Fi.
              </Text>

              <View style={styles.actionGrid}>
                {/* 1. Wake PC (WoL Magic Packet) */}
                <TouchableOpacity
                  style={[styles.actionTile, styles.tileWake]}
                  onPress={() => {
                    triggerHaptic('heavy');
                    if (isLocked && isConnected) {
                      Alert.alert(
                        'Workstation Locked',
                        'Your host PC is locked. Would you like to unlock it or dispatch a Wake-on-LAN packet?',
                        [
                          { text: 'Cancel', style: 'cancel' },
                          {
                            text: 'Unlock Workstation',
                            onPress: () => onTriggerPowerCommand('unlock', 'Unlock Workstation'),
                          },
                          {
                            text: 'Send WoL Burst',
                            onPress: () => onSendWakeOnLan(),
                          },
                        ]
                      );
                    } else {
                      onSendWakeOnLan();
                    }
                  }}
                  activeOpacity={0.75}
                  disabled={isSendingWol}
                >
                  <LinearGradient
                    colors={['rgba(16, 185, 129, 0.25)', 'rgba(6, 78, 59, 0.4)']}
                    style={styles.tileGradient}
                  >
                    {isSendingWol ? (
                      <ActivityIndicator size="small" color="#10B981" />
                    ) : (
                      <Ionicons name="flash" size={24} color="#10B981" />
                    )}
                    <Text style={[styles.tileTitle, { color: '#10B981' }]}>
                      {isLocked ? 'Wake / Unlock' : 'Wake PC'}
                    </Text>
                    <Text style={styles.tileSub}>{isLocked ? 'Unlock or WoL Burst' : 'WoL Magic Packet'}</Text>
                  </LinearGradient>
                </TouchableOpacity>

                {/* 2. Hibernate */}
                <TouchableOpacity
                  style={[styles.actionTile, styles.tileHibernate, !isConnected && styles.tileDisabled]}
                  onPress={() => {
                    if (!isConnected) {
                      Alert.alert('Offline', 'Connect to host over Wi-Fi to trigger Hibernate.');
                      return;
                    }
                    onTriggerPowerCommand('hibernate', 'Hibernate');
                  }}
                  activeOpacity={0.75}
                >
                  <LinearGradient
                    colors={['rgba(139, 92, 246, 0.25)', 'rgba(76, 29, 149, 0.4)']}
                    style={styles.tileGradient}
                  >
                    <Ionicons name="moon" size={24} color="#A78BFA" />
                    <Text style={[styles.tileTitle, { color: '#A78BFA' }]}>Hibernate</Text>
                    <Text style={styles.tileSub}>Save & Power Down</Text>
                  </LinearGradient>
                </TouchableOpacity>

                {/* 3. Sleep / Suspend */}
                <TouchableOpacity
                  style={[styles.actionTile, styles.tileSleep, !isConnected && styles.tileDisabled]}
                  onPress={() => {
                    if (!isConnected) {
                      Alert.alert('Offline', 'Connect to host over Wi-Fi to trigger Sleep.');
                      return;
                    }
                    onTriggerPowerCommand('sleep', 'Sleep');
                  }}
                  activeOpacity={0.75}
                >
                  <LinearGradient
                    colors={['rgba(59, 130, 246, 0.25)', 'rgba(30, 58, 138, 0.4)']}
                    style={styles.tileGradient}
                  >
                    <Ionicons name="bed-outline" size={24} color="#60A5FA" />
                    <Text style={[styles.tileTitle, { color: '#60A5FA' }]}>Sleep</Text>
                    <Text style={styles.tileSub}>Suspend Session</Text>
                  </LinearGradient>
                </TouchableOpacity>

                {/* 4. Lock / Unlock Workstation */}
                <TouchableOpacity
                  style={[
                    styles.actionTile,
                    isLocked ? styles.tileUnlock : styles.tileLock,
                    !isConnected && styles.tileDisabled,
                  ]}
                  onPress={() => {
                    if (!isConnected) {
                      Alert.alert('Offline', `Connect to host over Wi-Fi to trigger ${isLocked ? 'Unlock' : 'Lock'}.`);
                      return;
                    }
                    if (isLocked) {
                      onTriggerPowerCommand('unlock', 'Unlock');
                    } else {
                      onTriggerPowerCommand('lock', 'Lock');
                    }
                  }}
                  activeOpacity={0.75}
                >
                  <LinearGradient
                    colors={
                      isLocked
                        ? ['rgba(16, 185, 129, 0.25)', 'rgba(6, 78, 59, 0.4)']
                        : ['rgba(100, 116, 139, 0.25)', 'rgba(30, 41, 59, 0.4)']
                    }
                    style={styles.tileGradient}
                  >
                    <Ionicons
                      name={isLocked ? 'lock-open-outline' : 'lock-closed-outline'}
                      size={24}
                      color={isLocked ? '#10B981' : '#94A3B8'}
                    />
                    <Text style={[styles.tileTitle, { color: isLocked ? '#10B981' : '#94A3B8' }]}>
                      {isLocked ? 'Unlock' : 'Lock'}
                    </Text>
                    <Text style={styles.tileSub}>{isLocked ? 'Unlock Session' : 'Lock Screen'}</Text>
                  </LinearGradient>
                </TouchableOpacity>

                {/* 5. Reboot */}
                <TouchableOpacity
                  style={[styles.actionTile, styles.tileRestart, !isConnected && styles.tileDisabled]}
                  onPress={() => {
                    if (!isConnected) {
                      Alert.alert('Offline', 'Connect to host over Wi-Fi to trigger Reboot.');
                      return;
                    }
                    onTriggerPowerCommand('restart', 'Reboot');
                  }}
                  activeOpacity={0.75}
                >
                  <LinearGradient
                    colors={['rgba(245, 158, 11, 0.25)', 'rgba(120, 53, 15, 0.4)']}
                    style={styles.tileGradient}
                  >
                    <Ionicons name="refresh-outline" size={24} color="#FBBF24" />
                    <Text style={[styles.tileTitle, { color: '#FBBF24' }]}>Reboot</Text>
                    <Text style={styles.tileSub}>Restart System</Text>
                  </LinearGradient>
                </TouchableOpacity>

                {/* 6. Shutdown */}
                <TouchableOpacity
                  style={[styles.actionTile, styles.tileShutdown, !isConnected && styles.tileDisabled]}
                  onPress={() => {
                    if (!isConnected) {
                      Alert.alert('Offline', 'Connect to host over Wi-Fi to trigger Shutdown.');
                      return;
                    }
                    onTriggerPowerCommand('power_off', 'Shutdown');
                  }}
                  activeOpacity={0.75}
                >
                  <LinearGradient
                    colors={['rgba(239, 68, 68, 0.25)', 'rgba(127, 29, 29, 0.4)']}
                    style={styles.tileGradient}
                  >
                    <Ionicons name="power" size={24} color="#F87171" />
                    <Text style={[styles.tileTitle, { color: '#F87171' }]}>Shutdown</Text>
                    <Text style={styles.tileSub}>Power Off</Text>
                  </LinearGradient>
                </TouchableOpacity>
              </View>
            </View>

            {/* Target WoL & Network Config Toggle */}
            <View style={styles.card}>
              <TouchableOpacity
                style={styles.toggleRow}
                onPress={() => setShowSettings(!showSettings)}
                activeOpacity={0.7}
              >
                <View style={styles.inlineRow}>
                  <Ionicons name="settings-outline" size={16} color="#8A86AA" style={{ marginRight: 8 }} />
                  <Text style={styles.cardSectionTitle}>WAKE-ON-LAN CONFIGURATION</Text>
                </View>
                <Ionicons
                  name={showSettings ? 'chevron-up' : 'chevron-down'}
                  size={18}
                  color="#8A86AA"
                />
              </TouchableOpacity>

              {showSettings && (
                <View style={styles.settingsBody}>
                  <View style={styles.inputLabelRow}>
                    <Text style={styles.inputLabel}>TARGET MAC ADDRESS (PHYSICAL INTERFACE)</Text>
                    {systemInfo?.network?.mac_address ? (
                      <TouchableOpacity
                        onPress={() => {
                          triggerHaptic('light');
                          onChangeMacAddress(systemInfo.network.mac_address);
                        }}
                        style={styles.autofillBadge}
                        activeOpacity={0.7}
                      >
                        <Text style={styles.autofillText}>⚡ Auto-fill PC MAC</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                  <View style={styles.inputWrapper}>
                    <Ionicons name="hardware-chip-outline" size={18} color="#6C6985" style={styles.inputIcon} />
                    <TextInput
                      style={styles.input}
                      placeholder={systemInfo?.network?.mac_address || "e.g. 18:c0:4d:b9:0a:7d"}
                      placeholderTextColor="#6C6985"
                      value={macAddress}
                      onChangeText={onChangeMacAddress}
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>

                  <Text style={styles.inputLabel}>SUBNET BROADCAST IP</Text>
                  <View style={styles.inputWrapper}>
                    <Ionicons name="globe-outline" size={18} color="#6C6985" style={styles.inputIcon} />
                    <TextInput
                      style={styles.input}
                      placeholder="255.255.255.255"
                      placeholderTextColor="#6C6985"
                      value={wolBroadcastIp}
                      onChangeText={onChangeWolBroadcastIp}
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>

                  <TouchableOpacity
                    style={styles.wolBurstBtn}
                    onPress={() => {
                      triggerHaptic('medium');
                      onSendWakeOnLan();
                    }}
                    activeOpacity={0.8}
                    disabled={isSendingWol}
                  >
                    <LinearGradient
                      colors={['#10B981', '#059669']}
                      start={{ x: 0, y: 0 }}
                      end={{ x: 1, y: 1 }}
                      style={styles.wolBurstGradient}
                    >
                      <Ionicons name="send-outline" size={16} color="#FFFFFF" style={{ marginRight: 6 }} />
                      <Text style={styles.wolBurstText}>
                        {isSendingWol ? 'Sending Magic Packet...' : 'Dispatch WoL Burst'}
                      </Text>
                    </LinearGradient>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          </ScrollView>
        </View>
      </LinearGradient>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  safeArea: {
    flex: 1,
    paddingTop: Platform.OS === 'android' ? (StatusBar.currentHeight || 0) : 44,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.05)',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  boltBadge: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(255, 90, 54, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.35)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 2,
  },
  headerSubtitle: {
    fontSize: 11,
    color: '#8A86AA',
    fontWeight: '500',
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  refreshBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(167, 139, 250, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(167, 139, 250, 0.25)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  closeBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.12)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingVertical: 16,
    paddingBottom: 40,
  },
  statusPillRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.03)',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.07)',
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginBottom: 16,
  },
  statusIndicatorDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 10,
  },
  statusPillText: {
    flex: 1,
    color: '#FFFFFF',
    fontSize: 12.5,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  platformBadge: {
    backgroundColor: 'rgba(255, 90, 54, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.3)',
  },
  platformBadgeText: {
    color: '#FF5A36',
    fontSize: 10,
    fontWeight: '800',
  },
  powerEventAlertBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 90, 54, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.35)',
    borderRadius: 16,
    padding: 14,
    marginBottom: 16,
  },
  powerEventTitle: {
    color: '#FF5A36',
    fontSize: 13,
    fontWeight: '800',
    marginBottom: 2,
  },
  powerEventDesc: {
    color: '#E2E8F0',
    fontSize: 12,
    fontWeight: '500',
  },
  feedbackBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(16, 185, 129, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.3)',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  feedbackText: {
    color: '#10B981',
    fontSize: 12.5,
    fontWeight: '600',
    flex: 1,
  },
  card: {
    backgroundColor: 'rgba(22, 18, 38, 0.7)',
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
    padding: 18,
    marginBottom: 16,
  },
  cardSectionTitle: {
    color: '#A78BFA',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 1.5,
    marginBottom: 4,
  },
  cardSubtitle: {
    color: '#8A86AA',
    fontSize: 12,
    fontWeight: '500',
    marginBottom: 16,
  },
  telemetryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginVertical: 4,
  },
  telemetryItem: {
    flex: 1,
    paddingRight: 8,
  },
  telemetryLabel: {
    color: '#6C6985',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1,
    marginBottom: 4,
  },
  telemetryValue: {
    color: '#FFFFFF',
    fontSize: 13.5,
    fontWeight: '600',
  },
  inlineRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  divider: {
    height: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    marginVertical: 12,
  },
  ramSection: {
    marginTop: 4,
  },
  ramHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  ramValuesText: {
    color: '#A78BFA',
    fontSize: 12,
    fontWeight: '700',
  },
  ramBarTrack: {
    height: 6,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    borderRadius: 3,
    overflow: 'hidden',
  },
  ramBarFill: {
    height: '100%',
    borderRadius: 3,
  },
  actionGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  actionTile: {
    width: '48%',
    borderRadius: 16,
    overflow: 'hidden',
    borderWidth: 1,
  },
  tileGradient: {
    paddingVertical: 16,
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tileWake: {
    borderColor: 'rgba(16, 185, 129, 0.4)',
  },
  tileHibernate: {
    borderColor: 'rgba(139, 92, 246, 0.4)',
  },
  tileSleep: {
    borderColor: 'rgba(59, 130, 246, 0.4)',
  },
  tileLock: {
    borderColor: 'rgba(100, 116, 139, 0.4)',
  },
  tileUnlock: {
    borderColor: 'rgba(16, 185, 129, 0.4)',
  },
  tileRestart: {
    borderColor: 'rgba(245, 158, 11, 0.4)',
  },
  tileShutdown: {
    borderColor: 'rgba(239, 68, 68, 0.4)',
  },
  tileDisabled: {
    opacity: 0.5,
  },
  tileTitle: {
    fontSize: 14,
    fontWeight: '800',
    marginTop: 8,
    marginBottom: 2,
  },
  tileSub: {
    color: 'rgba(255, 255, 255, 0.5)',
    fontSize: 10.5,
    fontWeight: '600',
  },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  settingsBody: {
    marginTop: 16,
  },
  inputLabelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
    marginTop: 6,
  },
  autofillBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    backgroundColor: 'rgba(99, 102, 241, 0.2)',
    borderWidth: 1,
    borderColor: 'rgba(99, 102, 241, 0.4)',
  },
  autofillText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#A5B4FC',
    letterSpacing: 0.3,
  },
  inputLabel: {
    color: '#6C6985',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1,
    marginBottom: 6,
    marginTop: 6,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.4)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
    borderRadius: 12,
    paddingHorizontal: 12,
    height: 44,
    marginBottom: 10,
  },
  inputIcon: {
    marginRight: 10,
  },
  input: {
    flex: 1,
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '500',
  },
  wolBurstBtn: {
    borderRadius: 14,
    overflow: 'hidden',
    marginTop: 8,
  },
  wolBurstGradient: {
    height: 42,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  wolBurstText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '800',
  },
});
