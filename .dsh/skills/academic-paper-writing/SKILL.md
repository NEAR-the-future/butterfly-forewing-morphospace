---
name: academic-paper-writing
description: "Write, restructure, and diagnose research manuscripts targeting top-tier journals (Nature and Nature-family, Science, Cell, PNAS, Lancet, NEJM, IEEE/ACM top venues). Covers whole-paper architecture, the rhetorical job of every section and paragraph, abstract/title design, figure-legend logic, and journal-specific format limits. Use when drafting a manuscript, converting a thesis chapter into a paper, restructuring a rejected manuscript, or writing a cover letter / significance statement."
whenToUse: "Load for any task that produces or restructures a full manuscript, abstract, title, introduction, results narrative, discussion, or cover letter aimed at a high-impact journal."
---

# Writing for top-tier journals

This skill carries the *architecture* of a competitive manuscript. Sentence-level grammar and
diction live in `academic-language-editing`; references and citation mechanics live in
`academic-citations-and-references`; submission packages and reviewer responses live in
`academic-submission-and-revision`.

Read `references/journal-conventions.md` before formatting anything for a named journal, and
`references/section-blueprints.md` when you need paragraph-by-paragraph templates.

## Non-negotiable workflow

1. **Fix the one-sentence claim first.** Before writing any section, state the paper's single
   defensible claim in one sentence: *"We show that X causes/explains/enables Y under condition Z,
   evidenced by W."* If you cannot, stop and say so — do not paper over it with prose.
2. **Choose the journal before the voice.** Word limits, abstract style, reference style, and
   figure limits differ enough that drafting blind wastes work. Get the limits from
   `references/journal-conventions.md`; when a number is not recorded there, tell the user it must
   be checked against the live author guidelines rather than guessing.
3. **Draft in the order** Title → Abstract → Figures+legends → Results → Discussion →
   Introduction → Methods. Introduction last is deliberate: it must promise exactly what Results
   delivered.
4. **Audit structure, then language.** Run the architecture check in
   `references/self-audit-checklist.md` before touching wording, and only then hand off to the
   language skill. Rewriting sentences in a section that should not exist is wasted effort.
5. **Preserve the user's scientific content.** You are an editor of structure and clarity, never
   the inventor of findings, numbers, or citations. Anything you cannot support from the user's
   material, mark explicitly as `[AUTHOR INPUT NEEDED: …]`.

## Whole-paper architecture

### The hourglass
Top-tier papers are an hourglass, not a funnel. Introduction starts broad and narrows fast to the
gap; Results stay narrow and concrete; Discussion widens again but only in the last third.
Diagnostic: if the Introduction's last paragraph and the Discussion's first paragraph say the
same thing, the hourglass has collapsed and the paper feels padded.

### The "so what" ladder
Every paragraph must sit at exactly one rung and hand off upward:

```
observation (what we measured)
   → interpretation (what it means mechanistically)
      → implication (why a reader outside the subfield should care)
```

A paragraph that jumps from observation to implication with no interpretation is a reviewer's
favourite target. A paragraph that stops at observation and never interprets reads as a lab report.

### Front-loading
Journal editors and referees skim. Put the decisive result, the mechanism, and the consequence in
the first two sentences of the abstract and the first paragraph of Results. Bury nothing
important past the first screen of text.

### Claim–evidence adjacency
Never let more than one sentence separate a claim from the evidence for it. If a claim needs
evidence that appears three subsections later, either move the evidence or soften the claim.

## Section-level jobs (compressed; full blueprints in references)

| Section | Single job | Most common failure |
|---|---|---|
| Title | Name the finding, not the project | Reads like a grant title ("Towards understanding…") |
| Abstract | Claim + evidence + consequence, no citations | Too much background, vague quantification |
| Introduction | Establish gap in ≤4 paragraphs | Literature review instead of gap statement |
| Results | Evidence in causal order with subheads | Chronological lab-notebook order |
| Discussion | Interpretation, limits, then outlook | Repeats Results; overclaims |
| Methods | Reproducibility, past tense, no hedging | Prose hiding parameters in citations |
| Legends | Self-contained; title sentence then explanation | "See text for details" |

### Title rules
- Declarative titles state the finding ("X drives Y"); topical titles name the subject. Nature-family
  research articles favour declarative or strong topical titles; avoid question titles and colons
  unless the second half adds information rather than restating.
- ≤ 15 words for most journals; never use "novel", "first", "study of", "towards", "insight into".
- No abbreviations that are not universally read by the journal's audience.

### Abstract rules
- One paragraph unless the journal mandates structure (see conventions file).
- Sentence budget: 1 context → 1 gap → 2 evidence (with numbers) → 1 mechanism → 1 consequence.
  Cut context first when over length.
- Every quantitative claim must carry the numbers and error terms exactly as in Results.
- Zero citations, zero undefined abbreviations, zero hedging stacking.

### Introduction rules
- Paragraph 1: the field's consensus, in a form a neighbouring-field reader accepts.
- Paragraph 2: the specific unresolved tension; cite the work that establishes it.
- Paragraph 3 (optional): why existing approaches cannot settle it.
- Final paragraph: *"Here we show…"* — states approach, principal finding, and significance in
  three to four sentences, and matches Results claim-for-claim.

### Results rules
- Subheadings are claims, not labels: "Loss of X reduces Y" beats "Analysis of X".
- Each subsection: question → approach (one sentence) → result with statistics → control/robustness
  → one-sentence transition.
- Report n, the statistical test, the effect size or CI, and the exact p-value convention the
  journal requires.
- Controls and negative results stay in the narrative when they carry weight; move to supplementary
  only when they are truly mechanical.

### Discussion rules
- Open with the answer to the question posed in the Introduction, in two sentences, no new data.
- Then mechanism; then how the result changes the field's working model; then limitations
  (explicitly, in a short dedicated paragraph); then outlook (concrete next experiment, not
  "future work will be needed").
- Limitations are a strength-signal. Omitting them is the fastest way to lose a referee's trust.

## Journal-specific essentials

Full details in `references/journal-conventions.md`. Verify every number against the live author
guidelines before submission — limits change, and this file records typical values, not promises.

- **Nature research articles**: online-first ordering Title → Abstract (unreferenced, ~200 words)
  → main text → References → figure legends → Methods → data/code availability. Short abstract,
  hard word budget for the main text, display items capped low, extended data figures as the
  overflow mechanism.
- **Science**: abstract is a single self-contained paragraph; strong emphasis on a one-sentence
  takeaway for a broad audience.
- **Cell / Cell-family**: structured or summary-led abstract, "Highlights" bullet list, eTOC blurb,
  and a graphical abstract.
- **PNAS**: significance statement is a separate, required, non-specialist paragraph — write it as a
  standalone argument, not a summary.
- **NEJM / Lancet / JAMA-family**: structured abstracts with mandated headings, CONSORT/STROBE/
  PRISMA reporting checklists, and trial-registration identifiers in the abstract.

## Working with the user's material

- Match the requested language; if the user writes in Chinese, produce Chinese unless the target
  journal requires English, and say which you produced.
- Never fabricate a citation, DOI, dataset accession, or numeric value. Insert
  `[CITATION NEEDED: claim]` or `[AUTHOR INPUT NEEDED: …]` instead.
- When editing an existing manuscript, preserve the authors' voice and their claim strength.
  Downgrade overclaims in place and list every downgrade in your report.
- Report changes as a short table: location → problem → fix. Do not silently rewrite wholesale.
- Deliver editable text (Markdown or DOCX via the `office-docx` skill), never a screenshot of text.
