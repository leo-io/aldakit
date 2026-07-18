#!/usr/bin/env python3
"""Convert a MusicXML file to Alda source code.

aldakit has no native MusicXML support, so this script bridges the gap via
partitura (https://github.com/CPJKU/partitura), which parses MusicXML and
writes Standard MIDI Files. The intermediate MIDI file is then imported
through aldakit's own MIDI-to-Alda pipeline (Score.from_midi_file).

partitura is NOT a dependency of aldakit itself (aldakit is intentionally
zero-dependency). Run this script with an ephemeral dependency instead:

    uv run --with partitura python scripts/musicxml_to_alda.py INPUT.xml
"""

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a MusicXML file to Alda source code via partitura + aldakit.",
        epilog=(
            "This script requires partitura, which is not installed by default. Run it via:\n"
            "  uv run --with partitura python scripts/musicxml_to_alda.py INPUT.xml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to input MusicXML file (.xml, .musicxml, .mxl)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Write Alda output here (default: print to stdout)",
    )
    parser.add_argument(
        "-q", "--quantize",
        type=float,
        default=0.25,
        help="Quantize grid in beats, forwarded to Score.from_midi_file "
             "(default: 0.25 = 16th notes; 0 disables quantization)",
    )
    parser.add_argument(
        "--keep-temp-midi",
        type=Path,
        help="Also save the intermediate MIDI file here (debugging aid)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print progress to stderr",
    )
    return parser.parse_args()


def log(verbose: bool, message: str) -> None:
    if verbose:
        print(message, file=sys.stderr)


def main() -> int:
    args = parse_args()

    if not args.input.is_file():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    try:
        import partitura
    except ImportError:
        print(
            "partitura is not installed. Run this script via:\n"
            "  uv run --with partitura python scripts/musicxml_to_alda.py ...",
            file=sys.stderr,
        )
        return 1

    log(args.verbose, f"Parsing MusicXML: {args.input}")
    try:
        score = partitura.load_musicxml(str(args.input))
    except Exception as e:
        print(f"Failed to parse MusicXML: {e}", file=sys.stderr)
        return 1

    temp_midi_fd, temp_midi_name = tempfile.mkstemp(suffix=".mid")
    os.close(temp_midi_fd)
    temp_midi_path = Path(temp_midi_name)

    try:
        log(args.verbose, f"Writing intermediate MIDI: {temp_midi_path}")
        try:
            partitura.save_score_midi(score, str(temp_midi_path))
        except Exception as e:
            print(f"Failed to write intermediate MIDI file: {e}", file=sys.stderr)
            return 1

        log(args.verbose, f"Importing MIDI into aldakit (quantize_grid={args.quantize})")
        try:
            from aldakit import Score as AldaScore

            alda_score = AldaScore.from_midi_file(
                temp_midi_path, quantize_grid=args.quantize
            )
            alda_code = alda_score.to_alda()
        except Exception as e:
            print(f"Failed to convert MIDI to Alda: {e}", file=sys.stderr)
            return 1

        if args.keep_temp_midi:
            shutil.copyfile(temp_midi_path, args.keep_temp_midi)
            log(args.verbose, f"Saved intermediate MIDI to {args.keep_temp_midi}")
    finally:
        os.unlink(temp_midi_path)

    if args.output:
        args.output.write_text(alda_code, encoding="utf-8")
        log(args.verbose, f"Wrote Alda output to {args.output}")
    else:
        print(alda_code)

    return 0


if __name__ == "__main__":
    sys.exit(main())
