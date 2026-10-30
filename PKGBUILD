# Maintainer: Dominik Lübben <dominikluebben@googlemail.com>
pkgname=linux-media-encoder
# Version auch in version.py pflegen (Single Source für die App selbst)
pkgver=1.12.8
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
        "media_probe.py"
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
            '0cec309f21308feed72b6bfb2acc4dccde4d327a86ed14f72753e2dc62bcf387'
            '913c722e39d5048a9b9deb89998562223516b9175843e34de8816035b9e1b4ab'
            '3f5afa3550f791c35b0ea956abab5f017e69b0cb65e5f836d7f492f5e8121016'
            '849abc4e394ebd91c84f4c3be2815eea66767453e8815e8838b8f7c28c5bb7e8'
            'a5fee945e65bce86d1d161264fd10d1396a44a314c1905c54f3dc52468fcdb12'
            '906d96391e5a6f5734dd3f5b946810e3d14cb551663bc75280a897a2825797c4'
            '44f20862702f228a0f19570911c124e2d72ed69348daa35b7f61ea23178c7341'
            '71aac015741785d51e740b6cad3175673443db4f42fa2359207e6bf5f16ff992'
            '20d03f3bd868647e922ae6e2e3e5f4001bbc5e439c721339b1102a03a4256bc3'
            'a5ac2dbbf9fb3d8435f7cf4a2b59c579a1bd0fd036130c4f28f9ab87b12e0037'
            'b24b2d4be824a84bdfa5c73897b5b9b5d1b227c835bc85d14a3a366327564cf5'
            'eb75771edb53845cea484e0eafc9d7d2b6095eb2a1341a7fc441375277b5851c'
            '4987b3cb72b772a762c7b57fe3963cfe0018ea90c87cc561ad44e1aa3571a3cc'
            '69d131db1f6f059139223cfd5c99df7c5315a133e3400f66fa6807cad96c1757'
            '390273b23c29b01687683ca1bb8ac4c9e45d009e47e9092a85f17c068b59614c'
            '8116ad5182c8d19f94dccf50dda9e8df9e4e8178f1580c88f21d2b38d9712f52'
            '24b6c858e70ed5678712b9deb5761b32a152016d4cf35e9bc2bb73bcf5dd09c3'
            '79fcb30bee3903bf1dffef7a8e84c9cd775fe2aa369e279f9cd2eb876c69f8b0'
            '1a0e84aa52709fee60ab7968746424456f595614325461214af36bab70574724'
            '092e99891c0290e3751231141086491295ad7d350060111b351d09bfb2ff8104')

package() {
    local appdir="$pkgdir/usr/share/$pkgname"
    install -dm755 "$appdir"

    # Python-Quellen
    for f in main.py i18n.py translations.py mainwindow.py ffmpeg_worker.py media_probe.py presets.py crop_label.py \
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
