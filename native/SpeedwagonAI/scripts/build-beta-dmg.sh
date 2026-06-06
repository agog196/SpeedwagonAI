#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/package-common.sh"

require_command hdiutil

if [[ ! -d "$SIGNED_APP_DIR" ]]; then
  echo "Signed app not found: $SIGNED_APP_DIR" >&2
  echo "Run build-signed-app.sh and notarize-app.sh first." >&2
  exit 2
fi

rm -rf "$DMG_STAGING_DIR"
mkdir -p "$DMG_STAGING_DIR"
cp -R "$SIGNED_APP_DIR" "$DMG_STAGING_DIR/$APP_NAME.app"

cat > "$DMG_STAGING_DIR/README-SpeedwagonAI-Local-Beta.txt" <<TEXT
SpeedwagonAI $BUNDLE_SHORT_VERSION Private Beta

This app is signed/notarized for private beta testing, but it is still local-first.
Python 3.11 and the SpeedwagonAI repo checkout are still required on the tester machine.

Launch example:
  SPEEDWAGON_REPO_ROOT="$REPO_ROOT" open "$APP_NAME.app"

Before testing:
  1. Confirm Python 3.11 is installed.
  2. Keep the SpeedwagonAI repo checkout available.
  3. Open Settings in the app and run Check Readiness.
  4. Read the Keychain prompt explanation before saving secrets.

Docs:
  docs/privacy-policy-local-beta.md
  docs/terms-local-beta.md
TEXT

rm -f "$DMG_PATH"
hdiutil create \
  -volname "$APP_NAME $BUNDLE_SHORT_VERSION" \
  -srcfolder "$DMG_STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

MOUNT_OUTPUT="$(hdiutil attach "$DMG_PATH" -nobrowse -readonly)"
MOUNT_POINT="$(printf '%s\n' "$MOUNT_OUTPUT" | awk '/\/Volumes\// {print substr($0, index($0, "/Volumes/")); exit}')"
if [[ -n "$MOUNT_POINT" ]]; then
  test -d "$MOUNT_POINT/$APP_NAME.app"
  test -f "$MOUNT_POINT/README-SpeedwagonAI-Local-Beta.txt"
  hdiutil detach "$MOUNT_POINT"
fi

echo "Built beta DMG: $DMG_PATH"
