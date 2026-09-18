#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
APP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ICONSET="$APP_ROOT/.build/AppIcon.iconset"
mkdir -p "$ICONSET"
swiftc -swift-version 6 -sdk "$(xcrun --sdk macosx --show-sdk-path)" -target "$(uname -m)-apple-macosx14.0" \
  "$APP_ROOT/scripts/icon.swift" -o "$APP_ROOT/.build/generate-icon"
"$APP_ROOT/.build/generate-icon" "$ICONSET"
iconutil -c icns "$ICONSET" -o "$APP_ROOT/Resources/AppIcon.icns"
