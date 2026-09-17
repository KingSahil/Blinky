import React, { useState, useEffect, useRef } from 'react';
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
import Constants from 'expo-constants';
import * as Network from 'expo-network';
import { LinearGradient } from 'expo-linear-gradient';
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
export { triggerHaptic };

const STORAGE_KEY = '@blinky_pc_ip';
const TOKEN_STORAGE_KEY = '@blinky_pc_token';
const CERTIFICATE_PIN_STORAGE_KEY = '@blinky_pc_certificate_pin';
const WORKSTATION_PIN_STORAGE_KEY = '@blinky_workstation_pin';
const RELEASE_TRANSPORT = process.env.EXPO_PUBLIC_BLINKY_TRANSPORT_MODE === 'release';

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
    return loadNativeSecureSocketModule()?.getSecureValue(secureKey) || null;
  }
  return AsyncStorage.getItem(legacyKey);
};

const saveCredential = async (secureKey: string, legacyKey: string, value: string): Promise<void> => {
  if (RELEASE_TRANSPORT) {
    const nativeModule = loadNativeSecureSocketModule();
    if (!nativeModule) throw new Error('Secure credential storage is unavailable in this build.');
    await nativeModule.setSecureValue(secureKey, value);
    return;
  }
  await AsyncStorage.setItem(legacyKey, value);
};

let VolumeManager: any = null;
try {
  VolumeManager = require('react-native-volume-manager').VolumeManager;
} catch (e) {
  console.log('react-native-volume-manager not available in this environment');
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

const checkIpAddress = (rawIp: string, port = 9001, timeoutMs = 1500, certificatePin?: string): Promise<string> => {
  const clean = rawIp.trim().replace(/^https?:\/\//i, '').replace(/^wss?:\/\//i, '').replace(/\/+$/, '');
  const [ipOnly, customPort] = clean.includes(':') ? clean.split(':') : [clean, undefined];
  const targetPort = customPort ? parseInt(customPort, 10) : port;
  const ip = ipOnly;

  if (RELEASE_TRANSPORT) {
    const nativeModule = loadNativeSecureSocketModule();
    if (!nativeModule || !certificatePin?.trim()) {
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
      void nativeModule.connect(socketId, `wss://${ip}:${targetPort}`, certificatePin.trim()).catch((error: any) => {
        finish();
        reject(error);
      });
    });
  }

  return new Promise((resolve, reject) => {
    let ws: WebSocket | null = null;
    let isDone = false;

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
      ws = new WebSocket(`ws://${ip}:${targetPort}`);
      
      ws.onopen = () => {
        cleanup();
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
    checkIpAddress(ip, 9001, 1500, certificatePin)
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

/** Renders the Blinky mobile companion and coordinates its desktop connection. */
export default function App() {
  const [ipAddress, setIpAddress] = useState('');
  const [remoteToken, setRemoteToken] = useState('');
  const [certificatePin, setCertificatePin] = useState('');
  const {
    status,
    errorMsg,
    latestResponse,
    systemInfo,
    latestPowerEvent,
    connect,
    disconnect,
    sendCommand,
    sendQuery,
    fetchSystemInfo,
  } = usePCWebSocket();
  const [macAddress, setMacAddress] = useState('');
  const [wolBroadcastIp, setWolBroadcastIp] = useState('255.255.255.255');
  const [isSendingWol, setIsSendingWol] = useState(false);
  const [wolFeedback, setWolFeedback] = useState<string | null>(null);
  const [isWorkstationLocked, setIsWorkstationLocked] = useState(false);
  const [workstationPin, setWorkstationPin] = useState('');
  const isConnected = status === 'connected';
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryProgress, setDiscoveryProgress] = useState<string | null>(null);

  const [queryText, setQueryText] = useState('');
  const [runningQuery, setRunningQuery] = useState('');
  const [agentStatus, setAgentStatus] = useState<'idle' | 'processing' | 'success' | 'error'>('idle');
  
  // Custom message history state
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'blinky',
      text: 'Hello! I am Blinky. Ask me to do anything on your PC.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }
  ]);
  
  const activeBlinkyMsgIdRef = useRef<string | null>(null);
  const scrollViewRef = useRef<ScrollView>(null);

  const [showSettings, setShowSettings] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [timerSeconds, setTimerSeconds] = useState(0);
  const [previewImageUri, setPreviewImageUri] = useState<string | null>(null);

  const handleCaptureScreenshot = () => {
    setShowMenu(false);
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
  const audioRecorderRef = useRef<any>(null);
  const [isVoiceRecording, setIsVoiceRecording] = useState(false);
  const [isVoiceTranscribing, setIsVoiceTranscribing] = useState(false);

  // Cleanup audio recorder on unmount
  useEffect(() => {
    return () => {
      if (audioRecorderRef.current) {
        try {
          audioRecorderRef.current.stop();
        } catch (_) {}
      }
    };
  }, []);

  // Request Sarvam key from PC when connected
  useEffect(() => {
    if (isConnected) {
      sendCommand('get_sarvam_key' as any);
    } else {
      setSarvamApiKey(null);
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
      if (latestResponse.type === 'sarvam_key') {
        setSarvamApiKey(latestResponse.key);
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

  const handleQuery = () => {
    if (!queryText.trim()) {
      triggerHaptic('selection');
      Alert.alert('Empty query', 'Please enter a search/browsing query first.');
      return;
    }
    triggerHaptic('light');
    
    const query = queryText.trim();
    setRunningQuery(query);
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
        text: query,
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
  };

  // Voice recording handlers
  const startVoiceRecording = async () => {
    if (!isConnected) {
      triggerHaptic('selection');
      Alert.alert('Not Connected', 'Please establish a link to your PC first.');
      return;
    }
    if (!sarvamApiKey) {
      triggerHaptic('selection');
      Alert.alert('Configuration Missing', 'Waiting for Sarvam STT Key from your PC...');
      sendCommand('get_sarvam_key' as any);
      return;
    }

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

      const recorder = new AudioModule.AudioRecorder(RecordingPresets.HIGH_QUALITY);
      audioRecorderRef.current = recorder;
      await recorder.prepareToRecordAsync();
      recorder.record();
      triggerHaptic('heavy');
      setIsVoiceRecording(true);
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
    try {
      const recorder = audioRecorderRef.current;
      if (!recorder) {
        throw new Error('No active recorder found');
      }
      await recorder.stop();
      const uri = recorder.uri;
      audioRecorderRef.current = null;

      if (!uri) {
        throw new Error('No recording URI found');
      }

      const apiKeyToUse = sarvamApiKey;
      if (!apiKeyToUse) {
        throw new Error('Sarvam API key is not available');
      }

      const formData = new FormData();
      formData.append('file', {
        uri: uri,
        type: Platform.OS === 'android' ? 'audio/x-m4a' : 'audio/wav',
        name: Platform.OS === 'android' ? 'query.m4a' : 'query.wav',
      } as any);
      formData.append('model', 'saaras:v3');
      formData.append('language_code', 'en-IN');

      const res = await fetch('https://api.sarvam.ai/speech-to-text', {
        method: 'POST',
        headers: {
          'api-subscription-key': apiKeyToUse,
        },
        body: formData,
      });

      if (!res.ok) {
        let payload: any = {};
        try { payload = await res.json(); } catch {}
        throw new Error(payload.message || `HTTP ${res.status}`);
      }

      const data = await res.json();
      const transcript = data.transcript?.trim() || '';

      if (transcript) {
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
      } else {
        Alert.alert('STT Result', 'Could not hear anything clearly.');
      }
    } catch (err: any) {
      console.error('STT Voice error:', err);
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
    triggerHaptic('heavy');
    setAgentStatus('idle');
    setRunningQuery('');
    setQueryText('');
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
        if (savedToken) setRemoteToken(savedToken);
        if (savedPin) setCertificatePin(savedPin);

        // First attempt fast candidate probe (Tailscale, savedIp, USB reverse)
        const probedIp = await probeCandidateIps(savedPin || undefined);
        const detectedIp = getExpoHostIp();
        const initialIp = probedIp || savedIp || detectedIp || '';

        if (initialIp && initialIp !== 'localhost') {
          setIpAddress(initialIp);
          connect(initialIp, savedToken || undefined, savedPin || undefined);
        } else {
          // If no candidate responds, open settings and launch quiet Wi-Fi subnet scan
          setShowSettings(true);
          handleAutoDiscoverQuietly();
        }
      } catch (e) {
        console.error('Failed to load host IP address', e);
        setShowSettings(true);
        handleAutoDiscoverQuietly();
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

  // When connection succeeds, auto-close the settings card
  useEffect(() => {
    if (isConnected) {
      setShowSettings(false);
    }
  }, [isConnected]);

  // Quietly auto-discover and connect on start or when disconnected
  useEffect(() => {
    let active = true;
    if (status === 'disconnected' || status === 'error') {
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
  }, [status]);

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
    setShowMenu(false);
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

  /** Unlocks the host workstation by waking displays, dismissing lock screen, and typing optional PIN. */
  const handleUnlockWorkstation = (pin?: string) => {
    triggerHaptic('heavy');
    setShowMenu(false);
    const targetPin = (pin !== undefined ? pin : workstationPin).trim();
    const cmd = targetPin ? `unlock:${targetPin}` : 'unlock';
    const success = sendCommand(cmd as any);
    if (success) {
      setIsWorkstationLocked(false);
      setActionFeedback('⚡ Unlocking workstation...');
      setTimeout(() => setActionFeedback(null), 4000);
    } else {
      Alert.alert('Error', 'Failed to send unlock command. Check link to PC.');
    }
  };

  /** Handles Wake PC button tap, offering unlock if host workstation is locked. */
  const onWakePcPressed = () => {
    triggerHaptic('heavy');
    setShowMenu(false);
    if (isWorkstationLocked && isConnected) {
      Alert.alert(
        'Workstation Locked',
        'Your host PC is currently connected and locked. Would you like to unlock it or dispatch a Wake-on-LAN packet?',
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Unlock Workstation',
            onPress: () => handleUnlockWorkstation(),
          },
          {
            text: 'Send WoL Packet',
            onPress: () => handleSendWakeOnLan(),
          },
        ]
      );
      return;
    }
    handleSendWakeOnLan();
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
    setShowMenu(false);
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

    return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <LinearGradient colors={['#070313', '#090710', '#05020B']} style={styles.container}>
        <StatusBar barStyle="light-content" />
        <View style={styles.safeArea}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.keyboardView}
          >
          {/* Header */}
          <View style={styles.header}>
            <View style={styles.headerLeft}>
              <Ionicons name="sparkles" size={24} color="#FF5A36" style={{ marginRight: 8 }} />
              <Text style={styles.title}>BLINKY</Text>
            </View>
            <View style={styles.headerRight}>
              <TouchableOpacity
                style={styles.statusRowHeader}
                onPress={() => {
                  triggerHaptic('light');
                  setShowSettings(!showSettings);
                }}
                activeOpacity={0.7}
              >
                <View style={[styles.statusDotHeader, { backgroundColor: isConnected ? '#10B981' : (status === 'connecting' ? '#F59E0B' : '#EF4444') }]} />
                <Text style={styles.statusTextHeader}>
                  {isConnected ? 'Connected' : (status === 'connecting' ? 'Connecting...' : 'Disconnected')}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => { triggerHaptic('light'); setShowMenu(!showMenu); }} style={styles.menuBtn}>
                <Ionicons name="ellipsis-vertical" size={20} color="#FFFFFF" />
              </TouchableOpacity>
            </View>
          </View>

          {/* Three Dots Dropdown Overlay Menu */}
          {showMenu && (
            <View style={styles.dropdownMenu}>
              <TouchableOpacity style={styles.dropdownItem} onPress={() => { triggerHaptic('light'); setShowMenu(false); setShowSettings(!showSettings); }}>
                <Ionicons name="settings-outline" size={18} color="#FFFFFF" style={styles.dropdownIcon} />
                <Text style={styles.dropdownText}>Local Link Setup</Text>
              </TouchableOpacity>

              <View style={styles.dropdownDivider} />

              <TouchableOpacity
                style={styles.dropdownItem}
                onPress={onWakePcPressed}
                disabled={isSendingWol}
              >
                <Ionicons name="flash" size={18} color="#10B981" style={styles.dropdownIcon} />
                <Text style={[styles.dropdownText, { color: '#10B981', fontWeight: '600' }]}>
                  {isSendingWol ? 'Waking PC...' : isWorkstationLocked ? 'Wake / Unlock PC' : 'Wake PC (WoL)'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity style={styles.dropdownItem} onPress={() => triggerQuickAction('volume_mute', 'Mute')}>
                <Ionicons name="volume-mute-outline" size={18} color="#FFFFFF" style={styles.dropdownIcon} />
                <Text style={styles.dropdownText}>Mute Volume</Text>
              </TouchableOpacity>

              <TouchableOpacity style={styles.dropdownItem} onPress={handleCaptureScreenshot}>
                <Ionicons name="crop-outline" size={18} color="#FFFFFF" style={styles.dropdownIcon} />
                <Text style={styles.dropdownText}>Capture Screenshot</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.dropdownItem}
                onPress={() => {
                  if (isWorkstationLocked) {
                    handleUnlockWorkstation();
                  } else {
                    triggerQuickAction('lock' as any, 'Lock');
                  }
                }}
              >
                <Ionicons
                  name={isWorkstationLocked ? 'lock-open-outline' : 'lock-closed-outline'}
                  size={18}
                  color={isWorkstationLocked ? '#10B981' : '#FFFFFF'}
                  style={styles.dropdownIcon}
                />
                <Text style={[styles.dropdownText, isWorkstationLocked && { color: '#10B981', fontWeight: '600' }]}>
                  {isWorkstationLocked ? 'Unlock Workstation' : 'Lock Workstation'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity style={styles.dropdownItem} onPress={() => triggerPowerCommand('hibernate', 'Hibernate')}>
                <Ionicons name="moon" size={18} color="#A78BFA" style={styles.dropdownIcon} />
                <Text style={[styles.dropdownText, { color: '#A78BFA' }]}>Hibernate Host</Text>
              </TouchableOpacity>

              <TouchableOpacity style={styles.dropdownItem} onPress={() => triggerPowerCommand('sleep', 'Sleep')}>
                <Ionicons name="moon-outline" size={18} color="#FFFFFF" style={styles.dropdownIcon} />
                <Text style={styles.dropdownText}>Sleep Mode</Text>
              </TouchableOpacity>

              <TouchableOpacity style={styles.dropdownItem} onPress={() => triggerPowerCommand('restart', 'Reboot')}>
                <Ionicons name="refresh-outline" size={18} color="#FFFFFF" style={styles.dropdownIcon} />
                <Text style={styles.dropdownText}>Reboot PC</Text>
              </TouchableOpacity>

              <TouchableOpacity style={styles.dropdownItem} onPress={() => triggerPowerCommand('power_off', 'Shutdown')}>
                <Ionicons name="power-outline" size={18} color="#EF4444" style={styles.dropdownIcon} />
                <Text style={[styles.dropdownText, { color: '#EF4444' }]}>Shutdown PC</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Local Link Setup Box (Shows right below header when toggled) */}
          {showSettings && (
            <View style={styles.connectionCard}>
              <View style={styles.connectionHeaderRow}>
                <Text style={styles.connectionTitle}>Local Wi-Fi Link Setup</Text>
                <TouchableOpacity onPress={() => setShowSettings(false)}>
                  <Ionicons name="close" size={20} color="#8A86AA" />
                </TouchableOpacity>
              </View>
              <Text style={styles.connectionSubtitle}>
                {RELEASE_TRANSPORT
                  ? 'Enter the PC IP, remote token, and the pinned certificate value from the PC release build.'
                  : 'Enter your PC\'s IP (e.g. 100.122.62.2) or tap "Auto-Discover" to automatically locate and connect to Blinky.'}
              </Text>
              <View style={styles.inputWrapper}>
                <Ionicons name="link-outline" size={20} color="#6C6985" style={styles.inputIcon} />
                <TextInput
                  style={[styles.input, isConnected && styles.inputDisabled]}
                  placeholder="Enter PC IP (e.g. 100.122.62.2)"
                  placeholderTextColor="#6C6985"
                  value={ipAddress}
                  onChangeText={setIpAddress}
                  editable={!isConnected && status !== 'connecting'}
                  keyboardType="numeric"
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>
              <View style={styles.inputWrapper}>
                <Ionicons name="key-outline" size={20} color="#6C6985" style={styles.inputIcon} />
                <TextInput
                  style={[styles.input, isConnected && styles.inputDisabled]}
                  placeholder="Remote token (BLINKY_REMOTE_TOKEN)"
                  placeholderTextColor="#6C6985"
                  value={remoteToken}
                  onChangeText={setRemoteToken}
                  editable={!isConnected && status !== 'connecting'}
                  secureTextEntry
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>
              {RELEASE_TRANSPORT && (
                <View style={styles.inputWrapper}>
                  <Ionicons name="shield-checkmark-outline" size={20} color="#6C6985" style={styles.inputIcon} />
                  <TextInput
                    style={[styles.input, isConnected && styles.inputDisabled]}
                    placeholder="Certificate pin (sha256/...)"
                    placeholderTextColor="#6C6985"
                    value={certificatePin}
                    onChangeText={setCertificatePin}
                    editable={!isConnected && status !== 'connecting'}
                    autoCapitalize="none"
                    autoCorrect={false}
                  />
                </View>
              )}
              <View style={styles.inputWrapper}>
                <Ionicons name="lock-open-outline" size={20} color="#6C6985" style={styles.inputIcon} />
                <TextInput
                  style={styles.input}
                  placeholder="Workstation PIN / Password (optional)"
                  placeholderTextColor="#6C6985"
                  value={workstationPin}
                  onChangeText={(val) => {
                    setWorkstationPin(val);
                    AsyncStorage.setItem(WORKSTATION_PIN_STORAGE_KEY, val).catch(() => {});
                  }}
                  secureTextEntry
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>
              <View style={styles.actionRow}>

                {status !== 'connected' && status !== 'connecting' ? (
                  <>
                    <TouchableOpacity style={styles.connectBtn} onPress={handleConnect} activeOpacity={0.8} disabled={isDiscovering}>
                      <LinearGradient
                        colors={isDiscovering ? ['#4B5563', '#374151'] : ['#3B82F6', '#1D4ED8']}
                        start={{ x: 0, y: 0 }}
                        end={{ x: 1, y: 1 }}
                        style={styles.gradientBtn}
                      >
                        <Text style={styles.btnText}>Establish Link</Text>
                      </LinearGradient>
                    </TouchableOpacity>
                    <TouchableOpacity style={styles.discoverBtn} onPress={handleAutoDiscover} activeOpacity={0.8} disabled={isDiscovering}>
                      <LinearGradient
                        colors={isDiscovering ? ['#4B5563', '#374151'] : ['#8B5CF6', '#6D28D9']}
                        start={{ x: 0, y: 0 }}
                        end={{ x: 1, y: 1 }}
                        style={styles.gradientBtn}
                      >
                        <Text style={styles.btnText}>Auto-Discover</Text>
                      </LinearGradient>
                    </TouchableOpacity>
                  </>
                ) : (
                  <TouchableOpacity style={styles.disconnectBtn} onPress={() => { triggerHaptic('heavy'); disconnect(); }} activeOpacity={0.8}>
                    <Text style={styles.disconnectBtnText}>
                      {status === 'connecting' ? 'Cancel Connection' : 'Disconnect Link'}
                    </Text>
                  </TouchableOpacity>
                )}
              </View>
              {discoveryProgress && (
                <View style={styles.discoveryProgressContainer}>
                  <ActivityIndicator size="small" color="#8B5CF6" style={{ marginRight: 8 }} />
                  <Text style={styles.discoveryProgressText}>{discoveryProgress}</Text>
                </View>
              )}
              {errorMsg && (
                <View style={styles.errorContainer}>
                  <Text style={styles.errorText}>{errorMsg}</Text>
                </View>
              )}

              {/* Target MAC address for Wake-on-LAN */}
              <View style={{ marginTop: 12, paddingTop: 10, borderTopWidth: 1, borderTopColor: 'rgba(255, 255, 255, 0.08)' }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <Text style={{ color: '#8A86AA', fontSize: 11, fontWeight: '700', letterSpacing: 0.5 }}>TARGET PC MAC ADDRESS</Text>
                  {systemInfo?.network?.mac_address ? (
                    <TouchableOpacity
                      onPress={() => {
                        triggerHaptic('light');
                        setMacAddress(systemInfo.network.mac_address);
                      }}
                      style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: 'rgba(16, 185, 129, 0.15)', borderWidth: 1, borderColor: 'rgba(16, 185, 129, 0.3)' }}
                    >
                      <Text style={{ fontSize: 10, color: '#10B981', fontWeight: '700' }}>⚡ Auto-detected</Text>
                    </TouchableOpacity>
                  ) : null}
                </View>
                <View style={styles.inputWrapper}>
                  <Ionicons name="hardware-chip-outline" size={18} color="#6C6985" style={styles.inputIcon} />
                  <TextInput
                    style={styles.input}
                    placeholder={systemInfo?.network?.mac_address || "e.g. 68:c6:ac:a2:d2:30"}
                    placeholderTextColor="#6C6985"
                    value={macAddress}
                    onChangeText={setMacAddress}
                    autoCapitalize="none"
                    autoCorrect={false}
                  />
                </View>
              </View>
            </View>
          )}

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

          {/* Main Messaging Feed */}
          <ScrollView
            ref={scrollViewRef}
            showsVerticalScrollIndicator={false}
            contentContainerStyle={styles.chatScrollContent}
            keyboardShouldPersistTaps="handled"
          >
            {messages.map((message) => {
              const isUser = message.sender === 'user';
              return (
                <View key={message.id} style={isUser ? styles.userMessageRow : styles.blinkyMessageRow}>
                  {/* Blinky Avatar */}
                  {!isUser && (
                    <View style={styles.avatarContainer}>
                      <Ionicons name="sparkles" size={14} color="#FF5A36" />
                    </View>
                  )}

                  <View style={isUser ? styles.userMessageBubble : styles.blinkyMessageBubble}>
                    {/* Bubble main text */}
                    <Text style={styles.messageText}>{message.text}</Text>

                    {/* Nested Active Progress Card inside Blinky's response bubble */}
                    {!isUser && message.progress && (
                      <View style={styles.nestedProgressCard}>
                        {/* Progress slider line */}
                        <View style={styles.progressBarWrapper}>
                          <View style={styles.progressBarContainer}>
                            <View 
                              style={[
                                styles.progressBarFill, 
                                { width: `${message.progress.percent}%` }
                              ]} 
                            />
                          </View>
                          <Text style={styles.progressPercent}>{message.progress.percent}%</Text>
                        </View>

                        {/* Status message */}
                        <View style={styles.progressStatusRow}>
                          <View style={styles.progressStatusDot} />
                          <Text style={styles.progressStatusText} numberOfLines={2}>
                            {message.progress.statusText}
                          </Text>
                        </View>

                        {/* Stopwatch */}
                        <View style={styles.progressTimerRow}>
                          <Ionicons name="time-outline" size={14} color="#8A86AA" style={{ marginRight: 6 }} />
                          <Text style={styles.progressTimerText}>{formatTime(message.progress.duration)}</Text>
                        </View>
                      </View>
                    )}

                    {/* Screenshot results inside the final success bubble */}
                    {!isUser && message.screenshot_b64 && (
                      <TouchableOpacity
                        activeOpacity={0.88}
                        onPress={() => {
                          triggerHaptic('light');
                          setPreviewImageUri(`data:image/jpeg;base64,${message.screenshot_b64}`);
                        }}
                        style={styles.screenshotTouchable}
                      >
                        <Image
                          source={{ uri: `data:image/jpeg;base64,${message.screenshot_b64}` }}
                          style={styles.bubbleScreenshot}
                        />
                        <View style={styles.enlargeBadge}>
                          <Ionicons name="expand-outline" size={12} color="#FFFFFF" style={{ marginRight: 4 }} />
                          <Text style={styles.enlargeBadgeText}>Tap to enlarge</Text>
                        </View>
                      </TouchableOpacity>
                    )}

                    {/* Steps trace inside the final success bubble */}
                    {!isUser && message.steps && message.steps.length > 0 && (
                      <View style={styles.bubbleStepsContainer}>
                        {message.steps.map((step: any, index: number) => (
                          <View key={index} style={styles.bubbleStepItem}>
                            <View style={styles.bubbleStepBadge}>
                              <Text style={styles.bubbleStepBadgeText}>{step.step || index + 1}</Text>
                            </View>
                            <View style={styles.bubbleStepContent}>
                              <Text style={styles.bubbleStepText}>{step.instruction}</Text>
                              {step.target_text && (
                                <View style={styles.bubbleStepTargetBadge}>
                                  <Text style={styles.bubbleStepTargetText}>{step.target_text}</Text>
                                </View>
                              )}
                            </View>
                          </View>
                        ))}
                      </View>
                    )}
                  </View>

                  {/* Timestamp aligned right under user or blinky message */}
                  <View style={isUser ? styles.userMetaRow : styles.blinkyMetaRow}>
                    <Text style={styles.metaTimestamp}>{message.timestamp}</Text>
                    {isUser && (
                      <View style={styles.checkmarksRow}>
                        <Ionicons name="checkmark-done" size={14} color="#FF5A36" />
                      </View>
                    )}
                  </View>
                </View>
              );
            })}
          </ScrollView>

          {/* Bottom Chat Bar */}
          <View style={[styles.chatInputBar, !isConnected && styles.chatInputBarDisabled]}>
            {/* Voice Command Mic Circle Button */}
            {isVoiceTranscribing ? (
              <View style={styles.voiceSpinnerWrapper}>
                <ActivityIndicator size="small" color="#FF5A36" />
              </View>
            ) : (
              <TouchableOpacity
                style={[
                  styles.voiceMicBtn,
                  isVoiceRecording && styles.voiceMicBtnRecording,
                  !isConnected && styles.voiceMicBtnDisabled
                ]}
                onPress={toggleVoiceRecording}
                disabled={!isConnected || isVoiceTranscribing}
                activeOpacity={0.7}
              >
                <Ionicons 
                  name={isVoiceRecording ? "mic" : "mic"} 
                  size={20} 
                  color={isVoiceRecording ? "#EF4444" : "#FF5A36"} 
                />
              </TouchableOpacity>
            )}

            <TextInput
              style={styles.chatTextInput}
              placeholder="Message Blinky"
              placeholderTextColor="#6C6985"
              value={queryText}
              onChangeText={setQueryText}
              editable={isConnected && agentStatus !== 'processing'}
              autoCapitalize="none"
              autoCorrect={false}
              onSubmitEditing={handleQuery}
            />

            {/* Stop Action or Send Button */}
            {agentStatus === 'processing' ? (
              <TouchableOpacity 
                style={styles.stopCircleBtn} 
                onPress={handleStopQuery}
                activeOpacity={0.7}
              >
                <View style={styles.stopSquare} />
              </TouchableOpacity>
            ) : (
              <TouchableOpacity 
                style={[
                  styles.chatSendBtn, 
                  (!isConnected || !queryText.trim()) && styles.chatSendBtnDisabled
                ]}
                onPress={handleQuery}
                disabled={!isConnected || !queryText.trim()}
              >
                <Ionicons name="arrow-up" size={20} color="#FFFFFF" />
              </TouchableOpacity>
            )}
          </View>

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
        </KeyboardAvoidingView>
      </View>
    </LinearGradient>
    </GestureHandlerRootView>
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
  dropdownMenu: {
    position: 'absolute',
    top: Platform.OS === 'android' ? (StatusBar.currentHeight || 0) + 52 : 96,
    right: 20,
    width: 220,
    backgroundColor: '#16151A',
    borderRadius: 16,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
    zIndex: 1000,
    shadowColor: '#000',
    shadowOpacity: 0.5,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 10,
  },
  dropdownItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  dropdownIcon: {
    marginRight: 12,
    width: 20,
    textAlign: 'center',
  },
  dropdownText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
  dropdownDivider: {
    height: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
    marginVertical: 4,
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
});
