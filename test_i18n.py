import string
import sys
import unittest

from PyQt6 import QtWidgets

from i18n import (
    QComboBox,
    QLabel,
    QTabWidget,
    QWidget,
    active_locale,
    normalize_locale,
    set_locale,
)
from translations import EN_US, FR_FR


class LocalizationCatalogTest(unittest.TestCase):
    def test_catalogs_have_identical_complete_keys(self):
        self.assertEqual(set(EN_US), set(FR_FR))
        self.assertTrue(EN_US)
        self.assertTrue(all(value for value in EN_US.values()))
        self.assertTrue(all(value for value in FR_FR.values()))

    def test_format_placeholders_are_preserved(self):
        formatter = string.Formatter()

        def fields(value):
            return {
                name.split(".", 1)[0].split("[", 1)[0]
                for _, name, _, _ in formatter.parse(value)
                if name
            }

        for source in EN_US:
            with self.subTest(source=source):
                self.assertEqual(fields(source), fields(EN_US[source]))
                self.assertEqual(fields(source), fields(FR_FR[source]))

    def test_system_locale_mapping(self):
        self.assertEqual(normalize_locale("de_DE.UTF-8"), "de_DE")
        self.assertEqual(normalize_locale("en-US"), "en_US")
        self.assertEqual(normalize_locale("fr_CA"), "fr_FR")
        self.assertEqual(normalize_locale("C"), "en_US")


class LocalizedWidgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    def test_english_display_keeps_stable_source_values(self):
        set_locale("en_US")
        self.assertEqual(active_locale(), "en_US")

        label = QLabel("Warteschlange")
        self.assertEqual(label.text(), "Warteschlange")
        self.assertEqual(QtWidgets.QLabel.text(label), "Queue")

        combo = QComboBox()
        combo.addItems(["Automatisch erkennen", "Deutsch (DE)"])
        self.assertEqual(combo.itemText(0), "Automatisch erkennen")
        self.assertEqual(QtWidgets.QComboBox.itemText(combo, 0), "Detect automatically")

        tabs = QTabWidget()
        tabs.addTab(QWidget(), "Bild")
        self.assertEqual(tabs.tabText(0), "Bild")
        self.assertEqual(QtWidgets.QTabWidget.tabText(tabs, 0), "Image")

    def test_french_display_keeps_stable_source_values(self):
        set_locale("fr_FR")
        self.assertEqual(active_locale(), "fr_FR")

        label = QLabel("Warteschlange")
        self.assertEqual(label.text(), "Warteschlange")
        self.assertEqual(QtWidgets.QLabel.text(label), "File d’attente")

        combo = QComboBox()
        combo.addItem("Lokale KI (automatisch)")
        self.assertEqual(combo.currentText(), "Lokale KI (automatisch)")
        self.assertEqual(QtWidgets.QComboBox.currentText(combo), "IA locale (automatique)")

    def test_disc_ripper_dialog_translations_complete_en_and_fr(self):
        from disc_ripper_dialog import DiscRipperDialog
        from i18n import clear_missing_translations, missing_translations

        for loc in ("en_US", "fr_FR"):
            set_locale(loc)
            clear_missing_translations()
            dialog = DiscRipperDialog()
            self.assertEqual(
                missing_translations(),
                set(),
                f"Fehlende Übersetzungen im DiscRipperDialog unter {loc}: {missing_translations()}"
            )
            dialog.close()


if __name__ == "__main__":
    unittest.main()
