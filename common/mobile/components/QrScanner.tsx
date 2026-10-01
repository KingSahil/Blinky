import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { CameraView, useCameraPermissions, scanFromURLAsync } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
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
  const [isPickingImage, setIsPickingImage] = useState(false);

  const handlePickImage = async () => {
    try {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
      setIsPickingImage(true);
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: false,
        quality: 1,
      });

      if (!res.canceled && res.assets && res.assets.length > 0) {
        const uri = res.assets[0].uri;
        const scanResults = await scanFromURLAsync(uri, ['qr']);
        if (scanResults && scanResults.length > 0 && scanResults[0].data) {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
          onScanned(scanResults[0].data);
        } else {
          Alert.alert('No QR Code Found', 'Could not detect a valid Blinky QR code in that image. Please try scanning directly with the camera.');
        }
      }
    } catch (e: any) {
      Alert.alert('Error', e?.message || 'Failed to read QR from image.');
    } finally {
      setIsPickingImage(false);
    }
  };

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

        <TouchableOpacity
          style={[styles.permissionBtn, { backgroundColor: colors.surfaceElevated, marginTop: 8 }]}
          onPress={handlePickImage}
          activeOpacity={0.8}
          disabled={isPickingImage}
        >
          <Text style={[styles.permissionBtnText, { color: colors.textPrimary }]}>
            {isPickingImage ? 'Reading...' : 'Choose from Gallery'}
          </Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.wrapper}>
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

      <TouchableOpacity
        style={styles.galleryBtn}
        onPress={handlePickImage}
        activeOpacity={0.8}
        disabled={isPickingImage}
      >
        <Ionicons name="image-outline" size={16} color={colors.accent} style={{ marginRight: 6 }} />
        <Text style={styles.galleryBtnText}>
          {isPickingImage ? 'Scanning Image...' : 'Choose QR from Photos / Screenshot'}
        </Text>
      </TouchableOpacity>
    </View>
  );
}

const FRAME_SIZE = 200;

const styles = StyleSheet.create({
  wrapper: {
    width: '100%',
    marginBottom: spacing.md,
  },
  container: {
    width: '100%',
    height: 260,
    borderRadius: radius.lg,
    overflow: 'hidden',
    backgroundColor: '#000000',
    position: 'relative',
  },
  camera: {
    flex: 1,
    width: '100%',
    height: '100%',
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
    backgroundColor: 'rgba(0,0,0,0.6)',
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
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: radius.round,
  },
  rescanText: {
    ...typography.bodySmall,
    color: colors.white,
  },
  galleryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255, 90, 54, 0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.25)',
    paddingVertical: 10,
    borderRadius: radius.md,
    marginTop: 10,
  },
  galleryBtnText: {
    ...typography.bodySmall,
    color: colors.accent,
    fontWeight: '600',
  },
});
