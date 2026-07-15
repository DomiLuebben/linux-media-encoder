# Maintainer: Dominik Lübben <dominikluebben@googlemail.com>
pkgname=linux-media-encoder
# Version auch in version.py pflegen (Single Source für die App selbst)
pkgver=1.8.2
pkgrel=1
pkgdesc="GUI-Medien-Encoder für FFmpeg im Stil des Adobe Media Encoder (PyQt6)"
arch=('any')
url="https://nextcloud.bdluebben.de"
license=('MIT')
depends=('python' 'python-pyqt6' 'ffmpeg')
# Dieses PKGBUILD baut direkt aus den danebenliegenden Quelldateien.
# Einfach im entpackten Ordner ausführen:  makepkg -si
source=("main.py"
        "mainwindow.py"
        "ffmpeg_worker.py"
        "presets.py"
        "crop_label.py"
        "intelligent_dialog.py"
        "export_settings_dialog.py"
        "styles.py"
        "subtitle_editor_dialog.py"
        "subtitle_utils.py"
        "version.py"
        "sample_video_frame.png"
        "linux-media-encoder.svg"
        "linux-media-encoder.desktop"
        "LICENSE")
sha256sums=('cb32c2e2dbd09efb8772ae8dd8a3c032ea753d145f07fe6d293ff44bba6a948f'
            'f6d0f6b6ee0973923ae883b03c449a4ab59378d75a31e43ee651522c1cf51958'
            '8d2262e6057f66cfd37a8728fe5ad338d7dd53ea4cd913e475a3b392e9dfca38'
            '929ecb5efcbacde617f6f95832dc6b62ae1a31b60ff12945a68ac0c164c4545c'
            'bdc3eff96d04bfd33df99fbfff5c8d50f42477c0eb04846b00a010c30a8ec231'
            '22502f7d6b384df0d2b0c0aa2eee7bf344358a1847c8abf80d37638507b50b58'
            '38dd290964facb67277d36c15627b528643e6d3d4cdac1fe3a1844d7a108e081'
            '20d03f3bd868647e922ae6e2e3e5f4001bbc5e439c721339b1102a03a4256bc3'
            '0a4bc08ba03c40587a3f7451f9e22af10299b6267e83371012ad2a90498e73ea'
            'f02bf1229373dc36c5a83480ba44d24b912b4b40254f12a9abbdd4fd31c4096f'
            'ea73018bc8b1b9cca07450b52d09c7acdcd903bae1c036d522e25e1f85162693'
            '24b6c858e70ed5678712b9deb5761b32a152016d4cf35e9bc2bb73bcf5dd09c3'
            '79fcb30bee3903bf1dffef7a8e84c9cd775fe2aa369e279f9cd2eb876c69f8b0'
            'c89b29e161f979e133282e7aa2eb019c1c33c80e3699b0a9c7ba4ac0b893c0f4'
            '092e99891c0290e3751231141086491295ad7d350060111b351d09bfb2ff8104')

package() {
    local appdir="$pkgdir/usr/share/$pkgname"
    install -dm755 "$appdir"

    # Python-Quellen
    for f in main.py mainwindow.py ffmpeg_worker.py presets.py crop_label.py \
             intelligent_dialog.py export_settings_dialog.py styles.py \
             subtitle_editor_dialog.py subtitle_utils.py version.py \
             sample_video_frame.png linux-media-encoder.svg; do
        install -Dm644 "$srcdir/$f" "$appdir/$f"
    done

    # Launcher-Skript
    install -dm755 "$pkgdir/usr/bin"
    cat > "$pkgdir/usr/bin/$pkgname" <<EOF
#!/bin/sh
exec python "/usr/share/$pkgname/main.py" "\$@"
EOF
    chmod 755 "$pkgdir/usr/bin/$pkgname"

    # Desktop-Eintrag & Icon
    install -Dm644 "$srcdir/linux-media-encoder.desktop" \
        "$pkgdir/usr/share/applications/$pkgname.desktop"
    install -Dm644 "$srcdir/linux-media-encoder.svg" \
        "$pkgdir/usr/share/icons/hicolor/scalable/apps/$pkgname.svg"

    # Lizenz installieren
    install -Dm644 "$srcdir/LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
