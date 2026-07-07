# -*- coding: utf-8 -*-
"""
Test script for GUI classes instantiation and event loops.
"""

import sys
import os
from PyQt6.QtWidgets import QApplication

# Add project path to search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mainwindow import MainWindow
from export_settings_dialog import ExportSettingsDialog
from intelligent_dialog import IntelligentBitrateDialog
import presets

def test_ui():
    # Instantiate QApp
    app = QApplication(sys.argv)
    
    print("Testing MainWindow instantiation...")
    window = MainWindow()
    assert window.windowTitle() == "Linux Media Encoder", "MainWindow title mismatch!"
    print("MainWindow created successfully!")

    print("Testing native menu bar...")
    window.show()
    app.processEvents()
    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert menu_titles == ["Datei", "Design", "Ansicht", "Hilfe"], "Native menu bar entries mismatch!"
    print("Native menu bar works successfully!")
    
    # Create a dummy job to test dialog loading
    project_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(project_dir, "test_input.mp4")
    output_file = os.path.join(project_dir, "test_output.mp4")
    
    job_settings = dict(presets.PRESETS["Schnell 1080p30 (MP4 H.264)"])
    
    print("Testing ExportSettingsDialog instantiation...")
    dialog = ExportSettingsDialog(input_file, output_file, job_settings)
    print("ExportSettingsDialog created successfully!")
    
    print("Testing IntelligentBitrateDialog instantiation and formula calculation...")
    # 3 second video, libx264 codec
    ib_dialog = IntelligentBitrateDialog(3.0, "libx264")
    # Trigger mathematical calculation
    ib_dialog._calculate_formula()
    v_bit, a_bit = ib_dialog.get_calculated_bitrates()
    print(f"Formula bitrates computed - Video: {v_bit} Mbps, Audio: {a_bit}")
    
    # Assert values are reasonable for a 3-second video targeting 25MB (very high bitrate available)
    assert v_bit > 1.0, "Calculated video bitrate seems too low for a 25MB 3s video!"
    assert a_bit == "160k", "Calculated audio bitrate should be 160k!"
    print("IntelligentBitrateDialog works successfully!")
    
    print("Testing SubtitleEditorDialog instantiation...")
    from subtitle_editor_dialog import SubtitleEditorDialog
    sub_dialog = SubtitleEditorDialog(input_file, output_file, "Deutsch", "English (US)", auto_start=False)
    print("SubtitleEditorDialog created successfully!")
    
    # Simulate closing both to exit cleanly
    window.close()
    dialog.reject()
    ib_dialog.reject()
    sub_dialog.reject()
    
    print("UI components test passed successfully!")

if __name__ == "__main__":
    test_ui()
