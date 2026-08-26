# -*- coding: utf-8 -*-
"""
Optische Medien & Disc-Ripper Engine für den Linux Media Encoder (LME).
Verwaltet Laufwerkserkennung, Disc-Inspektion (Audio-CD, DVD-Video, Blu-ray, ISO),
TOC-/Titel-Parsing und Befehlsgenerierung für Transcoding, Remuxing und ISO-Dumps.
"""

from __future__ import annotations

import ast
import ctypes.util
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Tuple


class DiscType(Enum):
    AUDIO_CD = "audio_cd"
    DVD_VIDEO = "dvd_video"
    BLURAY = "bluray"
    DATA_DISC = "data_disc"
    EMPTY = "empty"
    UNKNOWN = "unknown"


@dataclass
class OpticalDriveInfo:
    device_path: str
    model: str = "Optisches Laufwerk"
    vendor: str = ""
    disc_present: bool = False
    media_type: str = ""
    volume_label: str = ""
    mount_point: Optional[str] = None
    disc_type: DiscType = DiscType.UNKNOWN


@dataclass
class AudioTrackInfo:
    track_num: int
    duration_sec: float
    start_sector: int = 0
    end_sector: int = 0
    title: str = ""
    artist: str = ""
    album: str = ""

    def formatted_duration(self) -> str:
        mins = int(self.duration_sec // 60)
        secs = int(self.duration_sec % 60)
        return f"{mins:02d}:{secs:02d}"


@dataclass
class AudioStreamInfo:
    stream_idx: int
    langcode: str = "und"
    language: str = "Unbekannt"
    codec: str = "ac3"
    channels: int = 2
    frequency: int = 48000
    title: str = ""

    def display_text(self) -> str:
        ch_str = "5.1" if self.channels == 6 else ("7.1" if self.channels == 8 else f"{self.channels}.0")
        codec_upper = self.codec.upper()
        if self.title:
            return f"[{self.stream_idx}] {self.language} ({codec_upper} {ch_str}) - {self.title}"
        return f"[{self.stream_idx}] {self.language} ({codec_upper} {ch_str})"


@dataclass
class SubtitleStreamInfo:
    stream_idx: int
    langcode: str = "und"
    language: str = "Unbekannt"
    codec: str = "dvd_subtitle"
    title: str = ""
    forced: bool = False

    def display_text(self) -> str:
        forced_tag = " [Forced]" if self.forced else ""
        if self.title:
            return f"[{self.stream_idx}] {self.language}{forced_tag} - {self.title}"
        return f"[{self.stream_idx}] {self.language}{forced_tag}"


@dataclass
class ChapterInfo:
    chapter_num: int
    duration_sec: float = 0.0
    start_sec: float = 0.0
    title: str = ""


@dataclass
class VideoTitleInfo:
    title_num: int
    duration_sec: float
    chapter_count: int = 1
    chapters: List[ChapterInfo] = field(default_factory=list)
    width: int = 720
    height: int = 576
    fps: float = 25.0
    aspect_ratio: str = "16:9"
    video_codec: str = "mpeg2video"
    bitrate_bps: int = 0
    audio_streams: List[AudioStreamInfo] = field(default_factory=list)
    subtitle_streams: List[SubtitleStreamInfo] = field(default_factory=list)
    is_main_feature: bool = False
    name: str = ""

    def formatted_duration(self) -> str:
        hrs = int(self.duration_sec // 3600)
        mins = int((self.duration_sec % 3600) // 60)
        secs = int(self.duration_sec % 60)
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"


@dataclass
class DiscInspectionResult:
    source_path: str
    disc_type: DiscType = DiscType.UNKNOWN
    disc_label: str = ""
    total_duration_sec: float = 0.0
    audio_tracks: List[AudioTrackInfo] = field(default_factory=list)
    video_titles: List[VideoTitleInfo] = field(default_factory=list)
    main_title_idx: int = -1
    error: Optional[str] = None


# --- LAUFWERKSERKENNUNG & HARDWARE-ABSTRAKTION ---

def scan_optical_drives(sysfs_root: str = "/sys/block", dev_root: str = "/dev") -> List[OpticalDriveInfo]:
    """
    Findet alle physischen optischen Laufwerke im System.
    sysfs_root und dev_root sind parametrisiert für isolierte Tests ohne echte Hardware.
    """
    drives: List[OpticalDriveInfo] = []
    if not os.path.exists(sysfs_root):
        return drives

    try:
        entries = sorted(os.listdir(sysfs_root))
    except OSError:
        return drives

    for name in entries:
        if not name.startswith("sr") and not name.startswith("scd"):
            continue

        dev_path = os.path.join(dev_root, name)
        sys_dev_dir = os.path.join(sysfs_root, name, "device")
        
        vendor = ""
        model = "Optisches Laufwerk"
        if os.path.exists(sys_dev_dir):
            vendor_file = os.path.join(sys_dev_dir, "vendor")
            model_file = os.path.join(sys_dev_dir, "model")
            if os.path.isfile(vendor_file):
                try:
                    with open(vendor_file, "r", encoding="utf-8", errors="ignore") as f:
                        vendor = f.read().strip()
                except OSError:
                    pass
            if os.path.isfile(model_file):
                try:
                    with open(model_file, "r", encoding="utf-8", errors="ignore") as f:
                        model = f.read().strip()
                except OSError:
                    pass

        # Udev-Eigenschaften abfragen, falls dev_root /dev ist
        disc_present = False
        media_type = ""
        volume_label = ""
        disc_type = DiscType.UNKNOWN

        if dev_root == "/dev" and os.path.exists(dev_path):
            udev_props = _get_udev_properties(dev_path)
            disc_present = udev_props.get("ID_CDROM_MEDIA_STATE") == "complete" or bool(udev_props.get("ID_CDROM_MEDIA"))
            media_type = udev_props.get("ID_CDROM_MEDIA_TYPE", "")
            volume_label = udev_props.get("ID_FS_LABEL", "")
            
            if udev_props.get("ID_CDROM_MEDIA_BD") == "1":
                disc_type = DiscType.BLURAY
                media_type = media_type or "BD-ROM"
            elif udev_props.get("ID_CDROM_MEDIA_DVD") == "1":
                disc_type = DiscType.DVD_VIDEO
                media_type = media_type or "DVD-ROM"
            elif udev_props.get("ID_CDROM_MEDIA_CD") == "1":
                track_audio = int(udev_props.get("ID_CDROM_MEDIA_TRACK_COUNT_AUDIO", 0) or 0)
                if track_audio > 0:
                    disc_type = DiscType.AUDIO_CD
                else:
                    disc_type = DiscType.DATA_DISC
                media_type = media_type or "CD-ROM"

        drive_info = OpticalDriveInfo(
            device_path=dev_path,
            model=model,
            vendor=vendor,
            disc_present=disc_present,
            media_type=media_type,
            volume_label=volume_label,
            disc_type=disc_type,
        )
        drives.append(drive_info)

    return drives


def _get_udev_properties(device_path: str) -> dict[str, str]:
    """Liest Udev-Eigenschaften für ein Blockgerät."""
    props = {}
    try:
        res = subprocess.run(
            ["udevadm", "info", "-q", "property", "-n", device_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    props[k.strip()] = v.strip()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return props


def eject_drive(device_path: str) -> Tuple[bool, str]:
    """Wirft das optische Laufwerk sicher aus."""
    try:
        res = subprocess.run(["eject", device_path], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return True, "Laufwerk ausgeworfen."
        return False, res.stderr.strip() or f"Eject fehlgeschlagen (Code {res.returncode})"
    except Exception as e:
        return False, str(e)


# --- DISC-TYP-ERKENNUNG & INSPEKTION ---

def detect_disc_type(source_path: str) -> DiscType:
    """
    Ermittelt den Disc-Typ aus einem Pfad (Gerät, ISO-Datei oder Ordner).
    """
    if not source_path or not os.path.exists(source_path):
        return DiscType.UNKNOWN

    # 1. Ordner-Strukturen
    if os.path.isdir(source_path):
        base_upper = os.path.basename(os.path.normpath(source_path)).upper()
        if base_upper == "VIDEO_TS" or os.path.isdir(os.path.join(source_path, "VIDEO_TS")):
            return DiscType.DVD_VIDEO
        if os.path.isfile(os.path.join(source_path, "VIDEO_TS.IFO")):
            return DiscType.DVD_VIDEO
        if base_upper == "BDMV" or os.path.isdir(os.path.join(source_path, "BDMV")):
            return DiscType.BLURAY
        if os.path.isfile(os.path.join(source_path, "index.bdmv")):
            return DiscType.BLURAY
        return DiscType.DATA_DISC

    # 2. ISO/Image-Dateien
    if os.path.isfile(source_path):
        ext = os.path.splitext(source_path)[1].lower()
        if ext in (".iso", ".img", ".nrg"):
            return _inspect_iso_disc_type(source_path)
        return DiscType.UNKNOWN

    # 3. Blockgeräte (/dev/sr*)
    if source_path.startswith("/dev/"):
        udev = _get_udev_properties(source_path)
        if udev.get("ID_CDROM_MEDIA_BD") == "1":
            return DiscType.BLURAY
        if udev.get("ID_CDROM_MEDIA_DVD") == "1":
            return DiscType.DVD_VIDEO
        if udev.get("ID_CDROM_MEDIA_CD") == "1":
            track_audio = int(udev.get("ID_CDROM_MEDIA_TRACK_COUNT_AUDIO", 0) or 0)
            if track_audio > 0:
                return DiscType.AUDIO_CD
            return DiscType.DATA_DISC

    return DiscType.UNKNOWN


def _inspect_iso_disc_type(iso_path: str) -> DiscType:
    """Prüft eine ISO-Datei auf DVD_VIDEO oder BLURAY Signaturen."""
    try:
        with open(iso_path, "rb") as f:
            # Die Verzeichniseinträge stehen kurz hinter den Volume-Descriptoren
            # (ab Sektor 16). Acht Megabyte decken auch UDF-Abbilder mit
            # ungewöhnlichem Aufbau ab und kosten kaum Zeit.
            header = f.read(8 * 1024 * 1024)
            if b"VIDEO_TS" in header or b"DVDVIDEO" in header:
                return DiscType.DVD_VIDEO
            if b"BDMV" in header or b"index.bdmv" in header:
                return DiscType.BLURAY
    except OSError:
        pass
    # Kein Video-Kennzeichen gefunden: als Daten-Abbild behandeln. Früher kam
    # hier DVD_VIDEO heraus — damit landete jede beliebige ISO (z. B. ein
    # Spiel- oder Installationsabbild) im DVD-Titelparser.
    return DiscType.DATA_DISC


# --- PARSER: AUDIO-CD (cdparanoia TOC auf STDERR & cd-info CD-TEXT) ---

def parse_cdparanoia_toc(stderr_content: str) -> List[AudioTrackInfo]:
    """
    Parst die Titelliste von 'cdparanoia -Q' (welche auf STDERR ausgegeben wird!).
    Umrechnung: 75 Sektoren = 1 Sekunde (CDDA).
    """
    tracks: List[AudioTrackInfo] = []
    if not stderr_content:
        return tracks

    line_pattern = re.compile(
        r"^\s*(\d+)\.\s+(\d+)\s+\[(\d+):(\d+)\.(\d+)\]\s+(\d+)\s+\[(\d+):(\d+)\.(\d+)\]"
    )

    for line in stderr_content.splitlines():
        match = line_pattern.match(line)
        if match:
            track_num = int(match.group(1))
            length_sectors = int(match.group(2))
            duration_sec = round(length_sectors / 75.0, 2)
            start_sector = int(match.group(6))
            end_sector = start_sector + length_sectors - 1

            track = AudioTrackInfo(
                track_num=track_num,
                duration_sec=duration_sec,
                start_sector=start_sector,
                end_sector=end_sector,
                title=f"Track {track_num:02d}",
            )
            tracks.append(track)

    return tracks


def parse_cd_text(cd_info_output: str) -> Tuple[str, str, dict[int, dict[str, str]]]:
    """
    Parst CD-TEXT Metadaten aus der Ausgabe von 'cd-info'.
    Gibt (album_title, disc_artist, {track_num: {"title": ..., "artist": ...}}) zurück.
    """
    album_title = ""
    disc_artist = ""
    track_meta: dict[int, dict[str, str]] = {}
    current_track: Optional[int] = None
    in_disc_block = False

    for line in cd_info_output.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("CD-TEXT for Disc:"):
            in_disc_block = True
            current_track = None
            continue
        elif trimmed.startswith("CD-TEXT for Track"):
            in_disc_block = False
            m = re.search(r"Track\s+(\d+)", trimmed)
            if m:
                current_track = int(m.group(1))
                if current_track not in track_meta:
                    track_meta[current_track] = {}
            continue
        elif trimmed.startswith("CD-ROM") or trimmed.startswith("Track"):
            in_disc_block = False
            current_track = None

        if "\t" in line or ":" in line:
            parts = trimmed.split(":", 1)
            if len(parts) == 2:
                key = parts[0].strip().upper()
                val = parts[1].strip()
                if in_disc_block:
                    if key == "TITLE":
                        album_title = val
                    elif key in ("PERFORMER", "ARTIST"):
                        disc_artist = val
                elif current_track is not None:
                    if key == "TITLE":
                        track_meta[current_track]["title"] = val
                    elif key in ("PERFORMER", "ARTIST"):
                        track_meta[current_track]["artist"] = val

    return album_title, disc_artist, track_meta


def scan_audio_cd(device_path: str) -> DiscInspectionResult:
    """
    Liest eine Audio-CD via 'cdparanoia -Q' (stderr) und optional 'cd-info' ein.
    """
    result = DiscInspectionResult(source_path=device_path, disc_type=DiscType.AUDIO_CD)

    try:
        res = subprocess.run(
            ["cdparanoia", "-Q", "-d", device_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
        tracks = parse_cdparanoia_toc(res.stdout)
        if not tracks:
            result.error = "Keine Audio-Tracks auf der Audio-CD gefunden."
            return result
        result.audio_tracks = tracks
        result.total_duration_sec = sum(t.duration_sec for t in tracks)
    except Exception as e:
        result.error = f"Audio-CD konnte nicht gelesen werden: {e}"
        return result

    # Optional CD-TEXT anreichern via cd-info
    try:
        cd_info_res = subprocess.run(
            ["cd-info", "--no-cddb", "--no-device-info", device_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if cd_info_res.returncode == 0:
            album, artist, track_dict = parse_cd_text(cd_info_res.stdout)
            if album:
                result.disc_label = album
            for t in result.audio_tracks:
                t.album = album
                t.artist = artist
                if t.track_num in track_dict:
                    if track_dict[t.track_num].get("title"):
                        t.title = track_dict[t.track_num]["title"]
                    if track_dict[t.track_num].get("artist"):
                        t.artist = track_dict[t.track_num]["artist"]
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    return result


# --- PARSER: DVD-VIDEO (lsdvd -Oy Python-Literal & ffprobe Fallback) ---

def parse_lsdvd_output(stdout_content: str) -> DiscInspectionResult:
    """
    Parst die Python-Literal-Ausgabe von 'lsdvd -Oy <source>'.
    """
    result = DiscInspectionResult(source_path="", disc_type=DiscType.DVD_VIDEO)
    if not stdout_content or "=" not in stdout_content:
        result.error = "Ungültige lsdvd-Ausgabe"
        return result

    try:
        literal_part = stdout_content.split("=", 1)[1].strip()
        data = ast.literal_eval(literal_part)
    except Exception as e:
        result.error = f"Fehler beim Parsen der lsdvd-Daten: {e}"
        return result

    result.source_path = str(data.get("device", ""))
    result.disc_label = str(data.get("title", "")).strip()

    raw_tracks = data.get("track", [])
    max_duration = -1.0
    main_idx = -1

    for idx, t in enumerate(raw_tracks):
        title_num = int(t.get("ix", idx + 1))
        length = float(t.get("length", 0.0))
        
        # Video-Infos: 'lsdvd -Oy' legt width/height/fps/aspect/format FLACH auf
        # dem Track ab, es gibt KEIN verschachteltes 'video'-Wörterbuch. Wer nur
        # unter 'video' nachsieht, bekommt für jeden Titel stillschweigend die
        # Vorgabewerte (720x576 @ 25 fps) — bei einer NTSC-DVD also falsche Maße
        # und eine falsche Bildrate. Der verschachtelte Weg bleibt als Rückfall
        # für Fremd-Wrapper erhalten, die flache Angabe hat Vorrang.
        v_info = t.get("video") if isinstance(t.get("video"), dict) else {}

        def _track_value(key, default):
            value = t.get(key, v_info.get(key, default))
            return default if value in (None, "") else value

        width = int(_track_value("width", 720))
        height = int(_track_value("height", 576))
        fps = float(_track_value("fps", 25.0))
        # lsdvd schreibt das Seitenverhältnis als '16/9', LME zeigt '16:9'.
        aspect = str(_track_value("aspect", "16:9")).replace("/", ":")
        v_codec = str(_track_value("codec", "mpeg2video"))

        # Kapitel
        chapters = []
        for c in t.get("chapter", []):
            c_num = int(c.get("ix", len(chapters) + 1))
            c_len = float(c.get("length", 0.0) or 0.0)
            chapters.append(ChapterInfo(chapter_num=c_num, duration_sec=c_len))

        # Audiospuren
        audio_streams = []
        for a_idx, a in enumerate(t.get("audio", [])):
            s_ix = int(a.get("ix", a_idx + 1))
            lang = str(a.get("language", "Unbekannt") or "Unbekannt")
            lcode = str(a.get("langcode", "und") or "und")
            fmt = str(a.get("format", "ac3") or "ac3")
            channels = int(a.get("channels", 2) or 2)
            freq = int(a.get("frequency", 48000) or 48000)
            audio_streams.append(AudioStreamInfo(
                stream_idx=s_ix,
                langcode=lcode,
                language=lang,
                codec=fmt,
                channels=channels,
                frequency=freq,
            ))

        # Untertitel
        sub_streams = []
        for s_idx, s in enumerate(t.get("subp", [])):
            s_ix = int(s.get("ix", s_idx + 1))
            lang = str(s.get("language", "Unbekannt") or "Unbekannt")
            lcode = str(s.get("langcode", "und") or "und")
            sub_streams.append(SubtitleStreamInfo(
                stream_idx=s_ix,
                langcode=lcode,
                language=lang,
                codec="dvd_subtitle",
            ))

        title_info = VideoTitleInfo(
            title_num=title_num,
            duration_sec=length,
            chapter_count=len(chapters) if chapters else 1,
            chapters=chapters,
            width=width,
            height=height,
            fps=fps,
            aspect_ratio=aspect,
            video_codec=v_codec,
            audio_streams=audio_streams,
            subtitle_streams=sub_streams,
            name=f"Titel {title_num:02d}",
        )
        result.video_titles.append(title_info)

        if length > max_duration:
            max_duration = length
            main_idx = idx

    if main_idx >= 0 and main_idx < len(result.video_titles):
        result.video_titles[main_idx].is_main_feature = True
        result.main_title_idx = main_idx

    result.total_duration_sec = sum(t.duration_sec for t in result.video_titles)
    return result


def scan_dvd_source(source_path: str) -> DiscInspectionResult:
    """
    Liest eine DVD-Quelle (Gerät, ISO oder VIDEO_TS-Ordner) ein.
    Verwendet 'lsdvd -Oy' als Primärweg, mit Fallback auf ffprobe dvdvideo.
    """
    try:
        res = subprocess.run(
            ["lsdvd", "-Oy", source_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if res.returncode == 0 and "lsdvd" in res.stdout:
            result = parse_lsdvd_output(res.stdout)
            result.source_path = source_path
            return result
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    return probe_dvd_titles_ffprobe(source_path)


def probe_dvd_titles_ffprobe(source_path: str, max_titles: int = 15) -> DiscInspectionResult:
    """
    Liest DVD-Titel via 'ffprobe -f dvdvideo -title N' sequentiell aus.
    """
    result = DiscInspectionResult(source_path=source_path, disc_type=DiscType.DVD_VIDEO)
    max_duration = -1.0
    main_idx = -1

    for title_num in range(1, max_titles + 1):
        cmd = [
            "ffprobe", "-v", "error",
            "-f", "dvdvideo",
            "-title", str(title_num),
            "-show_format", "-show_streams", "-show_chapters",
            "-of", "json",
            "-i", source_path,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                if title_num > 1 and len(result.video_titles) > 0:
                    break
                continue

            data = json.loads(res.stdout)
            fmt = data.get("format", {})
            duration = float(fmt.get("duration", 0.0) or 0.0)
            try:
                bitrate = int(fmt.get("bit_rate") or 0)
            except (TypeError, ValueError):
                bitrate = 0

            width, height, fps = 720, 576, 25.0
            aspect = "16:9"
            v_codec = "mpeg2video"
            audio_streams = []
            sub_streams = []

            for s in data.get("streams", []):
                stype = s.get("codec_type")
                if stype == "video":
                    width = int(s.get("width", 720) or 720)
                    height = int(s.get("height", 576) or 576)
                    v_codec = s.get("codec_name", "mpeg2video")
                    r_fps = s.get("r_frame_rate", "25/1")
                    if "/" in r_fps:
                        num, den = r_fps.split("/", 1)
                        fps = float(num) / float(den) if float(den) else 25.0
                elif stype == "audio":
                    tags = s.get("tags", {})
                    lang = tags.get("language", "und")
                    audio_streams.append(AudioStreamInfo(
                        stream_idx=len(audio_streams),
                        langcode=lang,
                        language=_resolve_language_name(lang),
                        codec=s.get("codec_name", "ac3"),
                        channels=int(s.get("channels", 2) or 2),
                        frequency=int(s.get("sample_rate", 48000) or 48000),
                        title=tags.get("title", ""),
                    ))
                elif stype == "subtitle":
                    tags = s.get("tags", {})
                    lang = tags.get("language", "und")
                    sub_streams.append(SubtitleStreamInfo(
                        stream_idx=len(sub_streams),
                        langcode=lang,
                        language=_resolve_language_name(lang),
                        codec=s.get("codec_name", "dvd_subtitle"),
                        title=tags.get("title", ""),
                    ))

            chapters = []
            for ch in data.get("chapters", []):
                ch_id = int(ch.get("id", len(chapters) + 1))
                ch_start = float(ch.get("start_time", 0.0) or 0.0)
                ch_end = float(ch.get("end_time", 0.0) or 0.0)
                chapters.append(ChapterInfo(
                    chapter_num=ch_id,
                    start_sec=ch_start,
                    duration_sec=max(0.0, ch_end - ch_start),
                ))

            title_info = VideoTitleInfo(
                title_num=title_num,
                duration_sec=duration,
                chapter_count=len(chapters) if chapters else 1,
                chapters=chapters,
                width=width,
                height=height,
                fps=fps,
                aspect_ratio=aspect,
                video_codec=v_codec,
                bitrate_bps=bitrate,
                audio_streams=audio_streams,
                subtitle_streams=sub_streams,
                name=f"Titel {title_num:02d}",
            )
            result.video_titles.append(title_info)

            if duration > max_duration:
                max_duration = duration
                main_idx = len(result.video_titles) - 1

        except Exception:
            break

    if main_idx >= 0 and main_idx < len(result.video_titles):
        result.video_titles[main_idx].is_main_feature = True
        result.main_title_idx = main_idx

    result.total_duration_sec = sum(t.duration_sec for t in result.video_titles)
    return result


# --- BLU-RAY: Playlists aus BDMV/PLAYLIST + Streams via ffprobe ---
#
# 'bd_info' aus libbluray taucht hier bewusst nur noch für den Datenträgernamen
# und den AACS-Status auf: das Programm gibt Kopfdaten aus (Volume Identifier,
# AACS/BD+-Status, Titelzahl), aber KEINE Playlist-Liste mit Dauern, Ton- und
# Untertitelspuren. Die Playlist-Nummern stehen in BDMV/PLAYLIST/<nnnnn>.mpls,
# die Inhalte liest ffprobe über das bluray:-Protokoll.

_MPLS_NAME_RE = re.compile(r"^(\d{1,5})\.mpls$", re.IGNORECASE)


def find_bdmv_root(source_path: str) -> Optional[str]:
    """Liefert das Verzeichnis, das den BDMV-Ordner enthält (oder None)."""
    if not source_path or not os.path.isdir(source_path):
        return None
    base = os.path.normpath(source_path)
    if os.path.isdir(os.path.join(base, "BDMV")):
        return base
    if os.path.basename(base).upper() == "BDMV":
        return os.path.dirname(base) or base
    return None


def list_bluray_playlists(source_path: str) -> List[int]:
    """Playlist-Nummern aus BDMV/PLAYLIST/*.mpls, aufsteigend und doppelfrei.

    Nur für Ordner-Quellen möglich — in einem Laufwerk oder einer ISO-Datei
    liegt das Dateisystem nicht offen. Dort bleibt nur der Vorgabe-Titel.
    """
    root = find_bdmv_root(source_path)
    if not root:
        return []
    playlist_dir = os.path.join(root, "BDMV", "PLAYLIST")
    if not os.path.isdir(playlist_dir):
        return []
    numbers: List[int] = []
    try:
        for entry in os.listdir(playlist_dir):
            match = _MPLS_NAME_RE.match(entry)
            if match:
                numbers.append(int(match.group(1)))
    except OSError:
        return []
    return sorted(set(numbers))


def parse_bdinfo_header(stdout_content: str) -> dict:
    """Liest die Kopfzeilen von 'bd_info' aus.

    Echtes Ausgabeformat (aus den Formatzeichenketten des Programms):
    'Volume Identifier   : %s', 'AACS detected       : %s',
    'libaacs detected    : %s', 'AACS handled        : %s'.
    """
    header = {
        "volume_id": "",
        "aacs_detected": False,
        "aacs_handled": True,
        "bdplus_detected": False,
        "bdplus_handled": True,
    }
    flags = {
        "AACS detected": "aacs_detected",
        "AACS handled": "aacs_handled",
        "BD+ detected": "bdplus_detected",
        "BD+ handled": "bdplus_handled",
    }
    for line in (stdout_content or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "Volume Identifier":
            header["volume_id"] = value
        elif key in flags:
            header[flags[key]] = value.lower().startswith("yes")
    return header


def read_bdinfo_header(source_path: str) -> dict:
    """Ruft 'bd_info' auf und gibt die ausgewerteten Kopfzeilen zurück."""
    try:
        res = subprocess.run(
            ["bd_info", source_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return {"volume_id": "", "aacs_detected": False, "aacs_handled": True}
    return parse_bdinfo_header(res.stdout or "")


def _probe_bluray_playlist(
    source_path: str,
    playlist: Optional[int],
    timeout: int = 20,
) -> Optional[VideoTitleInfo]:
    """Liest eine einzelne Playlist über 'ffprobe -playlist N -i bluray:<pfad>'.

    playlist=None nutzt die Vorgabe von libbluray (entspricht -playlist -1).
    """
    cmd = ["ffprobe", "-v", "error"]
    if playlist is not None and playlist >= 0:
        cmd.extend(["-playlist", str(playlist)])
    cmd.extend([
        "-show_format", "-show_streams", "-show_chapters",
        "-of", "json",
        "-i", f"bluray:{source_path}",
    ])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0:
            return None
        data = json.loads(res.stdout)
    except (subprocess.SubprocessError, OSError, ValueError):
        return None

    fmt = data.get("format") or {}
    duration = float(fmt.get("duration", 0.0) or 0.0)
    try:
        bitrate = int(fmt.get("bit_rate") or 0)
    except (TypeError, ValueError):
        bitrate = 0
    width, height, fps = 1920, 1080, 23.976
    v_codec = "h264"
    audio_streams: List[AudioStreamInfo] = []
    sub_streams: List[SubtitleStreamInfo] = []

    for stream in data.get("streams", []):
        stream_type = stream.get("codec_type")
        tags = stream.get("tags") or {}
        langcode = tags.get("language", "und")

        if stream_type == "video":
            width = int(stream.get("width") or width)
            height = int(stream.get("height") or height)
            v_codec = stream.get("codec_name", v_codec)
            r_fps = str(stream.get("r_frame_rate", "") or "")
            if "/" in r_fps:
                num, den = r_fps.split("/", 1)
                try:
                    if float(den):
                        fps = float(num) / float(den)
                except ValueError:
                    pass
        elif stream_type == "audio":
            audio_streams.append(AudioStreamInfo(
                stream_idx=len(audio_streams),
                langcode=langcode,
                language=_resolve_language_name(langcode),
                codec=stream.get("codec_name", "ac3"),
                channels=int(stream.get("channels") or 2),
                frequency=int(stream.get("sample_rate") or 48000),
                title=tags.get("title", ""),
            ))
        elif stream_type == "subtitle":
            sub_streams.append(SubtitleStreamInfo(
                stream_idx=len(sub_streams),
                langcode=langcode,
                language=_resolve_language_name(langcode),
                codec=stream.get("codec_name", "hdmv_pgs_subtitle"),
                title=tags.get("title", ""),
            ))

    chapters: List[ChapterInfo] = []
    for chapter in data.get("chapters", []):
        start = float(chapter.get("start_time", 0.0) or 0.0)
        end = float(chapter.get("end_time", 0.0) or 0.0)
        chapters.append(ChapterInfo(
            chapter_num=len(chapters) + 1,
            start_sec=start,
            duration_sec=max(0.0, end - start),
        ))

    number = playlist if (playlist is not None and playlist >= 0) else -1
    name = f"Playlist {number:05d}" if number >= 0 else "Vorgabe-Titel (Playlist unbekannt)"

    return VideoTitleInfo(
        title_num=number,
        duration_sec=duration,
        chapter_count=len(chapters) if chapters else 1,
        chapters=chapters,
        width=width,
        height=height,
        fps=fps,
        aspect_ratio="16:9",
        video_codec=v_codec,
        bitrate_bps=bitrate,
        audio_streams=audio_streams,
        subtitle_streams=sub_streams,
        name=name,
    )


def scan_bluray_source(
    source_path: str,
    min_duration_sec: float = 60.0,
    max_playlists: int = 40,
) -> DiscInspectionResult:
    """Liest eine Blu-ray-Quelle (Ordner, ISO oder Laufwerk) ein."""
    result = DiscInspectionResult(source_path=source_path, disc_type=DiscType.BLURAY)

    root = find_bdmv_root(source_path)
    probe_path = root or source_path

    header = read_bdinfo_header(probe_path)
    result.disc_label = header.get("volume_id") or os.path.basename(
        os.path.normpath(probe_path)
    )

    titles: List[VideoTitleInfo] = []
    for number in list_bluray_playlists(source_path)[:max_playlists]:
        info = _probe_bluray_playlist(probe_path, number)
        if info and info.duration_sec > 0:
            titles.append(info)

    # Playlist-Verschleierung: viele Discs legen dutzende Kurz-Playlists an.
    # Die kurzen nur wegwerfen, wenn danach überhaupt etwas übrig bleibt.
    long_enough = [t for t in titles if t.duration_sec >= min_duration_sec]
    if long_enough:
        titles = long_enough

    if not titles:
        # Laufwerk oder ISO: das Dateisystem liegt nicht offen, also bleibt
        # nur der Vorgabe-Titel von libbluray.
        info = _probe_bluray_playlist(probe_path, None)
        if info:
            titles = [info]

    if not titles:
        if header.get("aacs_detected") and not header.get("aacs_handled"):
            _, hint = check_bluray_encryption_support()
            result.error = (
                "Diese Blu-ray ist AACS-verschlüsselt und konnte nicht entschlüsselt "
                f"werden. {hint}"
            )
        elif header.get("bdplus_detected") and not header.get("bdplus_handled"):
            result.error = (
                "Diese Blu-ray ist zusätzlich mit BD+ geschützt und konnte nicht "
                "gelesen werden. Dafür wird libbdplus benötigt; AACS-Schlüssel allein "
                "genügen hier nicht."
            )
        else:
            result.error = "Blu-ray konnte nicht eingelesen werden."
        return result

    result.video_titles = titles
    main_idx = max(range(len(titles)), key=lambda i: titles[i].duration_sec)
    titles[main_idx].is_main_feature = True
    result.main_title_idx = main_idx
    result.total_duration_sec = sum(t.duration_sec for t in titles)
    return result


def inspect_source(source_path: str) -> DiscInspectionResult:
    """
    Haupt-Einstiegspunkt: Untersucht beliebige optische Quelle (Laufwerk, ISO, Ordner)
    und gibt die vollständige Titel-/Track-Struktur zurück.
    """
    disc_type = detect_disc_type(source_path)
    if disc_type == DiscType.AUDIO_CD:
        return scan_audio_cd(source_path)
    elif disc_type == DiscType.DVD_VIDEO:
        return scan_dvd_source(source_path)
    elif disc_type == DiscType.BLURAY:
        return scan_bluray_source(source_path)
    else:
        return DiscInspectionResult(
            source_path=source_path,
            disc_type=disc_type,
            error="Unbekannter oder nicht unterstützter Medientyp."
        )


# --- BEFEHLSGENERIERUNG (REINE FUNKTIONEN FÜR SAUBERE TESTS) ---

def build_dvd_rip_args(
    source_path: str,
    title_num: int = 1,
    chapter_start: int = 1,
    chapter_end: int = 0,
    audio_stream_idx: Optional[int] = None,
    subtitle_stream_idx: Optional[int] = None,
    output_file: str = "output.mkv",
    preset_settings: Optional[dict[str, Any]] = None,
    remux_mkv: bool = False,
    ignore_errors: bool = True,
) -> Tuple[List[str], str]:
    """
    Erzeugt die vollständige FFmpeg-Befehlszeile für einen DVD-Titel.
    Gibt (ffmpeg_args_liste, final_output_file) zurück.
    """
    if preset_settings and "ignore_errors" in preset_settings:
        ignore_errors = bool(preset_settings["ignore_errors"])

    input_args = [
        "-f", "dvdvideo",
        "-title", str(title_num),
        "-chapter_start", str(chapter_start),
        "-chapter_end", str(chapter_end),
    ]
    if ignore_errors:
        input_args = ["-err_detect", "ignore_err", "-fflags", "+discardcorrupt+genpts"] + input_args

    args = ["-y"] + input_args + ["-i", source_path]

    args += ["-map", "0:v:0"]
    # -1 bedeutet "alle Spuren dieser Art" (Auswahl 'Alle' im Ripper-Dialog)
    # und muss wie in presets.get_ffmpeg_args zu 0:a? / 0:s? werden — ein rohes
    # 0:a:-1 wählt laut FFmpeg die LETZTE Spur, nicht alle.
    if audio_stream_idx is None or audio_stream_idx == -1:
        args += ["-map", "0:a?"]
    else:
        args += ["-map", f"0:a:{audio_stream_idx}"]

    if subtitle_stream_idx == -1:
        args += ["-map", "0:s?"]
    elif subtitle_stream_idx is not None:
        args += ["-map", f"0:s:{subtitle_stream_idx}"]

    out_dir = os.path.dirname(output_file) or "."
    out_base = os.path.splitext(os.path.basename(output_file))[0]
    final_output = output_file

    if remux_mkv or subtitle_stream_idx is not None:
        if not output_file.lower().endswith(".mkv"):
            final_output = os.path.join(out_dir, f"{out_base}.mkv")

    if remux_mkv:
        args += ["-c:v", "copy", "-c:a", "copy"]
        if subtitle_stream_idx is not None:
            args += ["-c:s", "copy"]
    else:
        if preset_settings:
            v_codec = preset_settings.get("video_codec", "libx264")
            a_codec = preset_settings.get("audio_codec", "aac")
            v_bitrate = preset_settings.get("video_bitrate", "")
            crf = preset_settings.get("crf", "")
            a_bitrate = preset_settings.get("audio_bitrate", "192k")

            args += ["-c:v", v_codec]
            if crf:
                args += ["-crf", str(crf)]
            elif v_bitrate:
                args += ["-b:v", str(v_bitrate)]
            
            args += ["-c:a", a_codec]
            if a_bitrate and a_codec not in ("flac", "alac", "copy"):
                args += ["-b:a", str(a_bitrate)]

            if subtitle_stream_idx is not None:
                args += ["-c:s", "copy"]
        else:
            args += ["-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-b:a", "192k"]
            if subtitle_stream_idx is not None:
                args += ["-c:s", "copy"]

    args.append(final_output)
    return args, final_output


def build_bluray_rip_args(
    source_path: str,
    playlist_num: int = 1,
    audio_stream_idx: Optional[int] = None,
    subtitle_stream_idx: Optional[int] = None,
    output_file: str = "output.mkv",
    preset_settings: Optional[dict[str, Any]] = None,
    remux_mkv: bool = False,
    ignore_errors: bool = True,
) -> Tuple[List[str], str]:
    """
    Erzeugt die vollständige FFmpeg-Befehlszeile für eine Blu-ray Playlist.
    """
    if preset_settings and "ignore_errors" in preset_settings:
        ignore_errors = bool(preset_settings["ignore_errors"])

    input_args = ["-playlist", str(playlist_num)]
    if ignore_errors:
        input_args = ["-err_detect", "ignore_err", "-fflags", "+discardcorrupt+genpts"] + input_args

    probe_url = f"bluray:{source_path}"
    args = ["-y"] + input_args + ["-i", probe_url]

    args += ["-map", "0:v:0"]
    # -1 bedeutet "alle Spuren dieser Art" (Auswahl 'Alle' im Ripper-Dialog)
    # und muss wie in presets.get_ffmpeg_args zu 0:a? / 0:s? werden — ein rohes
    # 0:a:-1 wählt laut FFmpeg die LETZTE Spur, nicht alle.
    if audio_stream_idx is None or audio_stream_idx == -1:
        args += ["-map", "0:a?"]
    else:
        args += ["-map", f"0:a:{audio_stream_idx}"]

    if subtitle_stream_idx == -1:
        args += ["-map", "0:s?"]
    elif subtitle_stream_idx is not None:
        args += ["-map", f"0:s:{subtitle_stream_idx}"]

    out_dir = os.path.dirname(output_file) or "."
    out_base = os.path.splitext(os.path.basename(output_file))[0]
    final_output = output_file

    if remux_mkv or subtitle_stream_idx is not None:
        if not output_file.lower().endswith(".mkv"):
            final_output = os.path.join(out_dir, f"{out_base}.mkv")

    if remux_mkv:
        args += ["-c:v", "copy", "-c:a", "copy"]
        if subtitle_stream_idx is not None:
            args += ["-c:s", "copy"]
    else:
        if preset_settings:
            v_codec = preset_settings.get("video_codec", "libx264")
            a_codec = preset_settings.get("audio_codec", "aac")
            crf = preset_settings.get("crf", "20")
            a_bitrate = preset_settings.get("audio_bitrate", "192k")
            args += ["-c:v", v_codec, "-crf", str(crf), "-c:a", a_codec, "-b:a", str(a_bitrate)]
            if subtitle_stream_idx is not None:
                args += ["-c:s", "copy"]
        else:
            args += ["-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-b:a", "192k"]
            if subtitle_stream_idx is not None:
                args += ["-c:s", "copy"]

    args.append(final_output)
    return args, final_output


def build_audio_cd_rip_command(
    device_path: str,
    track_num: int,
    tmp_wav_output: str,
) -> List[str]:
    """
    Erzeugt den cdparanoia-Befehl für einen einzelnen Audio-Track.
    """
    return ["cdparanoia", "-d", device_path, f"{track_num}-{track_num}", tmp_wav_output]


def audio_codec_key_from_label(label: str) -> str:
    """Ordnet den Anzeigetext der Audio-CD-Formatauswahl einem Codec-Schlüssel zu.

    Einzige Quelle für beide Wege (Queue und Direkt-Rip): früher kannte der
    Queue-Zweig nur flac/mp3/wav und der Direkt-Zweig alac nicht — AAC, Opus
    und ALAC fielen stillschweigend auf WAV zurück.
    """
    choice = str(label or "").strip().lower()
    if "flac" in choice:
        return "flac"
    if "mp3" in choice:
        return "mp3"
    if "aac" in choice:
        return "aac"
    if "opus" in choice:
        return "opus"
    if "alac" in choice:
        return "alac"
    return "wav"


def audio_file_extension(codec_key: str) -> str:
    """Dateiendung zum Codec-Schlüssel (AAC und ALAC gehören in M4A)."""
    return {"aac": "m4a", "alac": "m4a", "opus": "opus"}.get(str(codec_key or "").lower(), str(codec_key or "wav").lower())


def build_audio_encode_args(
    tmp_wav_input: str,
    output_file: str,
    codec: str = "flac",
    bitrate: str = "320k",
    track_info: Optional[AudioTrackInfo] = None,
) -> List[str]:
    """
    Erzeugt den FFmpeg-Encodierungsbefehl für ein temporäres Audio-WAV inklusive Metadaten.
    """
    args = ["-y", "-i", tmp_wav_input]
    if codec == "flac":
        args += ["-c:a", "flac"]
    elif codec == "mp3":
        args += ["-c:a", "libmp3lame", "-b:a", bitrate or "320k"]
    elif codec == "aac":
        args += ["-c:a", "aac", "-b:a", bitrate or "256k"]
    elif codec == "opus":
        args += ["-c:a", "libopus", "-b:a", bitrate or "160k"]
    elif codec == "alac":
        args += ["-c:a", "alac"]
    elif codec == "wav":
        args += ["-c:a", "pcm_s16le"]
    else:
        args += ["-c:a", "flac"]

    if track_info:
        if track_info.title:
            args += ["-metadata", f"title={track_info.title}"]
        if track_info.artist:
            args += ["-metadata", f"artist={track_info.artist}"]
        if track_info.album:
            args += ["-metadata", f"album={track_info.album}"]
        if track_info.track_num:
            args += ["-metadata", f"track={track_info.track_num}"]

    args.append(output_file)
    return args


def build_iso_dump_command(
    device_path: str,
    output_iso_path: str,
    block_count: Optional[int] = None,
    conv_options: str = "noerror,sync",
) -> List[str]:
    """
    Erzeugt den dd-Befehl für ein 1:1 ISO-Abbild eines optischen Datenträgers.
    """
    cmd = ["dd", f"if={device_path}", f"of={output_iso_path}", "bs=2048"]
    if conv_options:
        cmd.append(f"conv={conv_options}")
    cmd.append("status=progress")
    if block_count and block_count > 0:
        cmd.append(f"count={block_count}")
    return cmd



# --- ZWISCHENSPEICHER FÜR DEN ZWEISTUFIGEN RIP ---
#
# Eine Disc wird erst verlustfrei ausgelesen und danach aus der Zwischendatei
# konvertiert. Das Laufwerk ist damit nach wenigen Minuten frei, statt über die
# ganze (oft stundenlange) Umwandlung hinweg zu laufen — und ein Lesefehler
# kostet nicht den kompletten Durchgang.
#
# Der Ort dafür darf NICHT blind /tmp sein: auf vielen Systemen ist das ein
# tmpfs und liegt damit im Arbeitsspeicher. Ein Blu-ray-Remux von 30+ GB würde
# dort den RAM auffressen. Deshalb wird nach freiem Platz ausgewählt.

# Fallback-Datenraten, wenn die Quelle keine meldet (Bit pro Sekunde).
_FALLBACK_BITRATE = {
    DiscType.BLURAY: 40_000_000,
    DiscType.DVD_VIDEO: 9_800_000,
}
STAGING_MARGIN = 1.15   # Sicherheitszuschlag auf die Schätzung


def estimate_remux_bytes(
    duration_sec: float,
    bitrate_bps: Optional[int] = None,
    disc_type: Optional[DiscType] = None,
) -> int:
    """Schätzt die Größe eines verlustfreien Auslesevorgangs in Bytes."""
    duration = max(0.0, float(duration_sec or 0.0))
    if not duration:
        return 0
    rate = int(bitrate_bps or 0)
    if rate <= 0:
        rate = _FALLBACK_BITRATE.get(disc_type or DiscType.BLURAY, 40_000_000)
    return int(duration * rate / 8.0)


def staging_candidates(
    preferred: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> List[str]:
    """Mögliche Orte für die Zwischendatei, in der Reihenfolge der Eignung.

    Zuerst der ausdrücklich eingestellte Ordner, dann TMPDIR, dann der
    Zielordner (den hat der Anwender selbst gewählt, dort ist meist Platz),
    danach die üblichen Ablagen. /tmp steht bewusst zuletzt.
    """
    candidates: List[str] = []

    def add(path: Optional[str]) -> None:
        if not path:
            return
        expanded = os.path.abspath(os.path.expanduser(str(path)))
        if expanded not in candidates:
            candidates.append(expanded)

    add(preferred)
    add(os.environ.get("TMPDIR"))
    add(output_dir)
    add(os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
        "linux-media-encoder",
    ))
    add("/var/tmp")
    add("/tmp")
    return candidates


def free_space(path: str) -> int:
    """Freier Platz am nächstgelegenen vorhandenen Elternverzeichnis (Bytes)."""
    probe = os.path.abspath(os.path.expanduser(path or "."))
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return 0
        probe = parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return 0


def choose_staging_dir(
    needed_bytes: int,
    preferred: Optional[str] = None,
    output_dir: Optional[str] = None,
    margin: float = STAGING_MARGIN,
) -> Tuple[Optional[str], List[Tuple[str, int]]]:
    """Wählt einen Zwischenspeicher mit genug Platz.

    Gibt (Ordner oder None, [(Kandidat, freier Platz), …]) zurück. Die Liste
    dient der Fehlermeldung: ohne konkrete Zahlen kann niemand entscheiden,
    was zu tun ist.
    """
    required = int(max(0, needed_bytes) * margin)
    report: List[Tuple[str, int]] = []
    chosen: Optional[str] = None

    for candidate in staging_candidates(preferred, output_dir):
        available = free_space(candidate)
        report.append((candidate, available))
        if chosen is None and available >= required:
            chosen = candidate

    return chosen, report


def format_bytes(value: int) -> str:
    """Größenangabe in einer für Menschen lesbaren Form."""
    size = float(max(0, int(value)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def get_optical_media_size(device_path: str) -> int:
    """Größe des eingelegten Datenträgers in Bytes (0 = unbekannt).

    Ohne diesen Wert liest 'dd' bis EOF — viele Laufwerke laufen dabei am
    Discende in einen Lesefehler, und der Fortschrittsbalken bleibt mangels
    Bezugsgröße die ganze Zeit auf 0 %.
    """
    try:
        res = subprocess.run(
            ["blockdev", "--getsize64", device_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            size = int((res.stdout or "0").strip() or 0)
            if size > 0:
                return size
    except (subprocess.SubprocessError, FileNotFoundError, OSError, ValueError):
        pass

    # Rückfall: Sektorzahl aus dem ISO-9660-Primary-Volume-Descriptor
    # (Sektor 16, Kennung 'CD001'; Volumenraum an Offset 80, Blockgröße an 128).
    try:
        with open(device_path, "rb") as handle:
            handle.seek(16 * 2048)
            pvd = handle.read(2048)
        if len(pvd) >= 132 and pvd[1:6] == b"CD001":
            blocks = int.from_bytes(pvd[80:84], "little")
            block_size = int.from_bytes(pvd[128:130], "little") or 2048
            if blocks > 0:
                return blocks * block_size
    except OSError:
        pass

    return 0


# --- LAUFZEIT- & VERSCHLÜSSELUNGSPRÜFUNGEN ---

def check_dvd_encryption_support() -> Tuple[bool, str]:
    """Prüft, ob libdvdcss zur Entschlüsselung von Video-DVDs verfügbar ist."""
    lib = ctypes.util.find_library("dvdcss")
    if lib:
        return True, "libdvdcss ist verfügbar."
    return False, "libdvdcss ist nicht installiert. Verschlüsselte Video-DVDs (CSS) können nicht abgespielt oder gerippt werden."


def aacs_keydb_search_paths() -> List[str]:
    """Alle Orte, an denen libaacs nach KEYDB.cfg sucht — in dieser Reihenfolge.

    libaacs folgt der XDG-Basisverzeichnis-Festlegung: zuerst
    $XDG_CONFIG_HOME/aacs (Vorgabe ~/.config/aacs), danach jedes Verzeichnis
    aus $XDG_CONFIG_DIRS (Vorgabe /etc/xdg). Nur den Benutzerpfad zu prüfen
    übersieht eine systemweit abgelegte Datenbank.
    """
    paths: List[str] = []
    config_home = os.environ.get("XDG_CONFIG_HOME", "").strip() or os.path.expanduser("~/.config")
    paths.append(os.path.join(config_home, "aacs", "KEYDB.cfg"))

    config_dirs = os.environ.get("XDG_CONFIG_DIRS", "").strip() or "/etc/xdg"
    for directory in config_dirs.split(":"):
        directory = directory.strip()
        if directory:
            paths.append(os.path.join(directory, "aacs", "KEYDB.cfg"))
    return paths


def find_aacs_keydb() -> Optional[str]:
    """Pfad der gefundenen AACS-Schlüsseldatenbank (oder None)."""
    for path in aacs_keydb_search_paths():
        if os.path.isfile(path):
            return path
    return None


def check_bluray_encryption_support() -> Tuple[bool, str]:
    """Prüft, ob libaacs und eine KEYDB.cfg für AACS-Blu-rays verfügbar sind."""
    lib = ctypes.util.find_library("aacs")
    if not lib:
        return False, (
            "libaacs ist nicht installiert. Verschlüsselte Blu-rays (AACS) können nicht "
            "gelesen werden. Unverschlüsselte Blu-rays und BDMV-Ordner funktionieren."
        )

    keydb_path = find_aacs_keydb()
    if not keydb_path:
        locations = " oder ".join(aacs_keydb_search_paths())
        return False, (
            "libaacs ist vorhanden, aber es liegt keine Schlüsseldatenbank KEYDB.cfg "
            f"an einem der Suchorte ({locations}). Kommerzielle Blu-rays benötigen diese Schlüssel."
        )

    return True, f"libaacs und KEYDB.cfg sind vorhanden ({keydb_path})."


def check_ffmpeg_optical_capabilities() -> dict[str, bool]:
    """Prüft die Unterstützung für dvdvideo Demuxer und bluray Protokoll in FFmpeg."""
    caps = {"dvdvideo": False, "bluray": False}
    try:
        res_demux = subprocess.run(["ffmpeg", "-demuxers"], capture_output=True, text=True, timeout=5)
        if "dvdvideo" in res_demux.stdout:
            caps["dvdvideo"] = True
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    try:
        res_proto = subprocess.run(["ffmpeg", "-protocols"], capture_output=True, text=True, timeout=5)
        if "bluray" in res_proto.stdout:
            caps["bluray"] = True
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    return caps


@dataclass
class OpticalComponent:
    """Eine externe Voraussetzung des Ripper-Bereichs und ihr Zustand.

    'blocking_for' nennt die Quellarten, die OHNE diese Komponente gar nicht
    gehen; alles andere ist eine Komfort- oder Entschlüsselungszutat.
    """
    key: str
    name: str
    available: bool
    purpose: str
    blocking_for: Tuple[DiscType, ...] = ()
    detail: str = ""

    @property
    def is_blocking(self) -> bool:
        return bool(self.blocking_for) and not self.available


def check_optical_environment() -> List[OpticalComponent]:
    """Erhebt den Zustand aller externen Voraussetzungen des Rippers.

    Bewusst eine reine Bestandsaufnahme ohne Nebenwirkungen: die Oberfläche
    entscheidet, was davon sie zeigt und was eine Aktion sperrt.
    """
    caps = check_ffmpeg_optical_capabilities()
    has_dvdcss, dvdcss_detail = check_dvd_encryption_support()
    has_aacs, aacs_detail = check_bluray_encryption_support()

    return [
        OpticalComponent(
            key="ffmpeg",
            name="ffmpeg",
            available=bool(shutil.which("ffmpeg")),
            purpose="Grundlage für alle Rip- und Konvertierungsvorgänge",
            blocking_for=(DiscType.AUDIO_CD, DiscType.DVD_VIDEO, DiscType.BLURAY),
        ),
        OpticalComponent(
            key="ffprobe",
            name="ffprobe",
            available=bool(shutil.which("ffprobe")),
            purpose="Auslesen von Titeln, Spuren und Kapiteln",
            blocking_for=(DiscType.DVD_VIDEO, DiscType.BLURAY),
        ),
        OpticalComponent(
            key="dvdvideo",
            name="ffmpeg: dvdvideo-Demuxer",
            available=bool(caps.get("dvdvideo")),
            purpose="DVD-Video einlesen (FFmpeg mit libdvdnav/libdvdread gebaut)",
            blocking_for=(DiscType.DVD_VIDEO,),
        ),
        OpticalComponent(
            key="bluray",
            name="ffmpeg: bluray-Protokoll",
            available=bool(caps.get("bluray")),
            purpose="Blu-ray einlesen (FFmpeg mit libbluray gebaut)",
            blocking_for=(DiscType.BLURAY,),
        ),
        OpticalComponent(
            key="cdparanoia",
            name="cdparanoia",
            available=bool(shutil.which("cdparanoia")),
            purpose="Audio-CDs auslesen (FFmpeg kann CDDA nicht selbst lesen)",
            blocking_for=(DiscType.AUDIO_CD,),
        ),
        OpticalComponent(
            key="dd",
            name="dd",
            available=bool(shutil.which("dd")),
            purpose="1:1 ISO-Abbild eines Datenträgers erstellen",
        ),
        OpticalComponent(
            key="cd-info",
            name="cd-info",
            available=bool(shutil.which("cd-info")),
            purpose="CD-Text als Titel- und Interpretenangabe (aus libcdio)",
        ),
        OpticalComponent(
            key="lsdvd",
            name="lsdvd",
            available=bool(shutil.which("lsdvd")),
            purpose="genaue DVD-Titel- und Kapitelangaben; ohne lsdvd greift ein langsamerer ffprobe-Weg",
        ),
        OpticalComponent(
            key="bd_info",
            name="bd_info",
            available=bool(shutil.which("bd_info")),
            purpose="Datenträgername und Kopierschutz-Zustand einer Blu-ray (aus libbluray)",
        ),
        OpticalComponent(
            key="libdvdcss",
            name="libdvdcss",
            available=has_dvdcss,
            purpose="kopiergeschützte (CSS-)DVDs lesen",
            detail=dvdcss_detail,
        ),
        OpticalComponent(
            key="libaacs",
            name="libaacs + KEYDB.cfg",
            available=has_aacs,
            purpose="AACS-geschützte Blu-rays lesen",
            detail=aacs_detail,
        ),
        OpticalComponent(
            key="libbdplus",
            name="libbdplus",
            available=bool(ctypes.util.find_library("bdplus")),
            purpose="zusätzlich BD+-geschützte Blu-rays lesen",
        ),
    ]


def missing_optical_components(
    disc_type: Optional[DiscType] = None,
    blocking_only: bool = False,
) -> List[OpticalComponent]:
    """Fehlende Komponenten, optional auf eine Quellart eingegrenzt."""
    result = []
    for component in check_optical_environment():
        if component.available:
            continue
        if blocking_only and not component.is_blocking:
            continue
        if disc_type is not None and blocking_only and disc_type not in component.blocking_for:
            continue
        result.append(component)
    return result


def _resolve_language_name(langcode: str) -> str:
    """Ermittelt einen lesbaren Sprachnamen aus einem ISO-Code."""
    code = langcode.lower().strip()
    mapping = {
        "de": "Deutsch", "deu": "Deutsch", "ger": "Deutsch",
        "en": "English", "eng": "English",
        "fr": "Français", "fra": "Français", "fre": "Français",
        "es": "Español", "spa": "Español",
        "it": "Italiano", "ita": "Italiano",
        "ja": "Japanisch", "jpn": "Japanisch",
        "zh": "Chinesisch", "zho": "Chinesisch", "chi": "Chinesisch",
        "ru": "Russisch", "rus": "Russisch",
        "und": "Unbekannt",
    }
    return mapping.get(code, langcode.upper() if len(code) <= 3 else langcode)
