import React from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, typography, radius, spacing } from '../theme/theme';

interface SystemScreenProps {
  systemInfo: any;
  isConnected: boolean;
  onPowerAction: (action: 'restart' | 'sleep' | 'lock' | 'hibernate') => void;
}

export function SystemScreen({ systemInfo, isConnected, onPowerAction }: SystemScreenProps) {
  const handlePowerAction = (action: 'restart' | 'sleep' | 'lock' | 'hibernate') => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
    onPowerAction(action);
  };

  const cpuUsage = systemInfo?.memory?.percent_used || 0; // fallback mock
  const ramUsage = systemInfo?.memory?.percent_used || 0;
  const batteryLevel = systemInfo?.battery?.percent || 100;
  const isCharging = systemInfo?.battery?.power_plugged || false;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.headerTitle}>System Monitor</Text>
      <View style={styles.statusRow}>
        <View style={[styles.statusIndicator, { backgroundColor: isConnected ? colors.success : colors.danger }]} />
        <Text style={styles.statusText}>{isConnected ? 'Connected to PC' : 'Disconnected'}</Text>
      </View>

      <Text style={styles.sectionTitle}>METRICS</Text>
      <View style={styles.metricsGrid}>
        <MetricCard icon="hardware-chip" title="CPU" value={`${cpuUsage.toFixed(1)}%`} color="#3B82F6" />
        <MetricCard icon="server" title="RAM" value={`${ramUsage.toFixed(1)}%`} color="#8B5CF6" />
        <MetricCard icon={isCharging ? "battery-charging" : "battery-half"} title="Battery" value={`${batteryLevel.toFixed(0)}%`} color={isCharging ? colors.success : "#10B981"} />
        <MetricCard icon="wifi" title="Network" value={systemInfo?.network?.ip_address || "Unknown"} color="#06B6D4" isSmallText />
      </View>

      <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>POWER CONTROLS</Text>
      <View style={styles.powerGrid}>
        <PowerButton icon="moon" label="Sleep" color="#8B5CF6" onPress={() => handlePowerAction('sleep')} disabled={!isConnected} />
        <PowerButton icon="lock-closed" label="Lock" color="#F59E0B" onPress={() => handlePowerAction('lock')} disabled={!isConnected} />
        <PowerButton icon="refresh" label="Restart" color="#06B6D4" onPress={() => handlePowerAction('restart')} disabled={!isConnected} />
        <PowerButton icon="power" label="Hibernate" color={colors.danger} onPress={() => handlePowerAction('hibernate')} disabled={!isConnected} />
      </View>
    </ScrollView>
  );
}

function MetricCard({ icon, title, value, color, isSmallText }: { icon: any, title: string, value: string, color: string, isSmallText?: boolean }) {
  return (
    <View style={styles.metricCard}>
      <View style={[styles.metricIconBox, { backgroundColor: `${color}15` }]}>
        <Ionicons name={icon} size={20} color={color} />
      </View>
      <View style={styles.metricData}>
        <Text style={styles.metricTitle}>{title}</Text>
        <Text style={[styles.metricValue, isSmallText && { fontSize: 13, letterSpacing: 0 }]} numberOfLines={1}>{value}</Text>
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
  }
});
