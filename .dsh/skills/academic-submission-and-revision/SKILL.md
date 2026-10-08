---
name: academic-submission-and-revision
description: "Prepare and defend the parts of a submission that surround the manuscript: cover letters, significance statements, highlights, graphical-abstract briefs, reporting checklists (CONSORT/STROBE/PRISMA/ARRIVE), data and code availability statements, author contribution and conflict statements, suggested and opposed reviewers, and point-by-point responses to reviewers with tracked revision strategy. Use when submitting, resubmitting, or answering referee reports."
whenToUse: "Load for cover letters, significance statements, highlights, checklists, availability statements, rebuttal letters, or revision planning."
---

# Submission packages and revision

The manuscript itself is governed by `academic-paper-writing`; language by
`academic-language-editing`. This skill covers everything else in the submission, and the strategy
for surviving peer review.

## Where a paper is actually rejected

Rank the causes honestly when a user asks why a paper was rejected, and fix in this order:

1. **Claim not supported by evidence** at the strength asserted. Fix by downgrading the claim, not
   by adding adjectives.
2. **Insufficient advance over the closest prior work** — usually a missing, weak, or unstated
   comparison. Fix by making the comparison quantitative and explicit.
3. **Missing control, replication, or generalisation** that the conclusion requires. This is real
   work; say so rather than arguing around it.
4. **Fit and scope** for the journal. Fix by choosing a different venue, not by inflating claims.
5. **Presentation** (structure, figures, language). Fix last, because it is cheapest.

## Cover letter

Four short paragraphs, one page maximum:

1. **One paragraph, no flattery**: title, manuscript type, and the finding in two sentences a
   non-specialist editor can repeat.
2. **Why this journal**: the specific scope, audience, or recent paper this work extends or
   contradicts. Generic praise ("your journal's high impact") damages credibility.
3. **Why it matters now**: the advance over the closest published work, named and cited.
4. **Statements**: originality, no concurrent submission, all authors approved, suggested/opposed
   reviewers if permitted, and any conflict or ethics declaration.

Rules: no invented reviewer names, no claims of novelty you cannot source, no more than the
journal's page limit, and never repeat the abstract verbatim — the editor reads both.

## Significance statement / highlights / graphical abstract

- **Significance statement (PNAS-style)**: a standalone argument for a non-specialist. Structure:
  the problem in plain language → what was unknown → what was found → why it changes practice or
  understanding. No citations, no jargon that a neighbouring field would not know, no restating of
  the abstract.
- **Highlights (Cell-style)**: 3–4 bullets, each ≤ 85 characters, each a finding, not a topic.
  Format: result, not method. No trailing full stops if the journal's examples omit them.
- **Graphical abstract brief**: describe the visual narrative as panels (input → mechanism →
  output) with the single message, then build it with the `publication-figures` skill. Text in the
  graphic should be limited to the claim, not a paragraph.

## Reporting checklists

Identify the study design first, then apply exactly one primary checklist:

| Design | Checklist |
|---|---|
| Randomised trial | CONSORT (+ extension: cluster, pilot, non-inferiority) |
| Observational cohort/case-control | STROBE |
| Systematic review / meta-analysis | PRISMA (+ PRISMA-DTA, -ScR, -IPD as applicable) |
| Animal study | ARRIVE |
| Diagnostic accuracy | STARD |
| Case report | CARE |
| Qualitative | COREQ / SRQR |
| Quality improvement | SQUIRE |

Fill the checklist from the manuscript, not from memory. Every "yes" must point at a page, section,
or supplementary item. Any "no" or "not applicable" is stated in the cover letter or the manuscript
itself, because reviewers check.

## Mandatory statements

- **Data availability**: name the repository and accession/DOI for every dataset. "Available from the
  corresponding author on request" is now rejected by most top-tier journals for the underlying
  data; if the user insists, flag it as a submission risk. State what is restricted (human data,
  participant privacy, third-party licence) and how access is granted.
- **Code availability**: repository URL, version tag or commit hash, licence, environment file.
  A bare GitHub link without a version is not reproducible.
- **Materials availability** where the journal requires it.
- **Author contributions** using the journal's taxonomy (CRediT terms where accepted); every author
  must have a contribution that is not "supervision" alone in a paper with many authors.
- **Competing interests**: state "The authors declare no competing interests" or list them; never
  leave the section blank.
- **Ethics, consent, and registration**: approval body and reference number, informed-consent
  statement, trial registration ID in the abstract if the journal requires it, animal welfare
  approval and ARRIVE reference.
- **Funding**: grant numbers, and the funder's role if the funder had one.

## Revision and rebuttal

- **Never argue with a factual point.** If the reviewer is right, fix it and say so in one sentence:
  "We agree; the text now reads… (lines X–Y)."
- Structure each response as: *reviewer's point, quoted verbatim* → *our response* → *exact change
  and location*. One block per point, in the reviewer's numbering, with no merging of points.
- **Disagreement protocol**: acknowledge the concern, give the evidence, state the limit of the
  evidence, and say precisely what the manuscript now says instead. Concede the part you cannot
  defend. Never concede a result you can defend just to end the exchange.
- **Track changes**: produce a marked-up version and a clean version. Report the mapping
  (reviewer point → file → section → lines) as a table, and keep a running change log across
  revision rounds.
- **New experiments**: state what was done, why it addresses the concern, and what it shows,
  including when it does not resolve the concern.
- **Escalation**: if a reviewer asks for work outside the paper's scope, offer the alternative
  (added discussion, softened claim, moved claim to limitations) and let the editor decide.
- **Resubmission to a new journal**: do not recycle the same letter. Rewrite the fit paragraph and
  re-derive the claim strength from the new venue's audience.
