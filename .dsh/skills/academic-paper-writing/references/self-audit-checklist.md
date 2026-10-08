# Self-audit checklist

Run this before spending effort on language. Structural problems cannot be fixed by rewriting
sentences, and a manuscript with a broken claim will be rejected regardless of its prose.

## Stage 1 — the claim (blocking)

- [ ] The paper's single claim is written in one sentence, with the evidence and the conditions.
- [ ] Every Results subsection either supports that claim or is deleted.
- [ ] The claim's strength matches the design (correlation report ≠ causal claim).
- [ ] The title states the claim.
- [ ] The abstract's final sentence and the Discussion's first paragraph agree with the claim.

## Stage 2 — advance over prior work (blocking)

- [ ] The closest published work is named and cited in the Introduction.
- [ ] The paper states what it does that the closest work did not, in one sentence.
- [ ] The comparison is quantitative where a quantitative comparison is possible.
- [ ] Any result contradicting prior work is addressed explicitly in the Discussion.

## Stage 3 — evidence adequacy (blocking)

- [ ] Each claim has a control that rules out the trivial explanation.
- [ ] n is stated per experiment and the unit of analysis is unambiguous (animal, cell, technical
      replicate).
- [ ] Statistics are reported with the test, df, effect size or CI, and an exact *P* where the
      journal allows it.
- [ ] Error bars are defined once, and are SD or SEM as stated, not both.
- [ ] The key result replicates, either internally or across an independent cohort/condition.

## Stage 4 — architecture

- [ ] Hourglass holds: Introduction narrows, Results stay concrete, Discussion widens only at the end.
- [ ] The Introduction's final paragraph promises exactly what Results deliver.
- [ ] Results subheadings are claims, not labels.
- [ ] Results are in causal order, not chronological acquisition order.
- [ ] The Discussion has an explicit limitations paragraph.
- [ ] No paragraph repeats the function of another (search for the same sentence in Introduction and
      Discussion).

## Stage 5 — sections complete

- [ ] Title, abstract, main text, references, figure legends, methods, availability statements,
      contributions, competing interests, funding, ethics/registration.
- [ ] Abstract respects the venue's word limit and does not cite.
- [ ] Display items match the number and format the venue allows.
- [ ] Every figure and table is cited in order in the text.
- [ ] Supplementary items are numbered and each is cited.

## Stage 6 — reproducibility

- [ ] Data availability names a repository and an accession or DOI.
- [ ] Code availability names a repository with a version tag or commit hash and a licence.
- [ ] Materials, antibodies (with RRID), cell lines, software versions and reference builds are
      identifiable.
- [ ] Reporting checklist completed and consistent with the manuscript, where one applies.

## Stage 7 — integrity

- [ ] No figure has been processed in a way that changes the interpretation.
- [ ] Every quantitative claim in the abstract and Discussion traces to a reported result.
- [ ] Every citation supports the sentence it is attached to.
- [ ] No image panel duplicates another panel without being declared.
- [ ] Authorship, contributions and conflicts are accurate.

## Reporting the audit

Deliver findings as a table ordered by severity, with the location of each problem:

| # | Severity | Location | Problem | Required fix |
|---|---|---|---|---|
| 1 | blocking | Abstract, sentence 2 | Causal claim from correlational data | Downgrade to "is associated with" |
| 2 | major | Results 3.2 | No control for batch effect | Add control or move claim to limitations |
| 3 | minor | Discussion ¶4 | No limitations paragraph | Add one paragraph |

Separate *what the science must fix* from *what the writing can fix*. Say plainly when a problem
requires new experiments rather than editing.
