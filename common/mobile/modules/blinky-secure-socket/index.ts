import { requireNativeModule, type EventSubscription } from 'expo-modules-core';

type NativeSecureSocketFunctions = {
  connect(id: string, url: string, pin: string): Promise<void>;
  sendText(id: string, data: string): Promise<void>;
  sendBinary(id: string, base64Data: string): Promise<void>;
  close(id: string): Promise<void>;
  getSecureValue(key: string): Promise<string | null>;
  setSecureValue(key: string, value: string): Promise<void>;
  deleteSecureValue(key: string): Promise<void>;
  hashFile(uri: string): Promise<{ size: number; sha256: string }>;
  uploadFile(options: {
    sourceUri: string;
    transferId: string;
    url: string;
    token: string;
    pin?: string;
    size: number;
    chunkSize: number;
    offset: number;
  }): Promise<{ transferId: string; uploadOffset: number; complete: boolean }>;
  downloadFile(options: {
    transferId: string;
    url: string;
    token: string;
    pin?: string;
    size: number;
    sha256: string;
    filename: string;
  }): Promise<string>;
};

export type SecureSocketEvent = {
  id: string;
  data?: string;
  error?: string;
  direction?: 'upload' | 'download';
  bytes?: number;
  total?: number;
};

export type SecureSocketEventName = 'onOpen' | 'onMessage' | 'onClose' | 'onError' | 'onTransferProgress';

type NativeSecureSocketModule = NativeSecureSocketFunctions & {
  addListener<EventName extends SecureSocketEventName>(
    eventName: EventName,
    listener: (event: SecureSocketEvent) => void,
  ): EventSubscription;
};

const NativeModule = requireNativeModule<NativeSecureSocketModule>('BlinkySecureSocket');

export const connect = (id: string, url: string, pin: string) => NativeModule.connect(id, url, pin);
export const sendText = (id: string, data: string) => NativeModule.sendText(id, data);
export const sendBinary = (id: string, base64Data: string) => NativeModule.sendBinary(id, base64Data);
export const close = (id: string) => NativeModule.close(id);
export const getSecureValue = (key: string) => NativeModule.getSecureValue(key);
export const setSecureValue = (key: string, value: string) => NativeModule.setSecureValue(key, value);
export const deleteSecureValue = (key: string) => NativeModule.deleteSecureValue(key);
export const hashFile = (uri: string) => NativeModule.hashFile(uri);
export const uploadFile = (options: Parameters<NativeSecureSocketFunctions['uploadFile']>[0]) => NativeModule.uploadFile(options);
export const downloadFile = (options: Parameters<NativeSecureSocketFunctions['downloadFile']>[0]) => NativeModule.downloadFile(options);

export function addListener(
  name: SecureSocketEventName,
  listener: (event: SecureSocketEvent) => void,
): EventSubscription {
  return NativeModule.addListener(name, listener);
}
