import { expect, mock, test } from 'bun:test';

// Render the composer as a React element tree while keeping native UI and picker APIs inert.
let stateIndex = 0;
let selectedFiles: any[] = [];
let attachmentUpdates = 0;
mock.module('react', () => ({
  default: {},
  __CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE: { A: null, recentlyCreatedOwnerStacks: 0 },
  useState(initial: unknown) {
    const index = stateIndex++;
    return [index === 0 ? true : index === 1 ? selectedFiles : initial, (update: any) => {
      if (index === 1) {
        attachmentUpdates++;
        selectedFiles = typeof update === 'function' ? update(selectedFiles) : update;
      }
    }];
  },
  useRef(initial: unknown) { return { current: initial }; },
  useEffect() {},
}));
mock.module('react-native', () => {
  const View = 'View';
  return {
    View, Text: 'Text', TextInput: 'TextInput', TouchableOpacity: 'TouchableOpacity', Image: 'Image', ScrollView: 'ScrollView',
    StyleSheet: { create: (styles: unknown) => styles },
    Animated: {
      Value: class { interpolate() { return 0; } },
      spring: () => ({ start() {} }),
      View,
    },
    Keyboard: {}, Platform: { OS: 'android' }, LayoutAnimation: {}, UIManager: {}, Alert: {},
  };
});

function findButton(element: any, icon: string): any {
  if (!element || typeof element !== 'object') return null;
  const children = element.props?.children;
  const list = Array.isArray(children) ? children : [children];
  if (element.props?.onPress && list.some(child => child?.props?.name === icon)) return element;
  for (const child of list) {
    const found = findButton(child, icon);
    if (found) return found;
  }
  return null;
}

test('pending sends cannot duplicate files and newly added attachments survive acceptance', async () => {
  stateIndex = 0;
  const original = { uri: 'original', name: 'receipt.png' };
  const later = { uri: 'later', name: 'next.png' };
  selectedFiles = [original];
  let accept!: (value: boolean) => void;
  let calls = 0;
  const tree = CommandComposer({
    queryText: 'Put this in receipts', setQueryText() {},
    onSubmit: () => { calls++; return new Promise(resolve => { accept = resolve; }); }, onStop() {},
    status: 'idle', isConnected: true, isVoiceRecording: false,
    isVoiceTranscribing: false, onToggleVoice() {},
  });
  const send = findButton(tree, 'arrow-up').props.onPress;
  const first = send();
  await send();
  expect(calls).toBe(1);
  selectedFiles = [original, later];
  accept(true);
  await first;
  expect(selectedFiles).toEqual([later]);
});

test('a rejected submission preserves attachments for retry', async () => {
  stateIndex = 0;
  selectedFiles = [{ uri: 'original', name: 'receipt.png' }];
  attachmentUpdates = 0;
  const tree = CommandComposer({
    queryText: 'Summarize', setQueryText() {}, async onSubmit() { return false; }, onStop() {},
    status: 'idle', isConnected: true, isVoiceRecording: false,
    isVoiceTranscribing: false, onToggleVoice() {},
  });
  await findButton(tree, 'arrow-up').props.onPress();
  expect(attachmentUpdates).toBe(0);
  expect(selectedFiles).toHaveLength(1);
});
mock.module('@expo/vector-icons', () => ({ Ionicons: 'Ionicons' }));
mock.module('expo-haptics', () => ({ ImpactFeedbackStyle: { Light: 'light', Medium: 'medium' }, impactAsync() {} }));
mock.module('expo-image-picker', () => ({}));
mock.module('expo-document-picker', () => ({}));

const { CommandComposer } = await import('../components/CommandComposer');

function findText(element: any, target: string): boolean {
  if (element === target) return true;
  if (!element || typeof element !== 'object') return false;
  if (typeof element.type === 'function') return findText(element.type(element.props), target);
  const children = element.props?.children;
  for (const child of Array.isArray(children) ? children : [children]) {
    if (findText(child, target)) return true;
  }
  return false;
}

test('attachment menu keeps four chat choices without a separate transfer entry', () => {
  stateIndex = 0;
  const tree = CommandComposer({
    queryText: '', setQueryText() {}, async onSubmit() { return true; }, onStop() {},
    status: 'idle', isConnected: true, isVoiceRecording: false,
    isVoiceTranscribing: false, onToggleVoice() {}, liveTranscript: undefined,
  });

  for (const label of ['File', 'Image', 'Camera', 'Screenshot']) {
    expect(findText(tree, label)).toBe(true);
  }
  expect(findText(tree, 'Send files to PC')).toBe(false);
});
