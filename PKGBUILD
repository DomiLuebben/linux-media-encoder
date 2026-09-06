# Maintainer: Dominik Lübben <dominikluebben@googlemail.com>
pkgname=linux-media-encoder
# Version auch in version.py pflegen (Single Source für die App selbst)
pkgver=1.12.0
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
            '830e2d99a0b63a617a76e3c0a7629b011defbbe9dafc90f4f6aed612b99e8fdf'
            '7991fde560f6f2daf9cca2fea18235f3bf09d55e994a0dec06530593e3c62a63'
            '8d2262e6057f66cfd37a8728fe5ad338d7dd53ea4cd913e475a3b392e9dfca38'
            'e870ee5a83c8f48e10ac1e2817b763d8025e13afea565fdea3060aafb4d5b035'
            '906d96391e5a6f5734dd3f5b946810e3d14cb551663bc75280a897a2825797c4'
            'da4132ad7c0ee19eae88d923dac1a33ba57cb992179902e39889a7f1ea590797'
            '0a5f5e608f88a0fdf3b19e63296af8f47020768330d6a1f89ac6d2b223d054ae'
            '20d03f3bd868647e922ae6e2e3e5f4001bbc5e439c721339b1102a03a4256bc3'
            'efb0eb2325220acf862fb5ecbb7ba404654735c75808f4b4249d6b71caeb0fc0'
            'b24b2d4be824a84bdfa5c73897b5b9b5d1b227c835bc85d14a3a366327564cf5'
            '8627170396c40f29107217dca45fbe69208bf755d6fbdbc19477b9dfaab126d1'
            '81371e250ba5f6bc3a162ed768d4e1dff7657c56351bc28a4799df389fc48e4e'
            '2c313ed339cd1b1b18e9fa0c9c14d39a817ae1a73ad2b9a29da9d74d0577da80'
            '390273b23c29b01687683ca1bb8ac4c9e45d009e47e9092a85f17c068b59614c'
            'dc51005d2ea0f95d7695c6cca6dd477952d8cfdead4f352e592793c036d2f72a'
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
