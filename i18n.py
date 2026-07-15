# -*- coding: utf-8 -*-
"""Runtime localization helpers for the Linux Media Encoder UI.

German source strings remain stable internal identifiers so existing settings,
presets, and sessions keep working. Widgets render localized text while Python
code continues to read the stable source value.
"""

from __future__ import annotations

import os
import re

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import QLibraryInfo, QLocale, Qt, QTranslator, pyqtSignal

from translations import EN_US, FR_FR


SUPPORTED_LOCALES = ("de_DE", "en_US", "fr_FR")
_active_locale = None
_qt_translator = None
_missing = set()
_NON_TRANSLATABLE = {
    "", "128k", "192k", "23.976", "24", "25", "256k", "29.97",
    "30", "320k", "50", "60", "-", "AAC", "ALAC", "Baseline", "CBR",
    "FLAC", "High", "Linux Media Encoder", "Main", "MP3", "Opus",
    "copy", "libsvtav1", "libvpx-vp9", "libx264", "libx265", "none",
    "⟲ 90°", "⟳ 90°",
}


class LocalizedString(str):
    """Rendered text carrying its stable German source value for UI wrappers."""

    def __new__(cls, rendered, source_text):
        value = super().__new__(cls, rendered)
        value.source_text = str(source_text)
        return value


def normalize_locale(locale_name):
    """Map a system locale to one of the three fully supported locales."""
    value = str(locale_name or "").replace("-", "_").lower()
    if value.startswith("de"):
        return "de_DE"
    if value.startswith("fr"):
        return "fr_FR"
    return "en_US"


def active_locale():
    global _active_locale
    if _active_locale is None:
        override = os.environ.get("LME_LOCALE", "").strip()
        _active_locale = normalize_locale(override or QLocale.system().name())
    return _active_locale


def set_locale(locale_name):
    """Override the locale before constructing widgets (primarily for tests)."""
    global _active_locale
    _active_locale = normalize_locale(locale_name)


def tr(message, **values):
    """Translate a stable German source string and optionally format it."""
    if message is None:
        return message
    if isinstance(message, LocalizedString) and not values:
        return message
    source = str(message)
    locale_name = active_locale()
    if locale_name == "de_DE":
        translated = source
    else:
        catalog = EN_US if locale_name == "en_US" else FR_FR
        translated = catalog.get(source)
        if translated is None:
            # Technical identifiers and already translated values are valid.
            if (not _is_nontranslatable(source)
                    and source not in EN_US.values()
                    and source not in FR_FR.values()):
                _missing.add(source)
            translated = source
    source_text = source
    if values:
        try:
            translated = translated.format(**values)
            source_text = source.format(**values)
        except (KeyError, ValueError):
            pass
    return LocalizedString(translated, source_text)


def _is_nontranslatable(source):
    if source in _NON_TRANSLATABLE:
        return True
    if os.path.isabs(source):
        return True
    if re.fullmatch(r"-?\d+(?:[.:]\d+)*(?:[kKmMgGx%°]|\s*(?:fps|kbps|kHz|Mbps|GB|MB))?", source):
        return True
    if re.fullmatch(r"[^<>\n]+\.[A-Za-z0-9]{1,8}", source):
        return True
    if re.fullmatch(r"(?:lib)?[a-z0-9]+(?:_[a-z0-9]+)+", source):
        return True
    if re.fullmatch(r"[A-Z][A-Za-z0-9.+/-]*\.\d+(?:\.\d+)?", source):
        return True
    return False


def missing_translations():
    return set(_missing)


def clear_missing_translations():
    _missing.clear()


def configure_application(app):
    """Install Qt's standard button/dialog translations for the active locale."""
    global _qt_translator
    locale_name = active_locale()
    QLocale.setDefault(QLocale(locale_name))
    translator = QTranslator(app)
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(f"qtbase_{locale_name[:2]}", translations_path):
        app.installTranslator(translator)
        _qt_translator = translator
    app.setProperty("lmeLocale", locale_name)


class _LocalizedWidgetMixin:
    def setWindowTitle(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_window_title = source
        super().setWindowTitle(rendered)

    def windowTitle(self):
        return getattr(self, "_lme_source_window_title", super().windowTitle())

    def setToolTip(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_tooltip = source
        super().setToolTip(rendered)

    def toolTip(self):
        return getattr(self, "_lme_source_tooltip", super().toolTip())


class _LocalizedTextMixin(_LocalizedWidgetMixin):
    def setText(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_text = source
        super().setText(rendered)

    def text(self):
        return getattr(self, "_lme_source_text", super().text())


def _source_and_rendered(text):
    if isinstance(text, LocalizedString):
        return text.source_text, str(text)
    return str(text), str(tr(text))


def _translated_constructor_args(args):
    args = list(args)
    source = None
    if args and isinstance(args[0], str):
        source, args[0] = _source_and_rendered(args[0])
    elif len(args) > 1 and isinstance(args[1], str):
        source, args[1] = _source_and_rendered(args[1])
    return tuple(args), source


class QWidget(_LocalizedWidgetMixin, QtWidgets.QWidget):
    pass


class QMainWindow(_LocalizedWidgetMixin, QtWidgets.QMainWindow):
    pass


class QDialog(_LocalizedWidgetMixin, QtWidgets.QDialog):
    pass


class QLabel(_LocalizedTextMixin, QtWidgets.QLabel):
    def __init__(self, *args, **kwargs):
        args, source = _translated_constructor_args(args)
        super().__init__(*args, **kwargs)
        if source is not None:
            self._lme_source_text = source


class QPushButton(_LocalizedTextMixin, QtWidgets.QPushButton):
    def __init__(self, *args, **kwargs):
        args, source = _translated_constructor_args(args)
        super().__init__(*args, **kwargs)
        if source is not None:
            self._lme_source_text = source


class QCheckBox(_LocalizedTextMixin, QtWidgets.QCheckBox):
    def __init__(self, *args, **kwargs):
        args, source = _translated_constructor_args(args)
        super().__init__(*args, **kwargs)
        if source is not None:
            self._lme_source_text = source


class QRadioButton(_LocalizedTextMixin, QtWidgets.QRadioButton):
    def __init__(self, *args, **kwargs):
        args, source = _translated_constructor_args(args)
        super().__init__(*args, **kwargs)
        if source is not None:
            self._lme_source_text = source


class QGroupBox(_LocalizedWidgetMixin, QtWidgets.QGroupBox):
    def __init__(self, *args, **kwargs):
        args, source = _translated_constructor_args(args)
        super().__init__(*args, **kwargs)
        if source is not None:
            self._lme_source_title = source

    def setTitle(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_title = source
        super().setTitle(rendered)

    def title(self):
        return getattr(self, "_lme_source_title", super().title())


class QLineEdit(_LocalizedWidgetMixin, QtWidgets.QLineEdit):
    def setPlaceholderText(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_placeholder = source
        super().setPlaceholderText(rendered)

    def placeholderText(self):
        return getattr(self, "_lme_source_placeholder", super().placeholderText())


class QTextEdit(_LocalizedWidgetMixin, QtWidgets.QTextEdit):
    def setPlaceholderText(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_placeholder = source
        super().setPlaceholderText(rendered)

    def placeholderText(self):
        return getattr(self, "_lme_source_placeholder", super().placeholderText())


class QProgressBar(_LocalizedWidgetMixin, QtWidgets.QProgressBar):
    def setFormat(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_format = source
        super().setFormat(rendered)

    def format(self):
        return getattr(self, "_lme_source_format", super().format())


class QComboBox(_LocalizedWidgetMixin, QtWidgets.QComboBox):
    """Localized display with translation-independent source values."""

    sourceTextChanged = pyqtSignal(str)
    _SOURCE_ROLE = int(Qt.ItemDataRole.UserRole) + 913

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.currentIndexChanged.connect(self._emit_source_text_changed)

    def _emit_source_text_changed(self, _index):
        self.sourceTextChanged.emit(self.currentText())

    def addItem(self, *args, **kwargs):
        values = list(args)
        text_index = 1 if values and isinstance(values[0], QtGui.QIcon) else 0
        source, rendered = _source_and_rendered(
            values[text_index] if len(values) > text_index else ""
        )
        values[text_index] = rendered
        super().addItem(*values, **kwargs)
        self.setItemData(self.count() - 1, str(source), self._SOURCE_ROLE)

    def addItems(self, texts):
        for text in texts:
            self.addItem(text)

    def insertItem(self, index, *args, **kwargs):
        values = list(args)
        text_index = 1 if values and isinstance(values[0], QtGui.QIcon) else 0
        source, rendered = _source_and_rendered(
            values[text_index] if len(values) > text_index else ""
        )
        values[text_index] = rendered
        super().insertItem(index, *values, **kwargs)
        self.setItemData(index, str(source), self._SOURCE_ROLE)

    def setItemText(self, index, text):
        source, rendered = _source_and_rendered(text)
        self.setItemData(index, source, self._SOURCE_ROLE)
        super().setItemText(index, rendered)

    def itemText(self, index):
        source = self.itemData(index, self._SOURCE_ROLE)
        return str(source) if source is not None else super().itemText(index)

    def currentText(self):
        index = self.currentIndex()
        rendered = super().currentText()
        if self.isEditable() and (
            index < 0 or rendered != super().itemText(index)
        ):
            return rendered
        source = self.itemData(index, self._SOURCE_ROLE)
        return str(source) if source is not None else rendered

    def findText(self, text, flags=Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchCaseSensitive):
        wanted = str(text)
        for index in range(self.count()):
            if self.itemText(index) == wanted or super().itemText(index) == wanted:
                return index
        return -1

    def setCurrentText(self, text):
        index = self.findText(text)
        if index >= 0:
            self.setCurrentIndex(index)
        elif self.isEditable():
            self.setEditText(str(text))
        else:
            super().setCurrentText(tr(text))


class QTableWidgetItem(QtWidgets.QTableWidgetItem):
    def __init__(self, *args, **kwargs):
        args, source = _translated_constructor_args(args)
        super().__init__(*args, **kwargs)
        if source is not None:
            self._lme_source_text = source

    def setText(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_text = source
        super().setText(rendered)

    def text(self):
        return getattr(self, "_lme_source_text", super().text())

    def setToolTip(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_tooltip = source
        super().setToolTip(rendered)

    def toolTip(self):
        return getattr(self, "_lme_source_tooltip", super().toolTip())


class QTableWidget(QtWidgets.QTableWidget):
    def setHorizontalHeaderLabels(self, labels):
        super().setHorizontalHeaderLabels([tr(label) for label in labels])


class QTabWidget(QtWidgets.QTabWidget):
    def addTab(self, *args):
        values = list(args)
        source = None
        if values and isinstance(values[-1], str):
            source, values[-1] = _source_and_rendered(values[-1])
        index = super().addTab(*values)
        if source is not None:
            self.tabBar().setTabData(index, source)
        return index

    def insertTab(self, *args):
        values = list(args)
        source = None
        if values and isinstance(values[-1], str):
            source, values[-1] = _source_and_rendered(values[-1])
        index = super().insertTab(*values)
        if source is not None:
            self.tabBar().setTabData(index, source)
        return index

    def setTabText(self, index, text):
        source, rendered = _source_and_rendered(text)
        self.tabBar().setTabData(index, source)
        super().setTabText(index, rendered)

    def tabText(self, index):
        source = self.tabBar().tabData(index)
        return str(source) if source is not None else super().tabText(index)


class QAction(QtGui.QAction):
    def __init__(self, *args, **kwargs):
        args, source = _translated_constructor_args(args)
        super().__init__(*args, **kwargs)
        if source is not None:
            self._lme_source_text = source

    def setText(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_text = source
        super().setText(rendered)

    def text(self):
        return getattr(self, "_lme_source_text", super().text())

    def setToolTip(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_tooltip = source
        super().setToolTip(rendered)


class QMenu(QtWidgets.QMenu):
    def __init__(self, *args, **kwargs):
        args, source = _translated_constructor_args(args)
        super().__init__(*args, **kwargs)
        if source is not None:
            self._lme_source_title = source

    def addAction(self, *args, **kwargs):
        values = list(args)
        if values and isinstance(values[0], str):
            values[0] = tr(values[0])
        return super().addAction(*values, **kwargs)


class QFileDialog(QtWidgets.QFileDialog):
    @staticmethod
    def getOpenFileName(parent=None, caption="", directory="", filter="", *args, **kwargs):
        return QtWidgets.QFileDialog.getOpenFileName(
            parent, tr(caption), directory, tr(filter), *args, **kwargs
        )

    @staticmethod
    def getOpenFileNames(parent=None, caption="", directory="", filter="", *args, **kwargs):
        return QtWidgets.QFileDialog.getOpenFileNames(
            parent, tr(caption), directory, tr(filter), *args, **kwargs
        )

    @staticmethod
    def getSaveFileName(parent=None, caption="", directory="", filter="", *args, **kwargs):
        return QtWidgets.QFileDialog.getSaveFileName(
            parent, tr(caption), directory, tr(filter), *args, **kwargs
        )

    @staticmethod
    def getExistingDirectory(parent=None, caption="", directory="", *args, **kwargs):
        return QtWidgets.QFileDialog.getExistingDirectory(
            parent, tr(caption), directory, *args, **kwargs
        )


class QMessageBox(_LocalizedTextMixin, QtWidgets.QMessageBox):
    def setDetailedText(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_detailed_text = source
        super().setDetailedText(rendered)

    def detailedText(self):
        return getattr(self, "_lme_source_detailed_text", super().detailedText())

    def setInformativeText(self, text):
        source, rendered = _source_and_rendered(text)
        self._lme_source_informative_text = source
        super().setInformativeText(rendered)

    def informativeText(self):
        return getattr(self, "_lme_source_informative_text", super().informativeText())

    @classmethod
    def _call(cls, method, parent, title, text, *args, **kwargs):
        return getattr(QtWidgets.QMessageBox, method)(
            parent, tr(title), tr(text), *args, **kwargs
        )

    @classmethod
    def warning(cls, parent, title, text, *args, **kwargs):
        return cls._call("warning", parent, title, text, *args, **kwargs)

    @classmethod
    def information(cls, parent, title, text, *args, **kwargs):
        return cls._call("information", parent, title, text, *args, **kwargs)

    @classmethod
    def question(cls, parent, title, text, *args, **kwargs):
        return cls._call("question", parent, title, text, *args, **kwargs)

    @classmethod
    def critical(cls, parent, title, text, *args, **kwargs):
        return cls._call("critical", parent, title, text, *args, **kwargs)

    @classmethod
    def about(cls, parent, title, text):
        return QtWidgets.QMessageBox.about(parent, tr(title), tr(text))


# Unmodified Qt classes re-exported for convenient import shadowing.
QDialogButtonBox = QtWidgets.QDialogButtonBox
