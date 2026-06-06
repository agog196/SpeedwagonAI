#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/package-common.sh"

require_command codesign
require_env SPEEDWAGON_SIGN_IDENTITY
require_env SPEEDWAGON_TEAM_ID

build_release_product
assemble_unsigned_app

rm -rf "$SIGNED_APP_DIR"
cp -R "$APP_DIR" "$SIGNED_APP_DIR"

codesign \
  --force \
  --deep \
  --options runtime \
  --timestamp \
  --sign "$SPEEDWAGON_SIGN_IDENTITY" \
  "$SIGNED_APP_DIR"

codesign --verify --deep --strict --verbose=2 "$SIGNED_APP_DIR"
codesign --display --verbose=2 "$SIGNED_APP_DIR"

echo "Built signed app: $SIGNED_APP_DIR"
