#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wendet alle Fixes des Code-Audits (v1.12.6) an, aktualisiert die SHA-256-Summen
im PKGBUILD, bereinigt Build-Artefakte und erstellt linux-media-encoder-1.12.6-fixed.zip.
"""

import hashlib
import os
import re
import shutil
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))


def replace_once(filename: str, old: str, new: str) -> None:
    path = os.path.join(ROOT, filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        if new in content:
            print(f"[OK] {filename}: bereits gepatcht.")
            return
        raise RuntimeError(f"Suchblock in {filename} nicht gefunden:\n{old[:200]}...")
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] {filename}")


def apply_patches() -> None:
    # 1. version.py -> 1.12.6
    replace_once(
        "version.py",
        '__version__ = "1.12.5"',
        '__version__ = "1.12.6"',
    )

    # 2. ffmpeg_worker.py: bluray:-Präfix bei os.path.exists & saubere -progress Platzierung
    # Note: in ffmpeg_worker.py line 90 has no trailing period on "einfügen"
    replace_once(
        "ffmpeg_worker.py",
        """    def start(self):
        \"\"\"Startet den FFmpeg-Prozess.\"\"\"
        if not os.path.exists(self.input_file):
            self._emit_finished(False, f"Eingabedatei existiert nicht: {self.input_file}")
            return

        self.process = QProcess(self)
        
        # Replace output_file (usually the last argument) with temp_output_file
        modified_args = list(self.ffmpeg_args)
        if modified_args and modified_args[-1] == self.output_file:
            modified_args[-1] = self.temp_output_file
        else:
            modified_args = [self.temp_output_file if arg == self.output_file else arg for arg in modified_args]

        # Wir fügen '-progress -' an den Anfang der FFmpeg-Argumente ein, 
        # damit FFmpeg Fortschrittsinformationen im Schlüssel-Wert-Format an stdout sendet.
        # So trennen wir Logs (stderr) von strukturierten Fortschritten (stdout).
        full_args = []
        # Argumente durchsuchen und '-progress -' nach dem Input, aber vor dem Output einfügen
        # Einfacher ist es, es direkt nach '-i <input>' einzufügen
        input_idx = -1
        for i, arg in enumerate(modified_args):
            if arg == "-i":
                input_idx = i + 2
                break
        
        if input_idx != -1 and input_idx < len(modified_args):
            full_args = modified_args[:input_idx] + ["-progress", "-"] + modified_args[input_idx:]
        else:
            # Fallback
            full_args = ["-progress", "-"] + modified_args""",
        """    def start(self):
        \"\"\"Startet den FFmpeg-Prozess.\"\"\"
        check_path = self.input_file[7:] if str(self.input_file).startswith("bluray:") else self.input_file
        if not os.path.exists(check_path):
            self._emit_finished(False, f"Eingabedatei existiert nicht: {self.input_file}")
            return

        self.process = QProcess(self)

        # Replace output_file (usually the last argument) with temp_output_file
        modified_args = list(self.ffmpeg_args)
        if modified_args and modified_args[-1] == self.output_file:
            modified_args[-1] = self.temp_output_file
        else:
            modified_args = [self.temp_output_file if arg == self.output_file else arg for arg in modified_args]

        # '-progress -' als globale Option direkt am Anfang (bzw. nach '-y')
        # einfügen, damit Multi-Input-Aufrufe (-i video -i srt) nicht getrennt werden.
        if modified_args and modified_args[0] == "-y":
            full_args = ["-y", "-progress", "-"] + modified_args[1:]
        else:
            full_args = ["-progress", "-"] + modified_args""",
    )

    # 3. optical_media.py: build_bluray_rip_args VBR/CRF/Lossless-Fix & playlist_num < 0 Schutz
    replace_once(
        "optical_media.py",
        """    input_args = ["-playlist", str(playlist_num)]
    if ignore_errors:
        input_args = ["-err_detect", "ignore_err", "-fflags", "+discardcorrupt+genpts"] + input_args

    probe_url = f"bluray:{find_bdmv_root(source_path) or source_path}"
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
                args += ["-c:s", "copy"]""",
        """    input_args = ["-playlist", str(playlist_num)] if (playlist_num is not None and playlist_num >= 0) else []
    if ignore_errors:
        input_args = ["-err_detect", "ignore_err", "-fflags", "+discardcorrupt+genpts"] + input_args

    probe_url = f"bluray:{find_bdmv_root(source_path) or source_path}"
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
            v_bitrate = preset_settings.get("video_bitrate", "")
            crf = preset_settings.get("crf", "")
            a_bitrate = preset_settings.get("audio_bitrate", "192k")

            args += ["-c:v", v_codec]
            if crf:
                args += ["-crf", str(crf)]
            elif v_bitrate:
                args += ["-b:v", str(v_bitrate)]
            else:
                args += ["-crf", "20"]

            args += ["-c:a", a_codec]
            if a_bitrate and a_codec not in ("flac", "alac", "pcm_s16le", "pcm_s24le", "copy"):
                args += ["-b:a", str(a_bitrate)]

            if subtitle_stream_idx is not None:
                args += ["-c:s", "copy"]
        else:
            args += ["-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-b:a", "192k"]
            if subtitle_stream_idx is not None:
                args += ["-c:s", "copy"]""",
    )

    # 4. presets.py: Rotation im Video-Zweig & Bitmap-Untertitel nur für MKV mappen
    replace_once(
        "presets.py",
        """    v_lower = str(settings.get("video_codec", "libx264")).strip().lower()
    a_lower = _resolve_audio_codec(settings).lower()
    crop = get_crop(settings)
    is_copy_cut = (
        not soft_subtitle
        and not hard_subtitle
        and not crop
        and (v_lower == "copy" or (v_lower == "none" and a_lower == "copy"))
    )""",
        """    v_lower = str(settings.get("video_codec", "libx264")).strip().lower()
    a_lower = _resolve_audio_codec(settings).lower()
    crop = get_crop(settings)
    rotate_angle = get_rotation(settings)
    is_copy_cut = (
        not soft_subtitle
        and not hard_subtitle
        and not crop
        and not rotate_angle
        and (v_lower == "copy" or (v_lower == "none" and a_lower == "copy"))
    )""",
    )

    replace_once(
        "presets.py",
        """    # Wenn Hard-Subtitles oder Crop aktiv sind, muss das Video neu codiert werden (keine Stream-Kopie möglich)
    if (hard_subtitle or crop) and v_codec == "copy":
        v_codec = _default_video_codec_for_container(container)""",
        """    # Wenn Hard-Subtitles, Crop oder Drehung aktiv sind, muss das Video neu codiert werden
    if (hard_subtitle or crop or rotate_angle) and v_codec == "copy":
        v_codec = _default_video_codec_for_container(container)""",
    )

    replace_once(
        "presets.py",
        """        if v_codec != "copy":
            vf_filters = []
            if crop:""",
        """        if v_codec != "copy":
            vf_filters = []
            rotate_expr = rotate_filter(rotate_angle)
            if rotate_expr:
                vf_filters.append(rotate_expr)
            if crop:""",
    )

    replace_once(
        "presets.py",
        """        if sub_idx is not None:
            if sub_idx == -1:
                args.extend(["-map", "0:s?"])
            elif sub_idx >= 0:
                args.extend(["-map", f"0:s:{sub_idx}?"])
            if container.lower() == "mkv":
                args.extend(["-c:s", "copy"])""",
        """        # DVD-/Blu-ray-Untertitel sind Bitmap-Streams (dvd_subtitle/hdmv_pgs_subtitle)
        # und können nur in MKV per Stream-Copy übernommen werden.
        if sub_idx is not None and container.lower() == "mkv":
            if sub_idx == -1:
                args.extend(["-map", "0:s?"])
            elif sub_idx >= 0:
                args.extend(["-map", f"0:s:{sub_idx}?"])
            args.extend(["-c:s", "copy"])""",
    )

    # 5. export_settings_dialog.py: Crop/Rotate bei Preset-Wechsel erhalten, Aspect-Sync bei Crop, sauberes closeEvent
    replace_once(
        "export_settings_dialog.py",
        """            if keep_rotate is not None:
                self.settings["rotate"] = keep_rotate
            if keep_crop and self.settings.get("container") in presets.IMAGE_CONTAINERS:
                self.settings["crop"] = keep_crop
            if self.settings.get("container") not in presets.IMAGE_CONTAINERS:
                if keep_subs:
                    self.settings.update(keep_subs)
                if keep_trim:
                    self.settings.update(keep_trim)
            self._set_output_extension(self.settings["container"])
            self._load_settings_to_ui()
            self._update_summary()
            return

        quick_settings = presets.quick_preset_settings(text)
        if quick_settings is not None:
            keep_subs = {k: self.settings[k] for k in presets.SUBTITLE_SETTING_KEYS if k in self.settings}
            keep_trim = {k: self.settings[k] for k in ("trim_start", "trim_end") if k in self.settings}
            self.settings = presets.preserve_disc_settings(quick_settings, self.settings)
            self.settings["custom_mode"] = False
            self.settings["preset_label"] = text
            if self.settings.get("container") not in presets.IMAGE_CONTAINERS:
                if keep_subs:
                    self.settings.update(keep_subs)
                if keep_trim:
                    self.settings.update(keep_trim)""",
        """            if keep_rotate is not None:
                self.settings["rotate"] = keep_rotate
            if keep_crop:
                self.settings["crop"] = keep_crop
            if self.settings.get("container") not in presets.IMAGE_CONTAINERS:
                if keep_subs:
                    self.settings.update(keep_subs)
                if keep_trim:
                    self.settings.update(keep_trim)
            self._set_output_extension(self.settings["container"])
            self._load_settings_to_ui()
            self._update_summary()
            return

        quick_settings = presets.quick_preset_settings(text)
        if quick_settings is not None:
            keep_crop = presets.get_crop(self.settings)
            keep_rotate = self.settings.get("rotate")
            keep_subs = {k: self.settings[k] for k in presets.SUBTITLE_SETTING_KEYS if k in self.settings}
            keep_trim = {k: self.settings[k] for k in ("trim_start", "trim_end") if k in self.settings}
            self.settings = presets.preserve_disc_settings(quick_settings, self.settings)
            self.settings["custom_mode"] = False
            self.settings["preset_label"] = text
            if keep_rotate is not None:
                self.settings["rotate"] = keep_rotate
            if keep_crop:
                self.settings["crop"] = keep_crop
            if self.settings.get("container") not in presets.IMAGE_CONTAINERS:
                if keep_subs:
                    self.settings.update(keep_subs)
                if keep_trim:
                    self.settings.update(keep_trim)""",
    )

    replace_once(
        "export_settings_dialog.py",
        """    def _on_video_crop_changed(self, crop):
        \"\"\"Wird ausgelöst, wenn der Anwender mit der Maus einen Rahmen aufzieht oder verschiebt.\"\"\"
        if crop:
            self.settings["crop"] = crop
        else:
            self.settings.pop("crop", None)
        self._update_crop_ui()
        self._update_summary()""",
        """    def _on_video_crop_changed(self, crop):
        \"\"\"Wird ausgelöst, wenn der Anwender mit der Maus einen Rahmen aufzieht oder verschiebt.\"\"\"
        if crop:
            self.settings["crop"] = crop
        else:
            self.settings.pop("crop", None)
        self._sync_size_spins_to_aspect("width")
        self._update_crop_ui()
        self._update_summary()""",
    )

    replace_once(
        "export_settings_dialog.py",
        """    def _on_clear_crop_clicked(self):
        \"\"\"Setzt den Zuschnitt zurück (volles Bild).\"\"\"
        self.settings.pop("crop", None)
        self.preview_label.set_crop(None)
        self._update_crop_ui()
        self._update_summary()""",
        """    def _on_clear_crop_clicked(self):
        \"\"\"Setzt den Zuschnitt zurück (volles Bild).\"\"\"
        self.settings.pop("crop", None)
        self.preview_label.set_crop(None)
        self._sync_size_spins_to_aspect("width")
        self._update_crop_ui()
        self._update_summary()""",
    )

    replace_once(
        "export_settings_dialog.py",
        """    def done(self, result):
        \"\"\"Räumt Vorschau-/Probe-Prozesse und Temp-Dateien beim Schließen auf.\"\"\"
        if self._probe_proc:""",
        """    def _cleanup_resources(self):
        \"\"\"Räumt Vorschau-/Probe-Prozesse und Temp-Dateien beim Schließen auf.\"\"\"
        if hasattr(self, "_probe_timer") and self._probe_timer:
            self._probe_timer.stop()
        if self._probe_proc:""",
    )

    replace_once(
        "export_settings_dialog.py",
        """        self._preview_temp_files.clear()
        super().done(result)

    def closeEvent(self, event):
        self.done(0)
        super().closeEvent(event)""",
        """        self._preview_temp_files.clear()

    def done(self, result):
        self._cleanup_resources()
        super().done(result)

    def closeEvent(self, event):
        self._cleanup_resources()
        super().closeEvent(event)""",
    )

    # 6. subtitle_editor_dialog.py: setPlainText statt setText, CrashExit-Prüfung, done()-Cleanup
    replace_once(
        "subtitle_editor_dialog.py",
        """    def _on_audio_extracted(self, exit_code, exit_status):
        \"\"\"Phase 2: pass the extracted audio to the local AI CLI.\"\"\"
        if exit_code != 0 or not os.path.exists(self.temp_audio_path) or os.path.getsize(self.temp_audio_path) == 0:""",
        """    def _on_audio_extracted(self, exit_code, exit_status):
        \"\"\"Phase 2: pass the extracted audio to the local AI CLI.\"\"\"
        if (
            exit_status != QProcess.ExitStatus.NormalExit
            or exit_code != 0
            or not self.temp_audio_path
            or not os.path.exists(self.temp_audio_path)
            or os.path.getsize(self.temp_audio_path) == 0
        ):""",
    )

    replace_once(
        "subtitle_editor_dialog.py",
        """    def _on_ai_finished(self, exit_code, exit_status):
        if exit_code != 0:""",
        """    def _on_ai_finished(self, exit_code, exit_status):
        if exit_status != QProcess.ExitStatus.NormalExit or exit_code != 0:""",
    )

    replace_once(
        "subtitle_editor_dialog.py",
        """    def _finish_srt(self, srt_content):
        self.srt_content = srt_content
        self.lbl_status.setText("Transkription erfolgreich abgeschlossen. Untertitel können jetzt bearbeitet werden.")
        self.txt_editor.setText(self.srt_content)""",
        """    def _finish_srt(self, srt_content):
        self.srt_content = srt_content
        self.lbl_status.setText("Transkription erfolgreich abgeschlossen. Untertitel können jetzt bearbeitet werden.")
        self.txt_editor.setPlainText(self.srt_content)""",
    )

    replace_once(
        "subtitle_editor_dialog.py",
        """    def reject(self):
        if self.sub_process:""",
        """    def _stop_processes(self):
        if self.sub_process:""",
    )

    replace_once(
        "subtitle_editor_dialog.py",
        """        self._cleanup_temp_files()
        super().reject()""",
        """        self.sub_process = None
        self.sub_ai_process = None
        self._cleanup_temp_files()

    def done(self, result):
        self._stop_processes()
        super().done(result)

    def reject(self):
        self._stop_processes()
        super().reject()""",
    )

    # 7. intelligent_dialog.py: CrashExit-Prüfung & Validierung positiver Bitraten
    replace_once(
        "intelligent_dialog.py",
        """    def _on_ai_finished(self, exit_code, exit_status):
        self.progress_bar.setVisible(False)
        self.btn_calc_ai.setEnabled(True)
        self.btn_calc_formula.setEnabled(True)
        engine = self.combo_engine.currentText()
        
        if exit_code != 0:""",
        """    def _on_ai_finished(self, exit_code, exit_status):
        self.progress_bar.setVisible(False)
        self.btn_calc_ai.setEnabled(True)
        self.btn_calc_formula.setEnabled(True)
        engine = self.combo_engine.currentText()
        
        if exit_status != QProcess.ExitStatus.NormalExit or exit_code != 0:""",
    )

    # 8. disc_ripper_dialog.py: _install_process Error/Close-Handling, Blu-ray title_num < 0, LocalizedString
    replace_once(
        "disc_ripper_dialog.py",
        """            # Nr.
            num_item = QTableWidgetItem(f"{t.title_num:02d}")""",
        """            # Nr.
            num_str = f"{t.title_num:02d}" if t.title_num >= 0 else "-"
            num_item = QTableWidgetItem(num_str)""",
    )

    replace_once(
        "disc_ripper_dialog.py",
        """                elif res.disc_type == DiscType.BLURAY:
                    input_args = ["-playlist", str(title.title_num)]""",
        """                elif res.disc_type == DiscType.BLURAY and title.title_num >= 0:
                    input_args = ["-playlist", str(title.title_num)]""",
    )

    replace_once(
        "disc_ripper_dialog.py",
        """        answer = QMessageBox.question(
            self,
            tr("Fehlende Komponenten installieren"),
            details,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )""",
        """        answer = QMessageBox.question(
            self,
            tr("Fehlende Komponenten installieren"),
            LocalizedString(str(details), str(details)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )""",
    )

    replace_once(
        "disc_ripper_dialog.py",
        """        self._install_process = QProcess(self)
        self._install_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._install_process.readyReadStandardOutput.connect(self._on_install_output)
        self._install_process.finished.connect(self._on_install_finished)
        self._install_process.start(plan.command[0], plan.command[1:])""",
        """        self._install_process = QProcess(self)
        self._install_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._install_process.readyReadStandardOutput.connect(self._on_install_output)
        self._install_process.finished.connect(self._on_install_finished)
        self._install_process.errorOccurred.connect(self._on_install_error)
        self._install_process.start(plan.command[0], plan.command[1:])

    def _on_install_error(self, error: QProcess.ProcessError):
        if error != QProcess.ProcessError.FailedToStart:
            return
        self._install_process = None
        self.lbl_status.setText(tr("Bereit"))
        self.btn_install_deps.setEnabled(True)
        QMessageBox.warning(
            self,
            tr("Installation fehlgeschlagen"),
            tr(
                "Die Installation wurde abgebrochen oder ist fehlgeschlagen "
                "(Rückgabewert {code}). Einzelheiten stehen im Protokoll.",
                code=-1,
            ),
        )""",
    )

    replace_once(
        "disc_ripper_dialog.py",
        """    def _stop_for_close(self):
        self._closing = True
        if self._is_ripping:
            self._is_ripping = False
            if self.active_worker:
                self.active_worker.stop()""",
        """    def _stop_for_close(self):
        self._closing = True
        if self._is_ripping:
            self._is_ripping = False
            if self.active_worker:
                self.active_worker.stop()
        proc = getattr(self, "_install_process", None)
        if proc is not None:
            try:
                proc.finished.disconnect()
                proc.errorOccurred.disconnect()
                proc.readyReadStandardOutput.disconnect()
            except (TypeError, RuntimeError):
                pass
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.kill()
                proc.waitForFinished(500)
            self._install_process = None""",
    )

    # 9. test_optical_media.py: Host-unabhängiger Test für optionale libdvdcss-Bibliothek
    replace_once(
        "test_optical_media.py",
        """    def test_encryption_and_capabilities_check(self):
        has_dvdcss, msg_dvd = check_dvd_encryption_support()
        self.assertTrue(has_dvdcss)

        caps = check_ffmpeg_optical_capabilities()
        self.assertTrue(caps.get("dvdvideo", False))
        self.assertTrue(caps.get("bluray", False))""",
        """    def test_encryption_and_capabilities_check(self):
        with patch("ctypes.util.find_library", return_value="libdvdcss.so.2"):
            has_dvdcss, msg_dvd = check_dvd_encryption_support()
            self.assertTrue(has_dvdcss)
        with patch("ctypes.util.find_library", return_value=None):
            has_dvdcss_missing, _ = check_dvd_encryption_support()
            self.assertFalse(has_dvdcss_missing)

        caps = check_ffmpeg_optical_capabilities()
        self.assertIn("dvdvideo", caps)
        self.assertIn("bluray", caps)""",
    )


def update_pkgbuild() -> None:
    pkgbuild_path = os.path.join(ROOT, "PKGBUILD")
    with open(pkgbuild_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r"^pkgver=.*$", "pkgver=1.12.6", content, flags=re.MULTILINE)

    src_match = re.search(r"source=\((.*?)\)", content, re.DOTALL)
    if not src_match:
        raise RuntimeError("source=() in PKGBUILD nicht gefunden.")
    sources = re.findall(r'"([^"]+)"', src_match.group(1))

    sums = []
    for src in sources:
        h = hashlib.sha256()
        with open(os.path.join(ROOT, src), "rb") as sf:
            h.update(sf.read())
        sums.append(h.hexdigest())

    formatted_sums = "sha256sums=('" + "'\n            '".join(sums) + "')"
    content = re.sub(r"sha256sums=\(.*?\)", formatted_sums, content, flags=re.DOTALL)

    with open(pkgbuild_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[UPDATED] PKGBUILD (pkgver=1.12.6, {len(sums)} sha256sums aktualisiert)")


def cleanup_artifacts_and_zip() -> str:
    for d in ("__pycache__", "pkg", "src", "work"):
        p = os.path.join(ROOT, d)
        if os.path.exists(p):
            shutil.rmtree(p)
            print(f"[CLEANED] {d}/")

    for extra in ("test_input_lme.mp4",):
        p = os.path.join(ROOT, extra)
        if os.path.exists(p):
            os.remove(p)
            print(f"[CLEANED] {extra}")

    zip_path = os.path.join(ROOT, "linux-media-encoder-1.12.6-fixed.zip")
    exclude_dirs = {".git", "__pycache__", "pkg", "src", "work", ".venv", "venv"}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in sorted(dirnames) if d not in exclude_dirs]
            for fname in sorted(filenames):
                if fname.endswith((".pyc", ".pkg.tar.zst", ".sha256")) or fname in (
                    "linux-media-encoder-1.12.6-fixed.zip",
                    "apply_audit_fixes.py",
                    "apply-fixes.py",
                ):
                    continue
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, ROOT)
                zf.write(full_path, rel_path)
    print(f"[CREATED] {zip_path}")
    return zip_path


if __name__ == "__main__":
    apply_patches()
    update_pkgbuild()
    cleanup_artifacts_and_zip()
