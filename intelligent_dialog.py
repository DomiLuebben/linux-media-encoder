# -*- coding: utf-8 -*-
"""
Intelligenter Bitraten-Rechner Dialog für den Linux Media Encoder.
Bietet AI-basierte Bitratenberechnung mit lokalem Claude- und Antigravity-Support sowie Formel-Fallback.
"""

import json
import re
from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QSpinBox, QDoubleSpinBox, QPushButton, QDialogButtonBox, QProgressBar, QComboBox,
)

import subtitle_utils

class IntelligentBitrateDialog(QDialog):
    def __init__(self, duration_sec, codec, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Intelligenter Bitraten-Rechner")
        self.setMinimumWidth(450)
        self.setModal(True)
        
        self.duration_sec = duration_sec
        self.codec = codec
        
        # Resultierende Bitraten (Standard-Fallback)
        self.result_video_bitrate_mbps = 8.0
        self.result_audio_bitrate_kbps = "192k"
        self.ai_process = None

        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)
        
        grid = QGridLayout()
        grid.setSpacing(8)
        
        # Duration input
        grid.addWidget(QLabel("Medien-Dauer (Sekunden):"), 0, 0)
        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(0.1, 1000000.0)
        self.spin_duration.setValue(self.duration_sec if self.duration_sec > 0 else 60.0)
        grid.addWidget(self.spin_duration, 0, 1)
        
        # Target size input
        grid.addWidget(QLabel("Zielgröße (MB):"), 1, 0)
        self.spin_size = QSpinBox()
        self.spin_size.setRange(1, 100000)
        self.spin_size.setValue(25)
        grid.addWidget(self.spin_size, 1, 1)
        
        # Codec info
        grid.addWidget(QLabel("Ziel-Video-Codec:"), 2, 0)
        self.lbl_codec = QLabel(self.codec)
        self.lbl_codec.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.lbl_codec, 2, 1)
        
        # AI Engine choice
        grid.addWidget(QLabel("Berechnungs-Engine:"), 3, 0)
        self.combo_engine = QComboBox()
        self.combo_engine.addItems(["Claude AI", "Antigravity AI"])
        grid.addWidget(self.combo_engine, 3, 1)
        
        layout.addLayout(grid)
        
        # Action buttons for calculation
        btn_layout = QHBoxLayout()
        self.btn_calc_formula = QPushButton("Schnell-Formel")
        self.btn_calc_formula.clicked.connect(self._calculate_formula)
        btn_layout.addWidget(self.btn_calc_formula)
        
        self.btn_calc_ai = QPushButton("Berechnen (AI)")
        self.btn_calc_ai.setObjectName("btn_primary")
        self.btn_calc_ai.clicked.connect(self._calculate_ai)
        btn_layout.addWidget(self.btn_calc_ai)
        layout.addLayout(btn_layout)
        
        # Progress indicator
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminate status
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)
        
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #888888; font-style: italic;")
        layout.addWidget(self.lbl_status)
        
        # Result display
        self.result_group = QWidget()
        res_layout = QGridLayout(self.result_group)
        res_layout.setContentsMargins(0, 8, 0, 8)
        res_layout.setSpacing(6)
        
        res_layout.addWidget(QLabel("Errechnete Video-Bitrate:"), 0, 0)
        self.lbl_res_vbitrate = QLabel("-")
        self.lbl_res_vbitrate.setStyleSheet("font-weight: bold; color: #2e9fd8;")
        res_layout.addWidget(self.lbl_res_vbitrate, 0, 1)
        
        res_layout.addWidget(QLabel("Errechnete Audio-Bitrate:"), 1, 0)
        self.lbl_res_abitrate = QLabel("-")
        self.lbl_res_abitrate.setStyleSheet("font-weight: bold; color: #2e9fd8;")
        res_layout.addWidget(self.lbl_res_abitrate, 1, 1)
        
        self.result_group.setVisible(False)
        layout.addWidget(self.result_group)
        
        # OK / Cancel
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self.button_box)

    def _calculate_formula(self):
        """Berechnet Bitraten mittels einer mathematischen Näherungsformel (Sofort-Fallback)."""
        duration = self.spin_duration.value()
        target_size_mb = self.spin_size.value()
        
        # Bits insgesamt
        total_bits = target_size_mb * 1024 * 1024 * 8
        total_bitrate_bps = total_bits / duration
        
        # 5% Puffer für Container-Overhead reservieren
        available_bitrate_bps = total_bitrate_bps * 0.95
        
        # Auf volle kbit/s abrunden. Damit können Rundung und die spätere UI-
        # Übernahme das verfügbare Gesamtbudget nicht wieder überschreiten.
        available_bitrate_kbps = int(available_bitrate_bps / 1000)
        min_audio_kbps = 16
        min_video_kbps = 10
        if available_bitrate_kbps < min_audio_kbps + min_video_kbps:
            minimum_size_mb = (
                (min_audio_kbps + min_video_kbps) * 1000 * duration
                / (0.95 * 8 * 1024 * 1024)
            )
            self.result_video_bitrate_mbps = 0.0
            self.result_audio_bitrate_kbps = "0k"
            self.lbl_res_vbitrate.setText("Nicht erreichbar")
            self.lbl_res_abitrate.setText("Nicht erreichbar")
            self.result_group.setVisible(True)
            self.lbl_status.setText(
                "Zielgröße zu klein für die minimalen Audio-/Video-Bitraten "
                f"(mindestens {minimum_size_mb:.1f} MB bei dieser Dauer)."
            )
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return

        # Bevorzugte Audioqualität nach Gesamtbudget, bei knappen Budgets aber
        # höchstens 40 %. So bleiben mindestens 60 % fürs Bild und die Summe
        # liegt in jedem Schwellenbereich sicher innerhalb des Zielbudgets.
        if available_bitrate_kbps > 500:
            preferred_audio_kbps = 160
        elif available_bitrate_kbps > 200:
            preferred_audio_kbps = 128
        elif available_bitrate_kbps > 100:
            preferred_audio_kbps = 96
        else:
            preferred_audio_kbps = int(available_bitrate_kbps * 0.40)

        audio_bitrate_kbps = max(
            min_audio_kbps,
            min(preferred_audio_kbps, int(available_bitrate_kbps * 0.40)),
        )
        video_bitrate_kbps = available_bitrate_kbps - audio_bitrate_kbps

        self.result_video_bitrate_mbps = video_bitrate_kbps / 1000.0
        self.result_audio_bitrate_kbps = f"{audio_bitrate_kbps}k"
        
        # Anzeige aktualisieren
        self.lbl_res_vbitrate.setText(f"{self.result_video_bitrate_mbps:.2f} Mbps")
        self.lbl_res_abitrate.setText(self.result_audio_bitrate_kbps)
        self.result_group.setVisible(True)
        self.lbl_status.setText("Formel-Berechnung abgeschlossen.")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def _calculate_ai(self):
        """Berechnet Bitraten asynchron über das installierte AI-Tool (Claude oder Antigravity)."""
        duration = self.spin_duration.value()
        target_size_mb = self.spin_size.value()
        codec = self.codec
        engine = self.combo_engine.currentText()
        
        prompt = (
            f"Calculate the optimal video and audio bitrates in kbps for a video with:\n"
            f"- Duration: {duration:.2f} seconds\n"
            f"- Target size: {target_size_mb} Megabytes (MB)\n"
            f"- Video Codec: {codec}\n"
            f"\n"
            f"Format the output strictly as a JSON object, without extra text or markdown blocks:\n"
            f"{{\n"
            f"  \"video_bitrate\": \"...k\",\n"
            f"  \"audio_bitrate\": \"...k\"\n"
            f"}}\n"
            f"Ensure total size does not exceed {target_size_mb} MB."
        )
        
        # UI sperren und Ladeindikator zeigen
        self.btn_calc_ai.setEnabled(False)
        self.btn_calc_formula.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_status.setText(f"{engine} berechnet Bitraten...")
        
        self.ai_process = QProcess(self)
        self.ai_process.finished.connect(self._on_ai_finished)
        self.ai_process.errorOccurred.connect(self._on_ai_failed_to_start)

        # Startet das ausgewählte AI-Tool asynchron
        if "Claude" in engine:
            cmd = "claude"
            args = ["-p", prompt]
        else:
            cmd = subtitle_utils.choose_ai_cli()
            args = subtitle_utils.build_ai_args(cmd, prompt)
        self.ai_process.start(cmd, args)
        if cmd in ("agy", "antigravity-cli"):
            self.ai_process.write(prompt.encode("utf-8"))
            self.ai_process.closeWriteChannel()

    def _on_ai_failed_to_start(self, error):
        """KI-CLI fehlt: 'finished' feuert nie — direkt auf die Formel ausweichen."""
        if error != QProcess.ProcessError.FailedToStart:
            return
        self.progress_bar.setVisible(False)
        self.btn_calc_ai.setEnabled(True)
        self.btn_calc_formula.setEnabled(True)
        self.lbl_status.setText("KI-CLI nicht gefunden. Wechsle zu Schnell-Formel.")
        self._calculate_formula()

    def _on_ai_finished(self, exit_code, exit_status):
        self.progress_bar.setVisible(False)
        self.btn_calc_ai.setEnabled(True)
        self.btn_calc_formula.setEnabled(True)
        engine = self.combo_engine.currentText()
        
        if exit_code != 0:
            self.lbl_status.setText(f"{engine}-Fehler (Exit-Code: {exit_code}). Wechsle zu Schnell-Formel.")
            self._calculate_formula()
            return
            
        output = self.ai_process.readAllStandardOutput().data().decode("utf-8", errors="replace").strip()
        
        try:
            # JSON aus der AI-Antwort extrahieren: bevorzugt das Objekt, das
            # tatsächlich "video_bitrate" enthält — die Antwort kann davor
            # anderen Text mit geschweiften Klammern enthalten.
            candidates = re.findall(r"\{[^{}]*\}", output, re.DOTALL)
            json_text = next(
                (c for c in candidates if "video_bitrate" in c),
                candidates[0] if candidates else None,
            )
            if json_text:
                data = json.loads(json_text)

                v_bit = str(data.get("video_bitrate", "1000k")).strip()
                a_bit = str(data.get("audio_bitrate", "128k")).strip()
                
                # Video-Bitrate zu float konvertieren
                v_match = re.search(r"([\d\.]+)\s*([kKMm]?)", v_bit)
                if v_match:
                    val = float(v_match.group(1))
                    unit = v_match.group(2).lower()
                    if unit == 'k':
                        self.result_video_bitrate_mbps = val / 1000.0
                    elif unit == 'm':
                        self.result_video_bitrate_mbps = val
                    else:
                        if val > 100:
                            self.result_video_bitrate_mbps = val / 1000.0
                        else:
                            self.result_video_bitrate_mbps = val
                else:
                    self.result_video_bitrate_mbps = 1.0
                    
                # Audio-Bitrate säubern
                a_match = re.search(r"(\d+)\s*k?", a_bit)
                if a_match:
                    self.result_audio_bitrate_kbps = f"{a_match.group(1)}k"
                else:
                    self.result_audio_bitrate_kbps = "128k"
                    
                self.lbl_res_vbitrate.setText(f"{self.result_video_bitrate_mbps:.2f} Mbps ({v_bit})")
                self.lbl_res_abitrate.setText(self.result_audio_bitrate_kbps)
                self.result_group.setVisible(True)
                self.lbl_status.setText(f"{engine}-Berechnung erfolgreich.")
                self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
            else:
                raise ValueError("JSON-Struktur in AI-Ausgabe nicht gefunden.")
        except Exception as e:
            print("AI parsing error:", e)
            self.lbl_status.setText("Fehler beim Verarbeiten der AI-Antwort. Wechsle zu Schnell-Formel.")
            self._calculate_formula()

    def get_calculated_bitrates(self):
        """Gibt die ermittelten Bitraten zurück."""
        return self.result_video_bitrate_mbps, self.result_audio_bitrate_kbps

    def done(self, result):
        """Räumt laufende AI-Prozesse beim Schließen auf."""
        if hasattr(self, "ai_process") and self.ai_process:
            try:
                self.ai_process.finished.disconnect()
                self.ai_process.errorOccurred.disconnect()
            except (TypeError, RuntimeError):
                pass
            if self.ai_process.state() != QProcess.ProcessState.NotRunning:
                self.ai_process.kill()
                self.ai_process.waitForFinished(500)
        self.ai_process = None
        super().done(result)
