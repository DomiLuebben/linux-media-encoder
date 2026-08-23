# -*- coding: utf-8 -*-
"""
Preset-Verwaltung für den Linux Media Encoder.
Definiert vordefinierte Profile und generiert die FFmpeg-Argumente.
"""

import functools
import re
import subprocess

# Vordefinierte Standard-Presets
PRESETS = {
    "MP4 (H.264 / AAC) - Standard 1080p": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "8M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "width": 1920,
        "height": 1080,
        "fps": "25",
        "profile": "High"
    },
    "MP4 (H.265 / AAC) - Hocheffizient (CRF 23)": {
        "container": "mp4",
        "video_codec": "libx265",
        "video_bitrate": "",
        "crf": "23",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "width": 1920,
        "height": 1080,
        "fps": "25",
        "profile": "Main"
    },
    "WebM (VP9 / Opus) - Web-optimiert": {
        "container": "webm",
        "video_codec": "libvpx-vp9",
        "video_bitrate": "4M",
        "crf": "",
        "audio_codec": "libopus",
        "audio_bitrate": "128k",
        "width": 1920,
        "height": 1080,
        "fps": "25",
        "profile": "Main"
    },
    "MKV (H.264 / FLAC) - Verlustfreies Audio": {
        "container": "mkv",
        "video_codec": "libx264",
        "video_bitrate": "10M",
        "crf": "",
        "audio_codec": "flac",
        "audio_bitrate": "",
        "width": 1920,
        "height": 1080,
        "fps": "25",
        "profile": "High"
    },
    "Match Source - Adaptive High Bitrate (H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "16M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "encoding_mode": "vbr",
        "match_source": True,
        "profile": "High"
    },
    "Match Source - Adaptive Medium Bitrate (H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "8M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "160k",
        "encoding_mode": "vbr",
        "match_source": True,
        "profile": "High"
    },
    "Match Source - Adaptive Low Bitrate (H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "4M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
        "encoding_mode": "vbr",
        "match_source": True,
        "profile": "Main"
    },
    "Match Source - High Bitrate (H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "20M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "encoding_mode": "vbr",
        "match_source": True,
        "profile": "High"
    },
    "Match Source - Medium Bitrate (H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "8M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "160k",
        "encoding_mode": "vbr",
        "match_source": True,
        "profile": "Main"
    },
    "YouTube 2160p 4K Ultra HD (H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "45M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "encoding_mode": "vbr",
        "width": 3840,
        "height": 2160,
        "fps": "30",
        "profile": "High"
    },
    "YouTube 1440p QHD (H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "24M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "encoding_mode": "vbr",
        "width": 2560,
        "height": 1440,
        "fps": "30",
        "profile": "High"
    },
    "YouTube 480p SD Wide (H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "3M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
        "encoding_mode": "vbr",
        "width": 854,
        "height": 480,
        "fps": "30",
        "profile": "Main"
    },
    "Vimeo 1080p HD (H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "12M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "encoding_mode": "vbr",
        "width": 1920,
        "height": 1080,
        "fps": "30",
        "profile": "High"
    },
    "Facebook 720p HD (H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "5M",
        "crf": "",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
        "encoding_mode": "vbr",
        "width": 1280,
        "height": 720,
        "fps": "30",
        "profile": "Main"
    },
    "Schnell 1080p30 (MP4 H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "",
        "crf": "22",
        "audio_codec": "aac",
        "audio_bitrate": "160k",
        "width": 1920,
        "height": 1080,
        "fps": "30",
        "profile": "Main"
    },
    "Schnell 720p30 (MP4 H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "",
        "crf": "21",
        "audio_codec": "aac",
        "audio_bitrate": "160k",
        "width": 1280,
        "height": 720,
        "fps": "30",
        "profile": "Main"
    },
    "Sehr schnell 1080p30 (MP4 H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "",
        "crf": "24",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
        "width": 1920,
        "height": 1080,
        "fps": "30",
        "profile": "Main"
    },
    "HQ 1080p30 (MP4 H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "",
        "crf": "20",
        "audio_codec": "aac",
        "audio_bitrate": "160k",
        "width": 1920,
        "height": 1080,
        "fps": "30",
        "profile": "High"
    },
    "Super schnell 1080p30 (MP4 H.264)": {
        "container": "mp4",
        "video_codec": "libx264",
        "video_bitrate": "",
        "crf": "28",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
        "width": 1920,
        "height": 1080,
        "fps": "30",
        "profile": "Main"
    },
    "H.265 MKV 1080p30": {
        "container": "mkv",
        "video_codec": "libx265",
        "video_bitrate": "",
        "crf": "22",
        "audio_codec": "aac",
        "audio_bitrate": "160k",
        "width": 1920,
        "height": 1080,
        "fps": "30",
        "profile": "Main"
    },
    "MP3 (Nur Audio) - High Quality 320k": {
        "container": "mp3",
        "video_codec": "none",
        "video_bitrate": "",
        "crf": "",
        "audio_codec": "libmp3lame",
        "audio_bitrate": "320k"
    },
    "FLAC (Nur Audio) - Archivierungsqualität": {
        "container": "flac",
        "video_codec": "none",
        "video_bitrate": "",
        "crf": "",
        "audio_codec": "flac",
        "audio_bitrate": ""
    },
    "1:1 Kopie (Stream-Copy)": {
        "container": "mkv",
        "video_codec": "copy",
        "video_bitrate": "",
        "crf": "",
        "audio_codec": "copy",
        "audio_bitrate": ""
    },
    "JPEG (Bild) - Hohe Qualität": {
        "container": "jpg",
        "video_codec": "mjpeg",
        "audio_codec": "none",
        "image_quality": 90,
        "match_source": True
    },
    "PNG (Bild) - Verlustfrei": {
        "container": "png",
        "video_codec": "png",
        "audio_codec": "none",
        "image_quality": 100,
        "match_source": True
    },
    "WebP (Bild) - Hohe Qualität": {
        "container": "webp",
        "video_codec": "libwebp",
        "audio_codec": "none",
        "image_quality": 90,
        "match_source": True
    },
    "AVIF (Bild) - Hohe Effizienz": {
        "container": "avif",
        "video_codec": "libaom-av1",
        "audio_codec": "none",
        "image_quality": 70,
        "match_source": True
    }
}

QUICK_PRESETS = [
    "YouTube 1080p HD",
    "YouTube 720p HD",
    "Hocheffizient (CRF 23)",
    "Stream-Kopie (Verlustfrei)",
]

CUSTOM_PRESET_NAME = "Benutzerdefiniert"

# Format-Dropdown-Einträge, getrennt nach Quelltyp: Bildformate erscheinen
# nur für Bild-Quellen, Video-/Audio-Formate nur für alles andere.
FORMAT_OPTIONS_VIDEO = [
    "H.264 (MP4)",
    "HEVC / H.265 (MP4)",
    "VP9 (WebM)",
    "AV1 (WebM)",
    "QuickTime (MOV)",
    "Universal-Container (MKV)",
    "MP3 (Nur Audio)",
    "FLAC (Nur Audio)",
    "WAV (Nur Audio)",
    "OGG (Nur Audio)",
]
FORMAT_OPTIONS_IMAGE = [
    "JPEG (Bild)",
    "PNG (Bild)",
    "WebP (Bild)",
    "AVIF (Bild)",
]

# Hardware-Encoder (NVENC): erscheinen nur, wenn das installierte FFmpeg sie kennt.
HW_VIDEO_CODECS = ("h264_nvenc", "hevc_nvenc", "av1_nvenc")
HW_FORMAT_OPTIONS = {
    "h264_nvenc": "H.264 (MP4, GPU/NVENC)",
    "hevc_nvenc": "HEVC (MP4, GPU/NVENC)",
    "av1_nvenc": "AV1 (MP4, GPU/NVENC)",
}
NVENC_CODECS = set(HW_VIDEO_CODECS)

# Framerate-Auswahl "wie Quelle": es wird kein -r gesetzt.
FPS_SOURCE_LABEL = "Wie Quelle"


def get_hw_video_codecs():
    """Verfügbare NVENC-Encoder des installierten FFmpeg (ggf. leer)."""
    installed = set(_ffmpeg_encoder_codecs()["video"])
    return [c for c in HW_VIDEO_CODECS if c in installed]


def get_format_options(image_input=False):
    """Format-Einträge passend zur Quelle (Bild vs. Video/Audio)."""
    if image_input:
        return list(FORMAT_OPTIONS_IMAGE)
    options = list(FORMAT_OPTIONS_VIDEO)
    hw = [HW_FORMAT_OPTIONS[c] for c in get_hw_video_codecs()]
    if hw:
        # GPU-Formate zwischen Video- und Audio-Formaten einsortieren
        idx = options.index("MP3 (Nur Audio)")
        options[idx:idx] = hw
    return options


def get_preset_dropdown_options(image_input=None):
    """Vorgaben-Liste; optional nach Quelltyp gefiltert (None = alle)."""
    if image_input is True:
        names = [n for n, s in PRESETS.items() if s.get("container") in IMAGE_CONTAINERS]
        return names + [CUSTOM_PRESET_NAME]
    if image_input is False:
        names = [n for n, s in PRESETS.items() if s.get("container") not in IMAGE_CONTAINERS]
        return QUICK_PRESETS + names + [CUSTOM_PRESET_NAME]
    return QUICK_PRESETS + list(PRESETS.keys()) + [CUSTOM_PRESET_NAME]


def container_from_format_text(text):
    """Zielcontainer aus dem Format-Dropdown-Text (Single Source für UI-Code)."""
    t = str(text or "").strip().lower()
    # Bildformate zuerst ("avif"/"webp" nicht in AV1-/WebM-Zweige lassen)
    if "jpeg" in t or "jpg" in t:
        return "jpg"
    if "png" in t:
        return "png"
    if "webp" in t:
        return "webp"
    if "avif" in t:
        return "avif"
    # NVENC-Formate vor dem AV1-Zweig prüfen ("AV1 (MP4, GPU/NVENC)" → mp4)
    if "nvenc" in t or "gpu" in t:
        return "mp4"
    if "h.264" in t or "h264" in t or "hevc" in t or "h.265" in t or "h265" in t:
        return "mp4"
    if "vp9" in t or "av1" in t or "webm" in t:
        return "webm"
    if "quicktime" in t or "mov" in t:
        return "mov"
    if "mkv" in t or "universal" in t:
        return "mkv"
    if "mp3" in t:
        return "mp3"
    if "flac" in t:
        return "flac"
    if "wav" in t:
        return "wav"
    if "ogg" in t:
        return "ogg"
    return t


# Standard-Settings pro Format-Dropdown-Eintrag (Single Source für beide UIs).
_VIDEO_FORMAT_DEFAULTS = {
    "H.264 (MP4)": {
        "container": "mp4", "video_codec": "libx264", "video_bitrate": "8M",
        "crf": "", "audio_codec": "aac", "audio_bitrate": "192k",
        "width": 1920, "height": 1080, "fps": "25", "profile": "High",
    },
    "HEVC / H.265 (MP4)": {
        "container": "mp4", "video_codec": "libx265", "video_bitrate": "",
        "crf": "23", "audio_codec": "aac", "audio_bitrate": "192k",
        "width": 1920, "height": 1080, "fps": "25", "profile": "Main",
    },
    "VP9 (WebM)": {
        "container": "webm", "video_codec": "libvpx-vp9", "video_bitrate": "4M",
        "crf": "", "audio_codec": "libopus", "audio_bitrate": "128k",
        "width": 1920, "height": 1080, "fps": "25", "profile": "Main",
    },
    "AV1 (WebM)": {
        "container": "webm", "video_codec": "libsvtav1", "video_bitrate": "4M",
        "crf": "", "audio_codec": "libopus", "audio_bitrate": "128k",
        "width": 1920, "height": 1080, "fps": "25", "profile": "Main",
    },
    "QuickTime (MOV)": {
        "container": "mov", "video_codec": "libx264", "video_bitrate": "8M",
        "crf": "", "audio_codec": "aac", "audio_bitrate": "192k",
        "width": 1920, "height": 1080, "fps": "25", "profile": "High",
    },
    "Universal-Container (MKV)": {
        "container": "mkv", "video_codec": "libx264", "video_bitrate": "8M",
        "crf": "", "audio_codec": "aac", "audio_bitrate": "192k",
        "width": 1920, "height": 1080, "fps": "25", "profile": "High",
    },
    "H.264 (MP4, GPU/NVENC)": {
        "container": "mp4", "video_codec": "h264_nvenc", "video_bitrate": "8M",
        "crf": "", "audio_codec": "aac", "audio_bitrate": "192k",
        "width": 1920, "height": 1080, "fps": "25", "profile": "High",
    },
    "HEVC (MP4, GPU/NVENC)": {
        "container": "mp4", "video_codec": "hevc_nvenc", "video_bitrate": "8M",
        "crf": "", "audio_codec": "aac", "audio_bitrate": "192k",
        "width": 1920, "height": 1080, "fps": "25", "profile": "Main",
    },
    "AV1 (MP4, GPU/NVENC)": {
        "container": "mp4", "video_codec": "av1_nvenc", "video_bitrate": "8M",
        "crf": "", "audio_codec": "aac", "audio_bitrate": "192k",
        "width": 1920, "height": 1080, "fps": "25", "profile": "",
    },
    "MP3 (Nur Audio)": {
        "container": "mp3", "video_codec": "none", "video_bitrate": "",
        "crf": "", "audio_codec": "libmp3lame", "audio_bitrate": "320k",
    },
    "FLAC (Nur Audio)": {
        "container": "flac", "video_codec": "none", "video_bitrate": "",
        "crf": "", "audio_codec": "flac", "audio_bitrate": "",
    },
    "WAV (Nur Audio)": {
        "container": "wav", "video_codec": "none", "video_bitrate": "",
        "crf": "", "audio_codec": "pcm_s16le", "audio_bitrate": "",
    },
    "OGG (Nur Audio)": {
        "container": "ogg", "video_codec": "none", "video_bitrate": "",
        "crf": "", "audio_codec": "libopus", "audio_bitrate": "192k",
    },
}

_IMAGE_FORMAT_PRESETS = {
    "JPEG (Bild)": "JPEG (Bild) - Hohe Qualität",
    "PNG (Bild)": "PNG (Bild) - Verlustfrei",
    "WebP (Bild)": "WebP (Bild) - Hohe Qualität",
    "AVIF (Bild)": "AVIF (Bild) - Hohe Effizienz",
}


def default_settings_for_format(text):
    """Standard-Settings für einen Format-Dropdown-Eintrag oder None."""
    if text in _VIDEO_FORMAT_DEFAULTS:
        return dict(_VIDEO_FORMAT_DEFAULTS[text])
    if text in _IMAGE_FORMAT_PRESETS:
        return dict(PRESETS[_IMAGE_FORMAT_PRESETS[text]])
    return None


def format_option_for_settings(settings):
    """Passender Format-Dropdown-Text zu Container/Codec (Umkehrung des Mappings)."""
    settings = settings or {}
    container = str(settings.get("container", "")).strip().lower()
    vcodec = str(settings.get("video_codec", "")).strip().lower()
    if vcodec in HW_FORMAT_OPTIONS:
        return HW_FORMAT_OPTIONS[vcodec]
    if container == "mp4":
        return "HEVC / H.265 (MP4)" if vcodec == "libx265" else "H.264 (MP4)"
    if container == "webm":
        return "AV1 (WebM)" if vcodec == "libsvtav1" else "VP9 (WebM)"
    simple = {
        "mov": "QuickTime (MOV)", "mkv": "Universal-Container (MKV)",
        "mp3": "MP3 (Nur Audio)", "flac": "FLAC (Nur Audio)",
        "wav": "WAV (Nur Audio)", "ogg": "OGG (Nur Audio)",
        "jpg": "JPEG (Bild)", "png": "PNG (Bild)",
        "webp": "WebP (Bild)", "avif": "AVIF (Bild)",
    }
    return simple.get(container, container)


# Gültige Auswahlmöglichkeiten für manuelle Konfigurationen
CONTAINERS = ["mp4", "mkv", "webm", "mov", "mp3", "flac", "wav", "ogg",
              "jpg", "png", "webp", "avif"]

# Bild-Container: Einzelbild-Ausgabe statt Video/Audio-Streams.
IMAGE_CONTAINERS = {"jpg", "png", "webp", "avif"}

# Container, die im UI als reine Audio-Ausgabe behandelt werden.
AUDIO_ONLY_CONTAINERS = {"mp3", "flac", "wav", "ogg"}

# Container, in denen FFmpeg Untertitelspuren sinnvoll muxen kann.
SUBTITLE_CONTAINERS = {"mp4", "mov", "mkv", "webm"}

# Untertitel-bezogene Settings-Schlüssel: müssen einen Format-/Preset-Wechsel
# überleben, weil die Handler das settings-Dict komplett ersetzen.
SUBTITLE_SETTING_KEYS = (
    "subtitles_enabled",
    "subtitles_mode",
    "subtitles_file_path",
    "subtitles_source",
    "subtitles_source_custom",
    "subtitles_translate",
    "subtitles_translate_custom",
)

# Nur für einen laufenden Job gültige Zwischenzustände — dürfen nie auf andere
# Jobs kopiert werden ("Einstellungen auf alle anwenden").
TRANSIENT_SETTING_KEYS = (
    "temp_srt_path",
    "temp_audio_path",
    "_subtitle_ai_stage",
    "_subtitle_source_srt",
)

# Quellbezogene Einstellungen (Zuschnitt, Drehung, Schnittmarken): gelten nur
# für die jeweilige Quelldatei und werden nie auf andere Jobs kopiert.
SOURCE_SETTING_KEYS = ("crop", "rotate", "trim_start", "trim_end")

# Als Bild-Quelle akzeptierte Dateiendungen (für Default-Preset bei Drag & Drop)
IMAGE_INPUT_EXTENSIONS = {
    "jpg", "jpeg", "png", "webp", "avif", "bmp", "tif", "tiff",
    "gif", "heic", "heif", "jxl",
}

VIDEO_CODECS = {
    "mp4": ["libx264", "libx265", "copy", "none"],
    "mkv": ["libx264", "libx265", "libvpx-vp9", "libsvtav1", "copy", "none"],
    "webm": ["libvpx-vp9", "libsvtav1", "copy", "none"],
    "mov": ["libx264", "libx265", "copy", "none"],
    "mp3": ["none"],
    "flac": ["none"],
    "wav": ["none"],
    "ogg": ["none"],
    "jpg": ["mjpeg"],
    "png": ["png"],
    "webp": ["libwebp"],
    "avif": ["libaom-av1"]
}

AUDIO_CODECS = {
    "mp4": ["aac", "libmp3lame", "copy", "none"],
    "mkv": ["aac", "libmp3lame", "libopus", "flac", "copy", "none"],
    "webm": ["libopus", "none"],
    "mov": ["aac", "copy", "none"],
    "mp3": ["libmp3lame"],
    "flac": ["flac"],
    "wav": ["pcm_s16le"],
    "ogg": ["libvorbis", "libopus"],
    "jpg": ["none"],
    "png": ["none"],
    "webp": ["none"],
    "avif": ["none"]
}

FALLBACK_CUSTOM_VIDEO_CODECS = [
    "copy",
    "libx264",
    "libx265",
    "libvpx-vp9",
    "libsvtav1",
    "libaom-av1",
    "h264_nvenc",
    "hevc_nvenc",
    "av1_nvenc",
    "h264_vaapi",
    "hevc_vaapi",
    "av1_vaapi",
    "mpeg4",
    "prores_ks",
    "dnxhd",
    "ffv1",
    "none",
]

FALLBACK_CUSTOM_AUDIO_CODECS = [
    "copy",
    "aac",
    "libmp3lame",
    "libopus",
    "flac",
    "alac",
    "pcm_s16le",
    "pcm_s24le",
    "libvorbis",
    "ac3",
    "eac3",
    "none",
]

AUDIO_CODEC_LABELS = {
    "aac": "AAC",
    "libmp3lame": "MP3",
    "libopus": "Opus",
    "flac": "FLAC",
    "alac": "ALAC",
    "pcm_s16le": "PCM 16-bit",
    "pcm_s24le": "PCM 24-bit",
    "libvorbis": "Vorbis",
    "ac3": "AC-3",
    "eac3": "E-AC-3",
    "copy": "Kopieren (Copy)",
    "none": "Kein Audio",
}

_AUDIO_LABEL_TO_CODEC = {
    label.casefold(): codec
    for codec, label in AUDIO_CODEC_LABELS.items()
}

VIDEO_BITRATES = ["Source / CRF", "1M", "2M", "4M", "8M", "12M", "16M", "20M"]
AUDIO_BITRATES = ["128k", "192k", "256k", "320k", "Source / Copy"]

# Skalierungsmodi für Video- und Bild-Export
SCALE_MODE_SOURCE = "source"    # Quellauflösung unverändert lassen
SCALE_MODE_FIT = "fit"          # In Zielgröße einpassen, Seitenverhältnis bleibt
SCALE_MODE_STRETCH = "stretch"  # Exakt auf Zielgröße ziehen (ggf. verzerrt)

SCALE_MODE_LABELS = {
    SCALE_MODE_SOURCE: "Quellgröße beibehalten",
    SCALE_MODE_FIT: "Seitenverhältnis beibehalten",
    SCALE_MODE_STRETCH: "Verzerren (exakte Größe)",
}

_SCALE_LABEL_TO_MODE = {label.casefold(): mode for mode, label in SCALE_MODE_LABELS.items()}


def scale_mode_options():
    """UI-Labels der Skalierungsmodi in fester Reihenfolge."""
    return [SCALE_MODE_LABELS[m] for m in (SCALE_MODE_SOURCE, SCALE_MODE_FIT, SCALE_MODE_STRETCH)]


def scale_mode_to_label(mode):
    return SCALE_MODE_LABELS.get(str(mode or "").lower(), SCALE_MODE_LABELS[SCALE_MODE_SOURCE])


def scale_mode_from_label(label):
    return _SCALE_LABEL_TO_MODE.get(str(label or "").strip().casefold(), SCALE_MODE_SOURCE)


def get_scale_mode(settings):
    """Skalierungsmodus aus den Settings; ältere Settings ohne 'scale_mode'
    fallen auf match_source (→ source) bzw. 'fit' zurück."""
    settings = settings or {}
    mode = str(settings.get("scale_mode", "")).lower()
    if mode in SCALE_MODE_LABELS:
        return mode
    return SCALE_MODE_SOURCE if settings.get("match_source") else SCALE_MODE_FIT


def get_crop(settings):
    """Validierter Zuschnitt aus den Settings: {"x","y","w","h"} in Quellpixeln
    oder None, wenn kein (brauchbarer) Zuschnitt gesetzt ist."""
    crop = (settings or {}).get("crop")
    if not isinstance(crop, dict):
        return None
    try:
        x = max(0, int(crop["x"]))
        y = max(0, int(crop["y"]))
        w = int(crop["w"])
        h = int(crop["h"])
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return {"x": x, "y": y, "w": w, "h": h}


# Erlaubte Drehwinkel (im Uhrzeigersinn) für den Bild-Dreh-Workflow.
ROTATE_ANGLES = (0, 90, 180, 270)

# FFmpeg-Filterausdruck je Drehwinkel; 0° braucht keinen Filter.
_ROTATE_FILTERS = {
    90: "transpose=1",   # 90° im Uhrzeigersinn
    180: "hflip,vflip",  # 180°: horizontal + vertikal spiegeln
    270: "transpose=2",  # 90° gegen den Uhrzeigersinn
}


def get_rotation(settings):
    """Validierter Drehwinkel aus den Settings (0/90/180/270), Default 0."""
    try:
        angle = int((settings or {}).get("rotate", 0)) % 360
    except (TypeError, ValueError):
        return 0
    return angle if angle in ROTATE_ANGLES else 0


def rotate_filter(angle):
    """FFmpeg-Filterausdruck für den gegebenen Drehwinkel, oder None für 0°."""
    return _ROTATE_FILTERS.get(angle)


def build_scale_filter(width, height, mode, even_dimensions=False):
    """FFmpeg-scale-Filter für den gewählten Modus. even_dimensions erzwingt
    gerade Kantenlängen (Pflicht für yuv420p-Video-Codecs wie x264/x265)."""
    def even_value(value):
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            text = str(value).strip()
            return f"trunc(({text})/2)*2" if text else text
        return str(max(2, ivalue - (ivalue % 2)))

    if mode == SCALE_MODE_STRETCH:
        if even_dimensions:
            width = even_value(width)
            height = even_value(height)
        return f"scale={width}:{height}"
    fit = f"scale={width}:{height}:force_original_aspect_ratio=decrease"
    if even_dimensions:
        fit += ":force_divisible_by=2"
    return fit


def build_subtitles_filter(subtitle_path):
    """FFmpeg-subtitles-Filter mit Filtergraph-tauglich escapedem Dateipfad."""
    path = str(subtitle_path or "")
    path = path.replace("\\", "\\\\")
    path = path.replace(" ", "\\ ")
    path = path.replace(":", "\\\\:")
    path = path.replace(",", "\\,")
    path = path.replace(";", "\\;")
    path = path.replace("[", "\\[").replace("]", "\\]")
    path = path.replace("'", "\\\\\\'")
    return f"subtitles=filename={path}"


def _default_video_codec_for_container(container):
    """Container-kompatibler Fallback, wenn Stream-Copy wegen Filtern unmoeglich ist."""
    return "libvpx-vp9" if str(container or "").lower() == "webm" else "libx264"


def _unique(items):
    seen = set()
    result = []
    for item in items:
        item = str(item).strip()
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result


@functools.lru_cache(maxsize=1)
def _ffmpeg_encoder_codecs():
    """Liest installierte FFmpeg-Encoder einmalig aus; Fallbacks halten die UI nutzbar."""
    codecs = {"video": [], "audio": []}
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return codecs

    if result.returncode != 0:
        return codecs

    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        flags, codec = parts[0], parts[1]
        if len(flags) < 6:
            continue
        if flags[0] == "V":
            codecs["video"].append(codec)
        elif flags[0] == "A":
            codecs["audio"].append(codec)
    return codecs


def get_custom_video_codecs():
    installed = _ffmpeg_encoder_codecs()["video"]
    return _unique(FALLBACK_CUSTOM_VIDEO_CODECS + installed + ["copy", "none"])


def get_custom_audio_codecs():
    installed = _ffmpeg_encoder_codecs()["audio"]
    return _unique(FALLBACK_CUSTOM_AUDIO_CODECS + installed + ["copy", "none"])


def get_video_codec_options(container, custom=False):
    if custom:
        return get_custom_video_codecs()
    options = list(VIDEO_CODECS.get(container, ["libx264", "libx265", "copy", "none"]))
    # Verfügbare NVENC-Encoder auch ohne Custom-Modus anbieten
    if container in ("mp4", "mkv", "mov"):
        insert_at = options.index("copy") if "copy" in options else len(options)
        for codec in get_hw_video_codecs():
            if codec not in options:
                options.insert(insert_at, codec)
                insert_at += 1
    return options


def get_audio_codec_options(container, custom=False):
    if custom:
        return get_custom_audio_codecs()
    return AUDIO_CODECS.get(container, ["aac", "copy", "none"])


def audio_codec_to_label(codec):
    codec = str(codec or "").strip()
    return AUDIO_CODEC_LABELS.get(codec.casefold(), codec)


def audio_label_to_codec(label):
    label = str(label or "").strip()
    return _AUDIO_LABEL_TO_CODEC.get(label.casefold(), label)


def get_audio_codec_labels(container, custom=False):
    return [audio_codec_to_label(codec) for codec in get_audio_codec_options(container, custom)]


def _resolve_audio_codec(settings):
    """Audio-Codec aus den Settings (Label oder Kurzname) als FFmpeg-Encoder-Name."""
    a_codec = str(audio_label_to_codec(settings.get("audio_codec", "aac"))).strip()
    return {
        "aac": "aac",
        "mp3": "libmp3lame",
        "opus": "libopus",
        "flac": "flac",
        "copy": "copy",
        "none": "none",
    }.get(a_codec.lower(), a_codec)


def _scale_bitrate(bitrate, factor):
    """Skaliert eine FFmpeg-Bitrate-Angabe wie '8M' oder '800k' um den Faktor.
    Gibt einen FFmpeg-tauglichen String mit derselben Einheit zurück."""
    if not bitrate:
        return bitrate
    m = re.match(r"^\s*([\d\.]+)\s*([kKmMgG]?)", str(bitrate))
    if not m:
        return bitrate
    val = float(m.group(1)) * factor
    unit = m.group(2).upper() if m.group(2) else ""
    # Ganze Zahlen ohne Nachkommastelle ausgeben, sonst gerundet
    num = f"{val:.0f}" if abs(val - round(val)) < 1e-6 else f"{val:.1f}"
    return f"{num}{unit}"


def _is_number(value):
    """True für int-/float-artige Strings ('23', '23.5'); FFmpeg akzeptiert beide als CRF."""
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def parse_seconds(value):
    """Sekundenwert aus Settings (float/int/str) oder None bei Unbrauchbarem."""
    if value is None or value == "":
        return None
    try:
        sec = float(value)
    except (TypeError, ValueError):
        return None
    return sec if sec >= 0 else None


def _format_trim_seconds(sec):
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def trim_label(settings):
    """Kompakte Schnitt-Anzeige für die Queue ('0:05–1:30'), '' ohne Schnitt.
    Spiegelt, welche Trim-Werte get_ffmpeg_args tatsächlich anwendet."""
    start = parse_seconds(settings.get("trim_start"))
    end = parse_seconds(settings.get("trim_end"))
    has_start = start is not None and start > 0
    has_end = end is not None and end > 0 and (start is None or end > start)
    if not has_start and not has_end:
        return ""
    start_txt = _format_trim_seconds(start if has_start else 0)
    end_txt = _format_trim_seconds(end) if has_end else "Ende"
    return f"{start_txt}–{end_txt}"


def format_mbps(value):
    value = float(value)
    if 0 < value < 0.1:
        # Der intelligente Rechner kann bei sehr langen Dateien unter 0,1
        # Mbps landen. Als kbit/s bleibt der Wert präzise und wird nicht zu
        # einem ungültigen "0.0M" gerundet.
        kbps = value * 1000.0
        num = f"{int(round(kbps))}" if abs(kbps - round(kbps)) < 1e-6 else f"{kbps:g}"
        return f"{num}k"
    if abs(value - round(value)) < 1e-6:
        return f"{int(round(value))}M"
    return f"{value:.1f}M"


def bitrate_to_mbps(value, default=None):
    """Wandelt FFmpeg-Bitratenangaben in Mbps für die UI um."""
    m = re.match(r"^\s*([\d.]+)\s*([kKmMgG]?)\s*$", str(value or ""))
    if not m:
        return default
    try:
        number = float(m.group(1))
    except ValueError:
        return default
    unit = m.group(2).lower()
    if unit == "k":
        return number / 1000.0
    if unit == "m":
        return number
    if unit == "g":
        return number * 1000.0
    # Ohne Einheit meint FFmpeg Bits/s. Kleine Werte stammen aber oft aus alten
    # UI-Settings und waren als Mbps gemeint.
    return number / 1_000_000.0 if number >= 10000 else number


def quick_preset_settings(name):
    """Vollständige Settings für die kurzen Preset-Namen im Dropdown."""
    if name == "YouTube 1080p HD":
        return {
            "container": "mp4",
            "video_codec": "libx264",
            "video_bitrate": "16M",
            "crf": "",
            "audio_codec": "aac",
            "audio_bitrate": "192k",
            "encoding_mode": "vbr",
            "width": 1920,
            "height": 1080,
            "fps": "30",
            "profile": "High",
            "scale_mode": SCALE_MODE_FIT,
            "match_source": False,
        }
    if name == "YouTube 720p HD":
        return {
            "container": "mp4",
            "video_codec": "libx264",
            "video_bitrate": "8M",
            "crf": "",
            "audio_codec": "aac",
            "audio_bitrate": "192k",
            "encoding_mode": "vbr",
            "width": 1280,
            "height": 720,
            "fps": "30",
            "profile": "High",
            "scale_mode": SCALE_MODE_FIT,
            "match_source": False,
        }
    if name == "Hocheffizient (CRF 23)":
        settings = dict(PRESETS["MP4 (H.265 / AAC) - Hocheffizient (CRF 23)"])
        settings["encoding_mode"] = "crf"
        settings.setdefault("scale_mode", SCALE_MODE_FIT)
        settings["match_source"] = False
        return settings
    if name == "Stream-Kopie (Verlustfrei)":
        settings = dict(PRESETS["1:1 Kopie (Stream-Copy)"])
        settings["encoding_mode"] = "copy"
        return settings
    return None


def get_ffmpeg_args(input_file, output_file, settings):
    """
    Erstellt das FFmpeg-Argumente-Array basierend auf den Einstellungen.
    """
    import os
    container = str(settings.get("container", "mp4")).strip().lower()

    # Subtitel-Konfiguration
    subtitles_enabled = bool(settings.get("subtitles_enabled", False))
    temp_srt_path = ""
    if subtitles_enabled:
        for candidate in (settings.get("temp_srt_path"), settings.get("subtitles_file_path")):
            candidate = str(candidate or "").strip()
            if candidate and os.path.exists(candidate):
                temp_srt_path = candidate
                break
    subtitles_mode = settings.get("subtitles_mode", "Soft-Untertitel (in Container einbetten)")
    soft_subtitle = bool(
        temp_srt_path
        and subtitles_mode == "Soft-Untertitel (in Container einbetten)"
        and container in SUBTITLE_CONTAINERS
    )
    hard_subtitle = bool(
        temp_srt_path
        and subtitles_mode == "Hard-Untertitel (in Video einbrennen)"
        and container not in AUDIO_ONLY_CONTAINERS
    )

    # -y überschreibt die Ausgabedatei automatisch
    # --- BILD-EXPORT (Einzelbild statt Video/Audio-Streams) ---
    if container in IMAGE_CONTAINERS:
        return _get_image_args(input_file, output_file, settings)

    # Cut-Strategie: Wird der Videostream 1:1 kopiert (oder gibt es nur eine
    # kopierte Audiospur), schneidet Input-Seeking (-ss/-t vor -i) verlustfrei,
    # schnell und keyframe-sauber. Output-Seeking (-ss/-to nach -i) würde bei
    # Stream-Copy mitten in die GOP schneiden (Bildfehler bis zum nächsten
    # Keyframe). Beim Re-Encoding bleibt Output-Seeking frame-genau, und die
    # Timestamps bleiben unverändert (wichtig für Untertitel-Synchronität).
    v_lower = str(settings.get("video_codec", "libx264")).strip().lower()
    a_lower = _resolve_audio_codec(settings).lower()
    is_copy_cut = (
        not soft_subtitle
        and not hard_subtitle
        and (v_lower == "copy" or (v_lower == "none" and a_lower == "copy"))
    )

    args = ["-y"]
    trim_start = parse_seconds(settings.get("trim_start"))
    trim_end = parse_seconds(settings.get("trim_end"))

    # Vor-Input-Optionen (z.B. für optische Medien wie -f dvdvideo -title N oder -playlist N)
    input_args = settings.get("input_args")
    if input_args and isinstance(input_args, list):
        args.extend(str(a) for a in input_args)

    actual_input = input_file
    if settings.get("disc_type") == "bluray" and not str(input_file).startswith("bluray:"):
        actual_input = f"bluray:{input_file}"

    if is_copy_cut:
        if trim_start is not None and trim_start > 0:
            args.extend(["-ss", f"{trim_start:.3f}"])
        if trim_end is not None and trim_end > 0 and (trim_start is None or trim_end > trim_start):
            duration = trim_end - (trim_start or 0.0)
            args.extend(["-t", f"{duration:.3f}"])
        args.extend(["-i", actual_input])
        if trim_start is not None and trim_start > 0:
            # Kopierte Pakete vor dem Seek-Punkt bekämen negative Timestamps —
            # auf 0 verschieben, sonst stolpern MP4-/MKV-Muxer und manche Player.
            args.extend(["-avoid_negative_ts", "make_zero"])
    else:
        args.extend(["-i", actual_input])
        if soft_subtitle:
            args.extend(["-i", temp_srt_path])
        if trim_start is not None and trim_start > 0:
            args.extend(["-ss", f"{trim_start:.3f}"])
        if trim_end is not None and trim_end > 0 and (trim_start is None or trim_end > trim_start):
            args.extend(["-to", f"{trim_end:.3f}"])

    # Video-Konfiguration
    v_codec = str(settings.get("video_codec", "libx264")).strip()
    if v_codec.lower() in ("copy", "none"):
        v_codec = v_codec.lower()

    # Wenn Hard-Subtitles eingebrannt werden, muss das Video neu codiert werden (keine Stream-Kopie möglich)
    if hard_subtitle and v_codec == "copy":
        v_codec = _default_video_codec_for_container(container)

    # Stream-Mapping bei Soft-Untertitelung (um korrekte Spurenzuweisung zu garantieren)
    if soft_subtitle:
        a_codec = _resolve_audio_codec(settings)

        if v_codec != "none":
            # 0:V (groß) = echte Videostreams ohne Cover-Art/attached_pic —
            # 0:v würde eingebettete Cover mit durch den Encoder jagen.
            args.extend(["-map", "0:V?"])
        if a_codec != "none":
            # Nur die erste Tonspur, konsistent zum Standardverhalten ohne Untertitel.
            args.extend(["-map", "0:a:0?"])
        args.extend(["-map", "1:s?"])

    if v_codec == "none":
        args.append("-vn")
    else:
        args.extend(["-c:v", v_codec])
        if v_codec != "copy":
            vf_filters = []
            scale_mode = get_scale_mode(settings)
            if scale_mode != SCALE_MODE_SOURCE:
                width = settings.get("width", "")
                height = settings.get("height", "")
                if width and height:
                    vf_filters.append(build_scale_filter(width, height, scale_mode, even_dimensions=True))

            # Framerate ist von der Skalierung unabhängig; leer / "Wie Quelle"
            # bedeutet: Quell-Framerate unverändert lassen (kein -r).
            fps = str(settings.get("fps", "") or "").strip()
            if fps and fps.casefold() != FPS_SOURCE_LABEL.casefold() and re.fullmatch(r"[\d./]+", fps):
                args.extend(["-r", fps])

            profile = settings.get("profile", "")
            if profile and v_codec in ("libx264", "h264", "h264_nvenc"):
                args.extend(["-profile:v", profile.lower()])
            elif profile and v_codec in ("libx265", "hevc", "hevc_nvenc"):
                # x265/NVENC-HEVC akzeptieren NICHT die x264-Profile (high/
                # baseline) – nur main/main10/... Ungültige Profile würden mit
                # "unknown profile" hart abbrechen. Daher nur gültige Profile
                # durchreichen, sonst weglassen (Encoder wählt selbst).
                hevc_valid = {"main", "main10", "main12", "mainstillpicture"}
                if profile.lower() in hevc_valid:
                    args.extend(["-profile:v", profile.lower()])

            crf = settings.get("crf", "")
            v_bitrate = settings.get("video_bitrate", "")

            # Encoding-Modus: explizit ("crf"/"cbr"/"vbr") oder aus den Werten abgeleitet.
            mode = str(settings.get("encoding_mode", "") or "").strip().lower()
            crf_capable = v_codec in (
                "libx264", "libx265", "libvpx-vp9", "libsvtav1", "libaom-av1",
            ) or v_codec in NVENC_CODECS
            if mode not in ("crf", "cbr", "vbr"):
                if crf and _is_number(crf):
                    mode = "crf"
                elif v_bitrate and v_bitrate != "Source / CRF":
                    mode = "vbr"
                else:
                    mode = "crf" if crf_capable else "vbr"

            if mode == "crf":
                # Ungültige/leere CRF-Werte fallen auf 23 zurück, statt den Job
                # stillschweigend ganz ohne Rate-Control laufen zu lassen.
                crf_value = str(crf).strip() if crf and _is_number(crf) else "23"
                if v_codec in NVENC_CODECS:
                    # NVENC kennt kein -crf; konstante Qualität läuft über -cq
                    # im VBR-Modus mit -b:v 0.
                    args.extend(["-rc", "vbr", "-cq", crf_value, "-b:v", "0"])
                else:
                    args.extend(["-crf", crf_value])
                    # VP9 verwendet -crf nur im Constant-Quality-Modus zusammen mit '-b:v 0',
                    # sonst interpretiert FFmpeg den Wert als constrained-quality-Obergrenze.
                    if v_codec == "libvpx-vp9":
                        args.extend(["-b:v", "0"])
            elif v_bitrate and v_bitrate != "Source / CRF":
                # Falls z. B. '8M' ausgewählt wurde
                args.extend(["-b:v", v_bitrate])
                if mode == "cbr":
                    # Echtes CBR: feste Ober-/Untergrenze + Decoder-Puffer (2x Bitrate).
                    args.extend([
                        "-minrate", v_bitrate,
                        "-maxrate", v_bitrate,
                        "-bufsize", _scale_bitrate(v_bitrate, 2),
                    ])

            # Kompatibilitäts-Pixelformat: garantiert abspielbare H.264/H.265-Dateien
            # auch aus 10-bit-/4:2:2-Quellen (Browser, QuickTime, Smart-TVs).
            if v_codec in ("libx264", "libx265") or v_codec in NVENC_CODECS:
                args.extend(["-pix_fmt", "yuv420p"])

            # Video-Filter für Hard-Subtitles (nach der Skalierung einbrennen)
            if hard_subtitle:
                vf_filters.append(build_subtitles_filter(temp_srt_path))

            if vf_filters:
                args.extend(["-vf", ",".join(vf_filters)])

    # Audio-Konfiguration
    a_codec = _resolve_audio_codec(settings)
    # Verlustfreie / PCM-Codecs ignorieren bzw. verweigern eine Bitrate-Angabe.
    lossless_audio = a_codec in ("flac", "alac", "pcm_s16le", "pcm_s24le", "wavpack")
    if a_codec == "none":
        args.append("-an")
    else:
        args.extend(["-c:a", a_codec])
        if a_codec != "copy" and not lossless_audio:
            a_bitrate = settings.get("audio_bitrate", "")
            if a_bitrate and a_bitrate != "Source / Copy":
                args.extend(["-b:a", a_bitrate])

    # Subtitle Codec für Soft Subtitles festlegen
    if soft_subtitle:
        if container.lower() == "mkv":
            args.extend(["-c:s", "subrip"])
        elif container.lower() in ("mp4", "mov"):
            args.extend(["-c:s", "mov_text"])
        elif container.lower() == "webm":
            # WebM unterstützt nur WebVTT, kein SRT/subrip → sonst
            # "Could not write header (incorrect codec parameters)".
            args.extend(["-c:s", "webvtt"])
        else:
            args.extend(["-c:s", "srt"])

    # Optische Medien: Audio-/Untertitel-Spurauswahl, falls angegeben und nicht soft_subtitle
    audio_idx = settings.get("audio_stream_idx")
    sub_idx = settings.get("subtitle_stream_idx")
    if (audio_idx is not None or sub_idx is not None) and not soft_subtitle:
        if v_codec != "none":
            args.extend(["-map", "0:v:0?"])
        if a_codec != "none":
            if audio_idx == -1:
                args.extend(["-map", "0:a?"])
            elif audio_idx is not None and audio_idx >= 0:
                args.extend(["-map", f"0:a:{audio_idx}?"])
            else:
                args.extend(["-map", "0:a:0?"])
        if sub_idx is not None:
            if sub_idx == -1:
                args.extend(["-map", "0:s?"])
            elif sub_idx >= 0:
                args.extend(["-map", f"0:s:{sub_idx}?"])
            if container.lower() == "mkv":
                args.extend(["-c:s", "copy"])

    # MP4/MOV streamingfähig machen (Moov-Atom an den Anfang → schnelles Web-Seeking).
    if container in ("mp4", "mov") and v_codec != "none":
        args.extend(["-movflags", "+faststart"])

    args.append(output_file)
    return args

_VIDEO_FORMAT_LABELS = {
    "libx264": "H.264", "h264_nvenc": "H.264", "h264_vaapi": "H.264", "h264": "H.264",
    "libx265": "HEVC", "hevc_nvenc": "HEVC", "hevc_vaapi": "HEVC", "hevc": "HEVC",
    "libvpx-vp9": "VP9",
    "libsvtav1": "AV1", "libaom-av1": "AV1", "av1_nvenc": "AV1", "av1_vaapi": "AV1",
    "prores_ks": "ProRes", "dnxhd": "DNxHD", "ffv1": "FFV1", "mpeg4": "MPEG-4",
}


_IMAGE_FORMAT_LABELS = {"jpg": "JPEG", "png": "PNG", "webp": "WebP", "avif": "AVIF"}


def is_image_input(file_path):
    """True, wenn die Datei anhand der Endung als Bild gilt."""
    import os
    ext = os.path.splitext(str(file_path or ""))[1].lstrip(".").lower()
    return ext in IMAGE_INPUT_EXTENSIONS


def format_label(settings):
    """AME-artiges Format-Label für die Queue-Spalte (z. B. 'H.264', 'HEVC', 'MP3')."""
    settings = settings or {}
    raw_container = str(settings.get("container", "")).strip().lower()
    if raw_container in IMAGE_CONTAINERS:
        return _IMAGE_FORMAT_LABELS[raw_container]
    container = raw_container.upper()
    vcodec = str(settings.get("video_codec", "")).strip().lower()
    if vcodec in _VIDEO_FORMAT_LABELS:
        return _VIDEO_FORMAT_LABELS[vcodec]
    if vcodec == "copy":
        return container or "Kopie"
    if vcodec in ("", "none"):
        acodec = str(settings.get("audio_codec", "")).strip().lower()
        label = audio_codec_to_label(acodec)
        if label and acodec not in ("", "none", "copy"):
            return label
        return container or "Audio"
    return vcodec


def preset_label(settings):
    """Vorgabe-Name für die Queue-Spalte; bevorzugt das beim Auswählen
    gespeicherte Label (Quick-Presets wie "YouTube 1080p HD" gehen sonst
    als "Benutzerdefiniert" verloren), sonst exakte Preset-Treffer."""
    settings = settings or {}
    if settings.get("custom_mode"):
        return CUSTOM_PRESET_NAME
    stored = str(settings.get("preset_label") or "").strip()
    if stored:
        return stored
    return get_preset_for_settings(settings)


def _get_image_args(input_file, output_file, settings):
    """FFmpeg-Argumente für Bild-zu-Bild-Konvertierung (JPEG/PNG/WebP/AVIF).

    Nimmt genau ein Frame (bei GIF/Video-Quellen das erste), skaliert optional
    und mappt den Qualitätsregler (1-100) auf die codec-eigene Skala.
    """
    container = str(settings.get("container", "jpg")).lower()
    quality = settings.get("image_quality", 90)
    try:
        quality = max(1, min(100, int(quality)))
    except (TypeError, ValueError):
        quality = 90

    args = ["-y", "-i", input_file, "-frames:v", "1", "-an"]

    vf_filters = []

    # Drehung zuerst anwenden: Der Zuschnitt aus der Vorschau bezieht sich auf
    # das dort bereits gedrehte Bild, muss also im Filterchain danach kommen.
    rotate_expr = rotate_filter(get_rotation(settings))
    if rotate_expr:
        vf_filters.append(rotate_expr)

    # Optionaler Zuschnitt (aus der interaktiven Bildvorschau), vor der Skalierung
    crop = get_crop(settings)
    if crop:
        vf_filters.append(f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']}")

    # Optionale Skalierung; Standard ist "Quellgröße beibehalten".
    scale_mode = get_scale_mode(settings)
    if scale_mode != SCALE_MODE_SOURCE:
        width = settings.get("width", "")
        height = settings.get("height", "")
        if width and height:
            vf_filters.append(build_scale_filter(width, height, scale_mode))

    if vf_filters:
        args.extend(["-vf", ",".join(vf_filters)])

    if container == "jpg":
        # mjpeg: -q:v 2 (beste) bis 31 (schlechteste)
        qv = round(2 + (100 - quality) * 29 / 100)
        args.extend(["-c:v", "mjpeg", "-q:v", str(qv)])
    elif container == "png":
        args.extend(["-c:v", "png"])
    elif container == "webp":
        webp_args = ["-c:v", "libwebp", "-quality", str(quality)]
        if quality >= 100:
            webp_args.extend(["-lossless", "1"])
        args.extend(webp_args)
    elif container == "avif":
        # libaom-AV1-Standbild: CRF 0 (beste) bis 63; konstante Qualität braucht -b:v 0.
        crf = round(63 - quality * 63 / 100)
        args.extend([
            "-c:v", "libaom-av1", "-still-picture", "1",
            "-crf", str(crf), "-b:v", "0", "-cpu-used", "6",
        ])

    args.append(output_file)
    return args


def get_preset_for_settings(settings):
    """
    Findet heraus, ob die aktuellen Einstellungen exakt einem Preset entsprechen.
    """
    for preset_name, preset_settings in PRESETS.items():
        match = True
        for key, preset_value in preset_settings.items():
            if settings.get(key) != preset_value:
                match = False
                break
        if match:
            return preset_name
    return "Benutzerdefiniert"
