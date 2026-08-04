"""Python tools for Anki

Modules:

- `fastanki.skill`: Anki flashcard tools for LLM-driven spaced repetition. Direct sqlite + AnkiWeb sync, no Anki app needed."""

__version__ = "0.0.7"
from .collection import *
from .syncer import *
from .media import *
from .core import *
