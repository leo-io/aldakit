"""Simple TUI Editor for Alda live coding using prompt_toolkit."""

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import aldakit.ext  # Ensures prompt_toolkit is in sys.path
from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.processors import Processor, Transformation, TransformationInput
from prompt_toolkit.widgets import TextArea

if TYPE_CHECKING:
    from .liveplayer import LivePlayer


class PlaybackHighlightProcessor(Processor):
    """Highlights currently playing notes in the editor."""

    def __init__(self, get_state: Callable) -> None:
        self.get_state = get_state

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        current_time, sequence = self.get_state()
        
        if not sequence:
            return Transformation(ti.fragments)
            
        # Find active notes that match this line (lineno is 0-indexed, source_line is 1-indexed)
        target_line = ti.lineno + 1
        active_cols = set()
        
        for note in sequence.notes:
            if note.source_line == target_line:
                if note.start_time <= current_time <= (note.start_time + note.duration):
                    if note.source_col:
                        active_cols.add(note.source_col)
                        
        if not active_cols:
            return Transformation(ti.fragments)
            
        # Reconstruct the line text
        text = "".join(f[1] for f in ti.fragments)
        if not text:
            return Transformation(ti.fragments)
            
        import re
        # Find all notation events (ignoring whitespace and structural chars)
        matches = list(re.finditer(r'[^\s\[\]{}|()]+', text))
        
        fragments = []
        last_idx = 0
        
        for m in matches:
            start_idx = m.start()
            end_idx = m.end()
            
            # The 1-indexed column of the start and end of this word
            match_start_col = start_idx + 1
            match_end_col = end_idx
            
            # Check if any active note starts within this word
            is_active = any(match_start_col <= col <= match_end_col for col in active_cols)
            
            # Add unhighlighted text before the word
            if start_idx > last_idx:
                fragments.append(("", text[last_idx:start_idx]))
                
            # Add the word itself, highlighted if active
            style = "class:playing-note" if is_active else ""
            fragments.append((style, text[start_idx:end_idx]))
            
            last_idx = end_idx
            
        # Add any remaining unhighlighted text
        if last_idx < len(text):
            fragments.append(("", text[last_idx:]))
            
        return Transformation(fragments)


def run_editor(file_path: str, player: "LivePlayer") -> None:
    """Run the TUI editor for the given file."""
    path = Path(file_path)
    
    # Read initial content
    initial_text = ""
    if path.exists():
        initial_text = path.read_text(encoding="utf-8")
        
    def get_player_state():
        return player.get_playback_state()
        
    text_area = TextArea(
        text=initial_text,
        lexer=None,  # We rely on processor for highlighting
        scrollbar=True,
        line_numbers=True,
        input_processors=[PlaybackHighlightProcessor(get_player_state)],
    )

    status_text = f" Editing: {path.name} | Press Ctrl+S to save/reload | Ctrl+Q or Ctrl+C to quit"
    status_bar = Window(
        height=1,
        content=FormattedTextControl(status_text),
        style="class:status",
    )

    layout = Layout(HSplit([text_area, status_bar]))

    bindings = KeyBindings()

    @bindings.add("c-q")
    @bindings.add("c-c")
    def _quit(event):
        event.app.exit()

    @bindings.add("c-s")
    def _save(event):
        try:
            path.write_text(text_area.text, encoding="utf-8")
            status_bar.content = FormattedTextControl(f" Saved {path.name} - Reloading...")
        except Exception as e:
            status_bar.content = FormattedTextControl(f" Error saving: {e}")

    # Custom styles
    from prompt_toolkit.styles import Style
    style = Style.from_dict({
        "status": "reverse",
        "playing-note": "bg:ansigreen fg:ansiwhite bold",
    })

    app = Application(
        layout=layout,
        key_bindings=bindings,
        style=style,
        full_screen=True,
    )

    # Background task to trigger UI redraws while music plays
    def auto_refresh():
        while not app.is_done:
            app.invalidate()
            time.sleep(0.05)  # 20 FPS refresh

    refresh_thread = threading.Thread(target=auto_refresh, daemon=True)
    refresh_thread.start()

    from prompt_toolkit.patch_stdout import patch_stdout
    with patch_stdout():
        app.run()
