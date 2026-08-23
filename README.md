# Linux Media Encoder (LME)

**English** | [Deutsch](README.de.md) | [Français](README.fr.md)

A professional **FFmpeg** GUI encoder inspired by Adobe Media Encoder, built
with Python 3 and PyQt6.

![LME](linux-media-encoder.svg)

## Features

- **CD / DVD / BD Ripper (Ctrl+D)**: Read and rip Audio CDs (with CD-Text metadata to FLAC/MP3/AAC/Opus), DVD-Video (with title and audio/subtitle stream selection to MKV or queue), Blu-ray Discs (with playlist inspection), and 1:1 ISO backups
- Multi-job queue with drag-and-drop file and disc/ISO image support
- AME-style export dialog with source preview and metadata from `ffprobe`
- Presets for MP4/H.264, HEVC, VP9, AV1, MKV, Match Source, Social/Delivery, MP3, FLAC, and stream copy
- Video controls for resolution, frame rate, profile, and **CRF / VBR / CBR**
- Audio support for AAC, MP3, Opus, FLAC, and copy; Custom mode exposes all detected FFmpeg video and audio codecs
- Batch actions for applying video/audio settings or output folders to the entire queue
- True stream copy: copy video unchanged while re-encoding only the audio track
- Intelligent bitrate calculator using an optional local AI CLI with a formula-based fallback
- AI subtitles: generate SRT files from audio, optionally translate them, and embed them as soft or hard subtitles
- Web-optimized MP4/MOV output with `+faststart` and compatible `yuv420p` output for H.264/H.265
- Live progress, speed, remaining time, overall queue progress, and an optional FFmpeg console
- **GPU encoding (NVENC)** for H.264, HEVC, and AV1 when supported by the installed FFmpeg build; CRF is mapped to `-cq`
- **Precise trimming** with timeline in/out points while keeping subtitles synchronized
- Additional WAV (PCM) and OGG (Opus) audio formats
- Queue context menu for starting, duplicating, reordering, and locating individual jobs, plus multi-selection deletion
- Failed jobs expose the latest FFmpeg messages through tooltips and double-click details
- Warning before overwriting existing output files
- Desktop notification when the queue finishes, with optional suspend or shutdown
- Persistent queue, window layout, and session state
- “Open with…” integration that adds files passed by a file manager directly to the queue
- Native desktop window decorations with a classic application menu bar
- AME-style Breeze Dark theme or the native system theme, with persistent selection

## Requirements

- Python 3.11 or newer
- PyQt6 (`python-pyqt6` on Arch Linux)
- FFmpeg, including `ffprobe`, available in `PATH`
- *Optional (for optical disc ripping)*: `cdparanoia` (Audio CDs), `lsdvd` (DVD structure inspection), `libbluray` (Blu-ray playlists), `libdvdcss` (encrypted DVDs), `libaacs` (encrypted Blu-rays)

> **Installing missing components:** When it opens, the ripper dialog checks which optional
> tools and libraries are present and offers an “Install missing components…” button. The
> distribution family is derived from `ID` and `ID_LIKE` in `/etc/os-release` (covering
> derivatives such as CachyOS, EndeavourOS, Garuda, Linux Mint, TUXEDO OS, Pop!_OS, Bazzite,
> Nobara or GeckoLinux); `pacman`, `apt`, `dnf` and `zypper` are supported, as are the immutable
> variants `rpm-ostree` (Bazzite, Silverblue, Kinoite) and `transactional-update` (openSUSE
> MicroOS, Aeon). Authentication uses `pkexec`. The full command is shown before it runs. Packages
> that cannot be found on the system are skipped and listed individually instead of failing the
> whole run. LME does not enable third-party sources (RPM Fusion, AUR) on its own. On Debian,
> Ubuntu and Mint, libdvdcss is built from source via `libdvd-pkg`; the required debconf step is
> pre-answered and runs inside the same privileged call, so the password prompt appears only
> once. It needs an internet connection and takes a few minutes; progress is shown in the log.
> On Fedora, LME checks whether RPM Fusion (free) is set up; if it is not, a notice asks you to
> set it up — all other components are still installed. The same applies to **Packman** on
> openSUSE, which is where libdvdcss lives there.
> On Arch, `pacman -Si` — and therefore the actual state of the machine — decides whether a
> package comes from a configured repository or only from the AUR: CachyOS, EndeavourOS and
> Garuda carry many packages in their own repositories, and that is detected as such. The
> confirmation dialog names the source repository for every package. Anything not found anywhere
> is reported as an AUR case — LME builds no AUR packages but names the matching command if an
> AUR helper is present.

> **Copy-protected Blu-rays:** LME ships no decryption keys and downloads none. Unencrypted discs
> and BDMV folders work out of the box. For AACS-protected discs, `libaacs` looks for a `KEYDB.cfg`
> in `$XDG_CONFIG_HOME/aacs/` (default `~/.config/aacs/`) and in the directories listed in
> `$XDG_CONFIG_DIRS` (default `/etc/xdg/aacs/`); LME searches all of these and reports what is
> missing in the ripper dialog. Providing such keys is up to the user and is not permitted in some
> jurisdictions (for example Germany, § 95a UrhG). Discs with additional BD+ protection also
> require `libbdplus`.

## Run Without Installing

```bash
python main.py
```

## Build and Install as an Arch Package

From the project directory:

```bash
makepkg -si
```

**Linux Media Encoder** will then appear in the application menu and can be
started with the `linux-media-encoder` command.

To remove the package:

```bash
sudo pacman -R linux-media-encoder
```

## License

MIT
