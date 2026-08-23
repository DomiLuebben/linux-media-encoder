# -*- coding: utf-8 -*-
"""Erkennung der Distribution und Nachinstallation fehlender Ripper-Komponenten.

Grundgedanke: Eine feste Liste von Distributionsnamen veraltet zwangsläufig.
Deshalb wird die Familie primär aus `ID` und `ID_LIKE` in /etc/os-release
abgeleitet — genau dafür setzen die Ableger dieses Feld (CachyOS meldet
`ID_LIKE=arch`, Linux Mint `ID_LIKE=ubuntu debian`, Bazzite `ID_LIKE=fedora`).
Eine Namensliste dient nur als Auffangnetz für Systeme, die `ID_LIKE` gar nicht
oder falsch setzen.

Zweiter Grundgedanke: Paketnamen werden **nicht** geraten. Bevor ein Befehl
gebaut wird, prüft das Modul beim Paketverwalter, welche der hinterlegten
Kandidaten es auf diesem System überhaupt gibt. Ein einziger nicht auflösbarer
Name würde sonst den ganzen Installationslauf scheitern lassen — `libbdplus`
liegt unter Arch zum Beispiel nur im AUR.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple


class DistroFamily(Enum):
    ARCH = "arch"
    DEBIAN = "debian"
    FEDORA = "fedora"
    UNKNOWN = "unknown"


# Auffangnetz für Systeme ohne (brauchbares) ID_LIKE. ID hat Vorrang vor ID_LIKE.
_FAMILY_BY_ID: Dict[str, DistroFamily] = {
    # Arch und Ableger
    "arch": DistroFamily.ARCH,
    "archarm": DistroFamily.ARCH,
    "artix": DistroFamily.ARCH,
    "arcolinux": DistroFamily.ARCH,
    "cachyos": DistroFamily.ARCH,
    "endeavouros": DistroFamily.ARCH,
    "garuda": DistroFamily.ARCH,
    "manjaro": DistroFamily.ARCH,
    "steamos": DistroFamily.ARCH,
    # Debian und Ableger
    "debian": DistroFamily.DEBIAN,
    "ubuntu": DistroFamily.DEBIAN,
    "linuxmint": DistroFamily.DEBIAN,
    "elementary": DistroFamily.DEBIAN,
    "pop": DistroFamily.DEBIAN,
    "neon": DistroFamily.DEBIAN,
    "zorin": DistroFamily.DEBIAN,
    "tuxedo": DistroFamily.DEBIAN,
    "tuxedoos": DistroFamily.DEBIAN,
    "raspbian": DistroFamily.DEBIAN,
    "deepin": DistroFamily.DEBIAN,
    "mx": DistroFamily.DEBIAN,
    # Fedora und Ableger
    "fedora": DistroFamily.FEDORA,
    "rhel": DistroFamily.FEDORA,
    "centos": DistroFamily.FEDORA,
    "rocky": DistroFamily.FEDORA,
    "almalinux": DistroFamily.FEDORA,
    "nobara": DistroFamily.FEDORA,
    "bazzite": DistroFamily.FEDORA,
    "bluefin": DistroFamily.FEDORA,
    "aurora": DistroFamily.FEDORA,
    "silverblue": DistroFamily.FEDORA,
    "kinoite": DistroFamily.FEDORA,
}


@dataclass
class DistroInfo:
    family: DistroFamily = DistroFamily.UNKNOWN
    distro_id: str = ""
    pretty_name: str = ""
    is_immutable: bool = False   # rpm-ostree (Bazzite, Silverblue, Kinoite …)


def parse_os_release(content: str) -> Dict[str, str]:
    """Zerlegt den Inhalt von /etc/os-release in ein Wörterbuch."""
    values: Dict[str, str] = {}
    for line in (content or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def family_from_os_release(values: Dict[str, str]) -> DistroFamily:
    """Leitet die Paketverwalter-Familie aus ID und ID_LIKE ab."""
    distro_id = (values.get("ID") or "").strip().lower()
    if distro_id in _FAMILY_BY_ID:
        return _FAMILY_BY_ID[distro_id]

    for token in (values.get("ID_LIKE") or "").lower().replace(",", " ").split():
        if token in _FAMILY_BY_ID:
            return _FAMILY_BY_ID[token]

    return DistroFamily.UNKNOWN


def detect_distro(
    os_release_path: str = "/etc/os-release",
    ostree_marker: str = "/run/ostree-booted",
) -> DistroInfo:
    """Ermittelt Distributionsfamilie und Bauart des laufenden Systems."""
    try:
        with open(os_release_path, encoding="utf-8") as handle:
            values = parse_os_release(handle.read())
    except OSError:
        values = {}

    return DistroInfo(
        family=family_from_os_release(values),
        distro_id=(values.get("ID") or "").strip().lower(),
        pretty_name=values.get("PRETTY_NAME") or values.get("NAME") or "",
        # Unveränderliche Systeme (Bazzite & Co.) installieren nicht mit dnf,
        # sondern mit rpm-ostree in eine neue Systemschicht.
        is_immutable=os.path.exists(ostree_marker),
    )


# Kandidaten je Komponente und Familie. Mehrere Namen = Alternativen; welcher
# davon existiert, entscheidet die Abfrage beim Paketverwalter.
COMPONENT_PACKAGES: Dict[DistroFamily, Dict[str, Tuple[str, ...]]] = {
    DistroFamily.ARCH: {
        "ffmpeg": ("ffmpeg",),
        "ffprobe": ("ffmpeg",),
        "cdparanoia": ("cdparanoia",),
        "cd-info": ("libcdio",),
        "lsdvd": ("lsdvd",),
        "bd_info": ("libbluray",),
        "libdvdcss": ("libdvdcss",),
        "libaacs": ("libaacs",),
        "libbdplus": ("libbdplus",),
    },
    DistroFamily.DEBIAN: {
        "ffmpeg": ("ffmpeg",),
        "ffprobe": ("ffmpeg",),
        "cdparanoia": ("cdparanoia",),
        "cd-info": ("libcdio-utils",),
        "lsdvd": ("lsdvd",),
        "bd_info": ("libbluray-bin", "libbluray2"),
        "libdvdcss": ("libdvdcss2", "libdvd-pkg"),
        "libaacs": ("libaacs0",),
        "libbdplus": ("libbdplus0",),
    },
    DistroFamily.FEDORA: {
        "ffmpeg": ("ffmpeg", "ffmpeg-free"),
        "ffprobe": ("ffmpeg", "ffmpeg-free"),
        "cdparanoia": ("cdparanoia",),
        "cd-info": ("libcdio-tools", "libcdio"),
        "lsdvd": ("lsdvd",),
        "bd_info": ("libbluray-utils", "libbluray"),
        "libdvdcss": ("libdvdcss",),
        "libaacs": ("libaacs",),
        "libbdplus": ("libbdplus",),
    },
}


# Komponenten, die kein Paket sind, sondern eine Übersetzungsoption von FFmpeg.
_FFMPEG_BUILD_OPTIONS = {
    "dvdvideo": "Der dvdvideo-Demuxer ist eine Übersetzungsoption von FFmpeg "
                "(--enable-libdvdnav --enable-libdvdread) und lässt sich nicht nachinstallieren. "
                "Nötig ist ein FFmpeg-Paket, das damit gebaut wurde.",
    "bluray": "Das bluray-Protokoll ist eine Übersetzungsoption von FFmpeg "
              "(--enable-libbluray) und lässt sich nicht nachinstallieren. "
              "Nötig ist ein FFmpeg-Paket, das damit gebaut wurde.",
}

# Fälle, die bewusst NICHT automatisch erledigt werden.
_MANUAL_NOTES: Dict[Tuple[DistroFamily, str], str] = {
    (DistroFamily.ARCH, "libbdplus"):
        "libbdplus liegt bei Arch und seinen Ablegern nur im AUR. LME baut keine "
        "AUR-Pakete; bitte mit einem AUR-Helfer nachinstallieren.",
    (DistroFamily.FEDORA, "libdvdcss"):
        "Unter Fedora liegt libdvdcss im RPM-Fusion-Repository. LME schaltet keine "
        "Fremdquellen eigenmächtig frei — bitte RPM Fusion (free) zuerst einrichten.",
}


@dataclass
class InstallPlan:
    """Was sich automatisch erledigen lässt und was nicht."""
    family: DistroFamily = DistroFamily.UNKNOWN
    distro_name: str = ""
    is_immutable: bool = False
    packages: List[str] = field(default_factory=list)
    command: List[str] = field(default_factory=list)
    # Feste deutsche Quelltexte — die Oberfläche schickt sie durch tr().
    manual_notes: List[str] = field(default_factory=list)
    # Wird erledigt, ist aber erwähnenswert (Dauer, Netzzugriff …).
    info_notes: List[str] = field(default_factory=list)
    # Komponenten, für die kein Paket auffindbar war (Namen, nicht übersetzbar).
    unresolved: List[str] = field(default_factory=list)
    needs_reboot: bool = False

    @property
    def has_work(self) -> bool:
        return bool(self.packages)


def _run(cmd: Sequence[str], timeout: int = 60) -> Tuple[int, str]:
    try:
        res = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
        return res.returncode, (res.stdout or "")
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return 127, ""


def package_exists(family: DistroFamily, package: str, runner: Callable = _run) -> bool:
    """Prüft ohne Root-Rechte, ob der Paketverwalter dieses Paket kennt."""
    if family == DistroFamily.ARCH:
        code, _ = runner(["pacman", "-Si", package])
        return code == 0
    if family == DistroFamily.DEBIAN:
        code, out = runner(["apt-cache", "policy", package])
        if code != 0 or not out.strip():
            return False
        # 'Candidate: (none)' bedeutet: bekannt, aber aus keiner Quelle beziehbar.
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("Candidate:"):
                return "(none)" not in stripped
        return False
    if family == DistroFamily.FEDORA:
        code, _ = runner(["dnf", "--quiet", "info", package])
        return code == 0
    return False


# libdvd-pkg lädt und übersetzt libdvdcss erst nach der Paketinstallation. Die
# Rückfrage danach ist eine debconf-Frage, kein Kennwort — sie lässt sich also
# vorab beantworten, sodass der Anwender nur die eine pkexec-Abfrage sieht.
DEBCONF_PRESEED_LINES = (
    "libdvd-pkg libdvd-pkg/build boolean true",
    "libdvd-pkg libdvd-pkg/post-invoke_hook-install boolean true",
)


def build_debian_libdvd_script(packages: Sequence[str]) -> str:
    """Baut die Shell-Folge für Debian-Systeme mit libdvd-pkg.

    Alles in einem einzigen privilegierten Aufruf, damit die Kennwortabfrage
    genau einmal erscheint. Jeder eingesetzte Wert wird zitiert; die Vorlage
    selbst ist fest und stammt nicht aus einer Eingabe.
    """
    quoted = " ".join(shlex.quote(name) for name in packages)
    preseed = "\n".join(DEBCONF_PRESEED_LINES)
    return (
        "set -e\n"
        "export DEBIAN_FRONTEND=noninteractive\n"
        f"apt-get install -y {quoted}\n"
        # Schlägt das Vorbeantworten fehl (unbekannte Vorlage in einer anderen
        # Paketfassung), greift unten trotzdem die Vorgabe.
        f"printf '%s\\n' {shlex.quote(preseed)} | debconf-set-selections || true\n"
        "dpkg-reconfigure -f noninteractive libdvd-pkg\n"
    )


def build_install_command(
    family: DistroFamily,
    packages: Sequence[str],
    is_immutable: bool = False,
    use_pkexec: bool = True,
) -> List[str]:
    """Baut den Installationsbefehl als Argumentliste (nie als Shell-Zeile).

    Ausnahme ist der Debian-Weg mit libdvd-pkg: dort müssen mehrere Schritte
    unter denselben Rechten laufen, sonst fragt pkexec zweimal nach dem
    Kennwort. Siehe build_debian_libdvd_script().
    """
    if not packages:
        return []

    if family == DistroFamily.DEBIAN and "libdvd-pkg" in packages:
        cmd = ["sh", "-c", build_debian_libdvd_script(packages)]
        return (["pkexec"] + cmd) if use_pkexec else cmd

    if family == DistroFamily.ARCH:
        base = ["pacman", "-S", "--needed", "--noconfirm"]
    elif family == DistroFamily.DEBIAN:
        base = ["apt-get", "install", "-y"]
    elif family == DistroFamily.FEDORA:
        # Unveränderliche Systeme kennen kein dnf install für das Grundsystem.
        base = (["rpm-ostree", "install", "-y", "--apply-live"]
                if is_immutable else ["dnf", "install", "-y"])
    else:
        return []

    cmd = base + list(packages)
    return (["pkexec"] + cmd) if use_pkexec else cmd


def plan_installation(
    missing_component_keys: Sequence[str],
    distro: Optional[DistroInfo] = None,
    runner: Callable = _run,
) -> InstallPlan:
    """Erstellt aus den fehlenden Komponenten einen konkreten Installationsplan."""
    info = distro or detect_distro()
    plan = InstallPlan(
        family=info.family,
        distro_name=info.pretty_name,
        is_immutable=info.is_immutable,
    )

    if info.family == DistroFamily.UNKNOWN:
        plan.manual_notes.append(
            "Die Distribution konnte nicht zugeordnet werden. Bitte die fehlenden "
            "Komponenten über den Paketverwalter des Systems nachinstallieren."
        )
        return plan

    catalog = COMPONENT_PACKAGES.get(info.family, {})
    chosen: List[str] = []

    for key in missing_component_keys:
        if key in _FFMPEG_BUILD_OPTIONS:
            plan.manual_notes.append(_FFMPEG_BUILD_OPTIONS[key])
            continue

        note = _MANUAL_NOTES.get((info.family, key))
        candidates = catalog.get(key, ())
        resolved = next(
            (name for name in candidates if package_exists(info.family, name, runner)),
            None,
        )

        if resolved is None:
            plan.unresolved.append(key)
            if note:
                plan.manual_notes.append(note)
            continue

        if note:
            # Auffindbar, aber trotzdem nicht mit einem Klick erledigt
            # (z. B. libdvd-pkg braucht noch dpkg-reconfigure).
            plan.manual_notes.append(note)

        if resolved not in chosen:
            chosen.append(resolved)

    # Debian: libdvd-pkg braucht Übersetzungswerkzeug. Nur mitnehmen, wenn es
    # der Paketverwalter auch kennt.
    if info.family == DistroFamily.DEBIAN and "libdvd-pkg" in chosen:
        for helper in ("dh-autoreconf", "build-essential"):
            if helper not in chosen and package_exists(info.family, helper, runner):
                chosen.append(helper)
        plan.info_notes.append(
            "libdvdcss wird bei Debian und Ubuntu über libdvd-pkg aus dem Quelltext gebaut. "
            "Das geschieht im selben Arbeitsgang, braucht eine Internetverbindung und kann "
            "einige Minuten dauern; der Fortschritt steht im Protokoll."
        )

    plan.packages = chosen
    plan.command = build_install_command(info.family, chosen, info.is_immutable)
    plan.needs_reboot = bool(chosen) and info.is_immutable
    return plan


def command_for_display(command: Sequence[str]) -> str:
    """Lesbare Fassung des Befehls für die Bestätigung.

    Bei der Shell-Folge für Debian wäre eine einzige Zeile unlesbar — dort wird
    das Skript selbst gezeigt, damit vor dem Klick sichtbar ist, was läuft.
    """
    parts = list(command)
    if not parts:
        return ""
    if len(parts) >= 2 and parts[-2] == "-c":
        prefix = " ".join(parts[:-1])
        return f"{prefix}\n\n{parts[-1].strip()}"
    return " ".join(parts)


def graphical_sudo_available() -> bool:
    """True, wenn pkexec für die grafische Kennwortabfrage bereitsteht."""
    return bool(shutil.which("pkexec"))
