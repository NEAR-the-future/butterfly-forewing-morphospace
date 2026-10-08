---
name: slide-editing
description: "Edit and build presentation decks for talks, group meetings, and conference sessions: fix or replace images, restructure a slide's argument, cut text to a readable density, build conference and job-talk decks from a manuscript, animate build steps, embed speaker notes and backup slides, and export slides to PDF. Works on .pptx and derives from .docx/manuscript sources. Use when editing an existing deck, repairing layout or picture problems, or converting a paper into a talk."
whenToUse: "Load for any task that edits, restructures, converts, or exports a slide deck, or that turns a manuscript into presentation slides."
---

# Slide editing and deck construction

For any actual `.pptx` read/write/check operation, load the bundled `office-pptx` skill and use its
toolchain as instructed — it owns the authoritative PPTX mechanics and the validated LibreOffice
path. This skill owns the *content, design, and narrative* decisions and the figure work that feeds
the deck.

Related: figure preparation and image cleanup → `publication-figures`; manuscript source and talk
narrative from a paper → `academic-paper-writing`; deck-to-PDF export → `pdf-compilation`.

## Decide the deck type before editing anything

| Type | Slides for | Density | Non-negotiable |
|---|---|---|---|
| Conference talk (10–15 min) | 10–15 | very low | one message per slide, readable from the back row |
| Seminar / job talk (45–60 min) | 30–45 | low, with detail slides | explicit narrative arc and a 3-slide summary |
| Group meeting | 8–20 | medium | raw data is acceptable and expected |
| Thesis defence | 30–50 | medium | every claim traceable to a chapter |
| Poster-derived / flash talk | 3–5 | very low | one figure, one sentence |

If the user has not said which, ask or state the assumption you used — the same content restructures
completely between a 12-minute conference slot and a 45-minute seminar.

## The editing loop

1. **Inventory first.** Dump slide titles, text, and image inventory before changing anything; a
   blind edit loses content the speaker relies on. Report the per-slide word count.
2. **Fix the story, then the pixels.** Order: narrative sequence → slide message → text density →
   image quality → alignment and typography. Reordering slides is often the whole fix.
3. **Edit in place on a copy.** Preserve the template, theme, fonts, and colour scheme; a deck that
   suddenly mixes two themes looks worse than the original problem. Write to a new file unless the
   user asks for in-place editing.
4. **Verify by rendering.** Always export the edited deck to PDF and inspect the pages you changed.
   PPTX XML can be valid while the slide is visually broken (overflowing text, image behind a shape,
   missing font).
5. **Report** a slide-by-slide table: slide number → problem → change.

## Content rules that make a talk land

- **One message per slide, stated in the title.** A title that names a topic ("Results") wastes the
  most-read element. Write titles as assertions ("Treatment X halves relapse rate").
- **Text density**: aim ≤ 6 lines of body text, ≤ 8 words per line. Move prose to speaker notes.
  Never paste a manuscript paragraph onto a slide.
- **Figures over tables, tables over bullets, bullets over paragraphs.** If a slide is all bullets,
  it is a note, not a slide.
- **Builds are for argument, not decoration.** Reveal one panel of a figure when you explain it, not
  each bullet for suspense. Never animate anything the audience must read and hold.
- **Font sizes**: body ≥ 20 pt, titles ≥ 28 pt, absolute floor 18 pt for a footnote. If content
  cannot fit, split the slide.
- **Contrast**: test the projector case — dark text on light background for a lit room, light on dark
  for a dark room, and never red text on a green background.
- **Colour-blind safety** carries over from `publication-figures`: never encode a category by
  red-versus-green alone.
- **Numbers on slides** must match the manuscript exactly. Slides are where stale numbers survive
  longest.
- **Accessibility**: alt text on meaningful images, real text instead of text-in-image where the
  tool allows, and a logical reading order for the automated accessibility checker.

## Structure templates

**Conference talk (12 min)**: title → motivation (1) → gap (1) → approach (1) → result 1 (2) →
result 2 (2) → control/robustness (1) → implication (1) → limitations (1) → conclusion (1) →
acknowledgements (1) → backup.

**Seminar (50 min)**: title → outline → problem framing (5) → prior attempts and their limits (6) →
approach (5) → results in three acts (15–18) → mechanism/integration (6) → limitations (2) →
outlook (3) → summary (3) → acknowledgements → backup.

**Job talk**: add 2 slides on future directions and 1 on teaching/fit if the institution expects it.

**Backup slides** (always): the mechanism schematic at full size, the statistics table, the methods
the audience always asks about, the negative control, and the "compared with the other method"
slide. Number backup slides so you can jump to them.

## Speaker notes

Write notes as spoken language, not as an outline: 2–4 sentences per slide, containing the one
transition sentence that connects to the next slide, plus the answers to the two questions the slide
invites. Put the exact numbers you must not misquote in the notes.

## Image and media hygiene in decks

- Replace low-resolution images with the source figure at the deck's native resolution; never
  screenshot a figure from a PDF and place it at full slide width.
- Keep one aspect ratio for embedded figures unless the content demands otherwise.
- Crop for the slide's message, but never crop data points out of a plot without saying so.
- Embed or link deliberately: linked media breaks when the deck moves to another machine. Prefer
  embedded media for anything presented away from the author's computer, and warn about deck size.
- Recompress only the images that are oversized; a 60 MB deck is a presentation risk on a strange
  laptop.
- Video: check the codec plays on the venue's machine, keep a still frame in the notes as a
  fallback, and always have the clip as a separate file as a plan B.

## Export and delivery

- Export to PDF for the archive copy and for venues with their own laptops; verify page count and
  that no slide reflowed.
- Export with speaker notes only if requested, and check whether the venue wants 1-up or handout
  layout.
- Verify fonts are embedded when using a non-standard typeface; otherwise switch to a standard
  sans-serif.
- Deliver: edited `.pptx`, rendered `.pdf`, and a short change report.
