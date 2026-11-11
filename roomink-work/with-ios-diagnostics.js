const fs = require('fs');
const path = require('path');
const { withXcodeProject } = require('expo/config-plugins');

module.exports = function withIosDiagnostics(config) {
  return withXcodeProject(config, config => {
    const sdkRoot = path.dirname(require.resolve('@twilio/voice-react-native-sdk/package.json'));
    const sdk = JSON.parse(fs.readFileSync(path.join(sdkRoot, 'package.json'), 'utf8'));
    if (sdk.version !== '1.8.0') throw new Error('Review Roomink diagnostic native hooks before upgrading Twilio SDK');
    const root = config.modRequest.platformProjectRoot;
    const filename = 'RoominkDiagnostics.m';
    fs.copyFileSync(path.join(__dirname, 'native', filename), path.join(root, filename));
    const project = config.modResults;
    if (!project.hasFile(filename)) {
      project.addSourceFile(filename, { target: project.getFirstTarget().uuid }, project.getFirstProject().firstProject.mainGroup);
    }
    return config;
  });
};
