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
            header = f.read(1024 * 1024)  # Erstes Megabyte lesen
            if b"VIDEO_TS" in header or b"DVDVIDEO" in header:
                return DiscType.DVD_VIDEO
            if b"BDMV" in header or b"index.bdmv" in header:
                return DiscType.BLURAY
    except OSError:
        pass
    return DiscType.DVD_VIDEO


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
        
        # Video-Infos
        v_info = t.get("video", {})
        width = int(v_info.get("width", 720) or 720)
        height = int(v_info.get("height", 576) or 576)
        fps = float(v_info.get("fps", 25.0) or 25.0)
        aspect = str(v_info.get("aspect", "16:9") or "16:9")
        v_codec = str(v_info.get("codec", "mpeg2video") or "mpeg2video")

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


# --- PARSER: BLU-RAY (bd_info & ffprobe bluray: Fallback) ---

def parse_bdinfo_output(stdout_content: str) -> DiscInspectionResult:
    """
    Parst die Ausgabe von 'bd_info <pfad>' (aus libbluray).
    """
    result = DiscInspectionResult(source_path="", disc_type=DiscType.BLURAY)
    if not stdout_content:
        result.error = "Leere bd_info Ausgabe"
        return result

    for line in stdout_content.splitlines():
        if "Volume Identifier" in line and ":" in line:
            result.disc_label = line.split(":", 1)[1].strip()
        elif "Disc Title" in line and ":" in line:
            if not result.disc_label:
                result.disc_label = line.split(":", 1)[1].strip()

    current_title: Optional[VideoTitleInfo] = None
    max_duration = -1.0
    main_idx = -1

    for line in stdout_content.splitlines():
        trimmed = line.strip()
        if "Playlist:" in trimmed:
            m = re.search(r"Playlist:\s*(\d+)(?:\.MPLS)?,?\s*Duration:\s*(\d+):(\d+):(\d+),?\s*Chapters:\s*(\d+)", trimmed, re.IGNORECASE)
            if m:
                p_id = int(m.group(1))
                hrs, mins, secs = int(m.group(2)), int(m.group(3)), int(m.group(4))
                dur = hrs * 3600 + mins * 60 + secs
                ch_count = int(m.group(5))

                current_title = VideoTitleInfo(
                    title_num=p_id,
                    duration_sec=float(dur),
                    chapter_count=ch_count,
                    width=1920,
                    height=1080,
                    fps=23.976,
                    video_codec="h264",
                    name=f"Playlist {p_id:05d}",
                )
                result.video_titles.append(current_title)

                if dur > max_duration:
                    max_duration = dur
                    main_idx = len(result.video_titles) - 1
            continue

        if current_title:
            if "Video Stream:" in trimmed:
                v_line = trimmed.split("Video Stream:", 1)[1]
                if "1080" in v_line:
                    current_title.width, current_title.height = 1920, 1080
                elif "2160" in v_line or "4K" in v_line:
                    current_title.width, current_title.height = 3840, 2160
                elif "720" in v_line:
                    current_title.width, current_title.height = 1280, 720
                if "H.264" in v_line or "AVC" in v_line:
                    current_title.video_codec = "h264"
                elif "HEVC" in v_line or "H.265" in v_line:
                    current_title.video_codec = "hevc"
                elif "VC-1" in v_line:
                    current_title.video_codec = "vc1"
            elif "Audio Stream:" in trimmed:
                a_line = trimmed.split("Audio Stream:", 1)[1]
                lang = "und"
                m_lang = re.search(r"\(([^)]+)\)", a_line)
                if m_lang:
                    lang = m_lang.group(1).strip()
                channels = 6 if "5.1" in a_line else (8 if "7.1" in a_line else 2)
                codec = "ac3"
                if "DTS-HD" in a_line:
                    codec = "dts-hd"
                elif "DTS" in a_line:
                    codec = "dts"
                elif "TrueHD" in a_line:
                    codec = "truehd"
                elif "PCM" in a_line or "LPCM" in a_line:
                    codec = "pcm"
                current_title.audio_streams.append(AudioStreamInfo(
                    stream_idx=len(current_title.audio_streams),
                    langcode=lang.lower()[:3],
                    language=lang,
                    codec=codec,
                    channels=channels,
                ))
            elif "Subtitle:" in trimmed:
                s_line = trimmed.split("Subtitle:", 1)[1]
                lang = "und"
                parts = s_line.split("/")
                if len(parts) > 1:
                    lang = parts[1].strip()
                current_title.subtitle_streams.append(SubtitleStreamInfo(
                    stream_idx=len(current_title.subtitle_streams),
                    langcode=lang.lower()[:3],
                    language=lang,
                    codec="hdmv_pgs_subtitle",
                ))

    if main_idx >= 0 and main_idx < len(result.video_titles):
        result.video_titles[main_idx].is_main_feature = True
        result.main_title_idx = main_idx

    result.total_duration_sec = sum(t.duration_sec for t in result.video_titles)
    return result


def scan_bluray_source(source_path: str) -> DiscInspectionResult:
    """
    Liest eine Blu-ray-Quelle via 'bd_info' oder ffprobe ein.
    """
    try:
        res = subprocess.run(
            ["bd_info", source_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if res.returncode == 0 and "Playlist" in res.stdout:
            result = parse_bdinfo_output(res.stdout)
            result.source_path = source_path
            return result
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    result = DiscInspectionResult(source_path=source_path, disc_type=DiscType.BLURAY)
    try:
        probe_url = f"bluray:{source_path}"
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", probe_url],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0:
            data = json.loads(res.stdout)
            fmt = data.get("format", {})
            dur = float(fmt.get("duration", 0.0) or 0.0)
            title_info = VideoTitleInfo(
                title_num=1,
                duration_sec=dur,
                name="Hauptfilm (Blu-ray)",
                is_main_feature=True,
            )
            result.video_titles.append(title_info)
            result.main_title_idx = 0
            result.total_duration_sec = dur
    except Exception as e:
        result.error = f"Blu-ray konnte nicht eingelesen werden: {e}"

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
) -> Tuple[List[str], str]:
    """
    Erzeugt die vollständige FFmpeg-Befehlszeile für einen DVD-Titel.
    Gibt (ffmpeg_args_liste, final_output_file) zurück.
    """
    input_args = [
        "-f", "dvdvideo",
        "-title", str(title_num),
        "-chapter_start", str(chapter_start),
        "-chapter_end", str(chapter_end),
    ]

    args = ["-y"] + input_args + ["-i", source_path]

    args += ["-map", "0:v:0"]
    if audio_stream_idx is not None:
        args += ["-map", f"0:a:{audio_stream_idx}"]
    else:
        args += ["-map", "0:a?"]

    if subtitle_stream_idx is not None:
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
) -> Tuple[List[str], str]:
    """
    Erzeugt die vollständige FFmpeg-Befehlszeile für eine Blu-ray Playlist.
    """
    input_args = ["-playlist", str(playlist_num)]
    probe_url = f"bluray:{source_path}"
    args = ["-y"] + input_args + ["-i", probe_url]

    args += ["-map", "0:v:0"]
    if audio_stream_idx is not None:
        args += ["-map", f"0:a:{audio_stream_idx}"]
    else:
        args += ["-map", "0:a?"]

    if subtitle_stream_idx is not None:
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
) -> List[str]:
    """
    Erzeugt den dd-Befehl für ein 1:1 ISO-Abbild eines optischen Datenträgers.
    """
    cmd = ["dd", f"if={device_path}", f"of={output_iso_path}", "bs=2048", "status=progress"]
    if block_count and block_count > 0:
        cmd.append(f"count={block_count}")
    return cmd


# --- LAUFZEIT- & VERSCHLÜSSELUNGSPRÜFUNGEN ---

def check_dvd_encryption_support() -> Tuple[bool, str]:
    """Prüft, ob libdvdcss zur Entschlüsselung von Video-DVDs verfügbar ist."""
    lib = ctypes.util.find_library("dvdcss")
    if lib:
        return True, "libdvdcss ist verfügbar."
    return False, "libdvdcss ist nicht installiert. Verschlüsselte Video-DVDs (CSS) können nicht abgespielt oder gerippt werden."


def check_bluray_encryption_support() -> Tuple[bool, str]:
    """Prüft, ob libaacs und KEYDB.cfg für AACS-Blu-rays verfügbar sind."""
    lib = ctypes.util.find_library("aacs")
    if not lib:
        return False, "libaacs ist nicht installiert. Verschlüsselte Blu-rays (AACS) können nicht gelesen werden."
    
    keydb_path = os.path.expanduser("~/.config/aacs/KEYDB.cfg")
    if not os.path.isfile(keydb_path):
        return False, "libaacs ist vorhanden, aber die Schlüsseldatenbank ~/.config/aacs/KEYDB.cfg fehlt. Kommerzielle Blu-rays benötigen diese Schlüssel."
    
    return True, "libaacs und KEYDB.cfg sind vorhanden."


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
