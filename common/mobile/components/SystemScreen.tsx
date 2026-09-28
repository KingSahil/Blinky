import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Modal,
  Animated,
  PanResponder,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, typography, radius, spacing } from '../theme/theme';

interface SystemScreenProps {
  systemInfo: any;
  isConnected: boolean;
  onPowerAction: (action: 'restart' | 'sleep' | 'lock' | 'hibernate') => void;
  onWakePc?: () => void;
  isSendingWol?: boolean;
  isWorkstationLocked?: boolean;
  onRefresh?: () => void;
}

export function SystemScreen({
  systemInfo,
  isConnected,
  onPowerAction,
  onWakePc,
  isSendingWol = false,
  isWorkstationLocked = false,
  onRefresh,
}: SystemScreenProps) {
  const [refreshing, setRefreshing] = useState(false);
  const [pendingAction, setPendingAction] = useState<'restart' | 'sleep' | 'lock' | 'hibernate' | null>(null);

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
            setPendingAction(null);
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
      setPendingAction(null);
    });
  };

  useEffect(() => {
    if (pendingAction) {
      panY.setValue(0);
    }
  }, [pendingAction]);

  // Poll live metrics periodically while viewing the System Monitor tab
  useEffect(() => {
    if (!isConnected || !onRefresh) return;

    onRefresh();

    const interval = setInterval(() => {
      onRefresh();
    }, 2500);

    return () => clearInterval(interval);
  }, [isConnected, onRefresh]);

  const handlePullRefresh = useCallback(() => {
    if (!onRefresh) return;
    setRefreshing(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    onRefresh();
    setTimeout(() => setRefreshing(false), 800);
  }, [onRefresh]);

  const handlePromptPowerAction = (action: 'restart' | 'sleep' | 'lock' | 'hibernate') => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setPendingAction(action);
  };

  const handleConfirmPowerAction = () => {
    if (!pendingAction) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
    onPowerAction(pendingAction);
    setPendingAction(null);
  };

  const handleWakePc = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
    if (onWakePc) {
      onWakePc();
    }
  };

  // Telemetry metrics
  const cpuUsage = systemInfo?.cpu?.percent ?? systemInfo?.cpu_percent ?? 0;
  const ramUsage = systemInfo?.memory?.percent ?? 0;
  const ramUsedGb = systemInfo?.memory?.used_mb ? (systemInfo.memory.used_mb / 1024).toFixed(1) : undefined;
  const ramTotalGb = systemInfo?.memory?.total_mb ? (systemInfo.memory.total_mb / 1024).toFixed(1) : undefined;
  const ramSubtitle = ramUsedGb && ramTotalGb ? `${ramUsedGb} / ${ramTotalGb} GB` : undefined;

  const hasBattery = systemInfo?.battery?.has_battery ?? false;
  const batteryLevel = systemInfo?.battery?.percent ?? 100;
  const isCharging = systemInfo?.battery?.is_charging ?? false;
  const isPowerPlugged = systemInfo?.battery?.power_plugged ?? isCharging;
  const isPluggedIn = isPowerPlugged || isCharging;
  const batteryStatus = systemInfo?.battery?.status;
  const batteryValue = !hasBattery ? 'AC Power' : `${batteryLevel.toFixed(0)}%`;
  const batterySubtitle = !hasBattery
    ? 'AC Mains Nominal'
    : (batteryStatus || (isPluggedIn ? (isCharging ? 'Charging' : 'Plugged In') : 'Discharging'));

  const ipAddress = systemInfo?.network?.ip_address;
  const networkIface = systemInfo?.network?.interface;
  const networkValue = ipAddress || networkIface || (isConnected ? 'Connected' : 'Offline');
  const networkSubtitle = ipAddress && networkIface ? networkIface : undefined;

  return (
    <ScrollView 
      style={styles.container} 
      contentContainerStyle={styles.content}
      refreshControl={
        onRefresh ? (
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handlePullRefresh}
            tintColor={colors.accent}
            colors={[colors.accent]}
          />
        ) : undefined
      }
    >
      <Text style={styles.headerTitle}>System Monitor</Text>
      <View style={styles.statusRow}>
        <View style={[styles.statusIndicator, { backgroundColor: isConnected ? colors.success : colors.danger }]} />
        <Text style={styles.statusText}>
          {isConnected ? `Connected to ${systemInfo?.hostname || 'PC'}` : 'Disconnected'}
        </Text>
      </View>

      <Text style={styles.sectionTitle}>METRICS</Text>
      <View style={styles.metricsGrid}>
        <MetricCard 
          icon="hardware-chip" 
          title="CPU" 
          value={`${cpuUsage.toFixed(1)}%`} 
          color="#3B82F6" 
          subtitle={systemInfo?.platform ? `${systemInfo.platform.toUpperCase()} Host` : undefined}
        />
        <MetricCard 
          icon="server" 
          title="RAM" 
          value={`${ramUsage.toFixed(1)}%`} 
          color="#8B5CF6" 
          subtitle={ramSubtitle}
        />
        <MetricCard 
          icon={!hasBattery ? "power" : (isPluggedIn ? "battery-charging" : (batteryLevel < 20 ? "battery-dead" : "battery-half"))} 
          title={!hasBattery ? "Power" : "Battery"} 
          value={batteryValue} 
          color={isPluggedIn || !hasBattery ? colors.success : (batteryLevel < 20 ? colors.danger : "#10B981")} 
          subtitle={batterySubtitle}
        />
        <MetricCard 
          icon="wifi" 
          title="Network" 
          value={networkValue} 
          color="#06B6D4" 
          isSmallText={networkValue.length > 13} 
          subtitle={networkSubtitle}
        />
      </View>

      <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>POWER CONTROLS</Text>
      
      {onWakePc && (
        <TouchableOpacity
          style={[styles.wakeBtn, isSendingWol && styles.wakeBtnActive]}
          onPress={handleWakePc}
          disabled={isSendingWol}
          activeOpacity={0.7}
        >
          <View style={styles.wakeIconBox}>
            {isSendingWol ? (
              <ActivityIndicator size="small" color={colors.success} />
            ) : (
              <Ionicons name="flash" size={22} color={colors.success} />
            )}
          </View>
          <View style={styles.wakeTextContainer}>
            <Text style={styles.wakeLabel}>
              {isSendingWol ? 'Waking PC...' : isWorkstationLocked ? 'Wake / Unlock PC' : 'Wake PC (WoL)'}
            </Text>
            <Text style={styles.wakeSubtext}>
              {isSendingWol
                ? 'Broadcasting Magic Packet...'
                : !isConnected
                ? 'Send Wake-on-LAN magic packet over network'
                : isWorkstationLocked
                ? 'Unlock display or send magic packet'
                : 'Send Wake-on-LAN magic packet'}
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={colors.textMuted} />
        </TouchableOpacity>
      )}

      <View style={styles.powerGrid}>
        <PowerButton icon="moon" label="Sleep" color="#8B5CF6" onPress={() => handlePromptPowerAction('sleep')} disabled={!isConnected} />
        <PowerButton icon="lock-closed" label="Lock" color="#F59E0B" onPress={() => handlePromptPowerAction('lock')} disabled={!isConnected} />
        <PowerButton icon="refresh" label="Restart" color="#06B6D4" onPress={() => handlePromptPowerAction('restart')} disabled={!isConnected} />
        <PowerButton icon="power" label="Hibernate" color={colors.danger} onPress={() => handlePromptPowerAction('hibernate')} disabled={!isConnected} />
      </View>

      {/* Confirmation Bottom Toastbar with Slide-down to Close */}
      <Modal
        visible={Boolean(pendingAction)}
        transparent
        animationType="fade"
        onRequestClose={handleDismiss}
      >
        <TouchableOpacity
          style={styles.modalBackdrop}
          activeOpacity={1}
          onPress={handleDismiss}
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
            {/* Drag Handle */}
            <View {...panResponder.panHandlers} style={styles.sheetHandleContainer}>
              <View style={styles.sheetHandleBar} />
            </View>

            <View style={styles.modalHeader}>
              <View
                style={[
                  styles.modalIconBox,
                  {
                    backgroundColor:
                      pendingAction === 'restart'
                        ? 'rgba(6, 182, 212, 0.15)'
                        : pendingAction === 'hibernate'
                        ? 'rgba(239, 68, 68, 0.15)'
                        : pendingAction === 'lock'
                        ? 'rgba(245, 158, 11, 0.15)'
                        : 'rgba(139, 92, 246, 0.15)',
                  },
                ]}
              >
                <Ionicons
                  name={
                    pendingAction === 'restart'
                      ? 'refresh'
                      : pendingAction === 'hibernate'
                      ? 'power'
                      : pendingAction === 'lock'
                      ? 'lock-closed'
                      : 'moon'
                  }
                  size={26}
                  color={
                    pendingAction === 'restart'
                      ? '#06B6D4'
                      : pendingAction === 'hibernate'
                      ? colors.danger
                      : pendingAction === 'lock'
                      ? '#F59E0B'
                      : '#8B5CF6'
                  }
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.modalTitle}>
                  {pendingAction === 'restart'
                    ? 'Restart Workstation'
                    : pendingAction === 'hibernate'
                    ? 'Hibernate Workstation'
                    : pendingAction === 'lock'
                    ? 'Lock Workstation'
                    : 'Sleep Workstation'}
                </Text>
                <Text style={styles.modalSubtitle}>
                  {pendingAction === 'restart'
                    ? 'Your PC will immediately reboot. Save any active work.'
                    : pendingAction === 'hibernate'
                    ? 'Saves state to disk and powers down completely.'
                    : pendingAction === 'lock'
                    ? 'Locks the Windows desktop session.'
                    : 'Puts your computer into low-power sleep mode.'}
                </Text>
              </View>
            </View>

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={[
                  styles.confirmActionBtn,
                  {
                    backgroundColor:
                      pendingAction === 'hibernate' || pendingAction === 'restart'
                        ? colors.danger
                        : colors.accent,
                  },
                ]}
                onPress={handleConfirmPowerAction}
                activeOpacity={0.8}
              >
                <Text style={styles.confirmActionBtnText}>
                  Confirm {pendingAction ? pendingAction.toUpperCase() : ''}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.cancelActionBtn}
                onPress={() => setPendingAction(null)}
                activeOpacity={0.8}
              >
                <Text style={styles.cancelActionBtnText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </Animated.View>
        </TouchableOpacity>
      </Modal>
    </ScrollView>
  );
}

function MetricCard({ 
  icon, 
  title, 
  value, 
  color, 
  isSmallText,
  subtitle,
}: { 
  icon: any; 
  title: string; 
  value: string; 
  color: string; 
  isSmallText?: boolean;
  subtitle?: string;
}) {
  return (
    <View style={styles.metricCard}>
      <View style={[styles.metricIconBox, { backgroundColor: `${color}15` }]}>
        <Ionicons name={icon} size={20} color={color} />
      </View>
      <View style={styles.metricData}>
        <Text style={styles.metricTitle}>{title}</Text>
        <Text style={[styles.metricValue, isSmallText && { fontSize: 13, letterSpacing: 0 }]} numberOfLines={1}>
          {value}
        </Text>
        {subtitle ? (
          <Text style={styles.metricSubtitle} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

function PowerButton({ icon, label, color, onPress, disabled }: { icon: any, label: string, color: string, onPress: () => void, disabled: boolean }) {
  return (
    <TouchableOpacity 
      style={[styles.powerBtn, disabled && styles.powerBtnDisabled]} 
      onPress={onPress}
      disabled={disabled}
      activeOpacity={0.7}
    >
      <View style={[styles.powerIconBox, { backgroundColor: `${color}15` }]}>
        <Ionicons name={icon} size={22} color={color} />
      </View>
      <Text style={styles.powerLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    padding: spacing.md,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xxxl,
  },
  headerTitle: {
    ...typography.heading2,
    color: colors.textPrimary,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs,
    marginBottom: spacing.xl,
  },
  statusIndicator: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  statusText: {
    ...typography.bodySmall,
    color: colors.textSecondary,
  },
  sectionTitle: {
    ...typography.label,
    color: colors.textMuted,
    marginBottom: spacing.md,
    marginLeft: 4,
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    justifyContent: 'space-between',
  },
  metricCard: {
    width: '47%',
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    padding: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderLight,
    marginBottom: spacing.xs,
  },
  metricIconBox: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
  },
  metricData: {
    flex: 1,
  },
  metricTitle: {
    ...typography.label,
    color: colors.textMuted,
    fontSize: 10,
    marginBottom: 2,
  },
  metricValue: {
    fontFamily: 'OkineSans',
    fontSize: 18,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  metricSubtitle: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    fontSize: 10,
    marginTop: 1,
  },
  powerGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    justifyContent: 'space-between',
  },
  powerBtn: {
    width: '47%',
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    padding: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderLight,
    marginBottom: spacing.xs,
  },
  powerBtnDisabled: {
    opacity: 0.5,
  },
  powerIconBox: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
  },
  powerLabel: {
    ...typography.bodyMedium,
    color: colors.textPrimary,
    fontWeight: '600',
  },
  wakeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    padding: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.25)',
    marginBottom: spacing.md,
  },
  wakeBtnActive: {
    borderColor: colors.success,
    backgroundColor: 'rgba(16, 185, 129, 0.08)',
  },
  wakeIconBox: {
    width: 42,
    height: 42,
    borderRadius: radius.md,
    backgroundColor: colors.successMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  wakeTextContainer: {
    flex: 1,
  },
  wakeLabel: {
    ...typography.bodyMedium,
    color: colors.textPrimary,
    fontWeight: '600',
    marginBottom: 2,
  },
  wakeSubtext: {
    ...typography.bodySmall,
    color: colors.textSecondary,
    fontSize: 12,
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#121216', // 100% OPAQUE SOLID DARK, NO TRANSPARENCY
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
    marginBottom: spacing.lg,
    marginTop: spacing.xs,
  },
  modalIconBox: {
    width: 50,
    height: 50,
    borderRadius: radius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  modalTitle: {
    ...typography.heading3,
    color: colors.textPrimary,
    marginBottom: 4,
  },
  modalSubtitle: {
    ...typography.bodySmall,
    color: colors.textMuted,
  },
  modalActions: {
    gap: spacing.sm,
  },
  confirmActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
    paddingVertical: 14,
  },
  confirmActionBtnText: {
    ...typography.bodyMedium,
    color: '#FFFFFF',
    fontWeight: '700',
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
});
