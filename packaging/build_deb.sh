#!/bin/sh
# Build a .deb from dist/SubBridge (run pyinstaller first).  Usage: packaging/build_deb.sh [version]
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
VER=${1:-$(grep -m1 '^VERSION' "$ROOT/subbridge/branding.py" | cut -d'"' -f2)}
ARCH=amd64
PKG="$ROOT/build/deb/subbridge_${VER}_${ARCH}"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/512x512/apps" "$PKG/usr/share/doc/subbridge"
cp -a "$ROOT/dist/SubBridge" "$PKG/opt/subbridge"
ln -s /opt/subbridge/subbridge "$PKG/usr/bin/subbridge"
cp "$ROOT/packaging/subbridge.png" "$PKG/usr/share/icons/hicolor/512x512/apps/subbridge.png"
cp "$ROOT/LICENSE" "$PKG/usr/share/doc/subbridge/copyright"
[ -f "$ROOT/THIRD_PARTY_LICENSES.md" ] && cp "$ROOT/THIRD_PARTY_LICENSES.md" "$PKG/usr/share/doc/subbridge/"
cat > "$PKG/usr/share/applications/subbridge.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=SubBridge
GenericName=Game subtitle translator
GenericName[hu]=Játékfelirat-fordító
Comment=Translate game subtitles live – on your screen and on your phone
Comment[hu]=Játékfeliratok élő fordítása – a képernyőn és a telefonon
Exec=subbridge
Icon=subbridge
Terminal=false
Categories=Game;Utility;
StartupWMClass=subbridge
DESK
SIZE=$(du -sk "$PKG/opt" | cut -f1)
cat > "$PKG/DEBIAN/control" <<CTRL
Package: subbridge
Version: $VER
Section: games
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE
Depends: libxcb-cursor0, libxkbcommon-x11-0, libegl1, libgl1
Maintainer: Roland Horváth <rolandhrvth@outlook.hu>
Homepage: https://rolandhrvth.hu/subbridge
Description: Live game subtitle translator for your screen and phone
 Reads a game's subtitles from a Remote Play window, a capture card or the screen,
 translates them (offline or with your own DeepL / Google Cloud / LibreTranslate key)
 and shows the translation over the game and on your phone.
CTRL
dpkg-deb --root-owner-group --build "$PKG" "$ROOT/dist/subbridge_${VER}_${ARCH}.deb"
