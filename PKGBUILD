# Maintainer: Dominik Lübben <dominikluebben@googlemail.com>
pkgname=linux-media-encoder
# Version auch in version.py pflegen (Single Source für die App selbst)
pkgver=1.8.0
pkgrel=1
pkgdesc="GUI-Medien-Encoder für FFmpeg im Stil des Adobe Media Encoder (PyQt6)"
arch=('any')
url="https://nextcloud.bdluebben.de"
license=('MIT')
depends=('python' 'python-pyqt6' 'ffmpeg')
# Dieses PKGBUILD baut direkt aus den danebenliegenden Quelldateien.
# Einfach im entpackten Ordner ausführen:  makepkg -si
source=()

package() {
    local appdir="$pkgdir/usr/share/$pkgname"
    install -dm755 "$appdir"

    # Python-Quellen
    for f in main.py mainwindow.py ffmpeg_worker.py presets.py crop_label.py \
             intelligent_dialog.py export_settings_dialog.py styles.py \
             subtitle_editor_dialog.py subtitle_utils.py version.py \
             sample_video_frame.png linux-media-encoder.svg; do
        install -Dm644 "$startdir/$f" "$appdir/$f"
    done

    # Launcher-Skript
    install -dm755 "$pkgdir/usr/bin"
    cat > "$pkgdir/usr/bin/$pkgname" <<EOF
#!/bin/sh
exec python "/usr/share/$pkgname/main.py" "\$@"
EOF
    chmod 755 "$pkgdir/usr/bin/$pkgname"

    # Desktop-Eintrag & Icon
    install -Dm644 "$startdir/linux-media-encoder.desktop" \
        "$pkgdir/usr/share/applications/$pkgname.desktop"
    install -Dm644 "$startdir/linux-media-encoder.svg" \
        "$pkgdir/usr/share/icons/hicolor/scalable/apps/$pkgname.svg"
}
