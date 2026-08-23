# Maintainer: Dominik Lübben <dominikluebben@googlemail.com>
pkgname=linux-media-encoder
# Version auch in version.py pflegen (Single Source für die App selbst)
pkgver=1.10.0
pkgrel=1
pkgdesc="FFmpeg media encoder GUI inspired by Adobe Media Encoder (PyQt6)"
arch=('any')
url="https://github.com/DomiLuebben/linux-media-encoder"
license=('MIT')
depends=('python' 'python-pyqt6' 'ffmpeg')
optdepends=('cdparanoia: Audio-CD ripping support'
            'lsdvd: Enhanced DVD-Video structure inspection'
            'libbluray: Blu-ray playlist inspection via bd_info'
            'libdvdcss: CSS decryption for video DVDs'
            'libaacs: AACS decryption for Blu-ray discs'
            'polkit: graphical password prompt for installing missing components')
# Dieses PKGBUILD baut direkt aus den danebenliegenden Quelldateien.
# Einfach im entpackten Ordner ausführen:  makepkg -si
source=("main.py"
        "i18n.py"
        "translations.py"
        "mainwindow.py"
        "ffmpeg_worker.py"
        "presets.py"
        "crop_label.py"
        "intelligent_dialog.py"
        "export_settings_dialog.py"
        "styles.py"
        "subtitle_editor_dialog.py"
        "subtitle_utils.py"
        "optical_media.py"
        "disc_rip_worker.py"
        "disc_ripper_dialog.py"
        "dependency_installer.py"
        "version.py"
        "sample_video_frame.png"
        "linux-media-encoder.svg"
        "linux-media-encoder.desktop"
        "LICENSE")
sha256sums=('c160ac9dc88b5cedd793a942d8551f22dfbc39b47ab4aa5fc13af708c3453dd8'
            '028689d75a0aa3d24f22a6c0be4902af8f687a82c80f9bda1a1fbe382e5bef73'
            '16230c71c585176ddbacd7f28282abfba93ad7c940b4fed0b878916be13f5f6f'
            '3e8d4371eab5fd0a8a5fa28727972117ae078abd8ac73405e5d49bc4cb6ba5b6'
            '8d2262e6057f66cfd37a8728fe5ad338d7dd53ea4cd913e475a3b392e9dfca38'
            'b0cb9c9070db457a072d3f4a7de70671f64abd0b5f6609dab964ee5ad2d42375'
            '906d96391e5a6f5734dd3f5b946810e3d14cb551663bc75280a897a2825797c4'
            'da4132ad7c0ee19eae88d923dac1a33ba57cb992179902e39889a7f1ea590797'
            '0664e108fc76c66bab199ea83b8fd2ba23a63369e159415ae491deb98e8acde0'
            '20d03f3bd868647e922ae6e2e3e5f4001bbc5e439c721339b1102a03a4256bc3'
            'efb0eb2325220acf862fb5ecbb7ba404654735c75808f4b4249d6b71caeb0fc0'
            'b24b2d4be824a84bdfa5c73897b5b9b5d1b227c835bc85d14a3a366327564cf5'
            '0a94763a9c8a2588e5b311552c5a489c3da56acb8d337ed53d37ea5832a633c9'
            'b780ef06ebb33bcb4a72044dd41b021c3080ed9116799040a0f196e29424abe4'
            '67f3f94f6f078e4a12a07cb1be30686764f17a2bda85868a7e5e6e4fcf186db4'
            '390273b23c29b01687683ca1bb8ac4c9e45d009e47e9092a85f17c068b59614c'
            'ae84000d4d936aba3dd498ae0599d9e22b9f306f21beaacce061cd203fb1dd3b'
            '24b6c858e70ed5678712b9deb5761b32a152016d4cf35e9bc2bb73bcf5dd09c3'
            '79fcb30bee3903bf1dffef7a8e84c9cd775fe2aa369e279f9cd2eb876c69f8b0'
            '1a0e84aa52709fee60ab7968746424456f595614325461214af36bab70574724'
            '092e99891c0290e3751231141086491295ad7d350060111b351d09bfb2ff8104')

package() {
    local appdir="$pkgdir/usr/share/$pkgname"
    install -dm755 "$appdir"

    # Python-Quellen
    for f in main.py i18n.py translations.py mainwindow.py ffmpeg_worker.py presets.py crop_label.py \
             intelligent_dialog.py export_settings_dialog.py styles.py \
             subtitle_editor_dialog.py subtitle_utils.py optical_media.py disc_rip_worker.py disc_ripper_dialog.py dependency_installer.py version.py \
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
