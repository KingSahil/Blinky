import React, { useState, useRef, useEffect } from 'react';
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
  Animated,
  PanResponder,
  TouchableWithoutFeedback,
  Keyboard,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, typography, radius, spacing } from '../theme/theme';
import { redeemPromoCode, PromoRedemptionResult } from '../lib/purchases';

export interface PromoCodeModalProps {
  visible: boolean;
  onClose: () => void;
  onSuccess?: (code: string) => void;
}

export function PromoCodeModal({ visible, onClose, onSuccess }: PromoCodeModalProps) {
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PromoRedemptionResult | null>(null);

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
        if (gestureState.dy > 90 || gestureState.vy > 0.5) {
          Animated.timing(panY, {
            toValue: 600,
            duration: 220,
            useNativeDriver: true,
          }).start(() => {
            handleClose();
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

  useEffect(() => {
    if (visible) {
      panY.setValue(0);
      setCode('');
      setResult(null);
      setLoading(false);
    }
  }, [visible]);

  const handleClose = () => {
    Keyboard.dismiss();
    panY.setValue(0);
    onClose();
  };

  const handleRedeem = async () => {
    const trimmed = code.trim().toUpperCase();
    if (!trimmed) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      setResult({
        success: false,
        message: 'Please enter a promo code.',
      });
      return;
    }

    setLoading(true);
    setResult(null);
    Keyboard.dismiss();

    try {
      const res = await redeemPromoCode(trimmed);
      setResult(res);

      if (res.success) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        if (onSuccess) {
          onSuccess(trimmed);
        }
        // Auto-close modal after brief success presentation
        setTimeout(() => {
          handleClose();
        }, 1400);
      } else {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      }
    } catch (err: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setResult({
        success: false,
        message: err?.message || 'Failed to validate code.',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={handleClose}
    >
      <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
        <View style={styles.overlay}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.keyboardAvoid}
          >
            <Animated.View
              style={[
                styles.modalCard,
                { transform: [{ translateY: panY }] },
              ]}
            >
              {/* Drag Handle */}
              <View {...panResponder.panHandlers} style={styles.dragHandleContainer}>
                <View style={styles.dragHandle} />
              </View>

              {/* Header */}
              <View style={styles.header}>
                <View style={styles.headerTitleRow}>
                  <View style={styles.iconCircle}>
                    <Ionicons name="ticket-outline" size={20} color={colors.accent} />
                  </View>
                  <Text style={styles.headerTitle}>Redeem Promo Code</Text>
                </View>
                <TouchableOpacity
                  onPress={handleClose}
                  style={styles.closeBtn}
                  hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                >
                  <Ionicons name="close" size={20} color={colors.textSecondary} />
                </TouchableOpacity>
              </View>

              <Text style={styles.description}>
                Enter your Shipathon pass or promotional voucher code to unlock full PC Controls without a subscription.
              </Text>

              {/* Code Input */}
              <View style={styles.inputContainer}>
                <Ionicons name="key-outline" size={18} color={colors.textMuted} style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  placeholder="e.g. SHIPATHON, BLINKYVIP"
                  placeholderTextColor={colors.textMuted}
                  value={code}
                  onChangeText={(val) => {
                    setCode(val.toUpperCase());
                    if (result) setResult(null);
                  }}
                  autoCapitalize="characters"
                  autoCorrect={false}
                  returnKeyType="done"
                  onSubmitEditing={handleRedeem}
                  editable={!loading && !(result?.success)}
                />
                {code.length > 0 && !loading && !(result?.success) && (
                  <TouchableOpacity
                    onPress={() => {
                      setCode('');
                      setResult(null);
                    }}
                    style={styles.clearBtn}
                  >
                    <Ionicons name="close-circle" size={18} color={colors.textMuted} />
                  </TouchableOpacity>
                )}
              </View>

              {/* Result banner */}
              {result && (
                <View
                  style={[
                    styles.resultBanner,
                    result.success ? styles.resultSuccess : styles.resultError,
                  ]}
                >
                  <Ionicons
                    name={result.success ? 'checkmark-circle' : 'alert-circle'}
                    size={18}
                    color={result.success ? colors.success : colors.danger}
                  />
                  <Text
                    style={[
                      styles.resultText,
                      result.success ? styles.resultTextSuccess : styles.resultTextError,
                    ]}
                  >
                    {result.message}
                  </Text>
                </View>
              )}

              {/* Action Buttons */}
              <View style={styles.actionRow}>
                <TouchableOpacity
                  style={[styles.btn, styles.cancelBtn]}
                  onPress={handleClose}
                  disabled={loading}
                >
                  <Text style={styles.cancelBtnText}>Cancel</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[
                    styles.btn,
                    styles.submitBtn,
                    loading && styles.btnDisabled,
                    result?.success && styles.submitBtnSuccess,
                  ]}
                  onPress={handleRedeem}
                  disabled={loading || !!result?.success}
                >
                  {loading ? (
                    <ActivityIndicator size="small" color={colors.white} />
                  ) : result?.success ? (
                    <View style={styles.btnSuccessContent}>
                      <Ionicons name="checkmark" size={18} color={colors.white} />
                      <Text style={styles.submitBtnText}>Unlocked!</Text>
                    </View>
                  ) : (
                    <Text style={styles.submitBtnText}>Redeem Code</Text>
                  )}
                </TouchableOpacity>
              </View>
            </Animated.View>
          </KeyboardAvoidingView>
        </View>
      </TouchableWithoutFeedback>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    justifyContent: 'flex-end',
  },
  keyboardAvoid: {
    width: '100%',
  },
  modalCard: {
    backgroundColor: '#0c0d12',
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingBottom: Platform.OS === 'ios' ? spacing.xxl : spacing.xl,
    paddingTop: spacing.sm,
  },
  dragHandleContainer: {
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  dragHandle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.border,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  iconCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.accentMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    ...typography.heading3,
    color: colors.textPrimary,
  },
  closeBtn: {
    padding: spacing.xs,
  },
  description: {
    ...typography.bodyMedium,
    color: colors.textSecondary,
    marginTop: spacing.xs,
    marginBottom: spacing.md,
    lineHeight: 20,
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    height: 50,
  },
  inputIcon: {
    marginRight: spacing.sm,
  },
  input: {
    flex: 1,
    color: colors.textPrimary,
    fontFamily: 'OkineSansMedium',
    fontSize: 15,
    letterSpacing: 1.2,
  },
  clearBtn: {
    padding: spacing.xs,
  },
  resultBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.sm,
    borderRadius: radius.sm,
    marginTop: spacing.md,
    borderWidth: 1,
  },
  resultSuccess: {
    backgroundColor: colors.successMuted,
    borderColor: 'rgba(16, 185, 129, 0.3)',
  },
  resultError: {
    backgroundColor: colors.dangerMuted,
    borderColor: 'rgba(239, 68, 68, 0.3)',
  },
  resultText: {
    ...typography.bodySmall,
    flex: 1,
  },
  resultTextSuccess: {
    color: colors.success,
  },
  resultTextError: {
    color: colors.danger,
  },
  actionRow: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.lg,
  },
  btn: {
    flex: 1,
    height: 48,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cancelBtn: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cancelBtnText: {
    ...typography.bodyMedium,
    color: colors.textSecondary,
    fontWeight: '600',
  },
  submitBtn: {
    backgroundColor: colors.accent,
  },
  submitBtnSuccess: {
    backgroundColor: colors.success,
  },
  btnDisabled: {
    opacity: 0.6,
  },
  submitBtnText: {
    ...typography.bodyMedium,
    color: colors.white,
    fontWeight: '700',
  },
  btnSuccessContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
});
