#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PACKAGE_DIR/../.." && pwd)"

APP_NAME="SpeedwagonAI"
PRODUCT_NAME="SpeedwagonAI"
BUNDLE_IDENTIFIER="ai.speedwagon.localbeta"
BUNDLE_VERSION="26"
BUNDLE_SHORT_VERSION="0.26.0-beta"

BUILD_DIR="$PACKAGE_DIR/.build/release"
DIST_DIR="$PACKAGE_DIR/dist"
APP_DIR="$DIST_DIR/$APP_NAME.app"
SIGNED_APP_DIR="$DIST_DIR/$APP_NAME-signed.app"
DMG_STAGING_DIR="$DIST_DIR/dmg-staging"
DMG_PATH="$DIST_DIR/$APP_NAME-$BUNDLE_SHORT_VERSION.dmg"

CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 2
  fi
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: $name" >&2
    exit 2
  fi
}

write_info_plist() {
  mkdir -p "$CONTENTS_DIR"
  cat > "$CONTENTS_DIR/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>$APP_NAME</string>
  <key>CFBundleIdentifier</key>
  <string>$BUNDLE_IDENTIFIER</string>
  <key>CFBundleName</key>
  <string>$APP_NAME</string>
  <key>CFBundleDisplayName</key>
  <string>$APP_NAME</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>$BUNDLE_SHORT_VERSION</string>
  <key>CFBundleVersion</key>
  <string>$BUNDLE_VERSION</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>NSMicrophoneUsageDescription</key>
  <string>SpeedwagonAI records meeting and voice-note audio only after you start capture.</string>
  <key>NSScreenCaptureUsageDescription</key>
  <string>SpeedwagonAI captures screenshots and system audio only after you request capture.</string>
</dict>
</plist>
PLIST
}

write_local_beta_env() {
  mkdir -p "$RESOURCES_DIR"
  cat > "$RESOURCES_DIR/local-beta.env" <<ENV
SPEEDWAGON_REPO_ROOT=$REPO_ROOT
ENV
}

build_release_product() {
  cd "$PACKAGE_DIR"
  swift build -c release --product "$PRODUCT_NAME"
}

assemble_unsigned_app() {
  rm -rf "$APP_DIR"
  mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
  cp "$BUILD_DIR/$PRODUCT_NAME" "$MACOS_DIR/$APP_NAME"
  write_info_plist
  write_local_beta_env
}

print_signing_setup() {
  cat >&2 <<'TEXT'
Required signing environment:
  SPEEDWAGON_SIGN_IDENTITY="Developer ID Application: ..."
  SPEEDWAGON_TEAM_ID="TEAMID1234"

Required notarization environment, choose one:
  SPEEDWAGON_NOTARY_PROFILE="notarytool-profile"

Or provide credentials accepted by xcrun notarytool:
  SPEEDWAGON_NOTARY_APPLE_ID="apple-id@example.com"
  SPEEDWAGON_NOTARY_PASSWORD="app-specific-password"

Optional:
  SPEEDWAGON_NOTARY_TIMEOUT="30m"
TEXT
}
