#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="AirTag Tracker"
BUNDLE_ID="local.danielyakobian.airtag-tracker"
VERSION="1.0"
BUILD_DIR="${SCRIPT_DIR}/build"
TEMP_APP="${BUILD_DIR}/${APP_NAME}.app"
TARGET_APP="/Applications/${APP_NAME}.app"
ICNS_SRC="${SCRIPT_DIR}/AirTagTracker.icns"

echo "==> Building ${APP_NAME}..."

mkdir -p "${BUILD_DIR}"
touch "${BUILD_DIR}/.metadata_never_index"
rm -rf "${TEMP_APP}"

# Compile AppleScript to application bundle
osacompile -o "${TEMP_APP}" "${SCRIPT_DIR}/launcher.applescript"

# Remove default AppleScript asset catalog so macOS uses our custom .icns
rm -f "${TEMP_APP}/Contents/Resources/Assets.car"

# Copy custom application icon
if [ -f "${ICNS_SRC}" ]; then
    cp "${ICNS_SRC}" "${TEMP_APP}/Contents/Resources/applet.icns"
    cp "${ICNS_SRC}" "${TEMP_APP}/Contents/Resources/AirTagTracker.icns"
fi

# Configure Info.plist
PLIST="${TEMP_APP}/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier ${BUNDLE_ID}" "${PLIST}" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string ${BUNDLE_ID}" "${PLIST}"

/usr/libexec/PlistBuddy -c "Set :CFBundleName ${APP_NAME}" "${PLIST}" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleName string ${APP_NAME}" "${PLIST}"

/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName ${APP_NAME}" "${PLIST}" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string ${APP_NAME}" "${PLIST}"

/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString ${VERSION}" "${PLIST}" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string ${VERSION}" "${PLIST}"

/usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${VERSION}" "${PLIST}" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string ${VERSION}" "${PLIST}"

/usr/libexec/PlistBuddy -c "Set :CFBundleIconFile AirTagTracker" "${PLIST}" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AirTagTracker" "${PLIST}"

/usr/libexec/PlistBuddy -c "Set :LSUIElement true" "${PLIST}" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "${PLIST}"

/usr/libexec/PlistBuddy -c "Set :OSAAppletShowStartupScreen false" "${PLIST}" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :OSAAppletShowStartupScreen bool false" "${PLIST}"

/usr/libexec/PlistBuddy -c "Set :NSAppleEventsUsageDescription Controls Google Chrome to activate or open the AirTag location history tracker." "${PLIST}" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :NSAppleEventsUsageDescription string Controls Google Chrome to activate or open the AirTag location history tracker." "${PLIST}"

# Sign ad-hoc
codesign --force --deep --sign - "${TEMP_APP}"

# Pre-quit running instances
osascript -e "tell application \"${APP_NAME}\" to quit" 2>/dev/null || killall "${APP_NAME}" 2>/dev/null || true

# Install to /Applications
echo "==> Installing to ${TARGET_APP}..."
rm -rf "${TARGET_APP}"
ditto "${TEMP_APP}" "${TARGET_APP}"
rm -rf "${TEMP_APP}"

# Re-register with LaunchServices
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "${TARGET_APP}"

echo "==> Verifying Spotlight indexing..."
mdfind "kMDItemFSName == '${APP_NAME}.app'"

# Check Dock pinning
echo "==> Pinning to Dock..."
python3 -c "
import plistlib, os, subprocess

plist_path = os.path.expanduser('~/Library/Preferences/com.apple.dock.plist')
with open(plist_path, 'rb') as f:
    d = plistlib.load(f)

apps = [item.get('tile-data', {}).get('file-label', '') for item in d.get('persistent-apps', [])]
if '${APP_NAME}' not in apps:
    cmd = [
        'defaults', 'write', 'com.apple.dock', 'persistent-apps', '-array-add',
        '<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>file:///Applications/${APP_NAME}.app/</string><key>_CFURLStringType</key><integer>15</integer></dict><key>file-label</key><string>${APP_NAME}</string></dict><key>tile-type</key><string>file-tile</string></dict>'
    ]
    subprocess.check_call(cmd)
    subprocess.check_call(['killall', 'Dock'])
    print('Added ${APP_NAME} to Dock.')
else:
    print('${APP_NAME} is already in the Dock.')
"

echo "==> Installed successfully."
