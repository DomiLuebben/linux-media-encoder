# Linux Media Encoder (LME)

[English](README.md) | [Deutsch](README.de.md) | **Français**

Une interface professionnelle pour encoder des médias avec **FFmpeg**, inspirée
d’Adobe Media Encoder et développée avec Python 3 et PyQt6.

![LME](linux-media-encoder.svg)

## Fonctionnalités

- **Conversion directe ou en deux étapes** (par défaut : directe) : le disque est converti
  directement — mesuré sur un Blu-ray, les deux voies lisent à la même vitesse (5,6× contre 5,5×),
  car la limite vient du lecteur et non du processeur. En option, les DVD et Blu-ray sont d’abord
  lus sans perte dans un dossier
  temporaire, puis convertis depuis celui-ci. Le lecteur ne tourne ainsi que pendant la courte
  lecture au lieu de toute la conversion. Les deux étapes affichent progression, vitesse et temps
  restant (« Étape 1/2 · Lecture du disque », « Étape 2/2 · Conversion »). LME choisit lui-même le
  dossier temporaire selon l’espace libre — `/tmp` est un tmpfs en mémoire sur de nombreux
  systèmes ; un dossier personnalisé peut être défini dans l’extracteur. Si aucun emplacement n’a la
  place, LME bascule automatiquement sur la conversion directe. Le mode en deux étapes est utile pour
  les codecs exigeants, les machines peu puissantes, plusieurs versions d’un même titre ou les
  disques rayés.
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

> **Installation des composants manquants :** à son ouverture, la boîte de dialogue vérifie quels
> outils et bibliothèques facultatifs sont présents et propose un bouton « Installer les composants
> manquants… ». La famille de distribution est déduite de `ID` et `ID_LIKE` dans `/etc/os-release`
> (ce qui couvre aussi les dérivés comme CachyOS, EndeavourOS, Garuda, Linux Mint, TUXEDO OS,
> Pop!_OS, Bazzite, Nobara ou GeckoLinux) ; `pacman`, `apt`, `dnf` et `zypper` sont pris en charge,
> tout comme les variantes immuables `rpm-ostree` (Bazzite, Silverblue, Kinoite) et
> `transactional-update` (openSUSE MicroOS, Aeon). L’authentification passe par `pkexec`. La commande complète est
> affichée avant exécution. Les paquets introuvables sur le système sont ignorés et signalés
> individuellement plutôt que de faire échouer toute l’opération. LME n’active pas de sources
> tierces (RPM Fusion, AUR) de lui-même. Sur Debian, Ubuntu et Mint, libdvdcss est compilé
> depuis les sources via `libdvd-pkg` ; l’étape debconf nécessaire est pré-répondue et s’exécute
> dans le même appel privilégié, de sorte que la demande de mot de passe n’apparaît qu’une fois.
> Cela nécessite une connexion Internet et prend quelques minutes ; la progression s’affiche dans
> le journal. Sur Fedora, LME vérifie si RPM Fusion (free) est configuré ; si ce n’est pas le
> cas, un message invite à le configurer — les autres composants sont installés malgré tout.
> Il en va de même pour **Packman** sur openSUSE, où se trouve libdvdcss.
> Sur Arch, c’est `pacman -Si`, et donc l’état réel de la machine, qui détermine si un paquet
> provient d’un dépôt configuré ou uniquement de l’AUR : CachyOS, EndeavourOS et Garuda
> proposent beaucoup de paquets dans leurs propres dépôts, ce qui est reconnu comme tel. La
> boîte de confirmation indique le dépôt d’origine de chaque paquet. Ce qui reste introuvable est
> signalé comme un cas AUR — LME ne compile aucun paquet AUR, mais indique la commande
> appropriée si un assistant AUR est présent.

> **Blu-ray protégés :** LME ne fournit aucune clé de déchiffrement et n’en télécharge aucune. Les
> disques non chiffrés et les dossiers BDMV fonctionnent tels quels. Pour les disques protégés par
> AACS, `libaacs` cherche un fichier `KEYDB.cfg` dans `$XDG_CONFIG_HOME/aacs/` (par défaut
> `~/.config/aacs/`) et dans les répertoires de `$XDG_CONFIG_DIRS` (par défaut `/etc/xdg/aacs/`) ;
> LME examine tous ces emplacements et indique ce qui manque dans la boîte de dialogue. La mise à
> disposition de telles clés relève de l’utilisateur et n’est pas autorisée dans certaines
> juridictions (par exemple en Allemagne, § 95a UrhG). Les disques protégés en plus par BD+
> nécessitent également `libbdplus`.

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
