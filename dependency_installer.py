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

import configparser
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
    SUSE = "suse"
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
    # openSUSE und SLE. Tumbleweed meldet ID="opensuse-tumbleweed" mit
    # ID_LIKE="opensuse suse", die beiden Sammelbegriffe fangen den Rest.
    "suse": DistroFamily.SUSE,
    "opensuse": DistroFamily.SUSE,
    "opensuse-leap": DistroFamily.SUSE,
    "opensuse-tumbleweed": DistroFamily.SUSE,
    "opensuse-slowroll": DistroFamily.SUSE,
    "opensuse-microos": DistroFamily.SUSE,
    "opensuse-aeon": DistroFamily.SUSE,
    "opensuse-kalpa": DistroFamily.SUSE,
    "sles": DistroFamily.SUSE,
    "sled": DistroFamily.SUSE,
    "sle-micro": DistroFamily.SUSE,
}

# openSUSE MicroOS, Aeon und Kalpa sind unveränderlich, benutzen aber nicht
# ostree, sondern transactional-update auf Btrfs-Schnappschüssen.
_SUSE_TRANSACTIONAL_IDS = frozenset({
    "opensuse-microos", "opensuse-aeon", "opensuse-kalpa", "sle-micro",
})


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

    distro_id = (values.get("ID") or "").strip().lower()
    return DistroInfo(
        family=family_from_os_release(values),
        distro_id=distro_id,
        pretty_name=values.get("PRETTY_NAME") or values.get("NAME") or "",
        # Unveränderliche Systeme installieren nicht in das laufende System:
        # Fedora-Ableger (Bazzite & Co.) über rpm-ostree, openSUSE MicroOS und
        # Aeon über transactional-update.
        is_immutable=(
            os.path.exists(ostree_marker)
            or (distro_id in _SUSE_TRANSACTIONAL_IDS and bool(shutil.which("transactional-update")))
        ),
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
    DistroFamily.SUSE: {
        # openSUSE führt FFmpeg je nach Stand unter versionierten Namen; welcher
        # davon existiert, entscheidet die Abfrage.
        "ffmpeg": ("ffmpeg-7", "ffmpeg-6", "ffmpeg-5", "ffmpeg-4", "ffmpeg"),
        "ffprobe": ("ffmpeg-7", "ffmpeg-6", "ffmpeg-5", "ffmpeg-4", "ffmpeg"),
        "cdparanoia": ("cdparanoia",),
        "cd-info": ("libcdio-utils", "libcdio-tools", "libcdio"),
        "lsdvd": ("lsdvd",),
        "bd_info": ("libbluray-tools", "libbluray-utils", "libbluray"),
        "libdvdcss": ("libdvdcss2", "libdvdcss"),
        "libaacs": ("libaacs0", "libaacs"),
        "libbdplus": ("libbdplus0", "libbdplus"),
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

# Fälle, die bewusst NICHT automatisch erledigt werden. Der AUR-Fall steht
# absichtlich NICHT hier: welches Paket im AUR liegt, unterscheidet sich je
# Arch-Ableger (CachyOS führt vieles in eigenen Quellen) und wird deshalb aus
# der tatsächlichen pacman-Abfrage abgeleitet, nicht aufgelistet.
_MANUAL_NOTES: Dict[Tuple[DistroFamily, str], str] = {}

AUR_ONLY_NOTE = (
    "Diese Komponenten sind in keiner auf diesem System eingerichteten Paketquelle "
    "enthalten und damit nur über das AUR erhältlich. LME baut grundsätzlich keine "
    "AUR-Pakete: dabei würde fremder Bauplan-Quelltext auf dem Rechner ausgeführt, "
    "und makepkg verweigert ohnehin den Lauf mit Administratorrechten."
)


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
    # Fremdquelle nötig, die LME nicht eigenmächtig freischaltet:
    # "" | "rpmfusion" (Fedora) | "packman" (openSUSE).
    needs_extra_repo: str = ""
    # Arch: vorhandener AUR-Helfer, damit der Hinweis einen konkreten
    # Befehl nennen kann statt „nimm irgendeinen Helfer".
    aur_helper: Optional[str] = None
    # Paket -> Quelle, aus der es kommt (Arch). Macht sichtbar, dass
    # z. B. CachyOS vieles aus eigenen Quellen liefert.
    repositories: Dict[str, str] = field(default_factory=dict)

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
    if family == DistroFamily.SUSE:
        # 'zypper search --match-exact' meldet mit 104, wenn nichts passt.
        # Zusätzlich gegen den Namen in der Ausgabe prüfen, damit ein
        # abweichender Rückgabewert nicht als Treffer durchgeht.
        code, out = runner([
            "zypper", "--non-interactive", "--quiet",
            "search", "--match-exact", package,
        ])
        return code == 0 and package in (out or "")
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
    elif family == DistroFamily.SUSE:
        # MicroOS/Aeon schreiben in einen neuen Btrfs-Schnappschuss, der erst
        # nach einem Neustart aktiv wird.
        base = (["transactional-update", "--non-interactive", "pkg", "install"]
                if is_immutable else ["zypper", "--non-interactive", "install"])
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

        # libdvdcss liegt bei Fedora und openSUSE nicht in den Standardquellen.
        # Ohne die jeweilige Fremdquelle gibt es das Paket gar nicht — das ist
        # kein Fehlschlag, sondern ein Schritt, den der Anwender bewusst gehen
        # muss. LME schaltet keine Fremdquellen eigenmächtig frei.
        if key == "libdvdcss":
            if info.family == DistroFamily.FEDORA and not rpmfusion_free_enabled(runner):
                plan.needs_extra_repo = "rpmfusion"
                continue
            if info.family == DistroFamily.SUSE and not packman_enabled(runner):
                plan.needs_extra_repo = "packman"
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

    if info.family == DistroFamily.ARCH:
        for name in chosen:
            repository = arch_package_repository(name, runner)
            if repository:
                plan.repositories[name] = repository
        if plan.unresolved:
            plan.manual_notes.append(AUR_ONLY_NOTE)
            plan.aur_helper = find_aur_helper()

    plan.packages = chosen
    plan.command = build_install_command(info.family, chosen, info.is_immutable)
    plan.needs_reboot = bool(chosen) and info.is_immutable
    return plan


# Reihenfolge = Vorzug bei der Empfehlung.
_AUR_HELPERS = ("paru", "yay", "pikaur", "trizen", "aurman")


def find_aur_helper() -> Optional[str]:
    """Name eines vorhandenen AUR-Helfers (oder None)."""
    for name in _AUR_HELPERS:
        if shutil.which(name):
            return name
    return None


def arch_package_repository(package: str, runner: Callable = _run) -> Optional[str]:
    """Paketquelle, aus der ein Paket stammt — None heißt: in keiner enthalten.

    Das beantwortet die Frage „Repo oder AUR?" ohne jede distributionsabhängige
    Liste: `pacman -Si` befragt genau die auf DIESEM System eingerichteten
    Quellen. Auf CachyOS sind das auch `cachyos`/`cachyos-extra-*`, auf einem
    System mit Chaotic-AUR eben auch dieses. Das AUR selbst kennt pacman nicht —
    „nirgends gefunden" ist also gleichbedeutend mit „nur über das AUR".

    `env LC_ALL=C` ist nicht schmückendes Beiwerk: pacman übersetzt die
    Feldnamen ("Repositorium" auf einem deutschen System), ein Parser auf
    "Repository" liefe sonst je nach Spracheinstellung ins Leere.
    """
    code, out = runner(["env", "LC_ALL=C", "pacman", "-Si", package])
    if code != 0 or not out:
        return None
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip().lower() == "repository":
            return value.strip() or None
    return None


def packman_enabled(
    runner: Callable = _run,
    repo_dir: str = "/etc/zypp/repos.d",
) -> bool:
    """Prüft, ob das Packman-Repository eingebunden ist.

    Packman ist bei openSUSE das, was RPM Fusion bei Fedora ist: libdvdcss und
    das vollständige FFmpeg liegen dort, nicht in den Standardquellen.
    """
    code, out = runner(["zypper", "--non-interactive", "--quiet", "lr"])
    if code == 0 and out:
        return any("packman" in line.lower() for line in out.splitlines())

    try:
        entries = sorted(os.listdir(repo_dir))
    except OSError:
        return False

    parser = configparser.ConfigParser(strict=False, interpolation=None)
    for entry in entries:
        if not entry.endswith(".repo"):
            continue
        try:
            parser.read(os.path.join(repo_dir, entry), encoding="utf-8")
        except (OSError, configparser.Error):
            continue

    for section in parser.sections():
        haystack = " ".join([
            section,
            parser.get(section, "name", fallback=""),
            parser.get(section, "baseurl", fallback=""),
        ]).lower()
        if "packman" not in haystack:
            continue
        if parser.get(section, "enabled", fallback="1").strip() == "1":
            return True
    return False


def rpmfusion_free_enabled(
    runner: Callable = _run,
    repo_dir: str = "/etc/yum.repos.d",
) -> bool:
    """Prüft, ob das RPM-Fusion-Repository (free) aktiv ist.

    Erst über `dnf repolist --enabled`; schlägt das fehl (auf rpm-ostree-Systemen
    ist dnf nicht immer benutzbar), werden die .repo-Dateien gelesen. Fehlt der
    Schlüssel `enabled`, gilt ein Repository als aktiv — so hält es dnf auch.
    """
    code, out = runner(["dnf", "repolist", "--enabled"])
    if code == 0 and out:
        for line in out.splitlines():
            if line.strip().lower().startswith("rpmfusion-free"):
                return True
        return False

    try:
        entries = sorted(os.listdir(repo_dir))
    except OSError:
        return False

    parser = configparser.ConfigParser(strict=False, interpolation=None)
    for entry in entries:
        if not entry.endswith(".repo"):
            continue
        try:
            parser.read(os.path.join(repo_dir, entry), encoding="utf-8")
        except (OSError, configparser.Error):
            continue

    for section in parser.sections():
        if not section.lower().startswith("rpmfusion-free"):
            continue
        if parser.get(section, "enabled", fallback="1").strip() == "1":
            return True
    return False


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
