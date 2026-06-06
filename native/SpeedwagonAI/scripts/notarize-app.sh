#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/package-common.sh"

require_command ditto
require_command xcrun
require_command codesign
require_env SPEEDWAGON_TEAM_ID

if [[ -z "${SPEEDWAGON_NOTARY_PROFILE:-}" && ( -z "${SPEEDWAGON_NOTARY_APPLE_ID:-}" || -z "${SPEEDWAGON_NOTARY_PASSWORD:-}" ) ]]; then
  print_signing_setup
  exit 2
fi

if [[ ! -d "$SIGNED_APP_DIR" ]]; then
  echo "Signed app not found: $SIGNED_APP_DIR" >&2
  echo "Run native/SpeedwagonAI/scripts/build-signed-app.sh first." >&2
  exit 2
fi

NOTARY_TIMEOUT="${SPEEDWAGON_NOTARY_TIMEOUT:-30m}"
ZIP_PATH="$DIST_DIR/$APP_NAME-$BUNDLE_SHORT_VERSION-notary.zip"
rm -f "$ZIP_PATH"
ditto -c -k --keepParent "$SIGNED_APP_DIR" "$ZIP_PATH"

if [[ -n "${SPEEDWAGON_NOTARY_PROFILE:-}" ]]; then
  xcrun notarytool submit "$ZIP_PATH" \
    --keychain-profile "$SPEEDWAGON_NOTARY_PROFILE" \
    --team-id "$SPEEDWAGON_TEAM_ID" \
    --wait \
    --timeout "$NOTARY_TIMEOUT"
elif [[ -n "${SPEEDWAGON_NOTARY_APPLE_ID:-}" && -n "${SPEEDWAGON_NOTARY_PASSWORD:-}" ]]; then
  xcrun notarytool submit "$ZIP_PATH" \
    --apple-id "$SPEEDWAGON_NOTARY_APPLE_ID" \
    --password "$SPEEDWAGON_NOTARY_PASSWORD" \
    --team-id "$SPEEDWAGON_TEAM_ID" \
    --wait \
    --timeout "$NOTARY_TIMEOUT"
else
  print_signing_setup
  exit 2
fi

xcrun stapler staple "$SIGNED_APP_DIR"
xcrun stapler validate "$SIGNED_APP_DIR"
codesign --verify --deep --strict --verbose=2 "$SIGNED_APP_DIR"

echo "Notarized and stapled app: $SIGNED_APP_DIR"
