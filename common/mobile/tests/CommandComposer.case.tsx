import { expect, mock, test } from 'bun:test';

// Render the composer as a React element tree while keeping native UI and picker APIs inert.
let stateIndex = 0;
mock.module('react', () => ({
  default: {},
  __CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE: { A: null, recentlyCreatedOwnerStacks: 0 },
  useState(initial: unknown) { return [stateIndex++ === 0 ? true : initial, () => {}]; },
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
    queryText: '', setQueryText() {}, onSubmit() {}, onStop() {},
    status: 'idle', isConnected: true, isVoiceRecording: false,
    isVoiceTranscribing: false, onToggleVoice() {}, liveTranscript: undefined,
  });

  for (const label of ['File', 'Image', 'Camera', 'Screenshot']) {
    expect(findText(tree, label)).toBe(true);
  }
  expect(findText(tree, 'Send files to PC')).toBe(false);
});
