"""Python tools for Anki

Modules:

- `fastanki.skill`: Anki flashcard tools for spaced repetition. Direct sqlite and AnkiWeb sync, with no Anki app needed."""

__version__ = "0.0.7"
from .collection import *
from .syncer import *
from .media import *
from .core import *
