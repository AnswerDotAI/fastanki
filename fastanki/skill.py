r"""Anki flashcard tools for spaced repetition. Direct sqlite and AnkiWeb sync, with no Anki app needed.

Reads/writes Anki's collection format and speaks the AnkiWeb sync protocol directly in Python: cards live in a local sqlite file and reach desktop/phone via AnkiWeb sync, as do media added with `add_media`. Importing this module calls `allow({'fastanki.*': ...})`, so sandboxes built on the pyskills registry (e.g. safepyrun) trust fastanki's operations.

## Workflow

`doc()` each function for its params.

- Add: `add_fb_card(front=, back=)` (Basic); `add_cloze_card(text)` with `{{c1::hidden}}` deletions; `add_card(model=, fields={...})` for any other note type, using its own field names.
- Find: `find_notes`/`find_cards` by `deck`, `tag`, `added_days`, or `fields` substrings; `find_cards` also by `is_due`; `find_note_ids`/`find_card_ids` return ids only.
- `get_note(id)`; `update_fb_note(id, front=...)` changes a Basic note's fields, `tags` (replace) or `add_tags`; `del_note(notes=id)` deletes notes with their cards.
- `add_media(path)` copies an image/sound in, returning the name to cite as `<img src="name">` or `[sound:name]`.
- `sync()` pushes/pulls AnkiWeb, media included; `user=`/`passw=` the first time only.

## Flashcard principles for mathematics

1. Understand before you memorize — only card things you've already worked through.
2. Split complex topics into cards that each test one fact.
3. Test both directions — for key relationships, card formula→name and name→formula.
4. Use cards to test the steps of a worked example.
5. When two formulas look alike, make cards that ask how they differ.
6. Occasionally make a summary card about a relationship between ideas. For example, ask how the distributive property explains why minus times minus is plus.
7. Ask why a rule works.
8. Card derivation steps separately — break multi-step derivations into a chain of step-cards.

## Example: creating precalculus cards

For each concept, create a theory card (what something is) and an applied card (a specific example). Keep cards short. If a derivation has many steps, split it into separate cards or focus on the key insight. Show the student your proposed cards, and let them approve before adding them.

### Distributive property — theory + applied

    # Student: I like them! Please add :)
    add_fb_card(
        front='What is the distributive property?',
        back='\(a(b + c) = ab + ac\)<br><br>Multiplying something by a sum equals multiplying by each term separately, then adding.'
    )
    add_fb_card(
        front='Expand using the distributive property: \(5(x + 3)\)',
        back='\(5x + 15\)'
    )

### Minus times minus — break down long cards

A first draft was too long (full derivation in one card). The student asked to break it down. We focused on the key insight, then swapped front/back so the question asks what the working proves:

    # Student: Can we break down the theory one a bit? Feels like too many steps!
    # Student: Let's switch the front and back around.
    # Student: Perfecto!
    add_fb_card(
        front='What does this prove, and how?<br>\(0 = (-1)(0) = (-1)(-1 + 1)\)<br>Distributing: \((-1)(-1) + (-1)(1) = 0\)',
        back='Proves that \((-1)(-1) = 1\) (minus times minus is plus), using the distributive property.'
    )

### Fraction rules — one fact per card

The student corrected a proposal to combine two rules into one card:

    # Student: No that would break our rule! :D Two cards, please
    add_fb_card(
        front='Intuitive Fraction Rule 1: What does \(\frac{a}{b}\) equal?',
        back='\(a\left(\frac{1}{b}\right)\)<br><br>(A fraction is the numerator times one over the denominator)'
    )
    add_fb_card(
        front='Intuitive Fraction Rule 2: What does \(\left(\frac{1}{a}\right)\left(\frac{1}{b}\right)\) equal?',
        back='\(\frac{1}{ab}\)<br><br>(A third of a tenth is a thirtieth)'
    )

### Exponent rule — theory + applied

    # Student: Can you suggest cards for Exponent Rule 4?
    add_fb_card(
        front='\((xy)^n = \) ?',
        back='\(x^n y^n\)'
    )
    add_fb_card(
        front='Simplify: \((2x)^3\)',
        back='\(8x^3\)'
    )
"""

from fastanki.core import *
from pyskills import allow

__all__ = ['add_fb_card', 'add_cloze_card', 'add_card', 'add_media', 'find_notes', 'find_note_ids', 'find_cards', 'find_card_ids', 'get_note', 'del_note', 'update_fb_note', 'sync']

allow({'fastanki.*': ...})
