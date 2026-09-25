export const colors = {
  background: '#040405', // Deep premium near-black
  surface: 'rgba(255, 255, 255, 0.03)',
  surfaceElevated: 'rgba(255, 255, 255, 0.06)',
  surfacePressed: 'rgba(255, 255, 255, 0.1)',
  border: 'rgba(255, 255, 255, 0.12)',
  borderLight: 'rgba(255, 255, 255, 0.04)',
  textPrimary: '#F4F4F5',
  textSecondary: '#A1A1AA',
  textMuted: '#52525B',
  accent: '#FF5A36',
  accentMuted: 'rgba(255, 90, 54, 0.15)',
  success: '#10B981',
  successMuted: 'rgba(16, 185, 129, 0.15)',
  warning: '#F59E0B',
  danger: '#EF4444',
  dangerMuted: 'rgba(239, 68, 68, 0.15)',
  white: '#FFFFFF',
  black: '#000000',
  transparent: 'transparent',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  xxxl: 64,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  round: 9999,
};

export const typography = {
  heading1: { fontFamily: 'Unigeo', fontSize: 32, fontWeight: '700', letterSpacing: -0.8 },
  heading2: { fontFamily: 'Unigeo', fontSize: 24, fontWeight: '600', letterSpacing: -0.5 },
  heading3: { fontFamily: 'Unigeo', fontSize: 17, fontWeight: '600', letterSpacing: -0.3 },
  bodyLarge: { fontFamily: 'OkineSans', fontSize: 16, fontWeight: '400', letterSpacing: -0.2 },
  bodyMedium: { fontFamily: 'OkineSans', fontSize: 14, fontWeight: '400', letterSpacing: -0.1 },
  bodySmall: { fontFamily: 'OkineSansMedium', fontSize: 13, fontWeight: '500', letterSpacing: 0 },
  label: { fontFamily: 'OkineSansMedium', fontSize: 11, fontWeight: '600', letterSpacing: 0.5, textTransform: 'uppercase' },
} as const;
