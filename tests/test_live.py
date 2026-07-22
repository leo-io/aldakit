"""Tests for the live-coding loop (LivePlayer)."""

import threading
from unittest.mock import patch

import pytest

from aldakit.liveplayer import LivePlayer
from aldakit.midi.backends.base import MidiBackend
from aldakit.midi.types import MidiSequence


class FakeBackend(MidiBackend):
    """A backend that records play/stop calls instead of emitting MIDI."""

    def __init__(self):
        self.played: list[MidiSequence] = []
        self.stop_calls = 0
        self.closed = False
        self._playing = False

    def play(self, sequence: MidiSequence) -> int | None:
        self.played.append(sequence)
        self._playing = True
        return 0

    def save(self, sequence, path) -> None:  # pragma: no cover - unused
        pass

    def stop(self) -> None:
        self.stop_calls += 1
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing

    # Context-manager protocol used by LivePlayer.run()
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False


@pytest.fixture
def alda_file(tmp_path):
    path = tmp_path / "song.alda"
    path.write_text("piano: c d e f g")
    return path


def _player(path, backend):
    return LivePlayer(path, backend=backend)


class TestLoad:
    def test_valid_file_returns_sequence(self, alda_file):
        player = LivePlayer(alda_file)
        seq = player._load()
        assert isinstance(seq, MidiSequence)
        assert seq.notes

    def test_parse_error_returns_none(self, tmp_path, capsys):
        path = tmp_path / "bad.alda"
        path.write_text("piano: c d (((")
        player = LivePlayer(path)
        assert player._load() is None
        assert "Parse error" in capsys.readouterr().err

    def test_empty_file_returns_none(self, tmp_path, capsys):
        path = tmp_path / "empty.alda"
        path.write_text("# just a comment\n")
        player = LivePlayer(path)
        assert player._load() is None
        assert "no notes" in capsys.readouterr().err.lower()

    def test_missing_file_returns_none(self, tmp_path, capsys):
        player = LivePlayer(tmp_path / "nope.alda")
        assert player._load() is None
        assert "Error reading" in capsys.readouterr().err


class TestPoll:
    def test_initial_play(self, alda_file):
        backend = FakeBackend()
        player = _player(alda_file, backend)
        player._last_mtime = player._current_mtime()
        player._sequence = player._load()

        player.poll(backend)

        assert len(backend.played) == 1
        assert backend.stop_calls == 0

    def test_natural_loop_replays_when_idle(self, alda_file):
        backend = FakeBackend()
        player = _player(alda_file, backend)
        player._last_mtime = player._current_mtime()
        player._sequence = player._load()

        player.poll(backend)  # starts playback
        assert len(backend.played) == 1

        backend._playing = False  # simulate cycle finished
        player.poll(backend)  # should replay
        assert len(backend.played) == 2
        assert backend.played[0] is backend.played[1]

    def test_no_replay_while_playing(self, alda_file):
        backend = FakeBackend()
        player = _player(alda_file, backend)
        player._last_mtime = player._current_mtime()
        player._sequence = player._load()

        player.poll(backend)
        player.poll(backend)  # still playing -> no new play
        assert len(backend.played) == 1

    def test_edit_restarts_with_new_sequence(self, alda_file):
        backend = FakeBackend()
        player = _player(alda_file, backend)
        player._last_mtime = player._current_mtime()
        player._sequence = player._load()
        player.poll(backend)
        first_seq = backend.played[0]

        # Edit the file and advance the mtime so the change is detected.
        alda_file.write_text("piano: g a b > c")
        player._last_mtime = (player._last_mtime or 0) - 1

        player.poll(backend)

        assert backend.stop_calls == 1
        assert len(backend.played) == 2
        assert backend.played[1] is not first_seq

    def test_parse_error_edit_keeps_last_good(self, alda_file, capsys):
        backend = FakeBackend()
        player = _player(alda_file, backend)
        player._last_mtime = player._current_mtime()
        player._sequence = player._load()
        player.poll(backend)
        good_seq = player._sequence

        alda_file.write_text("piano: c d (((")
        player._last_mtime = (player._last_mtime or 0) - 1

        player.poll(backend)

        assert player._sequence is good_seq  # unchanged
        assert backend.stop_calls == 0  # playback not interrupted
        assert len(backend.played) == 1
        assert "Parse error" in capsys.readouterr().err

    def test_no_play_when_no_notes(self, tmp_path):
        path = tmp_path / "empty.alda"
        path.write_text("# nothing here\n")
        backend = FakeBackend()
        player = LivePlayer(path, backend=backend)
        player._last_mtime = player._current_mtime()
        player._sequence = player._load()  # None

        player.poll(backend)
        assert backend.played == []


class TestRun:
    def test_run_exits_on_stop_event(self, alda_file):
        backend = FakeBackend()
        player = LivePlayer(alda_file, backend=backend, poll_interval=0.001)
        stop_event = threading.Event()

        # Stop the loop after the first poll.
        original_poll = player.poll

        def stopping_poll(bk):
            original_poll(bk)
            stop_event.set()

        with patch.object(player, "poll", side_effect=stopping_poll):
            rc = player.run(stop_event=stop_event)

        assert rc == 0
        assert backend.closed
        assert backend.stop_calls >= 1  # final stop on clean exit

    def test_run_handles_keyboard_interrupt(self, alda_file):
        backend = FakeBackend()
        player = LivePlayer(alda_file, backend=backend, poll_interval=0.001)

        with patch.object(player, "poll", side_effect=KeyboardInterrupt):
            rc = player.run()

        assert rc == 130
        assert backend.stop_calls >= 1
        assert backend.closed
