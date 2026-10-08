---
name: academic-language-editing
description: "Line-level editing of scholarly English: grammar, tense and voice, hedging calibration, word choice, terminology consistency, cohesion, punctuation, units and statistics formatting, and removal of non-native-speaker and AI-flavoured tics. Ships an offline rule-based linter (scripts/academic_lint.py) that flags the mechanical problems before a human reads the prose. Use when polishing a manuscript, abstract, response letter, or grant text for clarity and idiom."
whenToUse: "Load when the task is sentence- and word-level refinement rather than paper architecture, or when the user asks to check grammar, usage, word choice, or language quality."
---

# Academic language editing

Structure and section logic belong to `academic-paper-writing`. This skill owns everything from the
sentence down: grammar, tense, voice, hedging, diction, cohesion, punctuation, and convention
formatting. `references/style-rules.md` is the full rulebook; `references/word-choice.md` is the
substitution and confusable-pair list; `references/tense-and-voice.md` is the tense matrix.

## Mandatory pipeline

1. **Lint first, edit second.** Run the bundled linter so mechanical noise does not consume your
   attention:
   ```powershell
   & "C:\Users\16240\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" `
     "<skill-dir>\scripts\academic_lint.py" "<manuscript.txt>" --out "<workspace>\lint.json"
   ```
   It accepts `.txt`, `.md`, `.tex`, and (with python-docx available) `.docx`. Use
   `--format text` for a human-readable report, `--severity high` to see only blocking issues.
2. **Fix in severity order**: grammar/agreement → tense/voice → hedging → diction → cohesion →
   typography. Never restyle prose while a subject–verb disagreement is live in the same sentence.
3. **Verify each edit against the rulebook.** The linter is rule-based and will miss context
   (for example a legitimate passive in Methods). Treat every hit as a question, not a verdict.
4. **Report** as location → current → proposed → reason, grouped by severity. Preserve meaning
   exactly; if a sentence is ambiguous, ask rather than guess the intended claim.
5. **Re-run the linter** on the edited text and confirm the high-severity count dropped.

## The eight rules that matter most

1. **One idea per sentence.** Split sentences containing more than one finite clause joined by
   "and" when the two halves are logically independent. Target ≤ 30 words; hard ceiling 40.
2. **Tense is functional, not decorative.** Established knowledge and Results: past tense.
   Interpretation, implications, and figure/table references: present tense. See
   `references/tense-and-voice.md`.
3. **Voice follows the section.** Methods tolerate passive ("Samples were incubated");
   Introduction/Results/Discussion prefer active ("We measured…"). Never use first person
   plural to hedge ("We believe that…") — either claim it or drop it.
4. **Calibrate every hedge.** Strong evidence: *demonstrates, establishes, shows*. Moderate:
   *indicates, suggests, is consistent with*. Weak: *may, might, appears to*. Do not stack
   ("may possibly suggest"); do not claim causation from correlation ("affects" → "is associated
   with" unless the design supports causation).
5. **Cut empty intensifiers and hedges**: very, quite, rather, somewhat, relatively, arguably,
   it is important to note that, it should be emphasised that.
6. **Kill nominalizations.** "perform an analysis of" → "analyse"; "the implementation of" →
   "implementing". Verbs carry the argument; nouns bury it.
7. **Cohesion is explicit.** Each paragraph opens with a topic sentence that links to the previous
   paragraph, and closes by handing off. Use a small, consistent connective vocabulary
   (however, therefore, in contrast, consequently) — vary only when the logical relation changes.
8. **Terminology is frozen.** Fix one term per concept and use it everywhere, including in figures
   and legends. Do not rotate synonyms for elegance; identical concepts with different names read
   as different concepts.

## Typography and convention (the part referees notice)

- Numbers: spell out at sentence start and for one through nine in running text (unless a unit
  follows: "5 mL"); numerals for 10 and above, all measurements, all statistics, all times.
- Statistics: italic *P*, *n*, *t*, *F*, *r*; report exact *P* values to the journal's precision,
  never "*P* < 0.05" alone unless the journal mandates it; always pair a test statistic with its
  degrees of freedom; give mean ± SD or ± SEM and say which, once, at first use.
- Units: SI, with a non-breaking space between number and unit (5 mL, 37 °C, 3 h); use the
  multiplication sign × not the letter x for magnification; do not mix "uL" and "µL".
- Genes/proteins/species: follow the target journal's italicization and capitalization rules and the
  relevant nomenclature committee. Check every instance with `grep`, not by eye.
- Abbreviations: define at first use in the abstract *and* at first use in the main text (many
  journals require both); never define in the title; never abbreviate a term used fewer than three
  times.
- Punctuation: serial comma per journal; em dash without surrounding spaces; hyphenate compound
  modifiers before a noun ("dose-dependent effect") but not after ("the effect was dose
  dependent"); never use a semicolon where a full stop is honest.
- Remove: contractions, exclamation marks, rhetorical questions, "obviously", "clearly",
  "of course", "as everyone knows".
- AI-flavour removal: no "delve into", "it is worth noting that", "in today's rapidly evolving
  landscape", triadic lists used for rhythm rather than content, and no paragraph ending in a
  symmetrical summary sentence that adds no information.

## Language and venue

- Default to the language of the user's request. If the target is an English journal, produce
  English even when the user wrote Chinese, and state that you did.
- Use the journal's spelling convention consistently (British *-ise/organise, colour, analyse* vs
  American *-ize/organize, color, analyze*). Never mix within a manuscript.
- Keep the authors' voice when editing their text. Consistency with the rest of the manuscript
  beats your personal preference; note deviations rather than imposing them.
- Never change a number, unit, statistic, gene name, or citation to make a sentence flow.
