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
  Modal
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import * as Network from 'expo-network';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { Audio } from 'expo-av';
import { usePCWebSocket, ConnectionStatus } from './usePCWebSocket';

const STORAGE_KEY = '@blinky_pc_ip';

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

const checkIpAddress = (ip: string, port = 9001, timeoutMs = 800): Promise<string> => {
  return new Promise((resolve, reject) => {
    let ws: WebSocket | null = null;
    const timer = setTimeout(() => {
      if (ws) {
        try {
          ws.close();
        } catch (e) {}
      }
      reject(new Error('Timeout'));
    }, timeoutMs);

    try {
      ws = new WebSocket(`ws://${ip}:${port}`);
      
      ws.onopen = () => {
        clearTimeout(timer);
        try {
          ws?.close();
        } catch (e) {}
        resolve(ip);
      };
      
      ws.onerror = () => {
        clearTimeout(timer);
        try {
          ws?.close();
        } catch (e) {}
        reject(new Error('Connection error'));
      };
      
      ws.onclose = () => {
        clearTimeout(timer);
      };
    } catch (e) {
      clearTimeout(timer);
      reject(e);
    }
  });
};

const scanSubnet = async (
  subnet: string,
  onProgress?: (msg: string) => void
): Promise<string | null> => {
  const port = 9001;
  const timeoutMs = 600;
  const concurrency = 35;
  
  const ips: string[] = [];
  for (let i = 1; i <= 254; i++) {
    ips.push(`${subnet}.${i}`);
  }

  for (let i = 0; i < ips.length; i += concurrency) {
    const batch = ips.slice(i, i + concurrency);
    if (onProgress) {
      onProgress(`Searching subnet (checking IPs ${i + 1} to ${Math.min(i + concurrency, 254)})...`);
    }
    
    const promises = batch.map(ip => 
      checkIpAddress(ip, port, timeoutMs)
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

export default function App() {
  const [ipAddress, setIpAddress] = useState('');
  const { status, errorMsg, latestResponse, connect, disconnect, sendCommand, sendQuery } = usePCWebSocket();
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
  const [voiceRecording, setVoiceRecording] = useState<Audio.Recording | null>(null);
  const [isVoiceRecording, setIsVoiceRecording] = useState(false);
  const [isVoiceTranscribing, setIsVoiceTranscribing] = useState(false);

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
      Alert.alert('Empty query', 'Please enter a search/browsing query first.');
      return;
    }
    
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
      Alert.alert('Not Connected', 'Please establish a link to your PC first.');
      return;
    }
    if (!sarvamApiKey) {
      Alert.alert('Configuration Missing', 'Waiting for Sarvam STT Key from your PC...');
      sendCommand('get_sarvam_key' as any);
      return;
    }

    try {
      const perm = await Audio.requestPermissionsAsync();
      if (perm.status !== 'granted') {
        Alert.alert('Permission Denied', 'Microphone access is required for voice commands.');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const { recording } = await Audio.Recording.createAsync({
        android: {
          extension: '.m4a',
          outputFormat: Audio.AndroidOutputFormat.MPEG_4,
          audioEncoder: Audio.AndroidAudioEncoder.AAC,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 64000,
        },
        ios: {
          extension: '.wav',
          audioQuality: Audio.IOSAudioQuality.HIGH,
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 64000,
          linearPCMBitDepth: 16,
          linearPCMIsBigEndian: false,
          linearPCMIsFloat: false,
        },
        web: {
          mimeType: 'audio/webm',
          bitsPerSecond: 64000,
        }
      });
      setVoiceRecording(recording);
      setIsVoiceRecording(true);
    } catch (err) {
      console.error('Failed to start voice recording', err);
      Alert.alert('Error', 'Failed to start microphone recording.');
    }
  };

  const stopVoiceRecording = async () => {
    if (!voiceRecording) return;
    setIsVoiceRecording(false);
    setIsVoiceTranscribing(true);
    try {
      await voiceRecording.stopAndUnloadAsync();
      const uri = voiceRecording.getURI();
      setVoiceRecording(null);

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

  // Load saved IP address on launch
  useEffect(() => {
    async function loadIp() {
      try {
        const savedIp = await AsyncStorage.getItem(STORAGE_KEY);
        const detectedIp = getExpoHostIp();
        const initialIp = savedIp || detectedIp || 'localhost';
        setIpAddress(initialIp);
        connect(initialIp);
      } catch (e) {
        console.error('Failed to load host IP address', e);
        const fallback = getExpoHostIp() || 'localhost';
        setIpAddress(fallback);
        connect(fallback);
      }
    }
    loadIp();
  }, []);

  // Quietly auto-discover and connect on start
  useEffect(() => {
    let active = true;
    if (status === 'disconnected' || status === 'error') {
      const timer = setTimeout(async () => {
        if (!active) return;
        try {
          const deviceIp = await Network.getIpAddressAsync();
          if (deviceIp && deviceIp !== '0.0.0.0' && deviceIp !== '127.0.0.1') {
            console.log('Auto-discovery scan started...');
            handleAutoDiscoverQuietly();
          }
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
      const ip = await Network.getIpAddressAsync();
      if (!ip || ip === '0.0.0.0') return;
      const ipParts = ip.split('.');
      if (ipParts.length !== 4) return;
      const subnet = `${ipParts[0]}.${ipParts[1]}.${ipParts[2]}`;
      const foundIp = await scanSubnet(subnet);
      if (foundIp) {
        setIpAddress(foundIp);
        await AsyncStorage.setItem(STORAGE_KEY, foundIp);
        connect(foundIp);
      }
    } catch (err) {}
  };

  const validateIp = (ip: string): boolean => {
    const trimmed = ip.trim();
    if (!trimmed) return false;
    const ipPattern = /^([a-zA-Z0-9-]+\.)*[a-zA-Z0-9-]+(:\d+)?$/;
    const ipv4Pattern = /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}(:\d+)?$/;
    return ipPattern.test(trimmed) || ipv4Pattern.test(trimmed) || trimmed === 'localhost';
  };

  const handleConnect = async () => {
    if (!validateIp(ipAddress)) {
      Alert.alert('Invalid Address', 'Please enter a valid IP address or hostname.');
      return;
    }
    try {
      await AsyncStorage.setItem(STORAGE_KEY, ipAddress.trim());
    } catch (e) {}
    connect(ipAddress);
  };

  const handleAutoDiscover = async () => {
    setIsDiscovering(true);
    setDiscoveryProgress('Getting network details...');
    try {
      const ip = await Network.getIpAddressAsync();
      if (!ip || ip === '0.0.0.0') {
        Alert.alert('Discovery Failed', 'Could not get device IP address.');
        return;
      }
      const ipParts = ip.split('.');
      const subnet = `${ipParts[0]}.${ipParts[1]}.${ipParts[2]}`;
      const foundIp = await scanSubnet(subnet, (msg) => {
        setDiscoveryProgress(msg);
      });
      if (foundIp) {
        setIpAddress(foundIp);
        await AsyncStorage.setItem(STORAGE_KEY, foundIp);
        connect(foundIp);
      } else {
        Alert.alert('Blinky Not Found', 'Make sure the desktop app is running and connected.');
      }
    } catch (err: any) {
      Alert.alert('Error', `Discovery failed: ${err.message}`);
    } finally {
      setIsDiscovering(false);
      setDiscoveryProgress(null);
    }
  };

  const triggerPowerCommand = (command: 'power_off' | 'restart' | 'sleep', label: string) => {
    setShowMenu(false);
    Alert.alert(
      `Confirm Action`,
      `Are you sure you want to trigger "${label}" on your PC?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Confirm',
          style: 'destructive',
          onPress: () => {
            const success = sendCommand(command);
            if (success) {
              setActionFeedback(`Command "${label}" sent!`);
              setTimeout(() => setActionFeedback(null), 3000);
            } else {
              Alert.alert('Error', 'Failed to send command. Check link.');
            }
          },
        },
      ]
    );
  };

  const triggerQuickAction = (command: any, label: string) => {
    setShowMenu(false);
    const success = sendCommand(command);
    if (success) {
      setActionFeedback(`Command "${label}" sent!`);
      setTimeout(() => setActionFeedback(null), 3000);
    } else {
      Alert.alert('Error', 'Failed to send command. Check link.');
    }
  };

  return (
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
              <View style={styles.statusRowHeader}>
                <View style={[styles.statusDotHeader, { backgroundColor: isConnected ? '#FF5A36' : '#EF4444' }]} />
                <Text style={styles.statusTextHeader}>{isConnected ? 'Connected' : 'Disconnected'}</Text>
              </View>
              <TouchableOpacity onPress={() => setShowMenu(!showMenu)} style={styles.menuBtn}>
                <Ionicons name="ellipsis-vertical" size={20} color="#FFFFFF" />
              </TouchableOpacity>
            </View>
          </View>

          {/* Three Dots Dropdown Overlay Menu */}
          {showMenu && (
            <View style={styles.dropdownMenu}>
              <TouchableOpacity style={styles.dropdownItem} onPress={() => { setShowMenu(false); setShowSettings(!showSettings); }}>
                <Ionicons name="settings-outline" size={18} color="#FFFFFF" style={styles.dropdownIcon} />
                <Text style={styles.dropdownText}>Local Link Setup</Text>
              </TouchableOpacity>
              
              <View style={styles.dropdownDivider} />

              <TouchableOpacity style={styles.dropdownItem} onPress={() => triggerQuickAction('volume_mute', 'Mute')}>
                <Ionicons name="volume-mute-outline" size={18} color="#FFFFFF" style={styles.dropdownIcon} />
                <Text style={styles.dropdownText}>Mute Volume</Text>
              </TouchableOpacity>

              <TouchableOpacity style={styles.dropdownItem} onPress={handleCaptureScreenshot}>
                <Ionicons name="crop-outline" size={18} color="#FFFFFF" style={styles.dropdownIcon} />
                <Text style={styles.dropdownText}>Capture Screenshot</Text>
              </TouchableOpacity>

              <TouchableOpacity style={styles.dropdownItem} onPress={() => triggerQuickAction('lock' as any, 'Lock')}>
                <Ionicons name="lock-closed-outline" size={18} color="#FFFFFF" style={styles.dropdownIcon} />
                <Text style={styles.dropdownText}>Lock Workstation</Text>
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
              <Text style={styles.connectionTitle}>Local Link Setup</Text>
              <View style={styles.inputWrapper}>
                <Ionicons name="link-outline" size={20} color="#6C6985" style={styles.inputIcon} />
                <TextInput
                  style={[styles.input, isConnected && styles.inputDisabled]}
                  placeholder="Enter PC IP (e.g. 192.168.1.15)"
                  placeholderTextColor="#6C6985"
                  value={ipAddress}
                  onChangeText={setIpAddress}
                  editable={!isConnected && status !== 'connecting'}
                  keyboardType="numeric"
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
                        <Text style={styles.btnText}>Scan Subnet</Text>
                      </LinearGradient>
                    </TouchableOpacity>
                  </>
                ) : (
                  <TouchableOpacity style={styles.disconnectBtn} onPress={disconnect} activeOpacity={0.8}>
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
            </View>
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
                        onPress={() => setPreviewImageUri(`data:image/jpeg;base64,${message.screenshot_b64}`)}
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

          {/* Fullscreen Image Preview Modal */}
          <Modal
            visible={!!previewImageUri}
            transparent={true}
            animationType="fade"
            onRequestClose={() => setPreviewImageUri(null)}
          >
            <View style={styles.fullscreenModalContainer}>
              <TouchableOpacity
                style={styles.fullscreenCloseBtn}
                onPress={() => setPreviewImageUri(null)}
                activeOpacity={0.8}
              >
                <Ionicons name="close" size={26} color="#FFFFFF" />
              </TouchableOpacity>

              {previewImageUri && (
                <ScrollView
                  maximumZoomScale={5}
                  minimumZoomScale={1}
                  showsHorizontalScrollIndicator={false}
                  showsVerticalScrollIndicator={false}
                  centerContent={true}
                  contentContainerStyle={styles.zoomScrollViewContent}
                  style={styles.zoomScrollView}
                >
                  <TouchableWithoutFeedback onPress={() => setPreviewImageUri(null)}>
                    <View style={styles.fullscreenImageWrapper}>
                      <Image
                        source={{ uri: previewImageUri }}
                        style={styles.fullscreenImage}
                        resizeMode="contain"
                      />
                    </View>
                  </TouchableWithoutFeedback>
                </ScrollView>
              )}
            </View>
          </Modal>
        </KeyboardAvoidingView>
      </View>
    </LinearGradient>
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
    backgroundColor: 'rgba(21, 17, 43, 0.65)',
    borderRadius: 24,
    padding: 20,
    marginHorizontal: 20,
    marginTop: 10,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  connectionTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#FFFFFF',
    marginBottom: 16,
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
  zoomScrollView: {
    width: '100%',
    height: '100%',
  },
  zoomScrollViewContent: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
