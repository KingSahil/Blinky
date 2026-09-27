import { NativeModules, Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

export const MAC_STORAGE_KEY = '@blinky_pc_mac';
export const WOL_BROADCAST_STORAGE_KEY = '@blinky_wol_broadcast';

let RNWol: any = null;
try {
  RNWol = require('react-native-wol').default;
} catch (e) {
  console.log('react-native-wol native module not available in this environment');
}

/** Returns whether a MAC address contains exactly six hexadecimal octets. */
export const validateMacAddress = (mac: string): boolean => {
  const clean = mac.trim().replace(/[:\-]/g, '');
  return clean.length === 12 && /^[0-9a-fA-F]{12}$/.test(clean);
};

/** Normalizes a valid MAC address to lowercase colon-separated octets. */
export const formatMacAddress = (mac: string): string => {
  const clean = mac.trim().replace(/[:\-]/g, '').toLowerCase();
  if (clean.length !== 12) return mac.trim();
  return clean.match(/.{1,2}/g)?.join(':') || mac.trim();
};

export interface WolResult {
  success: boolean;
  message: string;
}

/**
 * Dispatches a Wake-on-LAN Magic Packet (UDP 9 & 7) to power on the target PC over LAN.
 */
export const sendWakeOnLan = async (
  macAddress: string,
  broadcastIp = '255.255.255.255',
  burstCount = 3
): Promise<WolResult> => {
  const formattedMac = formatMacAddress(macAddress);

  if (!validateMacAddress(formattedMac)) {
    return {
      success: false,
      message: `Invalid MAC address: "${macAddress}". Expected format: XX:XX:XX:XX:XX:XX`,
    };
  }

  // Save the latest used MAC address for persistence
  try {
    await AsyncStorage.setItem(MAC_STORAGE_KEY, formattedMac);
  } catch (e) {}

  if (Platform.OS === 'web') {
    return {
      success: false,
      message: 'Wake-on-LAN UDP packets cannot be sent directly from web browsers.',
    };
  }

  if (!RNWol || !NativeModules.Wol) {
    const msg =
      'Wake-on-LAN requires the compiled Blinky APK. Expo Go does not support raw native UDP packets.';
    console.warn(`[WoL] ${msg}`);
    return {
      success: false,
      message: msg,
    };
  }

  return new Promise((resolve) => {
    let sentCount = 0;
    let anySuccess = false;

    /** Sends each packet in the configured Wake-on-LAN burst. */
    const sendBurst = (index: number) => {
      try {
        RNWol.send(broadcastIp, formattedMac, (success: boolean, msg: string) => {
          if (success) anySuccess = true;
          sentCount += 1;

          if (index + 1 < burstCount) {
            setTimeout(() => sendBurst(index + 1), 150);
          } else {
            if (anySuccess) {
              resolve({
                success: true,
                message: `Magic Packet dispatched to ${formattedMac} (${burstCount}x burst).`,
              });
            } else {
              resolve({
                success: false,
                message: msg || 'Failed to dispatch Wake-on-LAN packet.',
              });
            }
          }
        });
      } catch (err: any) {
        resolve({
          success: false,
          message: err?.message || 'Failed to invoke Wake-on-LAN native module.',
        });
      }
    };

    sendBurst(0);
  });
};
