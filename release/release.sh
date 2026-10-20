#!/bin/bash
# Build, cloud-sign and notarize through the account signed into Xcode.
# Publishes nothing. TEAM_ID stays local; the public project has no team setting.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:?Usage: TEAM_ID=... release/release.sh VERSION BUILD_NUMBER}"
BUILD_NUMBER="${2:?Supply an increasing integer build number}"
: "${TEAM_ID:?Set your Apple Developer team ID locally}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Use a semantic version.' >&2; exit 1; }
[[ "$BUILD_NUMBER" =~ ^[1-9][0-9]*$ ]] || { echo 'Use a positive integer build.' >&2; exit 1; }
BUILD="release/build/$VERSION-$BUILD_NUMBER"
[[ ! -e "$BUILD" ]] || { echo 'Build folder exists; preserve it and use a new version.' >&2; exit 1; }
python3 release/prepare.py
mkdir -p "$BUILD"
xcodebuild -project TagTracker.xcodeproj -scheme TagTracker -configuration Release \
  -archivePath "$BUILD/TagTracker.xcarchive" -derivedDataPath "$BUILD/derived" \
  -allowProvisioningUpdates DEVELOPMENT_TEAM="$TEAM_ID" \
  MARKETING_VERSION="$VERSION" CURRENT_PROJECT_VERSION="$BUILD_NUMBER" archive -quiet
python3 - "$BUILD/ExportOptions.plist" "$TEAM_ID" <<'PY'
import plistlib,sys
with open(sys.argv[1],'wb') as stream:
    plistlib.dump({'method':'developer-id','destination':'upload','signingStyle':'automatic','teamID':sys.argv[2]},stream)
PY
xcodebuild -exportArchive -archivePath "$BUILD/TagTracker.xcarchive" \
  -exportOptionsPlist "$BUILD/ExportOptions.plist" -exportPath "$BUILD/export" -allowProvisioningUpdates -quiet
echo 'Waiting for Apple notarization. Re-run exportNotarizedApp with this archive if interrupted.'
attempt=0
until xcodebuild -exportNotarizedApp -archivePath "$BUILD/TagTracker.xcarchive" -exportPath "$BUILD/notarized"; do
  attempt=$((attempt+1))
  [[ "$attempt" -lt 90 ]] || { echo 'Notarization still pending. Preserve this archive and check Xcode Organizer.' >&2; exit 1; }
  sleep 20
done
APP="$BUILD/notarized/TagTracker.app"
codesign --verify --deep --strict "$APP"
spctl -a -vv -t exec "$APP"
ditto -c -k --keepParent "$APP" "$BUILD/TagTracker.zip"
python3 release/make-dmg.py "$APP" "$BUILD/TagTracker.dmg"
mkdir "$BUILD/feed"
ditto "$BUILD/TagTracker.zip" "$BUILD/feed/TagTracker.zip"
if [[ -e site/appcast.xml ]]; then cp site/appcast.xml "$BUILD/feed/appcast.xml"; fi
.tools/sparkle/bin/generate_appcast --account tagtracker --maximum-deltas 0 \
  --download-url-prefix "https://github.com/danielyaa5/tagtracker/releases/download/v$VERSION/" "$BUILD/feed"
echo "Prepared DMG, notarized app ZIP and signed update feed in $BUILD. Nothing published."
