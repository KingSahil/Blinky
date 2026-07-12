import React, { useState, useEffect } from 'react';
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
  SafeAreaView,
  StatusBar,
  ScrollView,
  Image
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import * as Network from 'expo-network';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
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
          ws.close();
        } catch (e) {}
        resolve(ip);
      };
      
      ws.onerror = () => {
        clearTimeout(timer);
        try {
          ws.close();
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
  const timeoutMs = 600; // 600ms is a sweet spot for local Wi-Fi pings
  const concurrency = 35; // Parallel checks
  
  const ips: string[] = [];
  for (let i = 1; i <= 254; i++) {
    ips.push(`${subnet}.${i}`);
  }

  // Scan in parallel batches
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

export default function App() {
  const [ipAddress, setIpAddress] = useState('');
  const { status, errorMsg, latestResponse, connect, disconnect, sendCommand, sendQuery } = usePCWebSocket();
  const isConnected = status === 'connected';
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryProgress, setDiscoveryProgress] = useState<string | null>(null);

  const [queryText, setQueryText] = useState('');
  const [agentStatus, setAgentStatus] = useState<'idle' | 'processing' | 'success' | 'error'>('idle');
  const [agentProgressMsg, setAgentProgressMsg] = useState('');
  const [agentResult, setAgentResult] = useState<any>(null);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [reasoning, setReasoning] = useState<string | null>(null);

  // Watch for incoming WebSocket responses from Python daemon
  useEffect(() => {
    if (latestResponse) {
      const { status: respStatus, data, error } = latestResponse;
      if (respStatus === 'processing') {
        setAgentStatus('processing');
        if (data?.is_chunk) {
          setAgentProgressMsg(prev => prev + (data?.message || ''));
        } else {
          setAgentProgressMsg(data?.message || 'Processing...');
          if (data?.confidence !== undefined) {
            setConfidence(data.confidence);
          }
          if (data?.reasoning !== undefined) {
            setReasoning(data.reasoning);
          }
        }
        setAgentError(null);
      } else if (respStatus === 'success') {
        setAgentStatus('success');
        setAgentResult(data);
        setAgentError(null);
      } else if (respStatus === 'error') {
        setAgentStatus('error');
        setAgentError(error?.message || 'An unknown error occurred');
      }
    }
  }, [latestResponse]);

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
    
    setAgentStatus('processing');
    setAgentProgressMsg('');
    setAgentResult(null);
    setAgentError(null);
    setConfidence(null);
    setReasoning(null);

    const success = sendQuery(queryText.trim(), generateUuid());
    if (!success) {
      setAgentStatus('error');
      setAgentError('Failed to send query. Check PC connection.');
    }
  };


  // Load saved IP address on launch, or prefill from the Expo dev server host.
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

  // Quietly auto-discover and connect on start if connection fails and device is on Wi-Fi
  useEffect(() => {
    let active = true;
    if (status === 'disconnected' || status === 'error') {
      const timer = setTimeout(async () => {
        if (!active) return;
        try {
          const deviceIp = await Network.getIpAddressAsync();
          if (deviceIp && deviceIp !== '0.0.0.0' && deviceIp !== '127.0.0.1') {
            console.log('Connection failed and Wi-Fi IP detected. Starting auto-discovery...');
            handleAutoDiscover();
          }
        } catch (e) {
          // No local network IP, ignore auto-discovery
        }
      }, 2500);
      return () => {
        active = false;
        clearTimeout(timer);
      };
    }
  }, [status]);

  // Listen to physical volume keys when connected
  useEffect(() => {
    if (!isConnected || !VolumeManager) return;

    try {
      // Disable system volume UI on phone when app is active
      VolumeManager.showNativeVolumeUI({ enabled: false });

      let lastVolume: number | null = null;

      // Get initial volume
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

        // Hack to keep volume off the edges (100% or 0%) so listener always fires on future button presses
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

  // Validate IP address format (simple pattern check)
  const validateIp = (ip: string): boolean => {
    const trimmed = ip.trim();
    if (!trimmed) return false;
    
    // Check if it's a valid host (either domain name, localhost, or IPv4 address)
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
    } catch (e) {
      console.error('Failed to save host IP address', e);
    }

    connect(ipAddress);
  };

  const handleAutoDiscover = async () => {
    setIsDiscovering(true);
    setDiscoveryProgress('Getting network details...');
    try {
      const ip = await Network.getIpAddressAsync();
      if (!ip || ip === '0.0.0.0') {
        Alert.alert('Discovery Failed', 'Could not get device IP address. Make sure Wi-Fi is enabled.');
        setIsDiscovering(false);
        setDiscoveryProgress(null);
        return;
      }

      const ipParts = ip.split('.');
      if (ipParts.length !== 4) {
        Alert.alert('Discovery Failed', `Unsupported network IP format: ${ip}`);
        setIsDiscovering(false);
        setDiscoveryProgress(null);
        return;
      }

      const subnet = `${ipParts[0]}.${ipParts[1]}.${ipParts[2]}`;
      const foundIp = await scanSubnet(subnet, (msg) => {
        setDiscoveryProgress(msg);
      });
      
      if (foundIp) {
        setIpAddress(foundIp);
        await AsyncStorage.setItem(STORAGE_KEY, foundIp);
        connect(foundIp);
      } else {
        Alert.alert('Blinky Not Found', 'Could not auto-detect Blinky on this network. Make sure the desktop app is running and connected to the same Wi-Fi.');
      }
    } catch (err: any) {
      console.error('Discovery error:', err);
      Alert.alert('Error', `Discovery failed: ${err.message || err}`);
    } finally {
      setIsDiscovering(false);
      setDiscoveryProgress(null);
    }
  };

  const triggerCommand = (command: 'power_off' | 'restart' | 'sleep', label: string) => {
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
              Alert.alert('Error', 'Failed to send command. Are you connected?');
            }
          },
        },
      ]
    );
  };

  const triggerVolumeCommand = (command: 'volume_up' | 'volume_down' | 'volume_mute') => {
    sendCommand(command);
  };

  const getStatusDetails = (currentStatus: ConnectionStatus) => {
    switch (currentStatus) {
      case 'connected':
        return {
          colors: ['#10B981', '#059669'] as const,
          label: 'CONNECTED',
          icon: 'checkmark-circle-outline' as const,
          borderColor: 'rgba(16, 185, 129, 0.4)'
        };
      case 'connecting':
        return {
          colors: ['#F59E0B', '#D97706'] as const,
          label: 'CONNECTING',
          icon: 'sync-outline' as const,
          borderColor: 'rgba(245, 158, 11, 0.4)'
        };
      case 'error':
        return {
          colors: ['#EF4444', '#DC2626'] as const,
          label: 'ERROR',
          icon: 'alert-circle-outline' as const,
          borderColor: 'rgba(239, 68, 68, 0.4)'
        };
      case 'disconnected':
      default:
        return {
          colors: ['#4B5563', '#374151'] as const,
          label: 'DISCONNECTED',
          icon: 'ellipse-outline' as const,
          borderColor: 'rgba(255, 255, 255, 0.08)'
        };
    }
  };

  const statusDetails = getStatusDetails(status);

  return (
    <LinearGradient colors={['#0A051C', '#0F092A', '#06030F']} style={styles.container}>
      <StatusBar barStyle="light-content" />
        <SafeAreaView style={styles.safeArea}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.keyboardView}
          >
            <ScrollView 
              showsVerticalScrollIndicator={false} 
              contentContainerStyle={styles.scrollContent}
              keyboardShouldPersistTaps="handled"
              keyboardDismissMode="on-drag"
            >
            {/* Header with Blinky Branding */}
            <View style={styles.header}>
              <View style={styles.logoBadge}>
                <Ionicons name="desktop-outline" size={26} color="#3B82F6" />
              </View>
              <Text style={styles.title}>BLINKY</Text>
              <Text style={styles.subtitle}>Remote PC Control Console</Text>
            </View>

            {/* Connection Control Card (Glassmorphic) */}
            <View style={[styles.card, { borderColor: statusDetails.borderColor }]}>
              <View style={styles.cardHeader}>
                <Text style={styles.cardTitle}>Local Link Setup</Text>
                
                <View style={styles.statusBadgeContainer}>
                  <LinearGradient
                    colors={statusDetails.colors}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 0 }}
                    style={styles.statusBadge}
                  >
                    {status === 'connecting' ? (
                      <ActivityIndicator size="small" color="#FFFFFF" style={{ marginRight: 6 }} />
                    ) : (
                      <Ionicons name={statusDetails.icon} size={14} color="#FFF" style={{ marginRight: 4 }} />
                    )}
                    <Text style={styles.statusText}>{statusDetails.label}</Text>
                  </LinearGradient>
                </View>
              </View>
              
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
                        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                          <Ionicons name="scan-outline" size={16} color="#FFF" style={{ marginRight: 6 }} />
                          <Text style={styles.btnText}>Auto Discover</Text>
                        </View>
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
                  <Ionicons name="warning-outline" size={16} color="#EF4444" style={{ marginRight: 6 }} />
                  <Text style={styles.errorText}>{errorMsg}</Text>
                </View>
              )}
            </View>

            {/* Blinky Browser Agent Card (Glassmorphic) */}
            <View style={[styles.card, !isConnected && styles.cardDisabled]}>
              <Text style={styles.cardTitle}>AI Browser Assistant</Text>
              
              <View style={styles.inputWrapper}>
                <Ionicons name="sparkles-outline" size={20} color="#6C6985" style={styles.inputIcon} />
                <TextInput
                  style={[styles.input, !isConnected && styles.inputDisabled]}
                  placeholder="Ask something"
                  placeholderTextColor="#6C6985"
                  value={queryText}
                  onChangeText={setQueryText}
                  editable={isConnected && agentStatus !== 'processing'}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              <View style={styles.actionRow}>
                <TouchableOpacity 
                  style={[styles.connectBtn, (!isConnected || agentStatus === 'processing') && styles.btnDisabled]} 
                  onPress={handleQuery} 
                  disabled={!isConnected || agentStatus === 'processing'}
                  activeOpacity={0.8}
                >
                  <LinearGradient
                    colors={isConnected && agentStatus !== 'processing' ? ['#10B981', '#059669'] : ['#4B5563', '#374151']}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 1 }}
                    style={styles.gradientBtn}
                  >
                    <Text style={styles.btnText}>Ask Blinky</Text>
                  </LinearGradient>
                </TouchableOpacity>
              </View>

              {agentStatus === 'processing' && (
                <View style={[styles.feedbackContainer, { flexDirection: 'column', alignItems: 'stretch' }]}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center' }}>
                    <ActivityIndicator size="small" color="#10B981" style={{ marginRight: 8 }} />
                    <Text style={styles.feedbackText}>{agentProgressMsg}</Text>
                  </View>
                  {confidence !== null && (
                    <View style={{ marginTop: 8, borderTopWidth: 1, borderTopColor: 'rgba(16, 185, 129, 0.2)', paddingTop: 6 }}>
                      <Text style={{ color: '#8A86AA', fontSize: 12, textAlign: 'center' }}>
                        Match Confidence: <Text style={{ color: '#10B981', fontWeight: 'bold' }}>{confidence}%</Text>
                      </Text>
                      {reasoning ? (
                        <Text style={{ color: 'rgba(255, 255, 255, 0.6)', fontSize: 11, textAlign: 'center', marginTop: 2 }}>
                          {reasoning}
                        </Text>
                      ) : null}
                    </View>
                  )}
                </View>
              )}

              {agentStatus === 'error' && agentError && (
                <View style={styles.errorContainer}>
                  <Ionicons name="warning-outline" size={16} color="#EF4444" style={{ marginRight: 6 }} />
                  <Text style={styles.errorText}>{agentError}</Text>
                </View>
              )}

              {agentStatus === 'success' && agentResult && (
                <View style={styles.resultContainer}>
                  <View style={styles.resultHeader}>
                    <Ionicons name="checkmark-circle" size={18} color="#10B981" style={{ marginRight: 6 }} />
                    <Text style={styles.resultTitle}>Result Details</Text>
                  </View>
                  {agentResult.screenshot_b64 || (agentResult.steps && agentResult.steps.length > 0) ? (
                    <View>
                      {agentResult.response ? (
                        <Text style={[styles.resultParagraph, { marginBottom: 8 }]}>{agentResult.response}</Text>
                      ) : null}

                      {agentResult.screenshot_b64 ? (
                        <Image
                          source={{ uri: `data:image/jpeg;base64,${agentResult.screenshot_b64}` }}
                          style={styles.screenshotImage}
                        />
                      ) : null}

                      {agentResult.steps && agentResult.steps.length > 0 ? (
                        <View style={styles.stepsContainer}>
                          {agentResult.steps.map((step: any, index: number) => (
                            <View key={index} style={styles.stepItem}>
                              <View style={styles.stepNumberBadge}>
                                <Text style={styles.stepNumberText}>{step.step || index + 1}</Text>
                              </View>
                              <View style={styles.stepContent}>
                                <Text style={styles.stepInstruction}>{step.instruction}</Text>
                                {step.target_text ? (
                                  <View style={styles.stepTargetBadge}>
                                    <Text style={styles.stepTargetText}>{step.target_text}</Text>
                                  </View>
                                ) : null}
                              </View>
                            </View>
                          ))}
                        </View>
                      ) : null}
                    </View>
                  ) : agentResult.response ? (
                    <Text style={styles.resultParagraph}>{agentResult.response}</Text>
                  ) : (
                    Object.entries(agentResult).map(([key, value]) => {
                      if (key === 'raw_metadata' && Array.isArray(value)) {
                        return null;
                      }
                      const displayValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
                      return (
                        <View key={key} style={styles.resultRow}>
                          <Text style={styles.resultKey}>{key.replace(/_/g, ' ').toUpperCase()}:</Text>
                          <Text style={styles.resultValue}>{displayValue}</Text>
                        </View>
                      );
                    })
                  )}
                </View>
              )}
            </View>

            {/* PC Volume Control Card (Glassmorphic) */}
            <View style={[styles.card, !isConnected && styles.cardDisabled]}>
              <Text style={styles.cardTitle}>Audio & Volume</Text>
              
              <View style={styles.volumeRow}>
                {/* Volume Down */}
                <TouchableOpacity
                  style={[styles.volumeBtn, !isConnected && styles.btnDisabled]}
                  disabled={!isConnected}
                  onPress={() => triggerVolumeCommand('volume_down')}
                  activeOpacity={0.7}
                >
                  <LinearGradient
                    colors={isConnected ? ['#1E293B', '#0F172A'] : ['#1F1D2B', '#1F1D2B']}
                    style={styles.volumeBtnGradient}
                  >
                    <Ionicons name="volume-low-outline" size={24} color={isConnected ? '#3B82F6' : '#4B5563'} />
                    <Text style={[styles.volumeBtnText, !isConnected && styles.textDisabled]}>Down</Text>
                  </LinearGradient>
                </TouchableOpacity>

                {/* Mute */}
                <TouchableOpacity
                  style={[styles.volumeBtn, !isConnected && styles.btnDisabled]}
                  disabled={!isConnected}
                  onPress={() => triggerVolumeCommand('volume_mute')}
                  activeOpacity={0.7}
                >
                  <LinearGradient
                    colors={isConnected ? ['#1E293B', '#0F172A'] : ['#1F1D2B', '#1F1D2B']}
                    style={styles.volumeBtnGradient}
                  >
                    <Ionicons name="volume-mute-outline" size={24} color={isConnected ? '#EF4444' : '#4B5563'} />
                    <Text style={[styles.volumeBtnText, !isConnected && styles.textDisabled]}>Mute</Text>
                  </LinearGradient>
                </TouchableOpacity>

                {/* Volume Up */}
                <TouchableOpacity
                  style={[styles.volumeBtn, !isConnected && styles.btnDisabled]}
                  disabled={!isConnected}
                  onPress={() => triggerVolumeCommand('volume_up')}
                  activeOpacity={0.7}
                >
                  <LinearGradient
                    colors={isConnected ? ['#1E293B', '#0F172A'] : ['#1F1D2B', '#1F1D2B']}
                    style={styles.volumeBtnGradient}
                  >
                    <Ionicons name="volume-high-outline" size={24} color={isConnected ? '#10B981' : '#4B5563'} />
                    <Text style={[styles.volumeBtnText, !isConnected && styles.textDisabled]}>Up</Text>
                  </LinearGradient>
                </TouchableOpacity>
              </View>
            </View>

            {/* PC Controls Card (Glassmorphic) */}
            <View style={[styles.card, !isConnected && styles.cardDisabled]}>
              <Text style={styles.cardTitle}>Power Operations</Text>
              
              {actionFeedback && (
                <View style={styles.feedbackContainer}>
                  <Ionicons name="checkmark-circle" size={18} color="#10B981" style={{ marginRight: 6 }} />
                  <Text style={styles.feedbackText}>{actionFeedback}</Text>
                </View>
              )}

              <View style={styles.controlGrid}>
                {/* Sleep Operation */}
                <TouchableOpacity
                  style={[styles.controlBtn, !isConnected && styles.btnDisabled]}
                  disabled={!isConnected}
                  onPress={() => triggerCommand('sleep', 'Sleep')}
                  activeOpacity={0.75}
                >
                  <LinearGradient
                    colors={isConnected ? ['#1E293B', '#0F172A'] : ['#1F1D2B', '#1F1D2B']}
                    style={styles.controlGradient}
                  >
                    <View style={[styles.iconContainer, isConnected && { backgroundColor: 'rgba(59, 130, 246, 0.15)' }]}>
                      <Ionicons name="moon" size={24} color={isConnected ? '#3B82F6' : '#4B5563'} />
                    </View>
                    <View style={styles.btnMeta}>
                      <Text style={[styles.controlBtnTitle, !isConnected && styles.textDisabled]}>Suspend (Sleep)</Text>
                      <Text style={styles.controlBtnDesc}>Place computer in low-power sleep mode</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={isConnected ? '#4B5563' : '#374151'} />
                  </LinearGradient>
                </TouchableOpacity>

                {/* Restart Operation */}
                <TouchableOpacity
                  style={[styles.controlBtn, !isConnected && styles.btnDisabled]}
                  disabled={!isConnected}
                  onPress={() => triggerCommand('restart', 'Restart')}
                  activeOpacity={0.75}
                >
                  <LinearGradient
                    colors={isConnected ? ['#1E293B', '#0F172A'] : ['#1F1D2B', '#1F1D2B']}
                    style={styles.controlGradient}
                  >
                    <View style={[styles.iconContainer, isConnected && { backgroundColor: 'rgba(245, 158, 11, 0.15)' }]}>
                      <Ionicons name="sync" size={24} color={isConnected ? '#F59E0B' : '#4B5563'} />
                    </View>
                    <View style={styles.btnMeta}>
                      <Text style={[styles.controlBtnTitle, !isConnected && styles.textDisabled]}>Reboot System</Text>
                      <Text style={styles.controlBtnDesc}>Restart operating system immediately</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={isConnected ? '#4B5563' : '#374151'} />
                  </LinearGradient>
                </TouchableOpacity>

                {/* Power Off Operation */}
                <TouchableOpacity
                  style={[styles.controlBtn, !isConnected && styles.btnDisabled]}
                  disabled={!isConnected}
                  onPress={() => triggerCommand('power_off', 'Shut Down')}
                  activeOpacity={0.75}
                >
                  <LinearGradient
                    colors={isConnected ? ['#1E293B', '#0F172A'] : ['#1F1D2B', '#1F1D2B']}
                    style={styles.controlGradient}
                  >
                    <View style={[styles.iconContainer, isConnected && { backgroundColor: 'rgba(239, 68, 68, 0.15)' }]}>
                      <Ionicons name="power" size={24} color={isConnected ? '#EF4444' : '#4B5563'} />
                    </View>
                    <View style={styles.btnMeta}>
                      <Text style={[styles.controlBtnTitle, !isConnected && styles.textDisabled]}>Shutdown PC</Text>
                      <Text style={styles.controlBtnDesc}>Power off target machine safely</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={isConnected ? '#4B5563' : '#374151'} />
                  </LinearGradient>
                </TouchableOpacity>
              </View>
            </View>
            
            <Text style={styles.footer}>Blinky Link Protocol v1.0.0</Text>
            </ScrollView>
          </KeyboardAvoidingView>
        </SafeAreaView>
      </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  safeArea: {
    flex: 1,
  },
  keyboardView: {
    flex: 1,
  },
  scrollContent: {
    paddingVertical: 24,
    paddingHorizontal: 20,
    flexGrow: 1,
    justifyContent: 'center',
  },
  header: {
    alignItems: 'center',
    marginBottom: 24,
  },
  logoBadge: {
    width: 54,
    height: 54,
    borderRadius: 18,
    backgroundColor: 'rgba(59, 130, 246, 0.12)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
    borderWidth: 1,
    borderColor: 'rgba(59, 130, 246, 0.25)',
  },
  title: {
    fontSize: 32,
    fontWeight: '900',
    color: '#FFFFFF',
    letterSpacing: 6,
    textShadowColor: 'rgba(59, 130, 246, 0.3)',
    textShadowOffset: { width: 0, height: 4 },
    textShadowRadius: 12,
  },
  subtitle: {
    fontSize: 14,
    color: '#8A86AA',
    marginTop: 6,
    fontWeight: '600',
    letterSpacing: 1.5,
  },
  card: {
    backgroundColor: 'rgba(21, 17, 43, 0.65)',
    borderRadius: 24,
    padding: 20,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.4,
    shadowRadius: 24,
    elevation: 10,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  cardDisabled: {
    opacity: 0.5,
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 0.3,
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
    height: 54,
    flex: 1,
    color: '#FFFFFF',
    fontSize: 16,
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
    height: 52,
    justifyContent: 'center',
    alignItems: 'center',
  },
  btnText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  disconnectBtn: {
    flex: 1,
    height: 52,
    borderRadius: 16,
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.3)',
  },
  disconnectBtnText: {
    color: '#EF4444',
    fontSize: 15,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  statusBadgeContainer: {
    borderRadius: 12,
    overflow: 'hidden',
  },
  statusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusText: {
    color: '#FFFFFF',
    fontWeight: '800',
    fontSize: 10,
    letterSpacing: 1,
  },
  errorContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
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
  feedbackContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(16, 185, 129, 0.1)',
    borderColor: 'rgba(16, 185, 129, 0.25)',
    borderWidth: 1,
    padding: 10,
    borderRadius: 12,
    marginBottom: 16,
  },
  feedbackText: {
    color: '#10B981',
    fontSize: 14,
    fontWeight: '700',
  },
  controlGrid: {
    gap: 12,
  },
  controlBtn: {
    borderRadius: 16,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.04)',
  },
  btnDisabled: {
    borderColor: 'transparent',
  },
  controlGradient: {
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  iconContainer: {
    width: 48,
    height: 48,
    borderRadius: 14,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  btnMeta: {
    flex: 1,
    paddingHorizontal: 16,
  },
  controlBtnTitle: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  textDisabled: {
    color: '#4B5563',
  },
  controlBtnDesc: {
    color: 'rgba(255, 255, 255, 0.45)',
    fontSize: 11,
    marginTop: 3,
  },
  resultContainer: {
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderRadius: 16,
    padding: 16,
    marginTop: 14,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  resultHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.08)',
    paddingBottom: 8,
  },
  resultTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#10B981',
    letterSpacing: 0.5,
  },
  resultRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.03)',
  },
  resultKey: {
    fontSize: 12,
    fontWeight: '700',
    color: '#8A86AA',
    marginRight: 8,
  },
  resultValue: {
    fontSize: 13,
    fontWeight: '600',
    color: '#FFFFFF',
    flex: 1,
    textAlign: 'right',
  },
  resultParagraph: {
    fontSize: 14,
    color: '#FFFFFF',
    lineHeight: 22,
    fontWeight: '500',
  },
  screenshotImage: {
    width: '100%',
    height: 220,
    resizeMode: 'contain',
    borderRadius: 12,
    marginVertical: 12,
    backgroundColor: '#0F172A',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
  },
  stepsContainer: {
    marginTop: 10,
  },
  stepItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: 'rgba(255, 255, 255, 0.03)',
    padding: 12,
    borderRadius: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  stepNumberBadge: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: '#FF5722',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
    marginTop: 2,
  },
  stepNumberText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '800',
  },
  stepContent: {
    flex: 1,
  },
  stepInstruction: {
    color: '#FFFFFF',
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '500',
  },
  stepTargetBadge: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(255, 87, 34, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
    marginTop: 6,
    borderWidth: 1,
    borderColor: 'rgba(255, 87, 34, 0.25)',
  },
  stepTargetText: {
    color: '#FF7043',
    fontSize: 11,
    fontWeight: '700',
  },
  volumeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
    marginTop: 12,
  },
  volumeBtn: {
    flex: 1,
    borderRadius: 16,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.04)',
  },
  volumeBtnGradient: {
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  volumeBtnText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },
  footer: {
    textAlign: 'center',
    color: '#494660',
    fontSize: 11,
    marginTop: 18,
    letterSpacing: 0.5,
  },
});

