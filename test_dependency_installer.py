# -*- coding: utf-8 -*-
"""Unit-Tests für die Distributionserkennung und den Installationsplan.

Kein Test ruft einen echten Paketverwalter auf: die Abfrage wird über den
`runner`-Parameter ersetzt, damit die Ergebnisse auf jedem Rechner gleich sind.
"""

import os
import tempfile
import unittest
import unittest.mock

from dependency_installer import (
    DistroFamily,
    DistroInfo,
    InstallPlan,
    build_debian_libdvd_script,
    build_install_command,
    command_for_display,
    detect_distro,
    family_from_os_release,
    package_exists,
    parse_os_release,
    plan_installation,
    rpmfusion_free_enabled,
    arch_package_repository,
    find_aur_helper,
    AUR_ONLY_NOTE,
)


# Echte /etc/os-release-Auszüge der genannten Systeme.
OS_RELEASE_SAMPLES = {
    "cachyos": 'NAME="CachyOS Linux"\nPRETTY_NAME="CachyOS"\nID=cachyos\nID_LIKE=arch\n',
    "endeavouros": 'NAME="EndeavourOS"\nID=endeavouros\nID_LIKE=arch\n',
    "garuda": 'NAME="Garuda Linux"\nID=garuda\nID_LIKE=arch\n',
    "manjaro": 'NAME="Manjaro Linux"\nID=manjaro\n',
    "arch": 'NAME="Arch Linux"\nID=arch\n',
    "linuxmint": 'NAME="Linux Mint"\nID=linuxmint\nID_LIKE="ubuntu debian"\n',
    "tuxedo": 'NAME="TUXEDO OS"\nID=tuxedo\nID_LIKE="ubuntu debian"\n',
    "ubuntu": 'NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\n',
    "debian": 'NAME="Debian GNU/Linux"\nID=debian\n',
    "pop": 'NAME="Pop!_OS"\nID=pop\nID_LIKE="ubuntu debian"\n',
    "bazzite": 'NAME="Bazzite"\nID=bazzite\nID_LIKE="fedora"\n',
    "nobara": 'NAME="Nobara Linux"\nID=nobara\nID_LIKE=fedora\n',
    "fedora": 'NAME="Fedora Linux"\nID=fedora\n',
    "kinoite": 'NAME="Fedora Linux"\nID=fedora\nVARIANT_ID=kinoite\n',
}

EXPECTED_FAMILY = {
    "cachyos": DistroFamily.ARCH,
    "endeavouros": DistroFamily.ARCH,
    "garuda": DistroFamily.ARCH,
    "manjaro": DistroFamily.ARCH,
    "arch": DistroFamily.ARCH,
    "linuxmint": DistroFamily.DEBIAN,
    "tuxedo": DistroFamily.DEBIAN,
    "ubuntu": DistroFamily.DEBIAN,
    "debian": DistroFamily.DEBIAN,
    "pop": DistroFamily.DEBIAN,
    "bazzite": DistroFamily.FEDORA,
    "nobara": DistroFamily.FEDORA,
    "fedora": DistroFamily.FEDORA,
    "kinoite": DistroFamily.FEDORA,
}


class DistroDetectionTest(unittest.TestCase):

    def test_all_known_derivatives_map_to_the_right_family(self):
        for name, content in OS_RELEASE_SAMPLES.items():
            with self.subTest(distro=name):
                values = parse_os_release(content)
                self.assertEqual(family_from_os_release(values), EXPECTED_FAMILY[name])

    def test_unknown_derivative_is_resolved_via_id_like(self):
        # Ein Ableger, den niemand namentlich kennt, aber der ID_LIKE korrekt
        # setzt — genau dafür ist die Ableitung da.
        values = parse_os_release('NAME="Irgendwas"\nID=voellig-neu\nID_LIKE=arch\n')
        self.assertEqual(family_from_os_release(values), DistroFamily.ARCH)

    def test_unknown_without_id_like_stays_unknown(self):
        values = parse_os_release('NAME="Exotisch"\nID=exotisch\n')
        self.assertEqual(family_from_os_release(values), DistroFamily.UNKNOWN)

    def test_parse_os_release_strips_quotes_and_comments(self):
        values = parse_os_release('# Kommentar\nID="arch"\nPRETTY_NAME=\'Arch Linux\'\nMUELL\n')
        self.assertEqual(values["ID"], "arch")
        self.assertEqual(values["PRETTY_NAME"], "Arch Linux")
        self.assertNotIn("MUELL", values)

    def test_detect_distro_reads_files_and_ostree_marker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os_release = os.path.join(tmpdir, "os-release")
            with open(os_release, "w", encoding="utf-8") as handle:
                handle.write(OS_RELEASE_SAMPLES["bazzite"])

            marker = os.path.join(tmpdir, "ostree-booted")
            info = detect_distro(os_release, marker)
            self.assertEqual(info.family, DistroFamily.FEDORA)
            self.assertEqual(info.distro_id, "bazzite")
            self.assertFalse(info.is_immutable)

            with open(marker, "w") as handle:
                handle.write("")
            self.assertTrue(detect_distro(os_release, marker).is_immutable)

    def test_missing_os_release_does_not_raise(self):
        info = detect_distro("/pfad/gibt/es/nicht", "/pfad/gibt/es/auch/nicht")
        self.assertEqual(info.family, DistroFamily.UNKNOWN)


class InstallCommandTest(unittest.TestCase):

    def test_command_per_family(self):
        self.assertEqual(
            build_install_command(DistroFamily.ARCH, ["lsdvd"]),
            ["pkexec", "pacman", "-S", "--needed", "--noconfirm", "lsdvd"],
        )
        self.assertEqual(
            build_install_command(DistroFamily.DEBIAN, ["lsdvd", "cdparanoia"]),
            ["pkexec", "apt-get", "install", "-y", "lsdvd", "cdparanoia"],
        )
        self.assertEqual(
            build_install_command(DistroFamily.FEDORA, ["lsdvd"]),
            ["pkexec", "dnf", "install", "-y", "lsdvd"],
        )

    def test_immutable_fedora_uses_rpm_ostree(self):
        self.assertEqual(
            build_install_command(DistroFamily.FEDORA, ["lsdvd"], is_immutable=True),
            ["pkexec", "rpm-ostree", "install", "-y", "--apply-live", "lsdvd"],
        )

    def test_no_packages_means_no_command(self):
        self.assertEqual(build_install_command(DistroFamily.ARCH, []), [])
        self.assertEqual(build_install_command(DistroFamily.UNKNOWN, ["lsdvd"]), [])

    def test_pkexec_can_be_omitted_for_display(self):
        self.assertEqual(
            build_install_command(DistroFamily.ARCH, ["lsdvd"], use_pkexec=False),
            ["pacman", "-S", "--needed", "--noconfirm", "lsdvd"],
        )


class PackageResolutionTest(unittest.TestCase):

    def test_apt_candidate_none_counts_as_missing(self):
        def runner(cmd, timeout=60):
            if cmd[-1] == "vorhanden":
                return 0, "vorhanden:\n  Installed: (none)\n  Candidate: 1.2-3\n"
            return 0, "fehlend:\n  Installed: (none)\n  Candidate: (none)\n"

        self.assertTrue(package_exists(DistroFamily.DEBIAN, "vorhanden", runner))
        self.assertFalse(package_exists(DistroFamily.DEBIAN, "fehlend", runner))

    def test_exit_codes_decide_for_pacman_and_dnf(self):
        def runner(cmd, timeout=60):
            return (0, "") if cmd[-1] == "da" else (1, "")

        self.assertTrue(package_exists(DistroFamily.ARCH, "da", runner))
        self.assertFalse(package_exists(DistroFamily.ARCH, "weg", runner))
        self.assertTrue(package_exists(DistroFamily.FEDORA, "da", runner))
        self.assertFalse(package_exists(DistroFamily.FEDORA, "weg", runner))


class RpmFusionTest(unittest.TestCase):

    def test_dnf_repolist_decides_when_it_works(self):
        aktiv = "repo id            repo name\nfedora             Fedora 42\nrpmfusion-free     RPM Fusion Free\n"
        ohne = "repo id            repo name\nfedora             Fedora 42\n"
        self.assertTrue(rpmfusion_free_enabled(lambda cmd, timeout=60: (0, aktiv)))
        self.assertFalse(rpmfusion_free_enabled(lambda cmd, timeout=60: (0, ohne)))

    def test_repo_files_are_the_fallback_when_dnf_is_unusable(self):
        # Auf rpm-ostree-Systemen ist dnf nicht immer benutzbar.
        def kaputtes_dnf(cmd, timeout=60):
            return 127, ""

        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertFalse(rpmfusion_free_enabled(kaputtes_dnf, tmpdir))

            pfad = os.path.join(tmpdir, "rpmfusion-free.repo")
            with open(pfad, "w", encoding="utf-8") as handle:
                handle.write("[rpmfusion-free]\nname=RPM Fusion Free\nenabled=0\n")
            self.assertFalse(rpmfusion_free_enabled(kaputtes_dnf, tmpdir))

            with open(pfad, "w", encoding="utf-8") as handle:
                handle.write("[rpmfusion-free]\nname=RPM Fusion Free\nenabled=1\n")
            self.assertTrue(rpmfusion_free_enabled(kaputtes_dnf, tmpdir))

    def test_missing_enabled_key_counts_as_enabled(self):
        # dnf behandelt ein Repository ohne 'enabled' als aktiv.
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "rf.repo"), "w", encoding="utf-8") as handle:
                handle.write("[rpmfusion-free-updates]\nname=RPM Fusion Free Updates\n")
            self.assertTrue(rpmfusion_free_enabled(lambda cmd, timeout=60: (127, ""), tmpdir))


class ArchRepositoryTest(unittest.TestCase):

    # pacman uebersetzt die Feldnamen. Ohne LC_ALL=C liefe ein Parser auf
    # "Repository" auf einem deutschen System ins Leere.
    PACMAN_SI_EN = (
        "Repository      : cachyos-extra-znver4\n"
        "Name            : lsdvd\n"
        "Version         : 0.21-1.1\n"
    )
    PACMAN_SI_DE = (
        "Repositorium             : extra\n"
        "Name                     : lsdvd\n"
    )

    def test_repository_is_read_from_pacman_output(self):
        calls = []

        def runner(cmd, timeout=60):
            calls.append(cmd)
            return 0, self.PACMAN_SI_EN

        self.assertEqual(arch_package_repository("lsdvd", runner), "cachyos-extra-znver4")
        # Die Sprachfestlegung muss im Aufruf stehen, sonst ist das Ergebnis
        # von der Spracheinstellung des Rechners abhaengig.
        self.assertEqual(calls[0][:3], ["env", "LC_ALL=C", "pacman"])

    def test_localized_output_without_lc_all_is_not_parsed(self):
        # Belegt, warum LC_ALL=C noetig ist: die deutsche Fassung trifft nicht.
        self.assertIsNone(arch_package_repository("lsdvd", lambda cmd, timeout=60: (0, self.PACMAN_SI_DE)))

    def test_unknown_package_has_no_repository(self):
        self.assertIsNone(arch_package_repository("libbdplus", lambda cmd, timeout=60: (1, "")))

    def test_find_aur_helper_picks_the_first_available(self):
        import dependency_installer

        with unittest.mock.patch.object(
            dependency_installer.shutil, "which",
            side_effect=lambda name: "/usr/bin/yay" if name == "yay" else None,
        ):
            self.assertEqual(find_aur_helper(), "yay")

        with unittest.mock.patch.object(dependency_installer.shutil, "which", return_value=None):
            self.assertIsNone(find_aur_helper())


class InstallPlanTest(unittest.TestCase):

    def _arch(self, immutable=False):
        return DistroInfo(
            family=DistroFamily.ARCH,
            distro_id="cachyos",
            pretty_name="CachyOS",
            is_immutable=immutable,
        )

    def test_unavailable_package_does_not_poison_the_whole_command(self):
        # libbdplus liegt bei Arch nur im AUR. Wuerde der Name trotzdem in den
        # pacman-Aufruf wandern, schluege der ganze Lauf fehl.
        def runner(cmd, timeout=60):
            return (1, "") if cmd[-1] == "libbdplus" else (0, "")

        plan = plan_installation(["lsdvd", "libbdplus"], self._arch(), runner)
        self.assertEqual(plan.packages, ["lsdvd"])
        self.assertEqual(plan.unresolved, ["libbdplus"])
        self.assertIn("lsdvd", plan.command)
        self.assertNotIn("libbdplus", plan.command)
        self.assertIn(AUR_ONLY_NOTE, plan.manual_notes)

    def test_aur_warning_is_derived_not_hardcoded(self):
        # Welches Paket im AUR liegt, unterscheidet sich je Ableger. Hier ist
        # ausgerechnet lsdvd nicht in den Quellen, libbdplus dagegen schon --
        # der Hinweis muss der tatsaechlichen Abfrage folgen.
        def runner(cmd, timeout=60):
            if cmd[-1] == "lsdvd":
                return 1, ""
            if cmd[:2] == ["env", "LC_ALL=C"]:
                return 0, "Repository      : eigene-quelle\nName            : libbdplus\n"
            return 0, ""

        plan = plan_installation(["lsdvd", "libbdplus"], self._arch(), runner)
        self.assertEqual(plan.unresolved, ["lsdvd"])
        self.assertEqual(plan.packages, ["libbdplus"])
        self.assertEqual(plan.repositories, {"libbdplus": "eigene-quelle"})
        self.assertIn(AUR_ONLY_NOTE, plan.manual_notes)

    def test_no_aur_note_when_everything_resolves(self):
        def runner(cmd, timeout=60):
            if cmd[:2] == ["env", "LC_ALL=C"]:
                return 0, "Repository      : cachyos-extra-znver4\n"
            return 0, ""

        plan = plan_installation(["lsdvd"], self._arch(), runner)
        self.assertEqual(plan.manual_notes, [])
        self.assertIsNone(plan.aur_helper)
        self.assertEqual(plan.repositories, {"lsdvd": "cachyos-extra-znver4"})

    def test_ffmpeg_build_options_are_reported_not_installed(self):
        plan = plan_installation(["dvdvideo", "bluray"], self._arch(), lambda cmd, timeout=60: (0, ""))
        self.assertEqual(plan.packages, [])
        self.assertFalse(plan.has_work)
        self.assertEqual(len(plan.manual_notes), 2)

    def test_duplicate_packages_appear_once(self):
        plan = plan_installation(["ffmpeg", "ffprobe"], self._arch(), lambda cmd, timeout=60: (0, ""))
        self.assertEqual(plan.packages, ["ffmpeg"])

    def test_unknown_distribution_yields_only_a_note(self):
        info = DistroInfo(family=DistroFamily.UNKNOWN, pretty_name="Exotisch")
        plan = plan_installation(["lsdvd"], info, lambda cmd, timeout=60: (0, ""))
        self.assertEqual(plan.packages, [])
        self.assertEqual(plan.command, [])
        self.assertEqual(len(plan.manual_notes), 1)

    def test_fedora_without_rpmfusion_asks_instead_of_failing(self):
        # libdvdcss gibt es ohne RPM Fusion gar nicht. Es darf weder still
        # verschwinden noch den restlichen Lauf verhindern.
        def runner(cmd, timeout=60):
            if cmd[:2] == ["dnf", "repolist"]:
                return 0, "repo id\nfedora  Fedora 42\n"
            return 0, ""

        info = DistroInfo(family=DistroFamily.FEDORA, pretty_name="Fedora 42")
        plan = plan_installation(["libdvdcss", "lsdvd"], info, runner)
        self.assertTrue(plan.needs_rpmfusion)
        self.assertEqual(plan.packages, ["lsdvd"])
        self.assertNotIn("libdvdcss", plan.unresolved)

    def test_fedora_with_rpmfusion_installs_libdvdcss_normally(self):
        def runner(cmd, timeout=60):
            if cmd[:2] == ["dnf", "repolist"]:
                return 0, "repo id\nrpmfusion-free  RPM Fusion Free\n"
            return 0, ""

        info = DistroInfo(family=DistroFamily.FEDORA, pretty_name="Fedora 42")
        plan = plan_installation(["libdvdcss"], info, runner)
        self.assertFalse(plan.needs_rpmfusion)
        self.assertEqual(plan.packages, ["libdvdcss"])

    def test_immutable_system_flags_reboot(self):
        info = DistroInfo(family=DistroFamily.FEDORA, pretty_name="Bazzite", is_immutable=True)
        plan = plan_installation(["lsdvd"], info, lambda cmd, timeout=60: (0, ""))
        self.assertTrue(plan.needs_reboot)
        self.assertIn("rpm-ostree", plan.command)

    def test_debian_prefers_ready_made_libdvdcss2_when_available(self):
        # Gibt es ein fertiges Paket (z. B. aus deb-multimedia), entfaellt der
        # ganze Bauweg ueber libdvd-pkg.
        info = DistroInfo(family=DistroFamily.DEBIAN, pretty_name="Debian")
        plan = plan_installation(["libdvdcss"], info, lambda cmd, timeout=60: (0, "  Candidate: 1.4\n"))
        self.assertEqual(plan.packages, ["libdvdcss2"])
        self.assertEqual(plan.command[:2], ["pkexec", "apt-get"])
        self.assertEqual(plan.info_notes, [])

    def test_debian_libdvd_pkg_runs_the_build_step_in_the_same_call(self):
        # Ohne fertiges libdvdcss2 faellt die Wahl auf libdvd-pkg. Der
        # anschliessende debconf-Schritt muss im SELBEN privilegierten Aufruf
        # laufen, sonst fragt pkexec ein zweites Mal nach dem Kennwort.
        def runner(cmd, timeout=60):
            if cmd[-1] == "libdvdcss2":
                return 0, "  Candidate: (none)\n"
            return 0, "  Candidate: 1.4\n"

        info = DistroInfo(family=DistroFamily.DEBIAN, pretty_name="Linux Mint")
        plan = plan_installation(["libdvdcss"], info, runner)

        self.assertIn("libdvd-pkg", plan.packages)
        self.assertIn("dh-autoreconf", plan.packages)
        self.assertEqual(plan.command[:3], ["pkexec", "sh", "-c"])

        script = plan.command[3]
        self.assertIn("DEBIAN_FRONTEND=noninteractive", script)
        self.assertIn("debconf-set-selections", script)
        self.assertIn("libdvd-pkg/build boolean true", script)
        self.assertIn("dpkg-reconfigure -f noninteractive libdvd-pkg", script)
        # Genau ein privilegierter Aufruf.
        self.assertEqual(plan.command.count("pkexec"), 1)
        # Der Bauschritt wird angekuendigt, nicht verschwiegen.
        self.assertTrue(any("libdvd-pkg" in note for note in plan.info_notes))
        self.assertEqual(plan.manual_notes, [])

    def test_generated_debian_script_is_valid_shell(self):
        import shutil
        import subprocess

        script = build_debian_libdvd_script(["cdparanoia", "libdvd-pkg"])
        sh = shutil.which("sh")
        self.assertIsNotNone(sh)
        # 'sh -n' prueft nur die Syntax und fuehrt nichts aus.
        res = subprocess.run([sh, "-n"], input=script, text=True, capture_output=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_package_names_are_quoted_in_the_script(self):
        script = build_debian_libdvd_script(["libdvd-pkg", "boeser name; rm -rf /"])
        self.assertIn("'boeser name; rm -rf /'", script)

    def test_command_for_display_unfolds_shell_scripts(self):
        plain = ["pkexec", "pacman", "-S", "lsdvd"]
        self.assertEqual(command_for_display(plain), "pkexec pacman -S lsdvd")

        shell = ["pkexec", "sh", "-c", "set -e\napt-get install -y lsdvd\n"]
        shown = command_for_display(shell)
        self.assertTrue(shown.startswith("pkexec sh -c"))
        self.assertIn("apt-get install -y lsdvd", shown)
        self.assertEqual(command_for_display([]), "")


if __name__ == "__main__":
    unittest.main()
