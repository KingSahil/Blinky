import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, typography, radius, spacing } from '../theme/theme';
import type { QrPairingPayload } from '../lib/pairing';

export type { QrPairingPayload };
export { parsePairingQr } from '../lib/pairing';

interface QrScannerProps {
  onScanned: (data: string) => void;
  /** When false the camera ignores scans (e.g. already connecting). */
  scanActive: boolean;
}

export function QrScanner({ onScanned, scanActive }: QrScannerProps) {
  const [permission, requestPermission] = useCameraPermissions();
  const [locked, setLocked] = useState(false);

  if (!permission) {
    return (
      <View style={styles.centerBox}>
        <ActivityIndicator size="small" color={colors.accent} />
        <Text style={styles.hint}>Preparing camera...</Text>
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.centerBox}>
        <Ionicons name="camera-outline" size={40} color={colors.textMuted} />
        <Text style={styles.hint}>Camera access is needed to scan the pairing QR.</Text>
        <TouchableOpacity
          style={styles.permissionBtn}
          onPress={() => {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
            requestPermission();
          }}
          activeOpacity={0.8}
        >
          <Text style={styles.permissionBtnText}>Allow Camera</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        style={styles.camera}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={
          scanActive && !locked
            ? ({ data }) => {
                setLocked(true);
                Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
                onScanned(data);
              }
            : undefined
        }
      />
      {/* Viewfinder overlay (touch-transparent) */}
      <View style={styles.overlay} pointerEvents="none">
        <View style={styles.frame} />
        <Text style={styles.overlayHint}>Point at the QR in the PC app</Text>
      </View>
      {locked && (
        <TouchableOpacity
          style={styles.rescanBtn}
          onPress={() => setLocked(false)}
          activeOpacity={0.8}
        >
          <Ionicons name="scan-outline" size={16} color={colors.white} />
          <Text style={styles.rescanText}>Tap to scan again</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const FRAME_SIZE = 220;

const styles = StyleSheet.create({
  container: {
    height: 300,
    borderRadius: radius.lg,
    overflow: 'hidden',
    backgroundColor: colors.black,
    marginBottom: spacing.md,
  },
  camera: {
    ...StyleSheet.absoluteFill,
  },
  overlay: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  frame: {
    width: FRAME_SIZE,
    height: FRAME_SIZE,
    borderWidth: 2,
    borderColor: colors.accent,
    borderRadius: radius.md,
    backgroundColor: 'transparent',
  },
  overlayHint: {
    ...typography.bodySmall,
    color: colors.white,
    marginTop: spacing.sm,
    backgroundColor: 'rgba(0,0,0,0.55)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  centerBox: {
    height: 220,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderLight,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.md,
    marginBottom: spacing.md,
    gap: spacing.sm,
  },
  hint: {
    ...typography.bodyMedium,
    color: colors.textMuted,
    textAlign: 'center',
  },
  permissionBtn: {
    backgroundColor: colors.accent,
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: radius.md,
    alignItems: 'center',
  },
  permissionBtnText: {
    ...typography.bodyMedium,
    fontWeight: '600',
    color: colors.white,
  },
  rescanBtn: {
    position: 'absolute',
    bottom: 12,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(0,0,0,0.65)',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: radius.round,
  },
  rescanText: {
    ...typography.bodySmall,
    color: colors.white,
  },
});
