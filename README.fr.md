# Linux Media Encoder (LME)

[English](README.md) | [Deutsch](README.de.md) | **Français**

Une interface professionnelle pour encoder des médias avec **FFmpeg**, inspirée
d’Adobe Media Encoder et développée avec Python 3 et PyQt6.

![LME](linux-media-encoder.svg)

## Fonctionnalités

- **Extracteur CD / DVD / BD (Ctrl+D)** : Lecture et extraction de CD audio (avec métadonnées CD-Text vers FLAC/MP3/AAC/Opus), DVD-Vidéo (sélection des titres, pistes audio et sous-titres vers MKV ou file d’attente), disques Blu-ray (analyse des listes de lecture) et création d’images ISO 1:1
- File d’attente multitâche avec glisser-déposer de fichiers et d’images ISO
- Réglages d’exportation, aperçu de la source et métadonnées via `ffprobe`
- Préréglages MP4/H.264, HEVC, VP9, AV1, MKV, audio et copie de flux
- Réglages vidéo pour la résolution, la fréquence d’images, le profil et les modes **CRF / VBR / CBR**
- Prise en charge de l’audio AAC, MP3, Opus, FLAC et de la copie de flux
- Actions par lot pour appliquer les réglages ou le dossier de sortie à toute la file d’attente
- Calculateur intelligent de débit avec une interface d’IA locale facultative et une formule de secours
- Génération de sous-titres SRT, traduction facultative et intégration en sous-titres logiciels ou incrustés
- Encodage GPU **NVENC** pour H.264, HEVC et AV1 lorsqu’il est disponible dans FFmpeg
- Découpe précise avec points d’entrée et de sortie sur la timeline
- Conversion d’images JPEG, PNG, WebP et AVIF avec redimensionnement, rotation et rognage
- Progression, vitesse, temps restant, journal FFmpeg facultatif et notifications du bureau
- Thème Breeze Dark ou thème natif du système
- Interface complète en allemand, anglais américain et français, choisie automatiquement selon la langue du système

## Prérequis

- Python 3.11 ou version ultérieure
- PyQt6 (`python-pyqt6` sous Arch Linux)
- FFmpeg avec `ffprobe`, disponible dans le `PATH`
- *Facultatif (pour les disques optiques)* : `cdparanoia` (CD audio), `lsdvd` (structures DVD), `libbluray` (listes de lecture Blu-ray), `libdvdcss` (DVD chiffrés), `libaacs` (Blu-ray chiffrés)

## Exécution sans installation

```bash
python main.py
```

## Création et installation du paquet Arch

Dans le dossier du projet :

```bash
makepkg -si
```

L’application apparaît ensuite dans le menu sous le nom **Linux Media Encoder**
et peut être lancée avec la commande `linux-media-encoder`.

Pour supprimer le paquet :

```bash
sudo pacman -R linux-media-encoder
```

## Licence

MIT
