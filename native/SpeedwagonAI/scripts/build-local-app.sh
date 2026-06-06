#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/package-common.sh"

build_release_product
assemble_unsigned_app

echo "Built unsigned local beta app: $APP_DIR"
echo "Run with:"
echo "  SPEEDWAGON_REPO_ROOT=\"$REPO_ROOT\" open \"$APP_DIR\""
