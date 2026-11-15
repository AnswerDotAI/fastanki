# NB: this file is designed for an LLM reader, not a human. Add it to your LLM's context and ask it to explain.
r"""Anki flashcard tools for spaced repetition. Direct sqlite and AnkiWeb sync, with no Anki app needed.

notation: /why

- collection changes, `add_media` files: local until `sync()`, then on desktop and phone via AnkiWeb
- importing allows `fastanki.*` calls in sandboxes built on the pyskills registry (e.g. safepyrun)

## Mathematics cards

- card only what's already been worked through    /understand before memorizing
- short, one fact per card; split complex topics
- each concept: a theory card and an applied card
- key relationships both ways: formula → name, name → formula
- worked example, derivation: a card per step; long derivation: or its key insight alone
- look-alike formulas: ask how they differ
- ask why a rule works
- occasionally, a summary card on how ideas relate, e.g. how distributivity explains minus times minus is plus
- show the student proposed cards; add once they approve

```python
# theory, applied
add_fb_card(front='What is the distributive property?', back='\(a(b + c) = ab + ac\)<br><br>Multiplying something by a sum equals multiplying by each term separately, then adding.')
add_fb_card(front='Expand using the distributive property: \(5(x + 3)\)', back='\(5x + 15\)')
# derivation too long: key insight only, working on the front, asking what it proves
add_fb_card(front='What does this prove, and how?<br>\(0 = (-1)(0) = (-1)(-1 + 1)\)<br>Distributing: \((-1)(-1) + (-1)(1) = 0\)', back='Proves that \((-1)(-1) = 1\) (minus times minus is plus), using the distributive property.')
# two rules: two cards
add_fb_card(front='Intuitive Fraction Rule 1: What does \(\frac{a}{b}\) equal?', back='\(a\left(\frac{1}{b}\right)\)<br><br>(A fraction is the numerator times one over the denominator)')
add_fb_card(front='Intuitive Fraction Rule 2: What does \(\left(\frac{1}{a}\right)\left(\frac{1}{b}\right)\) equal?', back='\(\frac{1}{ab}\)<br><br>(A third of a tenth is a thirtieth)')
```
"""

from fastanki.core import *
from pyskills import allow

__all__ = ['add_fb_card', 'add_cloze_card', 'add_card', 'add_media', 'find_notes', 'find_note_ids', 'find_cards', 'find_card_ids', 'get_note', 'del_note', 'update_fb_note', 'sync']

allow({'fastanki.*': ...})
