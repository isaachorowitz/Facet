#!/bin/bash
# Build a self-contained source bundle. Python dependencies and models are prepared on first launch.
# FACET_SIGN_IDENTITY overrides Developer ID Application, Apple Development, then ad hoc.
set -euo pipefail
cd "$(dirname "$0")/.."
APP="build/Facet.app"

if [[ -n "${FACET_SIGN_IDENTITY:-}" ]]; then
  IDENTITY="$FACET_SIGN_IDENTITY"
else
  IDENTITIES="$(security find-identity -v -p codesigning 2>/dev/null || true)"
  IDENTITY="$(awk -F'"' '/Developer ID Application/ {print $2; exit}' <<< "$IDENTITIES")"
  [[ -z "$IDENTITY" ]] && IDENTITY="$(awk -F'"' '/Apple Development/ {print $2; exit}' <<< "$IDENTITIES")"
  [[ -z "$IDENTITY" ]] && IDENTITY="-"
fi
echo "signing as: $IDENTITY"

swift build -c release --product FacetApp
BIN="$(swift build -c release --show-bin-path)"
mkdir -p build
if [[ ! -f build/AppIcon.icns || scripts/make-icon.swift -nt build/AppIcon.icns ]]; then
  ICONSET="build/AppIcon.iconset"
  mkdir -p "$ICONSET"
  swift scripts/make-icon.swift build/icon_1024.png
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" build/icon_1024.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    sips -z "$((size * 2))" "$((size * 2))" build/icon_1024.png --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o build/AppIcon.icns
fi

# Resolve uv before replacing the last successful bundle. No download or camera work at build time.
UV=""
for candidate in "$HOME/.local/bin/uv" /opt/homebrew/bin/uv; do
  if [[ -x "$candidate" ]]; then UV="$candidate"; break; fi
 done
[[ -z "$UV" ]] && UV="$(command -v uv || true)"
if [[ -z "$UV" ]]; then echo "uv is required to build Facet.app" >&2; exit 1; fi

rm -rf "${APP:?}"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/backend" "$APP/Contents/Resources/bin"
cp "$BIN/FacetApp" "$APP/Contents/MacOS/FacetApp"
cp Resources/Info.plist "$APP/Contents/Info.plist"
cp build/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"
BACKEND="$APP/Contents/Resources/backend"
rsync -a --exclude '__pycache__' --exclude '*.pyc' ../facet "$BACKEND/"
cp ../pyproject.toml ../uv.lock ../README.md "$BACKEND/"
if [[ -d ../web/dist ]]; then
  mkdir -p "$BACKEND/web"
  rsync -a ../web/dist "$BACKEND/web/"
fi
# Relative filenames and file contents make the version deterministic across build locations.
(
  cd "$BACKEND"
  find . -type f ! -name VERSION -print | LC_ALL=C sort | while IFS= read -r file; do
    shasum -a 256 "$file"
  done | shasum -a 256 | awk '{print $1}' > VERSION
)
cp -L "$UV" "$APP/Contents/Resources/bin/uv"
chmod 755 "$APP/Contents/Resources/bin/uv"

TIMESTAMP="--timestamp"
[[ "$IDENTITY" == "-" ]] && TIMESTAMP="--timestamp=none"
KEYCHAIN=()
[[ -n "${FACET_SIGN_KEYCHAIN:-}" ]] && KEYCHAIN=(--keychain "$FACET_SIGN_KEYCHAIN")
sign() {
  codesign --force --options runtime "$TIMESTAMP" ${KEYCHAIN[@]+"${KEYCHAIN[@]}"} --sign "$IDENTITY" "$@"
}
# Inside out. This app has no embedded Swift frameworks requiring AgentReel's ad hoc exception.
sign "$APP/Contents/Resources/bin/uv"
sign --entitlements Resources/Facet.entitlements "$APP"
codesign --verify --deep --strict "$APP"
plutil -lint "$APP/Contents/Info.plist"
echo "built $APP"
