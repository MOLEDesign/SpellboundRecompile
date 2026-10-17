#!/bin/sh
# Builds Spellbound.app from the compiled ./spellbound binary.
#   sh tools/make_app.sh [path/to/S_BND128.TAP]
# If a TAP path is given it is copied into the bundle so the app starts
# with a double-click. The binary links Homebrew's SDL2 dynamically; if
# `dylibbundler` is installed (brew install dylibbundler) SDL2 is copied
# into the bundle so it also runs on Macs without Homebrew.
set -e
TAP="$1"
APP=Spellbound.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp spellbound "$APP/Contents/MacOS/spellbound"
cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Spellbound</string>
  <key>CFBundleDisplayName</key><string>Spellbound</string>
  <key>CFBundleIdentifier</key><string>biz.moledesign.spellbound</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleExecutable</key><string>spellbound</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSMinimumSystemVersion</key><string>10.13</string>
</dict>
</plist>
EOF
if [ -n "$TAP" ] && [ -f "$TAP" ]; then
  cp "$TAP" "$APP/Contents/Resources/S_BND128.TAP"
  echo "bundled $TAP"
else
  echo "note: no TAP bundled; put S_BND128.TAP in $APP/Contents/Resources/"
fi
if command -v dylibbundler >/dev/null 2>&1; then
  dylibbundler -od -b -x "$APP/Contents/MacOS/spellbound" -d "$APP/Contents/libs" -p @executable_path/../libs >/dev/null
  echo "bundled SDL2 into the app"
fi
# ad-hoc sign so Gatekeeper on Apple Silicon will run it locally
if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep -s - "$APP" >/dev/null 2>&1 || true
fi
echo "built $APP"
