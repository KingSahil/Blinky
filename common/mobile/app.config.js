const { expo } = require('./app.json');

const isRelease = process.env.EXPO_PUBLIC_BLINKY_TRANSPORT_MODE === 'release';
const ios = { ...expo.ios, infoPlist: { ...expo.ios?.infoPlist } };
const plugins = [
  ...(expo.plugins || []),
  ['expo-build-properties', { android: { usesCleartextTraffic: !isRelease } }],
];

if (isRelease) {
  delete ios.infoPlist.NSAppTransportSecurity;
} else {
  ios.infoPlist.NSAppTransportSecurity = {
    ...ios.infoPlist.NSAppTransportSecurity,
    NSAllowsArbitraryLoads: true,
  };
}

module.exports = { ...expo, ios, plugins };
