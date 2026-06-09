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
  ScrollView
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { usePCWebSocket, ConnectionStatus } from './usePCWebSocket';
import Markdown from 'react-native-markdown-display';

const STORAGE_KEY = '@blinky_pc_ip';

export default function App() {
  const [ipAddress, setIpAddress] = useState('');
  const { status, errorMsg, latestResponse, connect, disconnect, sendCommand, sendQuery } = usePCWebSocket();
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  const [queryText, setQueryText] = useState('');
  const [agentStatus, setAgentStatus] = useState<'idle' | 'processing' | 'success' | 'error'>('idle');
  const [agentProgressMsg, setAgentProgressMsg] = useState('');
  const [agentResult, setAgentResult] = useState<any>(null);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [reasoning, setReasoning] = useState<string | null>(null);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [wilStage, setWilStage] = useState<'none' | 'planning' | 'retrieving' | 'acquiring' | 'processing' | 'reasoning'>('none');

  // Watch for incoming WebSocket responses from Python daemon
  useEffect(() => {
    if (latestResponse) {
      const { status: respStatus, data, error } = latestResponse;
      if (respStatus === 'processing') {
        setAgentStatus('processing');
        if (data?.status && data.status.startsWith('wil_')) {
          const stage = data.status.replace('wil_', '');
          setWilStage(stage);
        }
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
        setWilStage('none');
      } else if (respStatus === 'error') {
        setAgentStatus('error');
        setAgentError(error?.message || 'An unknown error occurred');
        setWilStage('none');
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
    setWilStage(webSearchEnabled ? 'planning' : 'none');

    const success = sendQuery(queryText.trim(), generateUuid(), webSearchEnabled);
    if (!success) {
      setAgentStatus('error');
      setAgentError('Failed to send query. Check PC connection.');
    }
  };


  // Load saved IP address on launch
  useEffect(() => {
    async function loadIp() {
      try {
        const savedIp = await AsyncStorage.getItem(STORAGE_KEY);
        if (savedIp) {
          setIpAddress(savedIp);
        }
      } catch (e) {
        console.error('Failed to load host IP address', e);
      }
    }
    loadIp();
  }, []);

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

  const isConnected = status === 'connected';
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
                  <TouchableOpacity style={styles.connectBtn} onPress={handleConnect} activeOpacity={0.8}>
                    <LinearGradient
                      colors={['#3B82F6', '#1D4ED8']}
                      start={{ x: 0, y: 0 }}
                      end={{ x: 1, y: 1 }}
                      style={styles.gradientBtn}
                    >
                      <Text style={styles.btnText}>Establish Link</Text>
                    </LinearGradient>
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity style={styles.disconnectBtn} onPress={disconnect} activeOpacity={0.8}>
                    <Text style={styles.disconnectBtnText}>
                      {status === 'connecting' ? 'Cancel Connection' : 'Disconnect Link'}
                    </Text>
                  </TouchableOpacity>
                )}
              </View>

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
              <Text style={styles.cardSubtitle}>Ask Blinky to search or navigate the web for you</Text>
              
              <View style={styles.inputWrapper}>
                <Ionicons name="sparkles-outline" size={20} color="#6C6985" style={styles.inputIcon} />
                <TextInput
                  style={[styles.input, !isConnected && styles.inputDisabled]}
                  placeholder="Ask something (e.g. Look up @MrBeast)"
                  placeholderTextColor="#6C6985"
                  value={queryText}
                  onChangeText={setQueryText}
                  editable={isConnected && agentStatus !== 'processing'}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                <TouchableOpacity
                  style={[
                    styles.webSearchToggle,
                    webSearchEnabled && styles.webSearchToggleActive
                  ]}
                  onPress={() => setWebSearchEnabled(!webSearchEnabled)}
                  disabled={!isConnected || agentStatus === 'processing'}
                  activeOpacity={0.7}
                >
                  <Ionicons 
                    name="globe-outline" 
                    size={20} 
                    color={webSearchEnabled ? '#3B82F6' : '#6C6985'} 
                  />
                </TouchableOpacity>
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
                  {webSearchEnabled && wilStage !== 'none' && (
                    <View style={styles.progressBarWrapper}>
                      <View style={styles.progressSegmentsRow}>
                        {['planning', 'retrieving', 'acquiring', 'processing', 'reasoning'].map((stage, idx) => {
                          const stages = ['planning', 'retrieving', 'acquiring', 'processing', 'reasoning'];
                          const currentStageIndex = stages.indexOf(wilStage);
                          const isCompletedOrActive = idx <= currentStageIndex;
                          return (
                            <View
                              key={stage}
                              style={[
                                styles.progressSegment,
                                isCompletedOrActive ? styles.progressSegmentActive : styles.progressSegmentInactive
                              ]}
                            />
                          );
                        })}
                      </View>
                      <Text style={styles.progressStageText}>
                        Web Search: {wilStage.charAt(0).toUpperCase() + wilStage.slice(1)}...
                      </Text>
                    </View>
                  )}
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
                  {agentResult.response ? (
                    <Markdown style={markdownStyles}>{agentResult.response}</Markdown>
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

            {/* PC Controls Card (Glassmorphic) */}
            <View style={[styles.card, !isConnected && styles.cardDisabled]}>
              <Text style={styles.cardTitle}>Power Operations</Text>
              <Text style={styles.cardSubtitle}>Ensure your PC is on the same local Wi-Fi network</Text>
              
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
  cardSubtitle: {
    fontSize: 13,
    color: '#6C6985',
    marginBottom: 20,
    marginTop: -16,
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
  footer: {
    textAlign: 'center',
    color: '#494660',
    fontSize: 11,
    marginTop: 18,
    letterSpacing: 0.5,
  },
  webSearchToggle: {
    padding: 8,
    borderRadius: 8,
    backgroundColor: 'transparent',
    marginLeft: 8,
  },
  webSearchToggleActive: {
    backgroundColor: 'rgba(59, 130, 246, 0.15)',
  },
  progressBarWrapper: {
    marginTop: 12,
    alignItems: 'center',
    width: '100%',
  },
  progressSegmentsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    width: '100%',
    marginBottom: 6,
    gap: 4,
  },
  progressSegment: {
    flex: 1,
    height: 6,
    borderRadius: 3,
  },
  progressSegmentActive: {
    backgroundColor: '#3B82F6',
  },
  progressSegmentInactive: {
    backgroundColor: 'rgba(255, 255, 255, 0.12)',
  },
  progressStageText: {
    color: '#8A86AA',
    fontSize: 12,
    fontWeight: '600',
    marginTop: 4,
  },
});

const markdownStyles = {
  body: {
    color: '#FFFFFF',
    fontSize: 14,
    lineHeight: 22,
    fontWeight: '500' as const,
  },
  heading1: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '700' as const,
    marginTop: 12,
    marginBottom: 6,
  },
  heading2: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600' as const,
    marginTop: 10,
    marginBottom: 6,
  },
  paragraph: {
    marginBottom: 8,
  },
  bullet_list: {
    marginBottom: 8,
  },
  ordered_list: {
    marginBottom: 8,
  },
  link: {
    color: '#3B82F6',
  },
};

