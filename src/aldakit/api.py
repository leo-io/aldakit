"""High-level convenience functions for working with Alda music."""

from __future__ import annotations

from pathlib import Path

from .midi.backends import LibremidiBackend
from .score import Score


def play(source: str, port: str | None = None, wait: bool = True) -> None:
    """Parse and play Alda source code.

    Args:
        source: Alda source code string.
        port: MIDI output port name. If None, uses the first available
            port or creates a virtual port named "AldakitMIDI".
        wait: If True (default), block until playback completes.

    Examples:
        >>> import aldakit
        >>> aldakit.play("piano: c d e f g")
        >>> aldakit.play("piano: c d e", port="FluidSynth", wait=False)
    """
    score = Score(source)
    score.play(port=port, wait=wait)


def play_file(path: str | Path, port: str | None = None, wait: bool = True) -> None:
    """Parse and play an Alda file.

    Args:
        path: Path to the Alda file.
        port: MIDI output port name. If None, uses the first available
            port or creates a virtual port named "AldakitMIDI".
        wait: If True (default), block until playback completes.

    Examples:
        >>> import aldakit
        >>> aldakit.play_file("song.alda")
    """
    score = Score.from_file(path)
    score.play(port=port, wait=wait)


def save(source: str, path: str | Path) -> None:
    """Parse Alda source code and save as a MIDI file.

    Args:
        source: Alda source code string.
        path: Output MIDI file path.

    Examples:
        >>> import aldakit
        >>> aldakit.save("piano: c d e f g", "output.mid")
    """
    score = Score(source)
    score.save(path)


def save_file(source_path: str | Path, output_path: str | Path) -> None:
    """Parse an Alda file and save as a MIDI file.

    Args:
        source_path: Path to the Alda file.
        output_path: Output MIDI file path.

    Examples:
        >>> import aldakit
        >>> aldakit.save_file("song.alda", "song.mid")
    """
    score = Score.from_file(source_path)
    score.save(output_path)


def live(
    path: str | Path,
    *,
    port: str | None = None,
    use_audio: bool = False,
    soundfont: str | None = None,
    verbose: bool = False,
) -> int:
    """Loop an Alda file, restarting playback whenever the file is saved.

    This is a live-coding helper: it plays the file continuously and watches it
    on disk. Saving a valid edit restarts playback from the beginning; a save
    with a parse error is ignored (the last good version keeps looping).

    Args:
        path: Path to the Alda file to loop.
        port: MIDI output port name (MIDI backend only).
        use_audio: Use the built-in TinySoundFont audio backend.
        soundfont: SoundFont path for the audio backend.
        verbose: Print extra status information.

    Returns:
        A process-style exit code (0 on clean stop, 130 on Ctrl+C).

    Examples:
        >>> import aldakit
        >>> aldakit.live("song.alda")  # Ctrl+C to stop
    """
    from .liveplayer import LivePlayer

    return LivePlayer(
        path,
        port=port,
        use_audio=use_audio,
        soundfont=soundfont,
        verbose=verbose,
    ).run()


def list_ports() -> list[str]:
    """List available MIDI output ports.

    Returns:
        List of MIDI output port names.

    Examples:
        >>> import aldakit
        >>> ports = aldakit.list_ports()
        >>> print(ports)
        ['IAC Driver Bus 1', 'FluidSynth virtual port']
    """
    backend = LibremidiBackend()
    return backend.list_output_ports()
