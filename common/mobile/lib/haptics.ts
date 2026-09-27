import { Platform } from 'react-native';
import * as Haptics from 'expo-haptics';

export const triggerHaptic = (style: 'light' | 'medium' | 'heavy' | 'selection' = 'light') => {
  try {
    if (Platform.OS === 'web') return;
    if (style === 'light') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    } else if (style === 'medium') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } else if (style === 'heavy') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
    } else if (style === 'selection') {
      Haptics.selectionAsync();
    }
  } catch (e) {}
};
