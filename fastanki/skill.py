"""Anki flashcard tools for LLM-driven spaced repetition. Direct sqlite + AnkiWeb sync, no Anki app needed.

fastanki reads and writes Anki's collection format and speaks the AnkiWeb sync protocol
directly in Python. Cards live in a local sqlite file and reach desktop/phone via AnkiWeb
sync, and so do media files added with `add_media`.

Importing this module also calls `allow({'fastanki.*': ...})`, so effect-gating sandboxes
built on the pyskills registry (such as safepyrun) trust fastanki's own operations.

## Workflow

- `add_fb_card(Front='...', Back='...')` — create a Basic card (use `deck=`, `tags=`, `model=` to customize)
- `find_cards(deck='Math')` / `find_notes(deck='Math')` — search by deck, tag, field substring, or due status
- `get_note(id)` — retrieve a single note by ID
- `update_fb_note(id, Front='...')` — modify fields; `add_tags='tag'` adds tags without replacing
- `del_note(notes=id)` — delete by note ID
- `add_media(path)` — copy an image/sound into the collection; cite the returned name in a field as `<img src="name">` or `[sound:name]`
- `sync()` — push/pull to AnkiWeb, media included (pass `user=`/`passw=` the first time; credentials are cached)

## Flashcard principles for mathematics

1. Understand before you memorize — only card things you've already worked through.
2. One fact per card — split complex topics into atomic Q&A pairs.
3. Test both directions — for key relationships, card formula→name and name→formula.
4. Include worked examples — card the *steps* of a representative problem, not just the result.
5. Combat interference — when two formulas look alike, make dedicated cards highlighting the difference.
6. Connect to the big picture — periodically create summary cards that anchor facts to structure.
7. Card the "why," not just the "what" — ask for the reasoning behind a rule, not only the bare fact.
8. Card derivation steps separately — break multi-step derivations into a chain of step-cards.

## Example: creating precalculus cards

For each concept, create a theory card (what something is) and an applied
card (a specific example). Keep cards short — if a derivation has many steps,
split it into separate cards or focus on the key insight. Show the student
your proposed cards and let them approve before adding.

### Distributive property — theory + applied

    # Student: I like them! Please add :)
    add_fb_card(
        Front='What is the distributive property?',
        Back='\\(a(b + c) = ab + ac\\)<br><br>Multiplying something by a sum equals multiplying by each term separately, then adding.'
    )
    add_fb_card(
        Front='Expand using the distributive property: \\(5(x + 3)\\)',
        Back='\\(5x + 15\\)'
    )

### Minus times minus — break down long cards

A first draft was too long (full derivation in one card). The student asked to
break it down. We focused on the key insight, then swapped front/back so the
question asks what the working proves:

    # Student: Can we break down the theory one a bit? Feels like too many steps!
    # Student: Let's switch the front and back around.
    # Student: Perfecto!
    add_fb_card(
        Front='What does this prove, and how?<br>\\(0 = (-1)(0) = (-1)(-1 + 1)\\)<br>Distributing: \\((-1)(-1) + (-1)(1) = 0\\)',
        Back='Proves that \\((-1)(-1) = 1\\) (minus times minus is plus), using the distributive property.'
    )

### Fraction rules — one fact per card

The student corrected a proposal to combine two rules into one card:

    # Student: No that would break our rule! :D Two cards, please
    add_fb_card(
        Front='Intuitive Fraction Rule 1: What does \\(\\frac{a}{b}\\) equal?',
        Back='\\(a\\left(\\frac{1}{b}\\right)\\)<br><br>(A fraction is the numerator times one over the denominator)'
    )
    add_fb_card(
        Front='Intuitive Fraction Rule 2: What does \\(\\left(\\frac{1}{a}\\right)\\left(\\frac{1}{b}\\right)\\) equal?',
        Back='\\(\\frac{1}{ab}\\)<br><br>(A third of a tenth is a thirtieth)'
    )

### Exponent rule — theory + applied

    # Student: Can you suggest cards for Exponent Rule 4?
    add_fb_card(
        Front='\\((xy)^n = \\) ?',
        Back='\\(x^n y^n\\)'
    )
    add_fb_card(
        Front='Simplify: \\((2x)^3\\)',
        Back='\\(8x^3\\)'
    )
"""

from fastanki.core import *
from pyskills import allow

__all__ = ['add_fb_card', 'add_media', 'find_notes', 'find_note_ids', 'find_cards', 'find_card_ids', 'get_note', 'del_note', 'update_fb_note', 'sync']

allow({'fastanki.*': ...})
