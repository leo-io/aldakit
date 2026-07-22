"""Live-coding loop: play an Alda file on repeat and restart it on save.

The :class:`LivePlayer` plays an ``.alda`` file continuously and watches the file
on disk. When the file is saved with a valid edit, playback restarts from the
beginning with the new version. A save that introduces a parse error is ignored
(the last good version keeps looping and the error is printed), so a half-typed
save never interrupts the sound.

File watching is done with ``Path.stat().st_mtime`` polling (aldakit has no
runtime dependencies, so there is no filesystem-notification library available).
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import DEFAULT_VIRTUAL_PORT_NAME, POLL_INTERVAL_PLAYBACK
from .errors import AldaParseError
from .midi import generate_midi
from .parser import parse

if TYPE_CHECKING:
    from .midi.backends.base import MidiBackend
    from .midi.types import MidiSequence


class LivePlayer:
    """Loop an Alda file and restart it whenever the file changes on disk.

    Example:
        >>> from aldakit import LivePlayer
        >>> LivePlayer("song.alda").run()  # Ctrl+C to stop

    The loop engine is deliberately small and testable: pass a ``backend`` to
    inject a fake for unit tests, and drive it one step at a time with
    :meth:`poll` instead of the blocking :meth:`run`.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        backend: MidiBackend | None = None,
        port: str | None = None,
        use_audio: bool = False,
        soundfont: str | None = None,
        virtual_port_name: str = DEFAULT_VIRTUAL_PORT_NAME,
        poll_interval: float = POLL_INTERVAL_PLAYBACK,
        verbose: bool = False,
    ) -> None:
        """Create a live player.

        Args:
            path: Path to the Alda file to loop.
            backend: A pre-built MIDI backend. If None (default), a backend is
                created lazily based on ``use_audio``/``port``/``soundfont``.
            port: MIDI output port name (MIDI backend only).
            use_audio: Use the built-in TinySoundFont audio backend.
            soundfont: SoundFont path for the audio backend.
            virtual_port_name: Virtual MIDI port name (MIDI backend only).
            poll_interval: Seconds between file-change / playback checks.
            verbose: Print extra status information.
        """
        self.path = Path(path)
        self._backend = backend
        self._port = port
        self._use_audio = use_audio
        self._soundfont = soundfont
        self._virtual_port_name = virtual_port_name
        self.poll_interval = poll_interval
        self.verbose = verbose

        self._sequence: MidiSequence | None = None
        self._last_mtime: float | None = None

    # ------------------------------------------------------------------
    # Backend / loading helpers

    def _build_backend(self) -> MidiBackend:
        """Create the playback backend from the configured options."""
        if self._use_audio:
            from .midi.backends import HAS_TSF, TsfBackend

            if not HAS_TSF:
                raise RuntimeError(
                    "Audio backend not available. The _tsf module was not built."
                )
            return TsfBackend(soundfont=self._soundfont)

        from .midi.backends import LibremidiBackend

        return LibremidiBackend(
            port_name=self._port,
            virtual_port_name=self._virtual_port_name,
        )

    def _current_mtime(self) -> float | None:
        """Return the file's modification time, or None if it is missing."""
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None

    def _load(self) -> MidiSequence | None:
        """Read, parse, and render the file to a MIDI sequence.

        Returns None (and prints to stderr) on a parse error, a missing file,
        or a score with no notes.
        """
        try:
            source = self.path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"Error reading {self.path}: {e}", file=sys.stderr)
            return None

        try:
            ast = parse(source, str(self.path))
        except AldaParseError as e:
            print(f"Parse error: {e}", file=sys.stderr)
            return None

        sequence = generate_midi(ast)
        if not sequence.notes:
            print("Warning: no notes generated.", file=sys.stderr)
            return None
        return sequence

    # ------------------------------------------------------------------
    # Loop engine

    def poll(self, backend: MidiBackend) -> None:
        """Advance the live loop by one step.

        On a file change, re-parse and restart immediately (keeping the last
        good version if the edit does not parse). Otherwise, (re)start playback
        whenever nothing is currently playing so the file loops continuously.
        """
        mtime = self._current_mtime()
        if mtime is not None and mtime != self._last_mtime:
            self._last_mtime = mtime
            new_sequence = self._load()
            if new_sequence is not None:
                self._sequence = new_sequence
                if self.verbose:
                    print(f"Reloaded {self.path} - restarting.", file=sys.stderr)
                backend.stop()
                backend.play(new_sequence)
            return

        if self._sequence is not None and not backend.is_playing():
            backend.play(self._sequence)

    def run(self, stop_event: threading.Event | None = None) -> int:
        """Play the file on a loop until interrupted.

        Args:
            stop_event: Optional event; when set, the loop exits cleanly. If
                None, the loop runs until Ctrl+C.

        Returns:
            A process-style exit code (0 on clean stop, 130 on Ctrl+C).
        """
        if stop_event is None:
            stop_event = threading.Event()

        backend = self._backend if self._backend is not None else self._build_backend()

        self._last_mtime = self._current_mtime()
        self._sequence = self._load()

        backend_name = "audio (TinySoundFont)" if self._use_audio else "MIDI"
        print(
            f"Live: looping {self.path} via {backend_name}. "
            "Save the file to restart. Ctrl+C to stop.",
            file=sys.stderr,
        )

        with backend:
            try:
                while not stop_event.is_set():
                    self.poll(backend)
                    time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                backend.stop()
                print(file=sys.stderr)
                return 130

            backend.stop()
        return 0
