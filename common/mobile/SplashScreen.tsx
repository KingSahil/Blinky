import React, { useEffect, useRef, useState } from 'react';
import {
  StyleSheet,
  Text,
  View,
  Animated,
  Dimensions,
  TouchableOpacity,
  StatusBar,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import MaskedView from '@react-native-masked-view/masked-view';
import * as Haptics from 'expo-haptics';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

interface SplashScreenProps {
  onDismiss: () => void;
}

export default function SplashScreen({ onDismiss }: SplashScreenProps) {
  // Phase 1: Loading
  const blinkAnim = useRef(new Animated.Value(1)).current;
  const logoScale = useRef(new Animated.Value(1)).current;
  const [phase, setPhase] = useState<'loading' | 'reveal' | 'idle'>('loading');

  // Phase 2: Reveal
  const overlayOpacity = useRef(new Animated.Value(1)).current; // Fades out to reveal gradient
  const cardsAnim = useRef(new Animated.Value(0)).current; // 0 to 1 for staggering
  
  // Entire screen dismiss
  const screenOpacity = useRef(new Animated.Value(1)).current;
  const screenScale = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    console.log("🔥 SPLASH SCREEN MOUNTED! 🔥");
    // 1. Start the blinking (pulsing) animation
    Animated.loop(
      Animated.sequence([
        Animated.timing(blinkAnim, {
          toValue: 0.3,
          duration: 800,
          useNativeDriver: true,
        }),
        Animated.timing(blinkAnim, {
          toValue: 1,
          duration: 800,
          useNativeDriver: true,
        }),
      ])
    ).start();

    // 2. Simulate loading time, then transition to "reveal" phase
    const timer = setTimeout(() => {
      setPhase('reveal');
      
      // Stop the blinking smoothly by animating it to 0 opacity
      Animated.timing(blinkAnim, {
        toValue: 0,
        duration: 400,
        useNativeDriver: true,
      }).start();

      // Fade out the solid white overlay to reveal the warm gradient background
      Animated.timing(overlayOpacity, {
        toValue: 0,
        duration: 800,
        useNativeDriver: true,
      }).start();

      // Spring the cards up in a staggered fashion
      Animated.spring(cardsAnim, {
        toValue: 1,
        tension: 40,
        friction: 8,
        useNativeDriver: true,
      }).start(() => setPhase('idle'));

    }, 2500);

    return () => clearTimeout(timer);
  }, []);

  const handleDismiss = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    
    // Graceful exit animation
    Animated.parallel([
      Animated.timing(screenOpacity, {
        toValue: 0,
        duration: 400,
        useNativeDriver: true,
      }),
      Animated.timing(screenScale, {
        toValue: 1.1,
        duration: 400,
        useNativeDriver: true,
      })
    ]).start(() => {
      onDismiss();
    });
  };

  // Interpolations for stagger effect
  const translateY1 = cardsAnim.interpolate({
    inputRange: [0, 0.4, 1],
    outputRange: [300, 300, 0],
    extrapolate: 'clamp',
  });
  const translateY2 = cardsAnim.interpolate({
    inputRange: [0, 0.6, 1],
    outputRange: [300, 300, 0],
    extrapolate: 'clamp',
  });
  const translateY3 = cardsAnim.interpolate({
    inputRange: [0, 0.8, 1],
    outputRange: [300, 300, 0],
    extrapolate: 'clamp',
  });
  
  const fade1 = cardsAnim.interpolate({ inputRange: [0, 0.4, 1], outputRange: [0, 0, 1] });
  const fade2 = cardsAnim.interpolate({ inputRange: [0, 0.6, 1], outputRange: [0, 0, 1] });
  const fade3 = cardsAnim.interpolate({ inputRange: [0, 0.8, 1], outputRange: [0, 0, 1] });

  return (
    <Animated.View style={[styles.container, { opacity: screenOpacity, transform: [{ scale: screenScale }] }]}>
      <StatusBar barStyle="dark-content" />

      {/* The Ambient Gradient Background */}
      <LinearGradient
        colors={['#18181B', '#09090B', '#000000']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={StyleSheet.absoluteFill}
      />

      {/* Floating Cards (Hidden during loading, slides up on reveal) */}
      <View style={styles.heroContainer}>
        {/* Card 1: Vision */}
        <Animated.View style={[styles.card, styles.cardRed, { transform: [{ translateY: translateY1 }, { rotateZ: '-8deg' }], opacity: fade1 }]}>
          <Ionicons name="eye" size={40} color="#FFF" style={styles.cardIcon} />
          <Text style={styles.cardTitle}>Computer Vision</Text>
        </Animated.View>

        {/* Card 2: Agent */}
        <Animated.View style={[styles.card, styles.cardBlue, { transform: [{ translateY: translateY2 }, { rotateZ: '4deg' }], opacity: fade2, marginLeft: 120, marginTop: -40 }]}>
          <Ionicons name="hardware-chip" size={32} color="#FFF" style={styles.cardIcon} />
          <Text style={styles.cardTitle}>Agent Actions</Text>
        </Animated.View>

        {/* Card 3: Web Search */}
        <Animated.View style={[styles.card, styles.cardGreen, { transform: [{ translateY: translateY3 }, { rotateZ: '-3deg' }], opacity: fade3, marginLeft: -40, marginTop: 20 }]}>
          <Ionicons name="search" size={28} color="#FFF" style={styles.cardIcon} />
          <Text style={styles.cardTitle}>Web Intelligence</Text>
        </Animated.View>
        
        {/* Card 4: Automate */}
        <Animated.View style={[styles.card, styles.cardPurple, { transform: [{ translateY: translateY1 }, { rotateZ: '6deg' }], opacity: fade1, marginLeft: 80, marginTop: 20 }]}>
          <Ionicons name="flash" size={36} color="#FFF" style={styles.cardIcon} />
          <Text style={styles.cardTitle}>Automate</Text>
        </Animated.View>
      </View>

      {/* Branding and Copy */}
      <Animated.View style={[styles.brandingContainer, { opacity: fade3 }]}>
        <View style={styles.logoRow}>
          <Ionicons name="sparkles" size={20} color="#71717A" style={{ marginRight: 6 }} />
          <Text style={styles.logoText}>blinky</Text>
        </View>

        <Text style={styles.headlineTitle}>Delightful</Text>
        <Text style={styles.headlineTitle}>automation</Text>
        
        <MaskedView
          style={{ height: 48 }}
          maskElement={
            <Text style={styles.headlineTitle}>starts here</Text>
          }
        >
          <LinearGradient
            colors={['#FF5A36', '#FF9800']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={{ flex: 1 }}
          >
            {/* The mask needs a child to fill it, we just render an invisible copy of the text to give it size */}
            <Text style={[styles.headlineTitle, { opacity: 0 }]}>starts here</Text>
          </LinearGradient>
        </MaskedView>
      </Animated.View>

      {/* CTA Button */}
      <Animated.View style={[styles.ctaContainer, { opacity: fade3 }]}>
        <TouchableOpacity 
          style={styles.ctaButton} 
          activeOpacity={0.8}
          onPress={handleDismiss}
        >
          <Ionicons name="arrow-forward" size={24} color="#000" />
        </TouchableOpacity>
      </Animated.View>

      {/* Initial Loading Overlay - Covers everything until phase switches to reveal */}
      <Animated.View style={[StyleSheet.absoluteFill, styles.loadingOverlay, { opacity: overlayOpacity }]} pointerEvents={phase === 'loading' ? 'auto' : 'none'}>
        <Animated.View style={{ opacity: blinkAnim }}>
          <Ionicons name="sparkles" size={80} color="#FF5A36" />
        </Animated.View>
      </Animated.View>

    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: '#09090B',
    zIndex: 9999,
    elevation: 9999,
  },
  loadingOverlay: {
    backgroundColor: '#09090B',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 10,
    elevation: 10,
  },
  heroContainer: {
    flex: 1,
    paddingTop: 80,
    paddingHorizontal: 24,
    alignItems: 'center',
    justifyContent: 'flex-start',
    zIndex: 1,
  },
  card: {
    padding: 24,
    borderRadius: 20,
    borderWidth: 1.5,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5,
    shadowRadius: 16,
    elevation: 8,
    alignItems: 'center',
    justifyContent: 'center',
    width: 160,
    height: 160,
    position: 'absolute',
  },
  cardRed: {
    backgroundColor: '#FF5A36', // Blinky Orange
    top: 60,
    left: 20,
  },
  cardBlue: {
    backgroundColor: '#3B82F6', // Blinky Blue
    top: 140,
    right: 20,
    width: 140,
    height: 140,
  },
  cardGreen: {
    backgroundColor: '#27272A', // Dark Slate
    top: 240,
    left: 30,
    width: 170,
    height: 120,
  },
  cardPurple: {
    backgroundColor: '#8B5CF6', // Blinky Purple
    top: 320,
    right: 30,
    width: 150,
    height: 150,
  },
  cardIcon: {
    marginBottom: 12,
  },
  cardTitle: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '700',
    textAlign: 'center',
    letterSpacing: 0.5,
  },
  brandingContainer: {
    position: 'absolute',
    bottom: 120,
    left: 24,
    zIndex: 2,
  },
  logoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  logoText: {
    fontFamily: 'System',
    fontSize: 22,
    fontWeight: '600',
    color: '#A1A1AA',
    letterSpacing: -0.5,
  },
  headlineTitle: {
    fontFamily: 'System',
    fontSize: 42,
    fontWeight: '800',
    color: '#FFFFFF',
    lineHeight: 48,
    letterSpacing: -1,
  },
  ctaContainer: {
    position: 'absolute',
    bottom: 40,
    alignSelf: 'center',
    zIndex: 2,
  },
  ctaButton: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 4,
  }
});
