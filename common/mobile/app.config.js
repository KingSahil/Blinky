const { expo } = require('./app.json');

const ios = {
  ...expo.ios,
  infoPlist: {
    ...expo.ios?.infoPlist,
    NSAllowsArbitraryLoads: true,
  },
};
const plugins = [
  ...(expo.plugins || []),
  ['expo-build-properties', { android: { usesCleartextTraffic: true } }],
];

module.exports = { ...expo, ios, plugins };
