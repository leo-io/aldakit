"""Convert parsed AST nodes into compose objects."""

from __future__ import annotations

from ..ast_nodes import (
    ASTNode,
    BarlineNode,
    BracketedSequenceNode,
    ChordNode,
    DurationNode,
    EventSequenceNode,
    NoteLengthMsNode,
    NoteLengthNode,
    NoteLengthSecondsNode,
    NoteNode,
    OctaveDownNode,
    OctaveSetNode,
    OctaveUpNode,
    RestNode,
)
from .attributes import OctaveDown, OctaveSet, OctaveUp
from .base import ComposeElement, UnsupportedAldaConstructError
from .core import Chord, Note, Rest, Seq


def _duration_kwargs(duration: DurationNode | None) -> dict:
    if duration is None:
        return {}
    if len(duration.components) != 1:
        raise UnsupportedAldaConstructError(
            "Compound/tied durations (multiple duration components) are not supported"
        )
    component = duration.components[0]
    if isinstance(component, NoteLengthNode):
        return {"duration": component.denominator, "dots": component.dots}
    if isinstance(component, NoteLengthMsNode):
        return {"ms": component.ms}
    if isinstance(component, NoteLengthSecondsNode):
        return {"seconds": component.seconds}
    raise UnsupportedAldaConstructError(
        f"Unsupported duration component type: {type(component).__name__}"
    )


def _note_from_node(node: NoteNode) -> Note:
    accidental = "".join(node.accidentals) if node.accidentals else None
    return Note(
        pitch=node.letter,
        accidental=accidental,
        slurred=node.slurred,
        **_duration_kwargs(node.duration),
    )


def _rest_from_node(node: RestNode) -> Rest:
    return Rest(**_duration_kwargs(node.duration))


def _chord_from_node(node: ChordNode) -> Chord:
    notes = []
    for entry in node.notes:
        if not isinstance(entry, NoteNode):
            raise UnsupportedAldaConstructError(
                f"Chord entries of type {type(entry).__name__} are not supported"
            )
        notes.append(_note_from_node(entry))
    return Chord(notes=tuple(notes))


def ast_to_elements(nodes: list[ASTNode]) -> list[ComposeElement]:
    """Convert AST nodes into compose objects.

    A top-level EventSequenceNode is transparently flattened (it's the
    parser's implicit wrapper for a bare snippet).

    Raises:
        UnsupportedAldaConstructError: if a node has no compose equivalent.
    """
    elements: list[ComposeElement] = []
    for node in nodes:
        if isinstance(node, EventSequenceNode):
            elements.extend(ast_to_elements(node.events))
        elif isinstance(node, BarlineNode):
            continue
        elif isinstance(node, NoteNode):
            elements.append(_note_from_node(node))
        elif isinstance(node, RestNode):
            elements.append(_rest_from_node(node))
        elif isinstance(node, ChordNode):
            elements.append(_chord_from_node(node))
        elif isinstance(node, BracketedSequenceNode):
            elements.append(Seq(elements=ast_to_elements(node.events.events)))
        elif isinstance(node, OctaveSetNode):
            elements.append(OctaveSet(value=node.octave))
        elif isinstance(node, OctaveUpNode):
            elements.append(OctaveUp())
        elif isinstance(node, OctaveDownNode):
            elements.append(OctaveDown())
        else:
            raise UnsupportedAldaConstructError(
                f"No compose equivalent for AST construct: {type(node).__name__}"
            )
    return elements
