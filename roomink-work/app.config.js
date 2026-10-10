const usesDistributionPush = ['preview', 'testflight'].includes(process.env.EAS_BUILD_PROFILE);

/** @type {import('expo/config').ExpoConfig} */
module.exports = {
  name: 'Roomink Work',
  slug: 'roomink-work',
  version: '1.0.0',
  scheme: 'roomink-work',
  orientation: 'portrait',
  icon: './assets/icon.png',
  userInterfaceStyle: 'automatic',
  ios: {
    bundleIdentifier: 'net.roomink.work',
    supportsTablet: true,
    infoPlist: {
      ITSAppUsesNonExemptEncryption: false,
    },
    entitlements: {
      // Development builds use the APNs sandbox. TestFlight builds must use production.
      'aps-environment': usesDistributionPush ? 'production' : 'development',
    },
  },
  android: {
    adaptiveIcon: {
      backgroundColor: '#FFFFFF',
      foregroundImage: './assets/android-icon-foreground.png',
    },
    predictiveBackGestureEnabled: false,
  },
  web: { favicon: './assets/favicon.png' },
  extra: {
    eas: { projectId: 'a0245d29-73b8-440e-9b45-8197a7c88273' },
  },
  plugins: [
    'expo-router',
    'expo-secure-store',
    ['@twilio/voice-react-native-sdk', {
      apsEnvironment: usesDistributionPush ? 'production' : 'development',
      microphoneUsageDescription: 'Roomink Work は受信した通話の音声を扱うためにマイクを使用します。',
    }],
  ],
};
