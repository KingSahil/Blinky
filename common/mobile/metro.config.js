const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// Prevent Metro from watching intermediate native build outputs in android/
config.resolver.blockList = [
  /.*[\/\\]android[\/\\].*/,
];

module.exports = config;
