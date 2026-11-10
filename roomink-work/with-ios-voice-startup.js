const { withAppDelegate } = require('expo/config-plugins');

const delegateAnchor = '    let delegate = ReactNativeDelegate()';
const moduleAnchor = '  // Extension point for config-plugins';

module.exports = function withIosVoiceStartup(config) {
  return withAppDelegate(config, (config) => {
    const { language, contents } = config.modResults;
    if (language !== 'swift' || !contents.includes(delegateAnchor) || !contents.includes(moduleAnchor)) {
      throw new Error('Roomink Work: unsupported Expo AppDelegate for iOS voice startup');
    }

    config.modResults.contents = contents
      .replace(delegateAnchor, delegateAnchor + '\n    delegate.startIncomingVoice()')
      .replace(moduleAnchor, `  private var incomingVoice: (any RCTBridgeModule)?

  func startIncomingVoice() {
    guard let voiceClass = NSClassFromString("TwilioVoiceReactNative") as? NSObject.Type,
          let voice = voiceClass.init() as? (NSObject & RCTBridgeModule) else {
      assertionFailure("Roomink Work: Twilio voice module is unavailable")
      return
    }
    let initializePushRegistry = NSSelectorFromString("initializePushRegistry")
    guard voice.responds(to: initializePushRegistry) else {
      assertionFailure("Roomink Work: Twilio PushKit initializer is unavailable")
      return
    }
    incomingVoice = voice
    _ = voice.perform(initializePushRegistry)
  }

  // Reuse the module holding the PushKit registry and CallKit state in React Native.
  @objc(extraModulesForBridge:)
  func extraModules(for bridge: RCTBridge!) -> [any RCTBridgeModule]! {
    guard let incomingVoice else { return [] }
    return [incomingVoice]
  }`);
    return config;
  });
};
