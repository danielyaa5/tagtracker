# Releasing TagTracker

The first packaged release supports Apple silicon and macOS 14+. Real collection has been exercised on macOS 27. Do not claim compatibility with other Find My layouts without testing them.

## One-time setup

Install Xcode, Go, Python 3.9+, and XcodeGen (`brew install xcodegen`). Sign into your Apple Developer account in Xcode. The app is distributed with Developer ID cloud signing and Apple notarization, independently of Mac App Store distribution.

`python3 release/prepare.py` downloads checksum-pinned Sparkle 2.10.0 and CPython 3.13.16, builds the native collectors, renders the app icon from the shared SVG, and generates the Xcode project. Downloaded dependencies, generated projects, archives, and signing output are ignored by Git. Each release includes its own Python interpreter; source setup uses the interpreter that runs `scripts/setup.py`.

The existing app embeds its public EdDSA key. Its corresponding private key is stored in the maintainer's macOS Keychain under the Sparkle account `tagtracker`. Preserve and securely back up that key. Never generate a replacement for an established app without planning Sparkle's supported key rotation. For a separately branded fork, generate your own key with `.tools/sparkle/bin/generate_keys --account YOUR_ACCOUNT`, replace the public key and feed URL in `project.yml`, and use your own bundle identifier and release URLs.

## Build and notarize

Run the full tests and capture demo media first:

```sh
make build test
npm run media
TEAM_ID=YOUR_TEAM_ID release/release.sh 0.1.0 1
```

Increase the integer build number for every update. Use a new version/build pair for every attempt; existing build folders are preserved. Xcode submits the archive using its signed-in account, and exports the notarized app after Apple finishes. The script validates the app signature and Gatekeeper assessment, creates `TagTracker.dmg` for first installs and `TagTracker.zip` for Sparkle, and generates a signed appcast. It publishes nothing.

Outputs are under `release/build/VERSION-BUILD/`. If Apple takes longer than the bounded wait, preserve the archive and resume `xcodebuild -exportNotarizedApp` for that archive. Do not restart a pending submission unnecessarily.

## Verify before publishing

Mount the DMG, copy the app to Applications, and open the installed copy. Confirm the matching installer ejects and unrelated disks stay mounted. Configure fictional test names in an isolated data folder when testing setup scripts; never publish personal histories or diagnostics. Verify the actual Find My permission and collection flow on a supported test Mac before claiming a new collector layout works.

Test Sparkle updates using two signed builds on a private test feed before changing updater behavior. Archive-signature verification and a no-update check do not establish the complete install-and-relaunch flow. Standard releases use explicit user approval to install updates; automatic checks send no system profile. Running local services are paused for an update and restored on relaunch. History and aliases remain outside the app bundle.

## Publish a verified build

Create a GitHub release tagged from the tested source commit and attach `TagTracker.dmg` and `TagTracker.zip`. Keep these filenames: the README and website use GitHub's `releases/latest/download/TagTracker.dmg` link. Copy `feed/appcast.xml` into `site/appcast.xml` and commit/push it only after the matching ZIP is accessible. The feed URL is `https://danielyaa5.github.io/tagtracker/appcast.xml`. GitHub Pages deploys the website and feed from `site/` on `main`.

Keep older appcast entries when generating the next feed. The release script seeds the generator with the current public appcast. Do not edit signature attributes by hand, move an archive to a different version URL, or replace an archive after generating its signature.
