import React, { useState, useEffect, useRef } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  TouchableWithoutFeedback,
  Keyboard,
  StatusBar,
  ScrollView,
  Image,
  Dimensions,
  Modal,
  LogBox,
  Animated,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { File, UploadType } from 'expo-file-system';
import Constants from 'expo-constants';
import * as Network from 'expo-network';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import {
  PinchGestureHandler,
  PinchGestureHandlerStateChangeEvent,
  PanGestureHandler,
  PanGestureHandlerStateChangeEvent,
  TapGestureHandler,
  TapGestureHandlerStateChangeEvent,
  State,
  GestureHandlerRootView,
} from 'react-native-gesture-handler';
import {
  AudioModule,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
} from 'expo-audio';
import { usePCWebSocket, ConnectionStatus } from './usePCWebSocket';
import { sendWakeOnLan, MAC_STORAGE_KEY, WOL_BROADCAST_STORAGE_KEY } from './lib/wol';
import { triggerHaptic } from './lib/haptics';
import { MarkdownRenderer } from './MarkdownRenderer';
import SplashScreen from './SplashScreen';
import { BrandHeader } from './components/BrandHeader';
import { MessageBubble } from './components/MessageBubble';
import { ChatHome } from './components/ChatHome';
import { CommandComposer } from './components/CommandComposer';
import { SlashCommandMenu, SlashCommandDef } from './components/SlashCommandMenu';
import { ActionsScreen } from './components/ActionsScreen';
import { SystemScreen } from './components/SystemScreen';
import { SettingsModal } from './components/SettingsModal';
import { FilesScreen } from './components/FilesScreen';
import { BottomNavigation } from './components/BottomNavigation';
import { SessionHistoryModal } from './components/SessionHistoryModal';
import {
  listSessions,
  getActiveSession,
  saveSession,
  createNewSession,
  deleteSession,
  clearAllSessions,
  generateSessionTitle,
  BlinkyChatSession,
} from './lib/session_manager';
import {
  listMobileNotebooks,
  buildMobileOkfContext,
  createMobileNotebook,
} from './lib/mobile_rag_db';
import { getSyncedApiKeys } from './lib/secure_keys';
import { PromoCodeModal } from './components/PromoCodeModal';
import {
  initializePurchases,
  hasPcAccess,
  addPcAccessListener,
  presentPcPaywall,
  restorePurchases,
} from './lib/purchases';
import { FileTransferPanel, FileTransferPanelRef, SelectedFile } from './FileTransferPanel';
import type { AttachmentRoute } from './lib/attachmentRouting';
import { TabScreen, AttachedFile } from './types';
import { colors } from './theme/theme';
import { useFonts } from 'expo-font';
export { triggerHaptic };

const STORAGE_KEY = '@blinky_pc_ip';
const TOKEN_STORAGE_KEY = '@blinky_pc_token';
const CERTIFICATE_PIN_STORAGE_KEY = '@blinky_pc_certificate_pin';
const WORKSTATION_PIN_STORAGE_KEY = '@blinky_workstation_pin';
const isProduction = typeof __DEV__ !== 'undefined' ? !__DEV__ : process.env.NODE_ENV === 'production';
const RELEASE_TRANSPORT = isProduction || process.env.EXPO_PUBLIC_BLINKY_TRANSPORT_MODE === 'release';

type NativeSecureSocketModule = typeof import('./modules/blinky-secure-socket');

const loadNativeSecureSocketModule = (): NativeSecureSocketModule | null => {
  try {
    return require('./modules/blinky-secure-socket') as NativeSecureSocketModule;
  } catch {
    return null;
  }
};

const readSavedCredential = async (secureKey: string, legacyKey: string): Promise<string | null> => {
  if (RELEASE_TRANSPORT) {
    const mod = loadNativeSecureSocketModule();
    if (mod && 'isNative' in mod && !(mod as any).isNative) return null;
    return mod?.getSecureValue(secureKey) || null;
  }
  return AsyncStorage.getItem(legacyKey);
};

const saveCredential = async (secureKey: string, legacyKey: string, value: string): Promise<void> => {
  if (RELEASE_TRANSPORT) {
    const nativeModule = loadNativeSecureSocketModule();
    if (!nativeModule || ('isNative' in nativeModule && !(nativeModule as any).isNative)) {
      throw new Error('Secure credential storage is unavailable in this build.');
    }
    await nativeModule.setSecureValue(secureKey, value);
    return;
  }
  await AsyncStorage.setItem(legacyKey, value);
};

const deleteSavedCredential = async (secureKey: string, legacyKey: string): Promise<void> => {
  if (RELEASE_TRANSPORT) {
    const mod = loadNativeSecureSocketModule();
    if (mod && 'isNative' in mod && !(mod as any).isNative) return;
    await mod?.deleteSecureValue(secureKey);
    return;
  }
  await AsyncStorage.removeItem(legacyKey);
};

let VolumeManager: any = null;
try {
  VolumeManager = require('react-native-volume-manager').VolumeManager;
} catch (e) {
  // VolumeManager is optional
}

const getExpoHostIp = (): string | null => {
  const hostUri =
    Constants.expoConfig?.hostUri ||
    Constants.expoGoConfig?.debuggerHost ||
    Constants.manifest?.debuggerHost;

  if (!hostUri) {
    return null;
  }

  const host = hostUri.split('/')[0]?.split(':')[0]?.trim();
  return host || null;
};

interface DiscoveryResponse {
  token: string;
  certificate_pin?: string;
  mode: string;
  websocket_port: number;
}

const DISCOVERY_PORT = 9004;

const fetchDiscoveryInfo = async (ip: string, port = 9001): Promise<DiscoveryResponse | null> => {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2000);
    // Try discovery port first
    const res = await fetch(`http://${ip}:${DISCOVERY_PORT}/discover`, {
      signal: controller.signal,
      headers: { 'Accept': 'application/json' },
    });
    clearTimeout(timeout);
    if (res.ok) {
      return await res.json();
    }
  } catch {}
  // Fallback to WebSocket port
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2000);
    const res = await fetch(`http://${ip}:${port}/discover`, {
      signal: controller.signal,
      headers: { 'Accept': 'application/json' },
    });
    clearTimeout(timeout);
    if (res.ok) {
      return await res.json();
    }
  } catch {}
  return null;
};

const checkIpAddress = (rawIp: string, port = 9001, timeoutMs = 3000, certificatePin?: string): Promise<string> => {
  const clean = rawIp.trim().replace(/^https?:\/\//i, '').replace(/^wss?:\/\//i, '').replace(/\/+$/, '');
  const [ipOnly, customPort] = clean.includes(':') ? clean.split(':') : [clean, undefined];
  const targetPort = customPort ? parseInt(customPort, 10) : port;
  const ip = ipOnly;

  if (RELEASE_TRANSPORT) {
    const nativeModule = loadNativeSecureSocketModule();
    const pin = certificatePin?.trim();
    if (!nativeModule || ('isNative' in nativeModule && !(nativeModule as any).isNative) || !pin) {
      return Promise.reject(new Error('Release discovery requires the secure socket module and certificate pin.'));
    }
    const socketId = `discovery-${ip}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return new Promise((resolve, reject) => {
      let finished = false;
      const subscriptions = [
        nativeModule.addListener('onOpen', (event) => {
          if (event.id !== socketId) return;
          finish();
          resolve(clean);
        }),
        nativeModule.addListener('onError', (event) => {
          if (event.id !== socketId) return;
          finish();
          reject(new Error(event.error || 'Connection error'));
        }),
        nativeModule.addListener('onClose', (event) => {
          if (event.id !== socketId || finished) return;
          finish();
          reject(new Error('Closed'));
        }),
      ];
      const timer = setTimeout(() => {
        finish();
        reject(new Error('Timeout'));
      }, timeoutMs);
      const finish = () => {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        subscriptions.forEach((subscription) => subscription.remove());
        void nativeModule.close(socketId).catch(() => undefined);
      };
      void nativeModule.connect(socketId, `wss://${ip}:${targetPort}`, pin).catch((error: any) => {
        finish();
        reject(error);
      });
    });
  }

  // Development mode: first try HTTP discovery to get token, then use it for WS auth
  return new Promise(async (resolve, reject) => {
    let ws: WebSocket | null = null;
    let isDone = false;
    let discoveredToken: string | null = null;

    const cleanup = () => {
      if (isDone) return;
      isDone = true;
      if (timer) clearTimeout(timer);
      if (ws) {
        try {
          ws.onopen = null;
          ws.onerror = null;
          ws.onclose = null;
          ws.close();
        } catch (e) {}
        ws = null;
      }
    };

    const timer = setTimeout(() => {
      cleanup();
      reject(new Error('Timeout'));
    }, timeoutMs);

    try {
      // Try to fetch token from discovery endpoint first
      const discovery = await fetchDiscoveryInfo(ip, targetPort);
      if (discovery?.token) {
        discoveredToken = discovery.token;
        if (discovery.certificate_pin && !certificatePin) {
          certificatePin = discovery.certificate_pin;
        }
      }

      ws = new WebSocket(`ws://${ip}:${targetPort}`);
      
      ws.onopen = () => {
        cleanup();
        // Send auth token if we have one
        if (discoveredToken) {
          ws?.send(`auth:${discoveredToken}`);
        }
        resolve(clean);
      };
      
      ws.onerror = () => {
        cleanup();
        reject(new Error('Connection error'));
      };
      
      ws.onclose = () => {
        cleanup();
        reject(new Error('Closed'));
      };
    } catch (e) {
      cleanup();
      reject(e);
    }
  });
};

const scanSubnet = async (
  subnet: string,
  onProgress?: (msg: string) => void,
  certificatePin?: string,
): Promise<string | null> => {
  const port = 9001;
  const timeoutMs = 1200;
  const concurrency = 15;
  
  // Prioritize common host IP suffixes first for faster discovery
  const prioritySuffixes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 20, 50, 100, 101, 102, 105, 110, 150, 200, 254];
  const remainingSuffixes: number[] = [];
  for (let i = 1; i <= 254; i++) {
    if (!prioritySuffixes.includes(i)) {
      remainingSuffixes.push(i);
    }
  }
  const orderedSuffixes = [...prioritySuffixes, ...remainingSuffixes];
  const ips = orderedSuffixes.map(i => `${subnet}.${i}`);

  for (let i = 0; i < ips.length; i += concurrency) {
    const batch = ips.slice(i, i + concurrency);
    if (onProgress) {
      onProgress(`Scanning Wi-Fi subnet ${subnet}.x (${i + 1}/${ips.length})...`);
    }
    
    const promises = batch.map(ip => 
      checkIpAddress(ip, port, timeoutMs, certificatePin)
        .then(foundIp => foundIp)
        .catch(() => null)
    );
    
    const results = await Promise.all(promises);
    const found = results.find(res => res !== null);
    if (found) {
      return found;
    }
  }
  
  return null;
};

const TAILSCALE_DEFAULT_IP = '100.122.62.2';

/**
 * Concurrently probes known fast candidate endpoints (Tailscale, saved IP, Expo host, USB reverse localhost).
 */
const probeCandidateIps = async (certificatePin?: string): Promise<string | null> => {
  const candidates: string[] = [];

  // Deterministic LAN address published by `bun run dev` into
  // common/mobile/.env (EXPO_PUBLIC_PC_IP). Highest priority: it survives
  // manually-started Metro (`bunx expo start`) where the Expo host IP may
  // point at a tunnel/virtual adapter instead of the real LAN PC.
  const envPcIp = process.env.EXPO_PUBLIC_PC_IP?.trim();
  if (envPcIp && !candidates.includes(envPcIp)) candidates.push(envPcIp);
  const envTailscale = process.env.EXPO_PUBLIC_TAILSCALE_IP?.trim();
  if (envTailscale && !candidates.includes(envTailscale)) candidates.push(envTailscale);
  if (!candidates.includes(TAILSCALE_DEFAULT_IP)) candidates.push(TAILSCALE_DEFAULT_IP);

  try {
    const saved = await AsyncStorage.getItem(STORAGE_KEY);
    if (saved && !candidates.includes(saved)) candidates.push(saved);
  } catch {}

  const expoHost = getExpoHostIp();
  if (expoHost && !candidates.includes(expoHost)) candidates.push(expoHost);

  if (!candidates.includes('127.0.0.1')) candidates.push('127.0.0.1');

  const probePromises = candidates.map((ip) =>
    checkIpAddress(ip, 9001, 3000, certificatePin)
      .then((found) => found)
      .catch(() => null)
  );

  const results = await Promise.all(probePromises);
  return results.find((r): r is string => Boolean(r)) || null;
};

interface Message {
  id: string;
  sender: 'user' | 'blinky';
  text: string;
  timestamp: string;
  progress?: {
    percent: number;
    statusText: string;
    duration: number;
  };
  screenshot_b64?: string;
  attachedFile?: AttachedFile;
  steps?: any[];
}

interface PinchableImageViewerProps {
  uri: string;
  onClose: () => void;
}

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

const PinchableImageViewer: React.FC<PinchableImageViewerProps> = ({ uri, onClose }) => {
  const panRef = useRef(null);
  const pinchRef = useRef(null);
  const doubleTapRef = useRef(null);

  const scale = useRef(new Animated.Value(1)).current;
  const translateX = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(0)).current;

  // Track absolute state values
  const scaleVal = useRef(1);
  const txVal = useRef(0);
  const tyVal = useRef(0);

  useEffect(() => {
    const idS = scale.addListener(({ value }) => { scaleVal.current = value; });
    const idX = translateX.addListener(({ value }) => { txVal.current = value; });
    const idY = translateY.addListener(({ value }) => { tyVal.current = value; });
    return () => {
      scale.removeListener(idS);
      translateX.removeListener(idX);
      translateY.removeListener(idY);
    };
  }, []);

  const getBounds = (currScale: number) => {
    const maxTx = Math.max(0, ((SCREEN_WIDTH * currScale) - SCREEN_WIDTH) / 2);
    const maxTy = Math.max(0, ((SCREEN_HEIGHT * currScale) - SCREEN_HEIGHT) / 2);
    return { maxTx, maxTy };
  };

  // Double Tap Handler: Toggle between 1x and 2.5x
  const onDoubleTap = (event: TapGestureHandlerStateChangeEvent) => {
    if (event.nativeEvent.state === State.ACTIVE) {
      if (scaleVal.current > 1.1) {
        triggerHaptic('light');
        Animated.parallel([
          Animated.spring(scale, { toValue: 1, useNativeDriver: true, bounciness: 3 }),
          Animated.spring(translateX, { toValue: 0, useNativeDriver: true, bounciness: 3 }),
          Animated.spring(translateY, { toValue: 0, useNativeDriver: true, bounciness: 3 }),
        ]).start();
      } else {
        triggerHaptic('medium');
        const targetScale = 2.5;
        const focalX = event.nativeEvent.x - SCREEN_WIDTH / 2;
        const focalY = event.nativeEvent.y - SCREEN_HEIGHT / 2;
        const { maxTx, maxTy } = getBounds(targetScale);
        const targetTx = Math.min(maxTx, Math.max(-maxTx, -focalX * (targetScale - 1)));
        const targetTy = Math.min(maxTy, Math.max(-maxTy, -focalY * (targetScale - 1)));

        Animated.parallel([
          Animated.spring(scale, { toValue: targetScale, useNativeDriver: true, bounciness: 3 }),
          Animated.spring(translateX, { toValue: targetTx, useNativeDriver: true, bounciness: 3 }),
          Animated.spring(translateY, { toValue: targetTy, useNativeDriver: true, bounciness: 3 }),
        ]).start();
      }
    }
  };

  // Pinch Tracking
  const pinchStartScale = useRef(1);
  const onPinchGestureEvent = (event: any) => {
    const newScale = Math.min(6, Math.max(0.6, pinchStartScale.current * event.nativeEvent.scale));
    scale.setValue(newScale);
  };

  const onPinchHandlerStateChange = (event: PinchGestureHandlerStateChangeEvent) => {
    if (event.nativeEvent.state === State.BEGAN) {
      pinchStartScale.current = scaleVal.current;
      triggerHaptic('selection');
    } else if (event.nativeEvent.state === State.END || event.nativeEvent.state === State.CANCELLED) {
      if (scaleVal.current < 1.05) {
        triggerHaptic('medium');
        Animated.parallel([
          Animated.spring(scale, { toValue: 1, useNativeDriver: true, bounciness: 3 }),
          Animated.spring(translateX, { toValue: 0, useNativeDriver: true, bounciness: 3 }),
          Animated.spring(translateY, { toValue: 0, useNativeDriver: true, bounciness: 3 }),
        ]).start();
      } else {
        const clampedScale = Math.min(5, Math.max(1, scaleVal.current));
        const { maxTx, maxTy } = getBounds(clampedScale);
        const clampedTx = Math.min(maxTx, Math.max(-maxTx, txVal.current));
        const clampedTy = Math.min(maxTy, Math.max(-maxTy, tyVal.current));
        triggerHaptic('light');

        Animated.parallel([
          Animated.spring(scale, { toValue: clampedScale, useNativeDriver: true, bounciness: 3 }),
          Animated.spring(translateX, { toValue: clampedTx, useNativeDriver: true, bounciness: 3 }),
          Animated.spring(translateY, { toValue: clampedTy, useNativeDriver: true, bounciness: 3 }),
        ]).start();
      }
    }
  };

  // Pan Tracking
  const panStartOffset = useRef({ x: 0, y: 0 });
  const onPanGestureEvent = (event: any) => {
    if (scaleVal.current <= 1.05) return;
    const { maxTx, maxTy } = getBounds(scaleVal.current);
    const rawX = panStartOffset.current.x + event.nativeEvent.translationX;
    const rawY = panStartOffset.current.y + event.nativeEvent.translationY;
    const boundedX = rawX > maxTx ? maxTx + (rawX - maxTx) * 0.3 : (rawX < -maxTx ? -maxTx + (rawX + maxTx) * 0.3 : rawX);
    const boundedY = rawY > maxTy ? maxTy + (rawY - maxTy) * 0.3 : (rawY < -maxTy ? -maxTy + (rawY + maxTy) * 0.3 : rawY);
    translateX.setValue(boundedX);
    translateY.setValue(boundedY);
  };

  const onPanHandlerStateChange = (event: PanGestureHandlerStateChangeEvent) => {
    if (event.nativeEvent.state === State.BEGAN) {
      panStartOffset.current = { x: txVal.current, y: tyVal.current };
    } else if (event.nativeEvent.state === State.END || event.nativeEvent.state === State.CANCELLED) {
      if (scaleVal.current <= 1.05) {
        Animated.parallel([
          Animated.spring(translateX, { toValue: 0, useNativeDriver: true }),
          Animated.spring(translateY, { toValue: 0, useNativeDriver: true }),
        ]).start();
      } else {
        const { maxTx, maxTy } = getBounds(scaleVal.current);
        const targetX = Math.min(maxTx, Math.max(-maxTx, txVal.current));
        const targetY = Math.min(maxTy, Math.max(-maxTy, tyVal.current));
        Animated.parallel([
          Animated.spring(translateX, { toValue: targetX, useNativeDriver: true, bounciness: 3 }),
          Animated.spring(translateY, { toValue: targetY, useNativeDriver: true, bounciness: 3 }),
        ]).start();
      }
    }
  };

  const resetZoom = () => {
    triggerHaptic('light');
    Animated.parallel([
      Animated.spring(scale, { toValue: 1, useNativeDriver: true, bounciness: 3 }),
      Animated.spring(translateX, { toValue: 0, useNativeDriver: true, bounciness: 3 }),
      Animated.spring(translateY, { toValue: 0, useNativeDriver: true, bounciness: 3 }),
    ]).start();
  };

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <View style={styles.fullscreenModalContainer}>
        <TouchableOpacity
          style={styles.fullscreenCloseBtn}
          onPress={() => {
            triggerHaptic('light');
            onClose();
          }}
          activeOpacity={0.8}
        >
          <Ionicons name="close" size={26} color="#FFFFFF" />
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.fullscreenResetBtn}
          onPress={resetZoom}
          activeOpacity={0.8}
        >
          <Ionicons name="refresh-outline" size={16} color="#FFFFFF" style={{ marginRight: 4 }} />
          <Text style={styles.fullscreenResetText}>Reset</Text>
        </TouchableOpacity>

        <TapGestureHandler
          ref={doubleTapRef}
          onHandlerStateChange={onDoubleTap}
          numberOfTaps={2}
        >
          <View style={styles.fullscreenImageWrapper}>
            <PanGestureHandler
              ref={panRef}
              simultaneousHandlers={[pinchRef, doubleTapRef]}
              onGestureEvent={onPanGestureEvent}
              onHandlerStateChange={onPanHandlerStateChange}
              minPointers={1}
              maxPointers={1}
              avgTouches={false}
            >
              <View style={styles.fullscreenImageWrapper}>
                <PinchGestureHandler
                  ref={pinchRef}
                  simultaneousHandlers={[panRef, doubleTapRef]}
                  onGestureEvent={onPinchGestureEvent}
                  onHandlerStateChange={onPinchHandlerStateChange}
                >
                  <Animated.View style={styles.fullscreenImageWrapper} collapsable={false}>
                    <Animated.Image
                      source={{ uri }}
                      style={[
                        styles.fullscreenImage,
                        {
                          transform: [
                            { translateX },
                            { translateY },
                            { scale },
                          ],
                        },
                      ]}
                      resizeMode="contain"
                    />
                  </Animated.View>
                </PinchGestureHandler>
              </View>
            </PanGestureHandler>
          </View>
        </TapGestureHandler>
      </View>
    </GestureHandlerRootView>
  );
};

interface SlashCommand {
  id: string;
  prefix: string;
  title: string;
  badge: string;
  description: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
}

const SLASH_COMMANDS: SlashCommandDef[] = [
  {
    id: 'antigravity',
    prefix: '/agy ',
    title: '/antigravity',
    badge: '/agy',
    description: 'Dispatch prompt directly to Antigravity IDE on PC',
    icon: 'flash',
    color: '#3B82F6',
  },
  {
    id: 'agent',
    prefix: '/agent ',
    title: '/agent',
    badge: 'AUTONOMOUS',
    description: 'Execute PC desktop agent with computer use',
    icon: 'hardware-chip',
    color: '#8B5CF6',
  },
  {
    id: 'ask',
    prefix: '/ask ',
    title: '/ask',
    badge: 'COMPANION',
    description: 'Ask Blinky companion a question or query',
    icon: 'sparkles',
    color: '#FF5A36',
  },
];

/** Renders the Blinky mobile companion and coordinates its desktop connection. */
export default function App() {
  const [fontsLoaded] = useFonts({
    'Unigeo': require('./assets/fonts/unigeo.ttf'),
    'TypoFormal': require('./assets/fonts/typo-formal.otf'),
    'OkineSans': require('./assets/fonts/okine-regular.otf'),
    'OkineSansMedium': require('./assets/fonts/okine-medium.otf'),
  });

  const [showSplash, setShowSplash] = useState(true);
  const [ipAddress, setIpAddress] = useState('');
  const [remoteToken, setRemoteToken] = useState('');
  const [certificatePin, setCertificatePin] = useState('');
  const {
    status,
    errorMsg,
    latestResponse,
    systemInfo,
    latestPowerEvent,
    latestLightEvent,
    quickAccessFolders,
    currentDirectory,
    recentFiles,
    fsSearchResults,
    fsLoading,
    fsError,
    fsFileData,
    fetchQuickAccess,
    listDirectory,
    fetchRecentFiles,
    searchFiles,
    openFileOnPC,
    readFileForMobile,
    clearFsFileData,
    resetDirectory,
    antigravityApproval,
    antigravityComplete,
    antigravityProgress,
    fileTransferMessage,
    connect,
    disconnect,
    sendCommand,
    sendQuery,
    fetchSystemInfo,
    sendAntigravityDecision,
    sendAntigravityPrompt,
    dismissAntigravityComplete,
    sendFileTransferMessage,
    getFileTransferModule,
    planAttachments,
    cancelAttachmentPlanning,
  } = usePCWebSocket();
  const [macAddress, setMacAddress] = useState('');
  const [wolBroadcastIp, setWolBroadcastIp] = useState('255.255.255.255');
  const [isSendingWol, setIsSendingWol] = useState(false);
  const [wolFeedback, setWolFeedback] = useState<string | null>(null);
  const [isWorkstationLocked, setIsWorkstationLocked] = useState(false);
  const [workstationPin, setWorkstationPin] = useState('damnthatsalongpassword');
  const [showPinPromptModal, setShowPinPromptModal] = useState(false);
  const [inputPin, setInputPin] = useState('');
  const [rememberPin, setRememberPin] = useState(true);
  const [pendingUnlockAfterWake, setPendingUnlockAfterWake] = useState(false);
  const isConnected = status === 'connected';
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [isLightOn, setIsLightOn] = useState<boolean>(false);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryProgress, setDiscoveryProgress] = useState<string | null>(null);
  const fileTransferPanelRef = useRef<FileTransferPanelRef>(null);
  const attachmentPlanningAttempt = useRef(0);
  const attachmentPreparationAttempt = useRef<number | null>(null);
  // Tracks the chat message ID showing live transfer status
  const transferStatusMsgIdRef = useRef<string | null>(null);

  const [queryText, setQueryText] = useState('');
  const [runningQuery, setRunningQuery] = useState('');
  const [agentStatus, setAgentStatus] = useState<'idle' | 'processing' | 'success' | 'error'>('idle');
  
  // Custom message history state
  const [activeTab, setActiveTab] = useState<TabScreen>('Chat');
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'blinky',
      text: 'Hello! I am Blinky. Ask me to do anything on your PC.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }
  ]);
  
  const activeBlinkyMsgIdRef = useRef<string | null>(null);
  const activeAntigravityMsgIdRef = useRef<string | null>(null);
  const scrollViewRef = useRef<ScrollView>(null);

  const [showSettings, setShowSettings] = useState(false);
  const [timerSeconds, setTimerSeconds] = useState(0);

  // PC Controls monetization & promo code state
  const [isPcUnlocked, setIsPcUnlocked] = useState(false);
  const [showPromoModal, setShowPromoModal] = useState(false);
  const [isRestoringPurchases, setIsRestoringPurchases] = useState(false);

  // Persistent Chat Sessions state
  const [currentSession, setCurrentSession] = useState<BlinkyChatSession | null>(null);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [sessionsList, setSessionsList] = useState<BlinkyChatSession[]>([]);
  const [chatMode, setChatMode] = useState<'autopilot' | 'grounded'>('autopilot');

  useEffect(() => {
    let mounted = true;
    void getActiveSession().then((session) => {
      if (!mounted) return;
      setCurrentSession(session);
      if (session.messages && session.messages.length > 0) {
        setMessages(session.messages);
      }
      if (session.mode) {
        setChatMode(session.mode === 'grounded' ? 'grounded' : 'autopilot');
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (currentSession && messages.length > 0) {
      void saveSession({
        ...currentSession,
        mode: chatMode === 'grounded' ? 'grounded' : 'general',
        messages,
      });
    }
  }, [messages, chatMode]);

  useEffect(() => {
    let mounted = true;
    initializePurchases().finally(async () => {
      if (!mounted) return;
      const unlocked = await hasPcAccess();
      setIsPcUnlocked(unlocked);
    });

    const unsubscribe = addPcAccessListener((hasAccess) => {
      if (mounted) {
        setIsPcUnlocked(hasAccess);
      }
    });

    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []);

  const handleUnlockPcPress = async () => {
    try {
      const res = await presentPcPaywall();
      if (res.success) {
        setIsPcUnlocked(true);
      } else if (res.error) {
        // Native paywall unavailable or unconfigured, open promo modal directly
        setShowPromoModal(true);
      }
    } catch {
      setShowPromoModal(true);
    }
  };

  const handleRestorePurchasesPress = async () => {
    setIsRestoringPurchases(true);
    try {
      const res = await restorePurchases();
      if (res.hasAccess) {
        setIsPcUnlocked(true);
        Alert.alert('Purchases Restored', res.message);
      } else {
        Alert.alert('Restore Purchases', res.message);
      }
    } catch (e: any) {
      Alert.alert('Restore Error', e?.message || 'Failed to restore purchases.');
    } finally {
      setIsRestoringPurchases(false);
    }
  };

  // Sync PC files when opening Files tab
  useEffect(() => {
    if (isConnected && activeTab === 'Files') {
      fetchQuickAccess();
      fetchRecentFiles();
    }
  }, [isConnected, activeTab, fetchQuickAccess, fetchRecentFiles]);

  // Handle light status event updates from PC Desktop
  useEffect(() => {
    if (latestLightEvent?.data) {
      const data = latestLightEvent.data;
      if (data.success === false) {
        // ESP32 unreachable: revert the optimistic toggle and say why.
        // Success path (r/g/b present) still syncs the card below.
        const err = data.error || 'ESP32 unreachable. Check it shares PC Wi-Fi and ESP32_HOST in .env.';
        setIsLightOn(prev => !prev);
        triggerHaptic('heavy');
        setActionFeedback(`💡 Light failed: ${err}`);
        setTimeout(() => setActionFeedback(null), 6000);
        return;
      }
      const on = (data.r ?? 0) > 0 || (data.g ?? 0) > 0 || (data.b ?? 0) > 0;
      setIsLightOn(on);
    }
  }, [latestLightEvent]);

  // Haptic feedback for Antigravity events
  useEffect(() => {
    if (antigravityApproval) {
      triggerHaptic('heavy');
    }
  }, [antigravityApproval]);

  // Stream Antigravity progress into chat bubble
  useEffect(() => {
    if (!antigravityProgress) return;
    const detail = antigravityProgress.detail || `Executing ${antigravityProgress.tool}`;
    setMessages(prev => {
      const activeId = activeAntigravityMsgIdRef.current;
      if (!activeId) return prev;
      return prev.map(m => {
        if (m.id === activeId) {
          return {
            ...m,
            progress: {
              percent: Math.min((m.progress?.percent || 15) + 12, 92),
              statusText: detail,
              duration: (m.progress?.duration || 0) + 1,
            }
          };
        }
        return m;
      });
    });
  }, [antigravityProgress]);

  // Display completed output in chat bubble
  useEffect(() => {
    if (!antigravityComplete) return;
    triggerHaptic('medium');
    const activeId = activeAntigravityMsgIdRef.current;
    const outputText = antigravityComplete.output?.trim() || `Antigravity session complete (${antigravityComplete.reason}).`;

    setMessages(prev => {
      if (activeId && prev.some(m => m.id === activeId)) {
        return prev.map(m => {
          if (m.id === activeId) {
            return {
              ...m,
              text: outputText,
              progress: undefined,
            };
          }
          return m;
        });
      } else {
        return [
          ...prev,
          {
            id: generateUuid(),
            sender: 'blinky',
            text: `⚡ Antigravity Session Output:\n\n${outputText}`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          }
        ];
      }
    });
    activeAntigravityMsgIdRef.current = null;
    setAgentStatus('idle');
  }, [antigravityComplete]);
  const [previewImageUri, setPreviewImageUri] = useState<string | null>(null);

  const handleCaptureScreenshot = () => {
    if (!isConnected) {
      Alert.alert('Error', 'Failed to capture screenshot. Check link to PC.');
      return;
    }
    const query = 'Capture screenshot of current PC screen';
    setRunningQuery(query);
    setQueryText('');
    setAgentStatus('processing');
    setTimerSeconds(0);

    const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsgId = generateUuid();
    const blinkyMsgId = generateUuid();

    activeBlinkyMsgIdRef.current = blinkyMsgId;

    setMessages(prev => [
      ...prev,
      {
        id: userMsgId,
        sender: 'user',
        text: 'Capture screenshot of current PC screen',
        timestamp: currentTime,
      },
      {
        id: blinkyMsgId,
        sender: 'blinky',
        text: "I'm on it. Capturing PC screen...",
        timestamp: currentTime,
        progress: {
          percent: 0,
          statusText: 'Taking PC screenshot...',
          duration: 0,
        }
      }
    ]);

    sendQuery(query, generateUuid());
  };

  // Voice command states
  const [sarvamApiKey, setSarvamApiKey] = useState<string | null>(null);
  const [assemblyaiApiKey, setAssemblyaiApiKey] = useState<string | null>(null);
  const [voiceProvider, setVoiceProvider] = useState<'assemblyai' | 'sarvam'>('assemblyai');
  const audioRecorderRef = useRef<any>(null);
  const [isVoiceRecording, setIsVoiceRecording] = useState(false);
  const [isVoiceTranscribing, setIsVoiceTranscribing] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState<string | null>(null);

  // Cleanup audio recorder on unmount
  useEffect(() => {
    return () => {
      if (audioRecorderRef.current) {
        try {
          void audioRecorderRef.current.stop().finally(() => audioRecorderRef.current?.release());
        } catch (_) {}
      }
    };
  }, []);

  // Request AssemblyAI & Sarvam keys and voice provider from PC when connected
  useEffect(() => {
    if (isConnected) {
      console.log('Connected to PC, requesting voice configuration...');
      sendCommand('get_assemblyai_key' as any);
      sendCommand('get_sarvam_key' as any);
      sendCommand('get_voice_provider' as any);
    } else {
      console.log('Disconnected from PC, clearing voice configuration');
      setAssemblyaiApiKey(null);
      setSarvamApiKey(null);
      setVoiceProvider('assemblyai');
    }
  }, [isConnected, sendCommand]);

  // Live Timer logic
  useEffect(() => {
    let interval: any = null;
    if (agentStatus === 'processing') {
      interval = setInterval(() => {
        setTimerSeconds(prev => {
          const next = prev + 1;
          // Live update timer duration & smooth real progress percentage on the active message
          if (activeBlinkyMsgIdRef.current) {
            setMessages(currentMessages =>
              currentMessages.map(m => {
                if (m.id === activeBlinkyMsgIdRef.current) {
                  const currentPercent = m.progress?.percent || 15;
                  const crawlPercent = currentPercent < 94 ? Math.min(94, currentPercent + 1) : currentPercent;
                  return {
                    ...m,
                    progress: {
                      ...m.progress!,
                      percent: crawlPercent,
                      duration: next,
                    }
                  };
                }
                return m;
              })
            );
          }
          return next;
        });
      }, 1000);
    } else if (agentStatus === 'idle') {
      setTimerSeconds(0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [agentStatus]);

  // Auto scroll to bottom when messages change
  useEffect(() => {
    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);
  }, [messages]);

  // Watch for incoming WebSocket responses from Python daemon
  useEffect(() => {
    if (latestResponse) {
      if (latestResponse.type === 'assemblyai_key') {
        const key = latestResponse.key;
        console.log('Received AssemblyAI key from PC:', key ? 'present' : 'missing');
        setAssemblyaiApiKey(key);
        return;
      }

      if (latestResponse.type === 'sarvam_key') {
        const key = latestResponse.key;
        console.log('Received Sarvam key from PC:', key ? 'present' : 'missing');
        setSarvamApiKey(key);
        return;
      }

      if (latestResponse.type === 'voice_provider') {
        const provider = latestResponse.provider || 'assemblyai';
        console.log('Received voice provider from PC:', provider);
        if (provider === 'sarvam' || provider === 'assemblyai') {
          setVoiceProvider(provider);
        } else {
          console.warn('Invalid voice provider received, defaulting to assemblyai:', provider);
          setVoiceProvider('assemblyai');
        }
        return;
      }

      const { status: respStatus, data, error } = latestResponse;
      const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const currentActiveId = activeBlinkyMsgIdRef.current;

      if (respStatus === 'processing') {
        setAgentStatus('processing');
        
        // Update active blinky message
        if (currentActiveId) {
          setMessages(prev => prev.map(m => {
            if (m.id === currentActiveId) {
              const prevMsg = m.progress?.statusText || '';
              const newMsg = data?.is_chunk ? (prevMsg + (data?.message || '')) : (data?.message || 'Processing...');
              
              let dynamicPercent = 15;
              if (data?.percent !== undefined) {
                dynamicPercent = data.percent;
              } else if (data?.confidence !== undefined && data.confidence > 0) {
                dynamicPercent = data.confidence;
              } else {
                const currentPercent = m.progress?.percent || 15;
                const lowerMsg = newMsg.toLowerCase();
                if (lowerMsg.includes('analyzing') || lowerMsg.includes('speech')) {
                  dynamicPercent = 15;
                } else if (lowerMsg.includes('screenshot') || lowerMsg.includes('capturing')) {
                  dynamicPercent = 50;
                } else if (lowerMsg.includes('opening') || lowerMsg.includes('triggering')) {
                  dynamicPercent = 60;
                } else if (lowerMsg.includes('testing playwright')) {
                  dynamicPercent = 55;
                } else {
                  dynamicPercent = Math.min(94, Math.max(currentPercent, Math.floor(15 + (timerSeconds * 8))));
                }
              }

              return {
                ...m,
                text: "I'm on it. Locating the request...",
                progress: {
                  percent: dynamicPercent,
                  statusText: newMsg,
                  duration: timerSeconds,
                }
              };
            }
            return m;
          }));
        }
      } else if (respStatus === 'success') {
        setAgentStatus('idle');
        
        // Freeze active message at 100%
        if (currentActiveId) {
          setMessages(prev => prev.map(m => {
            if (m.id === currentActiveId) {
              return {
                ...m,
                progress: {
                  percent: 100,
                  statusText: 'Action completed.',
                  duration: m.progress?.duration || timerSeconds,
                }
              };
            }
            return m;
          }));
        }
        activeBlinkyMsgIdRef.current = null;

        // Append final response bubble
        setMessages(prev => [
          ...prev,
          {
            id: generateUuid(),
            sender: 'blinky',
            text: data?.response || 'I completed the action on your screen.',
            timestamp: currentTime,
            screenshot_b64: data?.screenshot_b64,
            steps: data?.steps,
          }
        ]);
      } else if (respStatus === 'error') {
        setAgentStatus('error');
        
        // Mark active message as failed
        if (currentActiveId) {
          setMessages(prev => prev.map(m => {
            if (m.id === currentActiveId) {
              return {
                ...m,
                progress: {
                  percent: m.progress?.percent || 0,
                  statusText: error?.message || 'An error occurred during execution.',
                  duration: m.progress?.duration || timerSeconds,
                }
              };
            }
            return m;
          }));
        }
        activeBlinkyMsgIdRef.current = null;

        setMessages(prev => [
          ...prev,
          {
            id: generateUuid(),
            sender: 'blinky',
            text: error?.message || 'An unknown error occurred.',
            timestamp: currentTime,
          }
        ]);
      }
    }
  }, [latestResponse]);

  // Listen to physical volume keys when connected
  useEffect(() => {
    if (!isConnected || !VolumeManager) return;

    try {
      VolumeManager.showNativeVolumeUI({ enabled: false });

      let lastVolume: number | null = null;

      VolumeManager.getVolume().then((val: any) => {
        const vol = typeof val === 'object' ? val.volume : val;
        lastVolume = vol;
      }).catch(() => {});

      const volumeListener = VolumeManager.addVolumeListener((result: any) => {
        const currentVolume = result.volume;
        if (lastVolume !== null) {
          if (currentVolume > lastVolume) {
            sendCommand('volume_up');
          } else if (currentVolume < lastVolume) {
            sendCommand('volume_down');
          }
        }
        lastVolume = currentVolume;

        if (currentVolume >= 0.95) {
          VolumeManager.setVolume(0.9);
          lastVolume = 0.9;
        } else if (currentVolume <= 0.05) {
          VolumeManager.setVolume(0.1);
          lastVolume = 0.1;
        }
      });

      return () => {
        volumeListener.remove();
        VolumeManager.showNativeVolumeUI({ enabled: true });
      };
    } catch (err) {
      console.warn('Failed to initialize volume manager listener:', err);
    }
  }, [isConnected, sendCommand]);

  const generateUuid = () => {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  };

  /** Keep media editing separate from the destination requested in chat. */
  const extractTransferEdit = (text: string): string => {
    const match = /\b(trim|cut|merge|crop|rotate|caption|subtitle|speed up|slow down|add background music|remove audio)\b/i.exec(text);
    if (!match) return '';
    return text.slice(match.index)
      .replace(/\s+(?:and\s+)?(?:send|save|put|copy|transfer|upload)\b.*$/i, '')
      .trim();
  };

  const readUriAsBase64 = async (uri: string): Promise<string | null> => {
    try {
      // New expo-file-system File API
      const f = new File(uri);
      if (typeof (f as any).base64 === 'function') {
        return await (f as any).base64();
      }
      if (typeof (f as any).text === 'function') {
        // A question about an image must never silently become a file transfer.
        return null;
      }
      return null;
    } catch {
      return null;
    }
  };

  const handleQuery = async (attachedFiles: AttachedFile[] = []): Promise<boolean> => {
    let query = queryText.trim();
    if (!query && attachedFiles.length === 0) {
      triggerHaptic('selection');
      Alert.alert('Empty query', 'Please enter a search/browsing query or attach a file first.');
      return false;
    }

    if (currentSession && (currentSession.title === 'New Chat' || currentSession.title === 'Welcome Session' || currentSession.title === 'Current Session')) {
      const generated = generateSessionTitle(query || 'Attachment');
      setCurrentSession({ ...currentSession, title: generated });
    }

    // Grounded Knowledge mode: Query local vector store + LLM with document citations
    if (chatMode === 'grounded' && attachedFiles.length === 0) {
      const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const userMsgId = generateUuid();
      const blinkyMsgId = generateUuid();
      setMessages(prev => [
        ...prev,
        { id: userMsgId, sender: 'user' as const, text: query, timestamp: currentTime },
        {
          id: blinkyMsgId,
          sender: 'blinky' as const,
          text: '🔍 Grounding in local documents with vector search...',
          timestamp: currentTime,
          progress: { percent: 40, statusText: 'Synthesizing with verified citations...', duration: 0 },
        },
      ]);
      setQueryText('');
      setAgentStatus('processing');
      triggerHaptic('medium');

      void (async () => {
        try {
          const nbs = await listMobileNotebooks();
          let activeNb = nbs[0];
          if (!activeNb) {
            activeNb = await createMobileNotebook('My Documents');
          }
          const { systemPrompt, userPrompt, matchCount } = buildMobileOkfContext(activeNb, query, true);
          const keys = await getSyncedApiKeys();

          let answer = '';
          if (keys.groq_key) {
            const resp = await fetch('https://api.groq.com/openai/v1/chat/completions', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${keys.groq_key}`,
              },
              body: JSON.stringify({
                model: 'qwen/qwen3.8-27b',
                messages: [
                  { role: 'system', content: systemPrompt },
                  { role: 'user', content: userPrompt },
                ],
                temperature: 0.2,
              }),
            });
            const data = await resp.json().catch(() => ({}));
            answer = data?.choices?.[0]?.message?.content || 'No response generated from Groq.';
          } else if (keys.gemini_key) {
            const resp = await fetch(
              `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${encodeURIComponent(keys.gemini_key)}`,
              {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  system_instruction: { parts: [{ text: systemPrompt }] },
                  contents: [{ parts: [{ text: userPrompt }] }],
                }),
              }
            );
            const data = await resp.json().catch(() => ({}));
            answer = data?.candidates?.[0]?.content?.parts?.[0]?.text || 'No response generated from Gemini.';
          } else {
            // Forward to PC WebSocket tutor as grounded research query
            sendQuery(`[Grounded Research in "${activeNb.title}"]: ${query}`, generateUuid());
            return;
          }

          setMessages(prev => prev.map(m => m.id === blinkyMsgId ? {
            ...m,
            text: answer + (matchCount > 0 ? `\n\n*(Grounded across ${matchCount} local document sources in "${activeNb.title}")*` : ''),
            progress: undefined,
          } : m));
          setAgentStatus('success');
          triggerHaptic('medium');
        } catch (err: any) {
          setMessages(prev => prev.map(m => m.id === blinkyMsgId ? {
            ...m,
            text: `⚠️ Error during grounded retrieval: ${err?.message || 'Network error'}`,
            progress: undefined,
          } : m));
          setAgentStatus('error');
          triggerHaptic('heavy');
        }
      })();
      return true;
    }

    let attachmentRoute: AttachmentRoute | null = null;
    if (attachedFiles.length) {
      const attempt = ++attachmentPlanningAttempt.current;
      attachmentPreparationAttempt.current = attempt;
      setAgentStatus('processing');
      try {
        attachmentRoute = await planAttachments(query, attachedFiles);
        if (attempt !== attachmentPlanningAttempt.current) return false;
      } catch (error) {
        if (attempt !== attachmentPlanningAttempt.current) return false;
        Alert.alert('Attachment not sent', error instanceof Error ? error.message : 'Could not plan this attachment.');
        setAgentStatus('error');
        return false;
      } finally {
        if (attachmentPreparationAttempt.current === attempt) attachmentPreparationAttempt.current = null;
      }
      setAgentStatus('idle');
    }
    if (attachmentRoute === 'unsupported') {
      Alert.alert(
        'Attachment not sent',
        'Chat analysis currently supports one image at a time. To transfer these files instead, ask me to put them in a PC folder, or send them without a prompt for Downloads/Blinky.',
      );
      return false;
    }

    if (attachmentRoute === 'analyze-image') {
      const attempt = attachmentPlanningAttempt.current;
      attachmentPreparationAttempt.current = attempt;
      const img = attachedFiles[0];
      const explainQuery = query;
      const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const userMsgId = generateUuid();
      const blinkyMsgId = generateUuid();
      activeBlinkyMsgIdRef.current = blinkyMsgId;
      setMessages(prev => [
        ...prev,
        { id: userMsgId, sender: 'user' as const, text: explainQuery, timestamp: currentTime, attachedFiles },
        {
          id: blinkyMsgId, sender: 'blinky' as const, text: "I'm on it. Analyzing your image...",
          timestamp: currentTime,
          progress: { percent: 20, statusText: 'Analyzing image with Gemini vision...', duration: 0 },
        },
      ]);
      setAgentStatus('processing');
      setTimerSeconds(0);
      triggerHaptic('medium');
        try {
          let b64: string | null = img.base64 || null;
          if (!b64 && img.uri) b64 = await readUriAsBase64(img.uri);
          if (attempt !== attachmentPlanningAttempt.current) return false;
          if (!b64) throw new Error('Could not read this image. Please attach it again.');
          const clean = b64.includes('base64,') ? b64.split('base64,')[1] : b64;
          if (!sendQuery(explainQuery, generateUuid(), clean)) {
            throw new Error('Could not send the image to Blinky. Check the PC connection.');
          }
          setQueryText('');
          return true;
        } catch (error) {
          if (attempt !== attachmentPlanningAttempt.current) return false;
          activeBlinkyMsgIdRef.current = null;
          setAgentStatus('error');
          setMessages(prev => prev.map(message => message.id === blinkyMsgId
            ? { ...message, text: error instanceof Error ? error.message : 'Image analysis failed.', progress: undefined }
            : message));
          return false;
        } finally {
          if (attachmentPreparationAttempt.current === attempt) attachmentPreparationAttempt.current = null;
        }
    }

    // Blank prompts and explicit PC placement requests use the streaming
    // transfer path. The PC resolves any natural-language destination.
    if (attachmentRoute === 'transfer') {
      const transferPanel = fileTransferPanelRef.current;
      if (!transferPanel) {
        Alert.alert('Attachment not sent', 'File transfer is not ready. Please try again.');
        return false;
      }
      const instruction = extractTransferEdit(query);
      const filesToSend: SelectedFile[] = attachedFiles.map(file => ({
        uri: file.uri,
        name: file.name,
        size: file.size ? Math.round(file.size * 1024 * 1024) : undefined,
      }));

      // Show a user message in chat
      const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const userMsgId = generateUuid();
      const statusMsgId = generateUuid();
      transferStatusMsgIdRef.current = statusMsgId;

      const displayText = query || `Send ${attachedFiles.length} ${attachedFiles.length === 1 ? 'file' : 'files'} to PC`;

      setMessages(prev => [
        ...prev,
        { id: userMsgId, sender: 'user' as const, text: displayText, timestamp: currentTime, attachedFiles },
        {
          id: statusMsgId,
          sender: 'blinky' as const,
          text: '📤 Starting file transfer…',
          timestamp: currentTime,
          progress: { percent: 0, statusText: 'Preparing…', duration: 0 },
        },
      ]);

      setQueryText('');
      triggerHaptic('medium');

      transferPanel.startTransfer(filesToSend, instruction, '', query);
      return true;
    }

    // Direct prompt to Antigravity IDE
    if (
      query.startsWith('/agy ') ||
      query.startsWith('/antigravity ') ||
      query.toLowerCase().startsWith('antigravity:')
    ) {
      const prompt = query.replace(/^(\/(agy|antigravity)\s*|antigravity:\s*)/i, '').trim();
      if (prompt) {
        sendAntigravityPrompt(prompt);
        setAgentStatus('processing');
        setTimerSeconds(0);
        const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const agyMsgId = generateUuid();
        activeAntigravityMsgIdRef.current = agyMsgId;

        setMessages(prev => [
          ...prev,
          {
            id: generateUuid(),
            sender: 'user',
            text: `⚡ Sent to Antigravity: "${prompt}"`,
            timestamp: currentTime,
          },
          {
            id: agyMsgId,
            sender: 'blinky',
            text: "Antigravity session running on desktop...",
            timestamp: currentTime,
            progress: {
              percent: 10,
              statusText: 'Starting Antigravity agent...',
              duration: 0,
            }
          }
        ]);
        setQueryText('');
        triggerHaptic('medium');
        return true;
      }
    }

    triggerHaptic('light');

    // Parse agent or ask prefixes if provided
    if (query.startsWith('/agent ')) {
      query = query.replace(/^\/agent\s+/i, '').trim();
    } else if (query.startsWith('/ask ')) {
      query = query.replace(/^\/ask\s+/i, '').trim();
    }
    const displayQuery = query;
    setRunningQuery(displayQuery);
    setQueryText('');
    setAgentStatus('processing');
    setTimerSeconds(0);

    const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsgId = generateUuid();
    const blinkyMsgId = generateUuid();
    
    // Save reference of the active Blinky card to update later
    activeBlinkyMsgIdRef.current = blinkyMsgId;

    setMessages(prev => [
      ...prev,
      {
        id: userMsgId,
        sender: 'user',
        text: displayQuery,
        timestamp: currentTime,
      },
      {
        id: blinkyMsgId,
        sender: 'blinky',
        text: "I'm on it. Locating the request...",
        timestamp: currentTime,
        progress: {
          percent: 0,
          statusText: 'Analyzing query...',
          duration: 0,
        }
      }
    ]);

    const success = sendQuery(query, generateUuid());
    if (!success) {
      setAgentStatus('error');
      setMessages(prev => prev.map(m => {
        if (m.id === blinkyMsgId) {
          return {
            ...m,
            progress: {
              percent: 0,
              statusText: 'Failed to communicate with PC.',
              duration: 0,
            }
          };
        }
        return m;
      }));
    }
    return true;
  };

  // Voice recording handlers
  const startVoiceRecording = async () => {
    if (!isConnected) {
      triggerHaptic('selection');
      Alert.alert('Not Connected', 'Please establish a link to your PC first.');
      return;
    }

    // Check if we have at least one STT API key available
    if (!assemblyaiApiKey && !sarvamApiKey) {
      triggerHaptic('selection');
      Alert.alert('Configuration Missing', 'Waiting for voice AI keys from your PC...');
      sendCommand('get_assemblyai_key' as any);
      sendCommand('get_sarvam_key' as any);
      sendCommand('get_voice_provider' as any);
      return;
    }

    // Log the current voice provider configuration for debugging
    console.log('Voice recording started with provider:', voiceProvider);
    console.log('AssemblyAI key available:', !!assemblyaiApiKey);
    console.log('Sarvam key available:', !!sarvamApiKey);

    try {
      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('Permission Denied', 'Microphone access is required for voice commands.');
        return;
      }

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      });

      // expo-audio v57 exposes AudioRecorder as a SharedObject. Construct it
      // with options, prepare it, then call record(); the old expo-av-style
      // createAudioRecorderAsync/startAsync APIs are not available here.
      console.log('Creating audio recorder with HIGH_QUALITY preset');
      const recording = new AudioModule.AudioRecorder(RecordingPresets.HIGH_QUALITY);
      audioRecorderRef.current = recording;
      await recording.prepareToRecordAsync();
      recording.record();
      triggerHaptic('heavy');
      setIsVoiceRecording(true);
      setLiveTranscript('Listening...');
      console.log('Recording started successfully');
    } catch (err) {
      console.error('Failed to start voice recording', err);
      Alert.alert('Error', 'Failed to start microphone recording.');
    }
  };

  const stopVoiceRecording = async () => {
    if (!isVoiceRecording) return;
    triggerHaptic('medium');
    setIsVoiceRecording(false);
    setIsVoiceTranscribing(true);
    setLiveTranscript('Transcribing...');
    try {
      const recorder = audioRecorderRef.current;
      if (!recorder) {
        throw new Error('No active recorder found');
      }

      // Stop recording and get the file URI
      await recorder.stop();
      const uri = recorder.uri;
      audioRecorderRef.current = null;
      recorder.release();

      console.log('Recording stopped, URI:', uri);

      if (!uri) {
        throw new Error('No recording URI found');
      }

      let transcript = '';

      // Use the voice provider set by desktop app, with fallback to available keys
      if (voiceProvider === 'assemblyai' && assemblyaiApiKey) {
        try {
          console.log('Starting AssemblyAI transcription...');
          // React Native's fetch(uri).blob() can return the URI string as a
          // tiny text/plain Blob instead of reading the local recording.
          // Expo File uploads the native file bytes directly.
          const audioFile = new File(uri);
          console.log('Audio file size:', audioFile.size, 'bytes');
          if (audioFile.size < 100) {
            throw new Error('The recording file is empty or unreadable. Please record again.');
          }

          const uploadResult = await audioFile.upload('https://api.assemblyai.com/v2/upload', {
            httpMethod: 'POST',
            uploadType: UploadType.BINARY_CONTENT,
            headers: { Authorization: assemblyaiApiKey },
            mimeType: 'audio/mp4',
          });

          console.log('AssemblyAI upload response status:', uploadResult.status);

          if (uploadResult.status >= 200 && uploadResult.status < 300) {
            const { upload_url } = JSON.parse(uploadResult.body);
            console.log('AssemblyAI upload URL received');
            if (upload_url) {
              const transcriptRes = await fetch('https://api.assemblyai.com/v2/transcript', {
                method: 'POST',
                headers: {
                  Authorization: assemblyaiApiKey,
                  'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                  audio_url: upload_url,
                  speech_models: ['universal-3-5-pro'],
                  punctuate: true,
                  format_text: true,
                }),
              });

              console.log('AssemblyAI transcript request status:', transcriptRes.status);

              if (transcriptRes.ok) {
                const { id: transcriptId } = await transcriptRes.json();
                console.log('AssemblyAI transcript ID:', transcriptId);

                for (let i = 0; i < 30; i++) {
                  await new Promise(r => setTimeout(r, 600));
                  const pollRes = await fetch(`https://api.assemblyai.com/v2/transcript/${transcriptId}`, {
                    headers: { Authorization: assemblyaiApiKey },
                  });
                  if (pollRes.ok) {
                    const pollData = await pollRes.json();
                    console.log(`AssemblyAI poll ${i}: status = ${pollData.status}`);
                    if (pollData.status === 'completed') {
                      transcript = (pollData.text || '').trim();
                      console.log('AssemblyAI transcription completed, text length:', transcript.length);
                      break;
                    } else if (pollData.status === 'error') {
                      console.warn('AssemblyAI transcription reported error:', pollData.error);
                      break;
                    }
                  }
                }
              } else {
                const errorText = await transcriptRes.text();
                console.error('AssemblyAI transcript request failed:', transcriptRes.status, errorText);
              }
            }
          } else {
            console.error('AssemblyAI upload failed:', uploadResult.status, uploadResult.body);
          }
        } catch (aaiErr) {
          console.error('AssemblyAI mobile STT failed with exception:', aaiErr);
        }
      }

      // Fallback to Sarvam if AssemblyAI failed or key not available
      if (!transcript && sarvamApiKey) {
        const formData = new FormData();
        formData.append('file', {
          uri: uri,
          type: Platform.OS === 'android' ? 'audio/x-m4a' : 'audio/wav',
          name: Platform.OS === 'android' ? 'query.m4a' : 'query.wav',
        } as any);
        formData.append('model', 'saaras:v3');
        formData.append('language_code', 'en-IN');

        // Use XMLHttpRequest to avoid Expo fetch's "Unsupported FormDataPart implementation" error
        // Expo's fetch polyfill does not support React Native's file URI object in FormData,
        // whereas React Native's XMLHttpRequest natively handles `{ uri, type, name }` multipart uploads.
        const data: any = await new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open('POST', 'https://api.sarvam.ai/speech-to-text');
          xhr.setRequestHeader('api-subscription-key', sarvamApiKey);

          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              try {
                resolve(JSON.parse(xhr.responseText));
              } catch (e) {
                reject(new Error('Invalid JSON response from Sarvam STT'));
              }
            } else {
              let errorMsg = `HTTP ${xhr.status}`;
              try {
                const parsed = JSON.parse(xhr.responseText);
                if (parsed.message) errorMsg = parsed.message;
              } catch {}
              reject(new Error(errorMsg));
            }
          };

          xhr.onerror = () => {
            reject(new Error('Network error during speech recognition upload'));
          };

          xhr.ontimeout = () => {
            reject(new Error('Speech recognition request timed out'));
          };

          xhr.send(formData);
        });
        transcript = data.transcript?.trim() || '';
      }

      if (!transcript) {
        const errorMsg = voiceProvider === 'assemblyai'
          ? 'AssemblyAI transcription failed. Please check your API key configuration.'
          : 'Sarvam transcription failed. Please check your API key configuration.';
        console.error('STT failed:', errorMsg);
        throw new Error(errorMsg);
      }

      setLiveTranscript(null);
      setQueryText(transcript);
      setRunningQuery(transcript);
      setAgentStatus('processing');
      setTimerSeconds(0);

      const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const userMsgId = generateUuid();
      const blinkyMsgId = generateUuid();

      activeBlinkyMsgIdRef.current = blinkyMsgId;

      setMessages(prev => [
        ...prev,
        {
          id: userMsgId,
          sender: 'user',
          text: transcript,
          timestamp: currentTime,
        },
        {
          id: blinkyMsgId,
          sender: 'blinky',
          text: "I'm on it. Locating the request...",
          timestamp: currentTime,
          progress: {
            percent: 0,
            statusText: 'Analyzing speech...',
            duration: 0,
          }
        }
      ]);

      const success = sendQuery(transcript, generateUuid());
      if (!success) {
        setAgentStatus('error');
        setMessages(prev => prev.map(m => {
          if (m.id === blinkyMsgId) {
            return {
              ...m,
              progress: {
                percent: 0,
                statusText: 'Failed to communicate with PC.',
                duration: 0,
              }
            };
          }
          return m;
        }));
      }
    } catch (err: any) {
      console.error('STT Voice error:', err);
      setLiveTranscript(null);
      Alert.alert('Speech Recognition Failed', err.message || 'Error transcribing voice.');
    } finally {
      setIsVoiceTranscribing(false);
    }
  };

  const toggleVoiceRecording = () => {
    if (isVoiceRecording) {
      stopVoiceRecording();
    } else {
      startVoiceRecording();
    }
  };

  const handleStopQuery = () => {
    const preparingAttachment = attachmentPreparationAttempt.current !== null;
    attachmentPreparationAttempt.current = null;
    attachmentPlanningAttempt.current++;
    cancelAttachmentPlanning();
    triggerHaptic('heavy');
    setAgentStatus('idle');
    setRunningQuery('');
    if (!preparingAttachment) setQueryText('');
    const currentActiveId = activeBlinkyMsgIdRef.current;
    if (currentActiveId) {
      setMessages(prev => prev.map(m => {
        if (m.id === currentActiveId) {
          return {
            ...m,
            progress: {
              percent: m.progress?.percent || 0,
              statusText: 'Stopped by user.',
              duration: m.progress?.duration || timerSeconds,
            }
          };
        }
        return m;
      }));
    }
    activeBlinkyMsgIdRef.current = null;
  };

  const formatTime = (totalSecs: number) => {
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${pad(mins)}:${pad(secs)}`;
  };

  // Load saved IP address + remote token on launch
  useEffect(() => {
    /** Restores persisted connection and Wake-on-LAN settings on launch. */
    async function loadIp() {
      try {
        const [savedIp, savedToken, savedPin, savedMac, savedWolIp, savedWorkstationPin] = await Promise.all([
          AsyncStorage.getItem(STORAGE_KEY),
          readSavedCredential('remote_token', TOKEN_STORAGE_KEY),
          readSavedCredential('certificate_pin', CERTIFICATE_PIN_STORAGE_KEY),
          AsyncStorage.getItem(MAC_STORAGE_KEY),
          AsyncStorage.getItem(WOL_BROADCAST_STORAGE_KEY),
          AsyncStorage.getItem(WORKSTATION_PIN_STORAGE_KEY),
        ]);
        if (savedMac) setMacAddress(savedMac);
        if (savedWolIp) setWolBroadcastIp(savedWolIp);
        if (savedWorkstationPin) setWorkstationPin(savedWorkstationPin);
        else setWorkstationPin('damnthatsalongpassword');
        if (savedToken) setRemoteToken(savedToken);
        if (savedPin) setCertificatePin(savedPin);

        if (RELEASE_TRANSPORT) {
          if (savedToken && savedPin) {
            // Reconnect in background using saved secure credentials (WhatsApp Web flow)
            const probedIp = await probeCandidateIps(savedPin);
            const initialIp = probedIp || savedIp || '127.0.0.1';
            setIpAddress(initialIp);
            connect(initialIp, savedToken, savedPin, { secure: true });
          }
        } else {
          // Dev mode: probe candidates or run quiet auto-discovery
          const probedIp = await probeCandidateIps(savedPin || undefined);
          const detectedIp = getExpoHostIp();
          const initialIp = probedIp || savedIp || detectedIp || '';

          if (initialIp && initialIp !== 'localhost') {
            setIpAddress(initialIp);
            connect(initialIp, savedToken || undefined, savedPin || undefined);
          } else {
            handleAutoDiscoverQuietly();
          }
        }
      } catch (e) {
        console.error('Failed to load host IP address', e);
        if (!RELEASE_TRANSPORT) {
          handleAutoDiscoverQuietly();
        }
      }
    }
    loadIp();
  }, []);

  // Auto-fill target MAC from host telemetry if available
  useEffect(() => {
    if (systemInfo?.network?.mac_address) {
      const hostMac = systemInfo.network.mac_address.trim().toLowerCase();
      if (!macAddress || macAddress.trim().toLowerCase() !== hostMac) {
        setMacAddress(hostMac);
        AsyncStorage.setItem(MAC_STORAGE_KEY, hostMac).catch(() => {});
      }
    }
  }, [systemInfo?.network?.mac_address]);

  // Live alert banner for power events broadcast across clients
  useEffect(() => {
    if (latestPowerEvent) {
      triggerHaptic('heavy');
      setActionFeedback(`⚡ Sentinel: ${latestPowerEvent.action.toUpperCase()} action dispatched.`);
      setTimeout(() => setActionFeedback(null), 5000);
      if (latestPowerEvent.action === 'lock') {
        setIsWorkstationLocked(true);
      } else if (latestPowerEvent.action === 'unlock') {
        setIsWorkstationLocked(false);
      }
    }
  }, [latestPowerEvent]);

  // Synchronize lock state from telemetry
  useEffect(() => {
    if (systemInfo?.is_locked !== undefined) {
      setIsWorkstationLocked(systemInfo.is_locked);
    }
  }, [systemInfo?.is_locked]);

  // Auto-unlock workstation if Wake PC was triggered while host was offline
  useEffect(() => {
    if (isConnected && pendingUnlockAfterWake) {
      setPendingUnlockAfterWake(false);
      const timer = setTimeout(() => {
        handleUnlockWorkstation();
      }, 1200);
      return () => clearTimeout(timer);
    }
  }, [isConnected, pendingUnlockAfterWake]);

  // Periodically query telemetry to keep workstation lock state synchronized
  useEffect(() => {
    if (!isConnected) return;
    const interval = setInterval(() => {
      sendCommand('get_system_info');
    }, 6000);
    return () => clearInterval(interval);
  }, [isConnected]);

  // When connection succeeds, auto-close the settings card
  useEffect(() => {
    if (isConnected) {
      setShowSettings(false);
    }
  }, [isConnected]);

  // Quietly auto-reconnect in background when disconnected if credentials exist
  useEffect(() => {
    let active = true;
    if (status === 'disconnected' || status === 'error') {
      const isAuthRejected = errorMsg?.toLowerCase().includes('rejected') || errorMsg?.toLowerCase().includes('expired');
      if (isAuthRejected) {
        if (RELEASE_TRANSPORT) {
          handleUnlinkPc();
          setShowSettings(true);
        }
        return;
      }

      if (RELEASE_TRANSPORT) {
        if (remoteToken && certificatePin && ipAddress) {
          const timer = setTimeout(async () => {
            if (!active) return;
            connect(ipAddress, remoteToken, certificatePin, { secure: true });
          }, 3000);
          return () => {
            active = false;
            clearTimeout(timer);
          };
        }
      } else {
        const timer = setTimeout(async () => {
          if (!active) return;
          try {
            handleAutoDiscoverQuietly();
          } catch (e) {}
        }, 2500);
        return () => {
          active = false;
          clearTimeout(timer);
        };
      }
    }
  }, [status, errorMsg, remoteToken, certificatePin, ipAddress]);

  const handleUnlinkPc = async () => {
    triggerHaptic('heavy');
    disconnect();
    setIpAddress('');
    setRemoteToken('');
    setCertificatePin('');
    try {
      await Promise.all([
        AsyncStorage.removeItem(STORAGE_KEY),
        deleteSavedCredential('remote_token', TOKEN_STORAGE_KEY),
        deleteSavedCredential('certificate_pin', CERTIFICATE_PIN_STORAGE_KEY),
      ]);
    } catch (e) {}
  };

  const handleAutoDiscoverQuietly = async () => {
    try {
      // 1. First probe known fast candidate endpoints (Tailscale, USB reverse, env)
      const candidateFound = await probeCandidateIps(certificatePin || undefined);
      if (candidateFound) {
        setIpAddress(candidateFound);
        await AsyncStorage.setItem(STORAGE_KEY, candidateFound);
        connect(candidateFound, remoteToken || undefined, certificatePin || undefined);
        return;
      }

      const subnetsToScan: string[] = [];
      try {
        const ip = await Network.getIpAddressAsync();
        if (ip && ip !== '0.0.0.0' && ip.includes('.')) {
          const ipParts = ip.split('.');
          if (ipParts.length === 4) {
            subnetsToScan.push(`${ipParts[0]}.${ipParts[1]}.${ipParts[2]}`);
          }
        }
      } catch (e) {}

      // Common Wi-Fi router subnets fallback
      for (const fallbackSubnet of ['192.168.1', '192.168.0', '192.168.2', '10.0.0']) {
        if (!subnetsToScan.includes(fallbackSubnet)) {
          subnetsToScan.push(fallbackSubnet);
        }
      }

      for (const subnet of subnetsToScan) {
        const foundIp = await scanSubnet(subnet, undefined, certificatePin || undefined);
        if (foundIp) {
          setIpAddress(foundIp);
          await AsyncStorage.setItem(STORAGE_KEY, foundIp);
          connect(foundIp, remoteToken || undefined, certificatePin || undefined);
          break;
        }
      }
    } catch (err) {}
  };

  const validateIp = (ip: string): boolean => {
    const trimmed = ip.trim().replace(/^https?:\/\//i, '').replace(/^wss?:\/\//i, '');
    if (!trimmed) return false;
    const ipPattern = /^([a-zA-Z0-9-]+\.)*[a-zA-Z0-9-]+(:\d+)?$/;
    const ipv4Pattern = /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}(:\d+)?$/;
    return ipPattern.test(trimmed) || ipv4Pattern.test(trimmed) || trimmed === 'localhost';
  };

  const handleConnect = async () => {
    triggerHaptic('medium');
    const cleanedIp = ipAddress.trim().replace(/^https?:\/\//i, '').replace(/^wss?:\/\//i, '').replace(/\/+$/, '');
    if (!validateIp(cleanedIp)) {
      Alert.alert('Invalid Address', 'Please enter a valid IP address (e.g. 192.168.1.4).');
      return;
    }
    setIpAddress(cleanedIp);
    try {
      await Promise.all([
        AsyncStorage.setItem(STORAGE_KEY, cleanedIp),
        saveCredential('remote_token', TOKEN_STORAGE_KEY, remoteToken.trim()),
        saveCredential('certificate_pin', CERTIFICATE_PIN_STORAGE_KEY, certificatePin.trim()),
      ]);
    } catch (e) {}
    connect(cleanedIp, remoteToken || undefined, certificatePin || undefined);
  };

  /** One-scan connect from the PC app's "Connect Mobile" QR code. */
  const handleQrConnect = async (qr: { ip: string; token?: string; pin?: string; mode?: string }) => {
    triggerHaptic('medium');
    const cleanedIp = qr.ip.trim().replace(/^https?:\/\//i, '').replace(/^wss?:\/\//i, '').replace(/\/+$/, '');
    if (!validateIp(cleanedIp)) {
      Alert.alert('Invalid QR Code', 'This QR code does not contain a valid Blinky PC address. Scan the QR shown via the QR icon in the PC app header.');
      return;
    }
    const token = (qr.token || '').trim();
    const pin = (qr.pin || '').trim();
    setIpAddress(cleanedIp);
    if (token) setRemoteToken(token);
    if (pin) setCertificatePin(pin);
    try {
      // Never persist empty strings: that would clobber a working saved
      // token/pin with "" and poison every later auto-reconnect attempt.
      await Promise.all([
        AsyncStorage.setItem(STORAGE_KEY, cleanedIp),
        ...(token ? [saveCredential('remote_token', TOKEN_STORAGE_KEY, token)] : []),
        ...(pin ? [saveCredential('certificate_pin', CERTIFICATE_PIN_STORAGE_KEY, pin)] : []),
      ]);
    } catch (e) {}
    // A release QR must stay on the pinned secure channel even in dev builds;
    // a release build never downgrades regardless of QR mode (see connect()).
    connect(cleanedIp, token || undefined, pin || undefined, { secure: qr.mode === 'release' });
  };

  const handleAutoDiscover = async () => {
    triggerHaptic('medium');
    setIsDiscovering(true);
    setDiscoveryProgress('Probing Tailscale & direct links...');
    try {
      // 1. Probe Tailscale and fast candidates
      let found: string | null = await probeCandidateIps(certificatePin || undefined);

      // 2. If not found, scan local Wi-Fi subnets
      if (!found) {
        setDiscoveryProgress('Detecting Wi-Fi network...');
        const subnetsToScan: string[] = [];
        try {
          const ip = await Network.getIpAddressAsync();
          if (ip && ip !== '0.0.0.0' && ip.includes('.')) {
            const ipParts = ip.split('.');
            if (ipParts.length === 4) {
              subnetsToScan.push(`${ipParts[0]}.${ipParts[1]}.${ipParts[2]}`);
            }
          }
        } catch (e) {}

        for (const fallbackSubnet of ['192.168.1', '192.168.0', '192.168.2', '10.0.0']) {
          if (!subnetsToScan.includes(fallbackSubnet)) {
            subnetsToScan.push(fallbackSubnet);
          }
        }

        for (const subnet of subnetsToScan) {
          setDiscoveryProgress(`Scanning Wi-Fi subnet ${subnet}.x...`);
          found = await scanSubnet(subnet, (msg) => {
            setDiscoveryProgress(msg);
          }, certificatePin || undefined);
          if (found) break;
        }
      }

      if (found) {
        setIpAddress(found);
        await AsyncStorage.setItem(STORAGE_KEY, found);
        connect(found, remoteToken || undefined, certificatePin || undefined);
        Alert.alert('Blinky Connected!', `Found Blinky PC at ${found}`);
      } else {
        Alert.alert(
          'Blinky PC Not Found',
          'Could not automatically discover your PC. Please check your PC\'s Wi-Fi or Tailscale IP address (e.g. 100.122.62.2), enter it above, and tap "Establish Link".'
        );
      }
    } catch (err: any) {
      Alert.alert('Error', `Discovery failed: ${err.message}`);
    } finally {
      setIsDiscovering(false);
      setDiscoveryProgress(null);
    }
  };

  /** Confirms and dispatches a potentially disruptive host power command. */
  const triggerPowerCommand = (
    command: 'power_off' | 'restart' | 'sleep' | 'hibernate' | 'lock' | 'unlock',
    label: string
  ) => {
    if (command === 'unlock') {
      handleUnlockWorkstation();
      return;
    }
    triggerHaptic('heavy');
    Alert.alert(
      `Confirm ${label}`,
      `Are you sure you want to trigger "${label}" on your PC?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Confirm',
          style: command === 'power_off' || command === 'restart' || command === 'hibernate' ? 'destructive' : 'default',
          onPress: () => {
            triggerHaptic('heavy');
            const success = sendCommand(command);
            if (success) {
              if (command === 'lock') {
                setIsWorkstationLocked(true);
              }
              setActionFeedback(`Command "${label}" dispatched!`);
              setTimeout(() => setActionFeedback(null), 4000);
            } else {
              Alert.alert('Error', 'Failed to send command. Check link to PC.');
            }
          },
        },
      ]
    );
  };

  /** Unlocks the host workstation by waking displays, dismissing lock screen, and entering PIN or password. */
  const handleUnlockWorkstation = (pin?: string) => {
    triggerHaptic('heavy');
    const targetPin = (pin !== undefined ? pin : workstationPin).trim();
    if (!targetPin) {
      // Prompt user to enter their Windows password/PIN if not yet configured
      setShowPinPromptModal(true);
      return;
    }
    const cmd = `unlock:${targetPin}`;
    const success = sendCommand(cmd as any);
    if (success) {
      setIsWorkstationLocked(false);
      setActionFeedback('⚡ Unlocking workstation...');
      setTimeout(() => setActionFeedback(null), 4000);
    } else {
      Alert.alert('Error', 'Failed to send unlock command. Check link to PC.');
    }
  };

  /** Submits PIN from prompt modal, persists it if requested, and dispatches unlock. */
  const submitPinAndUnlock = () => {
    const trimmed = inputPin.trim();
    if (!trimmed) {
      Alert.alert('Required', 'Please enter your Windows password or PIN.');
      return;
    }
    if (rememberPin) {
      setWorkstationPin(trimmed);
      AsyncStorage.setItem(WORKSTATION_PIN_STORAGE_KEY, trimmed).catch(() => {});
    }
    setShowPinPromptModal(false);
    setInputPin('');
    handleUnlockWorkstation(trimmed);
  };

  /** Handles Wake PC button tap: wakes display, sends WoL, and unlocks host workstation automatically. */
  const onWakePcPressed = () => {
    triggerHaptic('heavy');
    if (isConnected) {
      handleUnlockWorkstation();
      return;
    }
    // If offline / PC asleep, broadcast WoL packet and auto-unlock once online
    setPendingUnlockAfterWake(true);
    handleSendWakeOnLan();
    setActionFeedback('⚡ Waking PC... Will auto-unlock once online.');
  };

  /** Sends a Wake-on-LAN request using the currently configured host settings. */
  const handleSendWakeOnLan = async () => {
    const targetMac = (macAddress.trim() || systemInfo?.network?.mac_address?.trim() || '');
    if (!targetMac) {
      Alert.alert(
        'Missing MAC Address',
        'Please connect to your PC once to auto-detect its MAC address, or enter it in Local Link Setup.'
      );
      return;
    }
    if (!macAddress.trim() && targetMac) {
      setMacAddress(targetMac);
    }
    setIsSendingWol(true);
    setActionFeedback('⚡ Dispatching Wake-on-LAN Magic Packet...');
    try {
      const res = await sendWakeOnLan(targetMac, wolBroadcastIp.trim());
      setWolFeedback(res.message);
      if (res.success) {
        setActionFeedback(`⚡ ${res.message}`);
        await AsyncStorage.setItem(MAC_STORAGE_KEY, targetMac);
        await AsyncStorage.setItem(WOL_BROADCAST_STORAGE_KEY, wolBroadcastIp.trim());
      } else {
        Alert.alert('Wake-on-LAN Notice', res.message);
      }
    } catch (err: any) {
      const msg = `WoL failed: ${err?.message || err}`;
      setWolFeedback(msg);
      setActionFeedback(msg);
    } finally {
      setIsSendingWol(false);
      setTimeout(() => setActionFeedback(null), 5000);
    }
  };

  const triggerQuickAction = (command: any, label: string) => {
    triggerHaptic('medium');
    if (command === 'unlock') {
      handleUnlockWorkstation();
      return;
    }
    const success = sendCommand(command);
    if (success) {
      if (command === 'lock') {
        setIsWorkstationLocked(true);
      }
      setActionFeedback(`Command "${label}" sent!`);
      setTimeout(() => setActionFeedback(null), 3000);
    } else {
      Alert.alert('Error', 'Failed to send command. Check link.');
    }
  };
  if (!fontsLoaded) {
    return null;
  }

  return (
    <SafeAreaProvider>
    <GestureHandlerRootView style={{ flex: 1 }}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <StatusBar barStyle="light-content" />
        <View style={styles.safeArea}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.keyboardView}
          >
          {/* Header */}
          <BrandHeader
            status={status}
            isConnected={isConnected}
            onPressConnection={() => setShowSettings(!showSettings)}
            onPressHistory={() => {
              void listSessions().then(setSessionsList);
              setShowHistoryModal(true);
            }}
          />

          {/* Session History Slide-Up Drawer */}
          <SessionHistoryModal
            visible={showHistoryModal}
            onClose={() => setShowHistoryModal(false)}
            sessions={sessionsList}
            activeSessionId={currentSession?.id || ''}
            onSelectSession={(sess) => {
              setCurrentSession(sess);
              setMessages(sess.messages);
              setChatMode(sess.mode === 'grounded' ? 'grounded' : 'autopilot');
            }}
            onNewSession={async () => {
              const fresh = await createNewSession(chatMode === 'grounded' ? 'grounded' : 'general');
              setCurrentSession(fresh);
              setMessages(fresh.messages);
              const updated = await listSessions();
              setSessionsList(updated);
            }}
            onDeleteSession={async (id) => {
              const next = await deleteSession(id);
              setCurrentSession(next);
              setMessages(next.messages);
              const updated = await listSessions();
              setSessionsList(updated);
            }}
            onClearAllSessions={async () => {
              const fresh = await clearAllSessions();
              setCurrentSession(fresh);
              setMessages(fresh.messages);
              const updated = await listSessions();
              setSessionsList(updated);
            }}
          />

          {/* Settings modal extracted to SettingsModal.tsx */}

          {/* Disconnected Alert Banner (if disconnected and settings not open) */}
          {!isConnected && !showSettings && (
            <TouchableOpacity
              style={styles.disconnectedAlertBanner}
              onPress={() => {
                triggerHaptic('light');
                setShowSettings(true);
              }}
              activeOpacity={0.8}
            >
              <Ionicons name="wifi-outline" size={16} color="#EF4444" style={{ marginRight: 8 }} />
              <Text style={styles.disconnectedAlertText}>
                {status === 'connecting' ? `Connecting to ${ipAddress || 'PC'}...` : 'Not connected to PC. Tap to connect.'}
              </Text>
              <Ionicons name="chevron-forward" size={14} color="#8A86AA" />
            </TouchableOpacity>
          )}

          {actionFeedback && (
            <View style={styles.feedbackBanner}>
              <Text style={styles.feedbackBannerText}>{actionFeedback}</Text>
            </View>
          )}

          {/* Antigravity Session Complete Banner */}
          {antigravityComplete && (
            <View style={styles.antigravityCompleteBanner}>
              <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
                <Ionicons name="checkmark-done-circle" size={18} color="#10B981" style={{ marginRight: 8 }} />
                <Text style={styles.antigravityCompleteText} numberOfLines={1}>
                  Antigravity session complete ({antigravityComplete.reason})
                </Text>
              </View>
              <TouchableOpacity onPress={dismissAntigravityComplete} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
                <Ionicons name="close" size={16} color="#8A86AA" />
              </TouchableOpacity>
            </View>
          )}

          {/* Antigravity Action Required Card */}
          {antigravityApproval && (
            <View style={styles.antigravityCard}>
              <View style={styles.antigravityCardHeader}>
                <View style={styles.antigravityBadge}>
                  <Ionicons name="hardware-chip" size={13} color="#A78BFA" style={{ marginRight: 5 }} />
                  <Text style={styles.antigravityBadgeText}>ANTIGRAVITY IDE</Text>
                </View>
                <Text style={styles.antigravityTimeText}>Approval Required</Text>
              </View>
              
              <Text style={styles.antigravityToolTitle}>
                Action: <Text style={{ color: '#FFFFFF', fontWeight: '700' }}>{antigravityApproval.tool}</Text>
              </Text>

              {antigravityApproval.args && (
                <View style={styles.antigravityArgsContainer}>
                  <Text style={styles.antigravityArgsText} numberOfLines={4}>
                    {antigravityApproval.args.CommandLine
                      ? `$ ${antigravityApproval.args.CommandLine}`
                      : antigravityApproval.args.TargetFile
                      ? `Target: ${antigravityApproval.args.TargetFile}`
                      : antigravityApproval.args.questions
                      ? `Q: ${JSON.stringify(antigravityApproval.args.questions)}`
                      : JSON.stringify(antigravityApproval.args, null, 2)}
                  </Text>
                </View>
              )}

              <View style={styles.antigravityActionsRow}>
                <TouchableOpacity
                  style={[styles.antigravityBtn, styles.antigravityRejectBtn]}
                  onPress={() => {
                    triggerHaptic('heavy');
                    sendAntigravityDecision(antigravityApproval.actionId, 'deny');
                  }}
                  activeOpacity={0.8}
                >
                  <Ionicons name="close-circle-outline" size={18} color="#EF4444" style={{ marginRight: 6 }} />
                  <Text style={styles.antigravityRejectBtnText}>Reject</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.antigravityBtn, styles.antigravityApproveBtn]}
                  onPress={() => {
                    triggerHaptic('medium');
                    sendAntigravityDecision(antigravityApproval.actionId, 'allow');
                  }}
                  activeOpacity={0.8}
                >
                  <Ionicons name="checkmark-circle-outline" size={18} color="#10B981" style={{ marginRight: 6 }} />
                  <Text style={styles.antigravityApproveBtnText}>Approve</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* TAB ROUTING */}
          {activeTab === 'Chat' && (
            <View style={{ flex: 1 }}>
              {/* Main Messaging Feed */}
              <ScrollView
                ref={scrollViewRef}
                style={{ flex: 1 }}
                showsVerticalScrollIndicator={false}
                contentContainerStyle={[styles.chatScrollContent, { paddingBottom: 24 }]}
                keyboardShouldPersistTaps="handled"
              >
                {messages.length <= 1 && (
                  <ChatHome
                    onQuickAction={(action) => {
                      if (action === 'Screenshot') handleCaptureScreenshot();
                      else if (action === 'Open app') setQueryText('Open ');
                      else if (action === 'Run command') setQueryText('Run ');
                    }}
                  />
                )}
                {messages.map((message) => (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    formatTime={formatTime}
                    onEnlargeScreenshot={(uri) => {
                      triggerHaptic('light');
                      setPreviewImageUri(uri);
                    }}
                  />
                ))}
              </ScrollView>

              {/* Slash Commands Dropdown Menu */}
              <SlashCommandMenu
                queryText={queryText}
                onSelectCommand={setQueryText}
                commands={SLASH_COMMANDS}
              />

              {/* Inline Grounding Mode Bar: PC Autopilot vs Grounded Knowledge */}
              <View style={styles.groundingModeBar}>
                <TouchableOpacity
                  style={[
                    styles.groundingPill,
                    chatMode === 'autopilot' && styles.groundingPillActiveAutopilot,
                  ]}
                  onPress={() => {
                    triggerHaptic('selection');
                    setChatMode('autopilot');
                  }}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name="desktop-outline"
                    size={13}
                    color={chatMode === 'autopilot' ? '#FF5A36' : '#8A86AA'}
                  />
                  <Text
                    style={[
                      styles.groundingPillText,
                      chatMode === 'autopilot' && styles.groundingPillTextActiveAutopilot,
                    ]}
                  >
                    PC Autopilot
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[
                    styles.groundingPill,
                    chatMode === 'grounded' && styles.groundingPillActiveGrounded,
                  ]}
                  onPress={() => {
                    triggerHaptic('selection');
                    setChatMode('grounded');
                  }}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name="book-outline"
                    size={13}
                    color={chatMode === 'grounded' ? '#A78BFA' : '#8A86AA'}
                  />
                  <Text
                    style={[
                      styles.groundingPillText,
                      chatMode === 'grounded' && styles.groundingPillTextActiveGrounded,
                    ]}
                  >
                    Grounded Knowledge
                  </Text>
                </TouchableOpacity>
              </View>

              {/* Command Composer */}
              <CommandComposer
                queryText={queryText}
                setQueryText={setQueryText}
                onSubmit={handleQuery}
                onStop={handleStopQuery}
                status={agentStatus}
                isConnected={isConnected}
                onPeekImage={(uri) => {
                  triggerHaptic('light');
                  setPreviewImageUri(uri);
                }}
                onCaptureScreenshot={handleCaptureScreenshot}
                isVoiceRecording={isVoiceRecording}
                isVoiceTranscribing={isVoiceTranscribing}
                onToggleVoice={toggleVoiceRecording}
                liveTranscript={liveTranscript || undefined}
              />
            </View>
          )}

          {activeTab === 'Actions' && (
            <ActionsScreen 
              isConnected={isConnected}
              isLightOn={isLightOn}
              onExecuteAction={(cmd) => {
                // Instant path: raw command goes straight to the Rust
                // fast handler (keypress / process spawn / ESP32 sidecar).
                // Only screenshot uses the chat/tutor pipeline.
                if (cmd === 'screenshot') {
                  setActiveTab('Chat');
                  handleCaptureScreenshot();
                  return;
                }
                sendCommand(cmd);
                if (cmd === 'toggle_lights') {
                  // Optimistic flip; corrected by light_event from PC.
                  setIsLightOn(prev => !prev);
                }
              }}
            />
          )}


          {activeTab === 'PC' && (
            <SystemScreen 
              systemInfo={systemInfo}
              isConnected={isConnected}
              onPowerAction={(action) => {
                sendCommand(action);
                setActionFeedback(`Power command dispatched: ${action}`);
                setTimeout(() => setActionFeedback(null), 2500);
              }}
              onWakePc={onWakePcPressed}
              isSendingWol={isSendingWol}
              isWorkstationLocked={isWorkstationLocked}
              onRefresh={fetchSystemInfo}
              isLocked={!isPcUnlocked}
              onUnlockPress={handleUnlockPcPress}
              onPromoCodePress={() => setShowPromoModal(true)}
              onRestorePress={handleRestorePurchasesPress}
              isRestoring={isRestoringPurchases}
            />
          )}

          {activeTab === 'Files' && (
            <FilesScreen
              isConnected={isConnected}
              quickAccessFolders={quickAccessFolders}
              currentDirectory={currentDirectory}
              recentFiles={recentFiles}
              searchResults={fsSearchResults}
              isLoading={fsLoading}
              fsError={fsError}
              fsFileData={fsFileData}
              onFetchQuickAccess={fetchQuickAccess}
              onListDirectory={listDirectory}
              onFetchRecentFiles={fetchRecentFiles}
              onSearch={searchFiles}
              onOpenFileOnPC={openFileOnPC}
              onOpenFileOnMobile={readFileForMobile}
              onClearFsFileData={clearFsFileData}
              onResetDirectory={resetDirectory}
              onPreviewImage={setPreviewImageUri}
              onAskBlinky={(file) => {
                setActiveTab('Chat');
                setQueryText(`Can you examine this file on my PC: "${file.path}"?`);
              }}
            />
          )}

          <SettingsModal 
            visible={showSettings && !showSplash}
            onClose={() => setShowSettings(false)}
            isConnected={isConnected}
            status={status}
            ipAddress={ipAddress}
            setIpAddress={setIpAddress}
            remoteToken={remoteToken}
            setRemoteToken={setRemoteToken}
            certificatePin={certificatePin}
            setCertificatePin={setCertificatePin}
            workstationPin={workstationPin}
            setWorkstationPin={setWorkstationPin}
            macAddress={macAddress}
            setMacAddress={setMacAddress}
            systemInfo={systemInfo}
            isDiscovering={isDiscovering}
            handleConnect={handleConnect}
            handleAutoDiscover={handleAutoDiscover}
            handleQrConnect={handleQrConnect}
            disconnect={disconnect}
            onUnlink={handleUnlinkPc}
            discoveryProgress={discoveryProgress}
            errorMsg={errorMsg}
            RELEASE_TRANSPORT={RELEASE_TRANSPORT}
            WORKSTATION_PIN_STORAGE_KEY={WORKSTATION_PIN_STORAGE_KEY}
          />

          {/* Windows PIN / Password Entry Modal */}
          <Modal
            visible={showPinPromptModal}
            transparent={true}
            animationType="fade"
            onRequestClose={() => {
              setShowPinPromptModal(false);
              setInputPin('');
            }}
          >
            <KeyboardAvoidingView
              behavior={Platform.OS === 'ios' ? 'padding' : undefined}
              style={{ flex: 1, backgroundColor: 'rgba(0, 0, 0, 0.75)', justifyContent: 'center', alignItems: 'center', padding: 24 }}
            >
              <View
                style={{
                  width: '100%',
                  maxWidth: 380,
                  backgroundColor: '#161426',
                  borderRadius: 24,
                  padding: 24,
                  borderWidth: 1,
                  borderColor: 'rgba(255, 90, 54, 0.3)',
                  shadowColor: '#000',
                  shadowOffset: { width: 0, height: 12 },
                  shadowOpacity: 0.5,
                  shadowRadius: 24,
                  elevation: 10,
                }}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
                  <View
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 14,
                      backgroundColor: 'rgba(255, 90, 54, 0.15)',
                      justifyContent: 'center',
                      alignItems: 'center',
                      marginRight: 14,
                    }}
                  >
                    <Ionicons name="key" size={22} color="#FF5A36" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 17, fontWeight: '800', color: '#FFFFFF' }}>
                      Unlock Workstation
                    </Text>
                    <Text style={{ fontSize: 12, color: 'rgba(255, 255, 255, 0.5)' }}>
                      Windows Password or PIN
                    </Text>
                  </View>
                </View>

                <Text style={{ fontSize: 13, color: 'rgba(255, 255, 255, 0.7)', marginBottom: 16, lineHeight: 18 }}>
                  Enter your Windows lockscreen PIN or password to unlock your host workstation automatically.
                </Text>

                <View
                  style={{
                    backgroundColor: 'rgba(0, 0, 0, 0.4)',
                    borderRadius: 16,
                    borderWidth: 1,
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    flexDirection: 'row',
                    alignItems: 'center',
                    paddingHorizontal: 16,
                    marginBottom: 16,
                  }}
                >
                  <Ionicons name="lock-closed" size={18} color="#FF5A36" style={{ marginRight: 10 }} />
                  <TextInput
                    style={{ height: 48, flex: 1, color: '#FFFFFF', fontSize: 15 }}
                    placeholder="Enter Windows PIN or password"
                    placeholderTextColor="rgba(255, 255, 255, 0.35)"
                    value={inputPin}
                    onChangeText={setInputPin}
                    secureTextEntry
                    autoFocus
                    autoCapitalize="none"
                    autoCorrect={false}
                    onSubmitEditing={submitPinAndUnlock}
                  />
                </View>

                <TouchableOpacity
                  style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 20 }}
                  onPress={() => setRememberPin(!rememberPin)}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name={rememberPin ? 'checkbox' : 'square-outline'}
                    size={20}
                    color={rememberPin ? '#FF5A36' : 'rgba(255, 255, 255, 0.4)'}
                    style={{ marginRight: 8 }}
                  />
                  <Text style={{ fontSize: 13, color: 'rgba(255, 255, 255, 0.8)', fontWeight: '500' }}>
                    Remember for future Wake PC taps
                  </Text>
                </TouchableOpacity>

                <View style={{ flexDirection: 'row', gap: 12 }}>
                  <TouchableOpacity
                    style={{
                      flex: 1,
                      height: 46,
                      borderRadius: 14,
                      backgroundColor: 'rgba(255, 255, 255, 0.08)',
                      justifyContent: 'center',
                      alignItems: 'center',
                    }}
                    onPress={() => {
                      setShowPinPromptModal(false);
                      setInputPin('');
                    }}
                    activeOpacity={0.7}
                  >
                    <Text style={{ color: 'rgba(255, 255, 255, 0.7)', fontSize: 14, fontWeight: '700' }}>
                      Cancel
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={{
                      flex: 1,
                      height: 46,
                      borderRadius: 14,
                      backgroundColor: '#FF5A36',
                      justifyContent: 'center',
                      alignItems: 'center',
                    }}
                    onPress={submitPinAndUnlock}
                    activeOpacity={0.8}
                  >
                    <Text style={{ color: '#FFFFFF', fontSize: 14, fontWeight: '800' }}>
                      Unlock PC
                    </Text>
                  </TouchableOpacity>
                </View>
              </View>
            </KeyboardAvoidingView>
          </Modal>

          {/* Fullscreen Image Preview Modal with Pinch to Zoom */}
          <Modal
            visible={!!previewImageUri}
            transparent={true}
            animationType="fade"
            onRequestClose={() => setPreviewImageUri(null)}
          >
            {previewImageUri && (
              <PinchableImageViewer
                uri={previewImageUri}
                onClose={() => setPreviewImageUri(null)}
              />
            )}
          </Modal>
          <FileTransferPanel
            ref={fileTransferPanelRef}
            visible={false}
            connected={isConnected}
            hostAddress={ipAddress}
            releaseTransport={RELEASE_TRANSPORT}
            certificatePin={certificatePin}
            fileTransferMessage={fileTransferMessage}
            sendMessage={sendFileTransferMessage}
            getNativeModule={getFileTransferModule}
            onClose={() => {}}
            onTransferStatusChange={(status) => {
              const msgId = transferStatusMsgIdRef.current;
              if (!msgId) return;
              setMessages(prev => prev.map(m => {
                if (m.id !== msgId) return m;
                return {
                  ...m,
                  text: status ? `📤 ${status}` : m.text,
                  progress: status
                    ? { percent: 50, statusText: status, duration: 0 }
                    : m.progress,
                };
              }));
            }}
            onTransferDone={(success, message) => {
              const msgId = transferStatusMsgIdRef.current;
              transferStatusMsgIdRef.current = null;
              if (!msgId) return;
              setMessages(prev => prev.map(m => {
                if (m.id !== msgId) return m;
                return {
                  ...m,
                  text: message,
                  progress: undefined,
                };
              }));
            }}
          />
          <PromoCodeModal
            visible={showPromoModal}
            onClose={() => setShowPromoModal(false)}
            onSuccess={() => {
              setIsPcUnlocked(true);
            }}
          />
        </KeyboardAvoidingView>
        <BottomNavigation
          activeTab={activeTab}
          isPcLocked={!isPcUnlocked}
          onTabChange={(tab) => {
            if (tab === 'Files') {
              resetDirectory();
            }
            setActiveTab(tab);
          }}
        />
      </View>
      {showSplash && (
        <SplashScreen
          onDismiss={() => {
            setShowSplash(false);
            if (RELEASE_TRANSPORT) {
              if (!remoteToken || !certificatePin) {
                setShowSettings(true);
              }
            } else {
              if (!isConnected && status !== 'connecting') {
                setShowSettings(true);
              }
            }
          }}
        />
      )}
      </View>
    </GestureHandlerRootView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  safeArea: {
    flex: 1,
    paddingTop: Platform.OS === 'android' ? (StatusBar.currentHeight || 0) : 44,
  },
  keyboardView: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.04)',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  title: {
    fontSize: 16,
    fontWeight: '700',
    color: '#FFFFFF',
    letterSpacing: 4,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  statusRowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.02)',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  statusDotHeader: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 6,
  },
  statusTextHeader: {
    color: 'rgba(255, 255, 255, 0.65)',
    fontSize: 12,
    fontWeight: '600',
  },
  menuBtn: {
    padding: 6,
    backgroundColor: 'rgba(255, 255, 255, 0.02)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },

  connectionCard: {
    backgroundColor: 'rgba(21, 17, 43, 0.9)',
    borderRadius: 24,
    padding: 20,
    marginHorizontal: 20,
    marginTop: 10,
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.25)',
  },
  connectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  connectionTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#FFFFFF',
  },
  connectionSubtitle: {
    fontSize: 12,
    color: '#8A86AA',
    marginBottom: 14,
    lineHeight: 16,
  },
  disconnectedAlertBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.3)',
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginHorizontal: 20,
    marginTop: 10,
  },
  disconnectedAlertText: {
    flex: 1,
    color: '#FCA5A5',
    fontSize: 12.5,
    fontWeight: '600',
  },
  inputWrapper: {
    backgroundColor: 'rgba(0, 0, 0, 0.45)',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
    marginBottom: 16,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  inputIcon: {
    marginRight: 12,
  },
  input: {
    height: 48,
    flex: 1,
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '500',
  },
  inputDisabled: {
    color: '#6C6985',
  },
  actionRow: {
    flexDirection: 'row',
  },
  connectBtn: {
    flex: 1,
    borderRadius: 16,
    overflow: 'hidden',
  },
  discoverBtn: {
    flex: 1,
    borderRadius: 16,
    overflow: 'hidden',
    marginLeft: 10,
  },
  gradientBtn: {
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  btnText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '800',
  },
  disconnectBtn: {
    flex: 1,
    height: 44,
    borderRadius: 16,
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.3)',
  },
  disconnectBtnText: {
    color: '#EF4444',
    fontSize: 13,
    fontWeight: '800',
  },
  errorContainer: {
    backgroundColor: 'rgba(239, 68, 68, 0.08)',
    borderColor: 'rgba(239, 68, 68, 0.18)',
    borderWidth: 1,
    padding: 10,
    borderRadius: 12,
    marginTop: 14,
  },
  errorText: {
    color: '#EF4444',
    fontSize: 13,
    fontWeight: '600',
    textAlign: 'center',
  },
  discoveryProgressContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(139, 92, 246, 0.08)',
    borderColor: 'rgba(139, 92, 246, 0.18)',
    borderWidth: 1,
    padding: 10,
    borderRadius: 12,
    marginTop: 14,
  },
  discoveryProgressText: {
    color: '#C084FC',
    fontSize: 13,
    fontWeight: '600',
  },
  feedbackBanner: {
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.3)',
    paddingVertical: 8,
    paddingHorizontal: 16,
    marginHorizontal: 20,
    marginTop: 10,
    borderRadius: 12,
  },
  feedbackBannerText: {
    color: '#10B981',
    fontWeight: '700',
    fontSize: 13,
    textAlign: 'center',
  },
  chatScrollContent: {
    paddingHorizontal: 20,
    paddingVertical: 20,
    flexGrow: 1,
  },
  userMessageRow: {
    alignSelf: 'flex-end',
    maxWidth: '80%',
    marginBottom: 16,
    alignItems: 'flex-end',
  },
  blinkyMessageRow: {
    alignSelf: 'flex-start',
    maxWidth: '85%',
    marginBottom: 16,
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  avatarContainer: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.4)',
    backgroundColor: '#171324',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
    marginTop: 2,
  },
  userMessageBubble: {
    backgroundColor: 'rgba(255, 90, 54, 0.06)',
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.3)',
    borderRadius: 20,
    borderBottomRightRadius: 4,
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  blinkyMessageBubble: {
    flex: 1,
    backgroundColor: '#121115',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.06)',
    borderRadius: 20,
    borderTopLeftRadius: 4,
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  messageText: {
    color: '#FFFFFF',
    fontSize: 14.5,
    lineHeight: 20,
    fontWeight: '500',
  },
  nestedProgressCard: {
    marginTop: 12,
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.25)',
    borderRadius: 14,
    padding: 12,
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
  },
  progressBarWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  progressBarContainer: {
    flex: 1,
    height: 3,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    borderRadius: 1.5,
    marginRight: 10,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: '#FF5A36',
    borderRadius: 1.5,
  },
  progressPercent: {
    color: '#8A86AA',
    fontSize: 12,
    fontWeight: '600',
  },
  progressStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  progressStatusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#FF5A36',
    marginRight: 8,
  },
  progressStatusText: {
    color: 'rgba(255, 255, 255, 0.9)',
    fontSize: 13,
    fontWeight: '500',
    flex: 1,
  },
  progressTimerRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  progressTimerText: {
    fontSize: 12,
    color: '#8A86AA',
    fontWeight: '600',
  },
  bubbleScreenshot: {
    width: '100%',
    height: 160,
    resizeMode: 'contain',
    borderRadius: 8,
    backgroundColor: '#05020B',
    marginTop: 10,
  },
  bubbleStepsContainer: {
    marginTop: 10,
  },
  bubbleStepItem: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255, 255, 255, 0.02)',
    padding: 8,
    borderRadius: 8,
    marginBottom: 6,
  },
  bubbleStepBadge: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: '#FF5A36',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
  },
  bubbleStepBadgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '800',
  },
  bubbleStepContent: {
    flex: 1,
  },
  bubbleStepText: {
    color: '#FFFFFF',
    fontSize: 12.5,
  },
  bubbleStepTargetBadge: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(255, 90, 54, 0.1)',
    paddingHorizontal: 6,
    paddingVertical: 1.5,
    borderRadius: 4,
    marginTop: 4,
  },
  bubbleStepTargetText: {
    color: '#FF5A36',
    fontSize: 9,
    fontWeight: '700',
  },
  userMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 6,
  },
  blinkyMetaRow: {
    width: '100%',
    paddingLeft: 40,
    marginTop: 6,
  },
  metaTimestamp: {
    color: '#494660',
    fontSize: 11,
    fontWeight: '500',
  },
  checkmarksRow: {
    marginLeft: 6,
  },
  footerText: {
    textAlign: 'center',
    color: '#494660',
    fontSize: 11,
    marginVertical: 10,
  },
  chatInputBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0F0D15',
    borderRadius: 30,
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.35)',
    paddingHorizontal: 10,
    paddingVertical: 6,
    marginHorizontal: 16,
    marginBottom: Platform.OS === 'ios' ? 10 : 16,
  },
  chatInputBarDisabled: {
    opacity: 0.5,
  },
  chatTextInput: {
    flex: 1,
    height: 40,
    color: '#FFFFFF',
    paddingHorizontal: 8,
    fontSize: 15,
  },
  fileAttachBtn: {
    width: 36,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 2,
  },
  chatSendBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#FF5A36',
    justifyContent: 'center',
    alignItems: 'center',
  },
  chatSendBtnDisabled: {
    opacity: 0.5,
  },
  voiceSpinnerWrapper: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 6,
  },
  voiceMicBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#171324',
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.2)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 6,
  },
  voiceMicBtnRecording: {
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    borderColor: '#EF4444',
  },
  voiceMicBtnDisabled: {
    opacity: 0.5,
  },
  stopCircleBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#EF4444',
    backgroundColor: 'rgba(239, 68, 68, 0.08)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  stopSquare: {
    width: 12,
    height: 12,
    backgroundColor: '#EF4444',
    borderRadius: 2,
  },
  screenshotTouchable: {
    position: 'relative',
    marginTop: 10,
  },
  enlargeBadge: {
    position: 'absolute',
    bottom: 8,
    right: 8,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
  },
  enlargeBadgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '600',
  },
  fullscreenModalContainer: {
    flex: 1,
    backgroundColor: 'rgba(5, 2, 11, 0.96)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  fullscreenCloseBtn: {
    position: 'absolute',
    top: Platform.OS === 'android' ? (StatusBar.currentHeight || 20) + 12 : 50,
    right: 20,
    zIndex: 20,
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  fullscreenResetBtn: {
    position: 'absolute',
    top: Platform.OS === 'android' ? (StatusBar.currentHeight || 20) + 12 : 50,
    left: 20,
    zIndex: 20,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.18)',
  },
  fullscreenResetText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '600',
  },
  fullscreenImageWrapper: {
    width: Dimensions.get('window').width,
    height: Dimensions.get('window').height,
    justifyContent: 'center',
    alignItems: 'center',
  },
  fullscreenImage: {
    width: '94%',
    height: '84%',
  },
  antigravityCompleteBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'rgba(16, 185, 129, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.3)',
    borderRadius: 12,
    marginHorizontal: 20,
    marginBottom: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  antigravityCompleteText: {
    color: '#A7F3D0',
    fontSize: 13,
    fontWeight: '600',
  },
  antigravityCard: {
    marginHorizontal: 20,
    marginBottom: 12,
    backgroundColor: '#1C1A24',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: 'rgba(139, 92, 246, 0.3)',
    padding: 14,
    shadowColor: '#8B5CF6',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 10,
    elevation: 6,
  },
  antigravityCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  antigravityBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(139, 92, 246, 0.16)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
  },
  antigravityBadgeText: {
    color: '#C4B5FD',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  antigravityTimeText: {
    color: '#F59E0B',
    fontSize: 12,
    fontWeight: '600',
  },
  antigravityToolTitle: {
    color: '#9CA3AF',
    fontSize: 13,
    marginBottom: 8,
  },
  antigravityArgsContainer: {
    backgroundColor: 'rgba(0, 0, 0, 0.4)',
    borderRadius: 10,
    padding: 10,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  antigravityArgsText: {
    color: '#E5E7EB',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontSize: 12,
  },
  antigravityActionsRow: {
    flexDirection: 'row',
    gap: 10,
  },
  antigravityBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: 12,
  },
  antigravityRejectBtn: {
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.4)',
  },
  antigravityRejectBtnText: {
    color: '#EF4444',
    fontWeight: '700',
    fontSize: 14,
  },
  antigravityApproveBtn: {
    backgroundColor: 'rgba(16, 185, 129, 0.2)',
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.5)',
  },
  antigravityApproveBtnText: {
    color: '#10B981',
    fontWeight: '700',
    fontSize: 14,
  },
  slashMenuContainer: {
    marginHorizontal: 16,
    marginBottom: 8,
    backgroundColor: 'rgba(18, 15, 28, 0.97)',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(255, 90, 54, 0.3)',
    overflow: 'hidden',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 8,
  },
  slashMenuHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 7,
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.06)',
  },
  slashMenuHeaderText: {
    color: '#8A86AA',
    fontSize: 10.5,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  slashMenuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  slashMenuItemBorder: {
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.06)',
  },
  slashMenuIconBadge: {
    width: 30,
    height: 30,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  slashMenuContent: {
    flex: 1,
  },
  slashMenuTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 2,
  },
  slashMenuTitle: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },
  slashMenuBadge: {
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: 4,
  },
  slashMenuBadgeText: {
    fontSize: 9.5,
    fontWeight: '800',
    letterSpacing: 0.4,
  },
  slashMenuDesc: {
    color: '#9CA3AF',
    fontSize: 11.5,
  },
  groundingModeBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    marginHorizontal: 16,
    marginBottom: 6,
  },
  groundingPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  groundingPillActiveAutopilot: {
    backgroundColor: 'rgba(255, 90, 54, 0.12)',
    borderColor: 'rgba(255, 90, 54, 0.4)',
  },
  groundingPillActiveGrounded: {
    backgroundColor: 'rgba(167, 139, 250, 0.15)',
    borderColor: 'rgba(167, 139, 250, 0.45)',
  },
  groundingPillText: {
    fontSize: 11.5,
    fontWeight: '600',
    color: '#8A86AA',
  },
  groundingPillTextActiveAutopilot: {
    color: '#FF5A36',
    fontWeight: '700',
  },
  groundingPillTextActiveGrounded: {
    color: '#C4B5FD',
    fontWeight: '700',
  },
});
