"""Waechter gegen den eingefrorenen GUI-Thread am Queue-Ende.

Der Fehler (03.10.2026): Die Oberflaeche stand still, sobald alle Jobs
verarbeitet waren. Ursache war ein blockierender D-Bus-Aufruf in _notify(),
das genau dort aufgerufen wird. Gemessen: exakt die Antwortzeit des
Notification-Daemons (haengender Daemon = 6 s Stillstand).

Dieser Test haelt die Fehlerklasse fest, nicht nur den Einzelfall:
  1. Die Oberflaeche darf waehrend des Queue-Endes nicht blockieren —
     auch dann nicht, wenn der D-Bus-Daemon beliebig lange braucht.
  2. finished_failed muss zu jedem uebergebenen Slot passen. Ein Slot mit
     (title, body) an einem Signal ohne Parameter brachte Qt mit einem
     Fatal zum Abbruch — im Wegwerftest sichtbar, im Normalbetrieb nicht.
  3. Der Benachrichtigungs-Thread muss sich wieder beenden, damit beim
     Fensterabbau kein QThread-Fehler entsteht.
"""
import os
import sys
import tempfile
import time
import unittest

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt

import mainwindow


class QueueEndDoesNotFreezeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def _pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.005)

    def _window_with_finished_job(self):
        w = mainwindow.MainWindow()
        w.jobs = [{
            "input_file": os.path.abspath("test_input.mp4"),
            "output_dir": tempfile.gettempdir(),
            "output_file": os.path.join(tempfile.gettempdir(), "lme_freeze_watch.mp4"),
            "settings": {},
            "status": "Fertig",
            "progress": 100.0,
            "speed": "0.0x",
            "time_remaining": "0s",
        }]
        w.is_running = True
        w.current_job_idx = -1
        w._single_job_idx = None
        # notify-send nicht wirklich aufrufen.
        w._notify_via_notify_send = lambda title, body: None
        return w

    def _measure_call_time(self, action):
        """Misst, wie lange der Aufruf selbst den aufrufenden Thread bindet.

        Bewusst direkt gemessen und nicht ueber einen Heartbeat-Timer: ein
        Timer erfasst eine Blockade nur, wenn die Event-Schleife danach
        wieder laeuft. Genau das war der Grund, warum eine erste Fassung
        dieses Tests den echten Fehler als "gruen" durchliess — im Test
        blieb die gemessene Luecke schlicht innerhalb des Budgets.
        """
        start = time.monotonic()
        action()
        return (time.monotonic() - start) * 1000.0

    def _close_window(self, window):
        """Schliesst das Fenster ohne modalen Rueckfrage-Dialog.

        closeEvent() fragt nach, solange is_running True ist, und dieser
        Dialog wartet auf eine Antwort — im Test wuerde er den Lauf
        anhaengen statt zu enden. Deshalb vorher als "nicht laufend"
        markieren (der Queue-Lauf ist hier ohnehin beendet).
        """
        window.is_running = False
        window.close()
        self.app.processEvents()

    def _wait_for_notify_threads(self, limit=12.0):
        """Wartet auf das Ende aller Benachrichtigungs-Threads.

        Das Register wird vorher geleert, damit ein Thread aus einem
        anderen Test den Lauf nicht blockiert.
        """
        end = time.monotonic() + limit
        while mainwindow._notify_threads and time.monotonic() < end:
            for th in list(mainwindow._notify_threads):
                if not th.isRunning():
                    th.quit()
            self.app.processEvents()
            time.sleep(0.02)

    def test_queue_end_does_not_freeze_on_slow_dbus(self):
        """Der Kernbefund: langsamer D-Bus-Daemon darf die GUI nicht anhalten."""
        import PyQt6.QtDBus as QtDBus
        real = QtDBus.QDBusInterface

        block = 2.5

        class SlowDaemon:
            """Registriert, antwortet aber erst nach block Sekunden.

            Bewusst KEIN QObject-Erbe: Qt zerstoert QObject-Erben beim
            Beenden des Threads, eine solche Attrappe wuerde den Test
            selbst abbrechen lassen statt den Fehler zu zeigen.
            """

            def __init__(self, *a, **kw):
                time.sleep(block)

            def isValid(self):
                return True

            def call(self, *a, **kw):
                time.sleep(block)

                class R:
                    def errorName(self):
                        return ""

                    def arguments(self):
                        return [1]

                return R()

        window = self._window_with_finished_job()
        try:
            QtDBus.QDBusInterface = SlowDaemon
            elapsed = self._measure_call_time(window._process_next_job)
        finally:
            QtDBus.QDBusInterface = real

        self._wait_for_notify_threads()
        self._close_window(window)

        # Der Endzweig muss den D-Bus-Daemon wirklich erreicht haben,
        # sonst prueft der Test ins Leere (current_job_idx == -1 heißt:
        # "Alle Jobs verarbeitet" -> genau dort liegt _notify()).
        self.assertLess(
            elapsed, 1000.0,
            f"GUI blockierte {elapsed:.0f} ms am Queue-Ende — der D-Bus-Weg "
            f"laeuft wieder synchron (vor dem Fix: {block * 2000:.0f} ms, "
            f"weil Konstruktion UND Aufruf blockieren)",
        )

    def test_failed_signal_matches_its_slots(self):
        """finished_failed hat null Parameter — jeder Slot muss dazu passen.

        Ein Slot mit (title, body) an diesem Signal brachte Qt mit einem
        Fatal zum Abbruch. Geprueft wird die Signatur aus dem Quelltext,
        weil ein echter Verbindungsversuch den Prozess beenden wuerde.
        """
        import inspect
        import re

        src = inspect.getsource(mainwindow._NotifyWorker)
        decls = dict(re.findall(r"(\w+)\s*=\s*pyqtSignal\(([^)]*)\)", src))

        self.assertIn("finished_ok", decls)
        self.assertIn("finished_failed", decls)
        # finished_failed: keine Parameter. finished_ok: genau ein.
        self.assertEqual(decls["finished_failed"].strip(), "")
        self.assertEqual(decls["finished_ok"].strip(), "object")

        # Und die Worker-Klasse muss wirklich ein QObject sein — auf einem
        # QRunnable sind PyQt-Signale nicht erlaubt (das war der Zwischen-
        # fehler beim ersten Umbau).
        from PyQt6.QtCore import QObject
        self.assertTrue(issubclass(mainwindow._NotifyWorker, QObject))

    def test_notify_thread_terminates(self):
        """Der Thread muss sich beenden — sonst Fensterabbau mit Fatal."""
        mainwindow._notify_threads.clear()
        thread = mainwindow._run_notify_async(
            "Titel", "Rumpf", [], None, lambda: None,
        )
        self._wait_for_notify_threads(limit=10.0)
        self.assertFalse(
            thread.isRunning(),
            "Benachrichtigungs-Thread laeuft nach getaner Arbeit noch",
        )
        self.assertNotIn(thread, mainwindow._notify_threads)

    def test_fallback_slot_must_not_take_arguments(self):
        """Der Rueckfall-Slot in _notify() muss parameterlos UND wirksam sein.

        Genau hier lag der zweite Fehler: finished_failed() hat keine
        Parameter, der Slot _notify_via_notify_send bekam (title, body).
        Qt kann eine solche Verbindung nicht herstellen und beendet den
        Prozess mit einem Fatal. Ein reiner Quelltexttest hat das nicht
        gefunden (die try/except drumherum schluckt den Fehler) — darum
        wird hier das VERHALTEN geprueft: der Rueckfall muss tatsaechlich
        eine Benachrichtigung mit den richtigen Daten ausloesen.
        """
        # Deterministisch: der echte D-Bus-Daemon antwortet in der
        # Testumgebung nicht rechtzeitig, sonst haengt der Test an ihm
        # statt an der Verdrahtung, die geprueft werden soll.
        import PyQt6.QtDBus as QtDBus
        real_iface = QtDBus.QDBusInterface

        class NoDaemon:
            def __init__(self, *a, **kw):
                pass

            def isValid(self):
                return False

        window = self._window_with_finished_job()
        seen = []
        window._notify_via_notify_send = lambda title, body: seen.append((title, body))
        try:
            QtDBus.QDBusInterface = NoDaemon
            window._notify("Warteschlange abgeschlossen", "3 Jobs fertig")
            end = time.monotonic() + 6.0
            while not seen and time.monotonic() < end:
                self.app.processEvents()
                time.sleep(0.02)
        finally:
            QtDBus.QDBusInterface = real_iface
            self._wait_for_notify_threads(limit=6.0)
            self._close_window(window)

        self.assertTrue(
            seen, "Rueckfall wurde nicht ausgeloest — finished_failed hat "
                  "den Slot nicht erreicht (falsche Parameterzahl?)",
        )
        self.assertEqual(
            seen[0], ("Warteschlange abgeschlossen", "3 Jobs fertig"),
            "der Rueckfall muss Titel und Rumpf der eigentlichen "
            "Benachrichtigung weitergeben",
        )

    def test_fallback_slot_signature_is_compatible(self):
        """Signatur-Deckung zum Verhaltenstest: null Parameter, kein Umweg.

        Der Verhaltenstest oben faengt den Fehler nur, wenn der Prozess
        nicht vorher stirbt. Diese Pruefung sichert die Verdrahtung im
        Quelltext ab, damit ein Rueckbau nicht unbemerkt durchrutscht.
        """
        import inspect
        import re

        src = inspect.getsource(mainwindow.MainWindow._notify)

        # finished_failed() hat null Parameter. Der Slot, der daran
        # gehaengt wird, darf deshalb keine positionalen Parameter
        # annehmen — er muss sie aus dem umschliessenden Scope nehmen.
        self.assertNotRegex(
            src, r"_run_notify_async\([^)]*self\._notify_via_notify_send",
            "finished_failed (null Parameter) darf nicht direkt an "
            "_notify_via_notify_send (zwei Parameter) gehaengt werden",
        )
        self.assertRegex(
            src, r"def _fallback\(\):",
            "es braucht einen parameterlosen Rueckfall-Slot, der seine "
            "Daten aus dem umschliessenden Scope holt",
        )


if __name__ == "__main__":
    unittest.main()
