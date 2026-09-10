import { requireNativeModule, type EventSubscription } from 'expo-modules-core';

type NativeSecureSocketFunctions = {
  connect(id: string, url: string, pin: string): Promise<void>;
  sendText(id: string, data: string): Promise<void>;
  sendBinary(id: string, base64Data: string): Promise<void>;
  close(id: string): Promise<void>;
  getSecureValue(key: string): Promise<string | null>;
  setSecureValue(key: string, value: string): Promise<void>;
  deleteSecureValue(key: string): Promise<void>;
};

export type SecureSocketEvent = {
  id: string;
  data?: string;
  error?: string;
};

export type SecureSocketEventName = 'onOpen' | 'onMessage' | 'onClose' | 'onError';

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

export function addListener(
  name: SecureSocketEventName,
  listener: (event: SecureSocketEvent) => void,
): EventSubscription {
  return NativeModule.addListener(name, listener);
}
