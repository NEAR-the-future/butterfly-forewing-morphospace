---
name: academic-citations-and-references
description: "Build, verify, and normalise scholarly references and in-text citations: citation-style mechanics (numeric-superscript, numbered, author-date), bibliography field completeness, orphan and uncited-reference detection, duplicate and retracted-item screening, DOI/accession hygiene, and citation-accuracy checks against the claim being supported. Ships an offline reference auditor (scripts/ref_audit.py) for .bib, plain-text, Markdown, LaTeX, and DOCX bibliographies. Use when formatting a reference list, checking citation consistency, or preparing a bibliography for submission."
whenToUse: "Load whenever a manuscript, response letter, or grant contains citations or a reference list that must be checked, reformatted, or verified."
---

# Citations and references

Never invent a reference. This skill's first law is that an uncited or unverifiable item must be
flagged, not fabricated. You are offline unless the user has a working network: DOI resolution,
PubMed lookups, and retraction-database checks must then be reported as *unverified*, never as
*verified*.

## Pipeline

1. **Extract.** Collect the bibliography and every in-text citation marker:
   - `.bib` → parse with `ref_audit.py` or `biber`/`bibtex` tooling from TeX Live.
   - LaTeX → `\cite{...}`, `\citep`, `\citet`, `\ref`, `\label`.
   - DOCX → the `office-docx` skill; fields may be EndNote/Zotero-managed, so never rewrite a
     field-managed bibliography by hand without warning the user that the field code will be stale.
   - Plain text first, then tooling. If the document is a PDF, say that re-extraction loses field
     structure and ask for the source.
2. **Audit mechanically.** Run:
   ```powershell
   & "C:\Users\16240\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" `
     "<skill-dir>\scripts\ref_audit.py" "<manuscript-or-bib>" --format text
   ```
   It reports: uncited references, missing references, numbering gaps and repeats, duplicate keys and
   duplicate DOIs, missing required fields, missing DOIs, preprint markers (`bioRxiv`, `medRxiv`,
   `arXiv`, `Research Square`), retraction/correction markers, and non-consecutive first citations.
3. **Fix order and numbering** to the journal's style (below), then re-run the auditor until
   high-severity findings are zero.
4. **Check content, not just form** — see *Citation accuracy* below. The auditor cannot do this.
5. **Report** unresolved items explicitly as `[REF NEEDED: claim]` or
   `[UNVERIFIED — offline: DOI 10.xxxx/yyy]` in the manuscript so the author sees them.

## Style mechanics

Reference *formats* change; the mechanics below are stable. Confirm the exact pattern against the
target journal's current author guidelines before final submission, and never state a limit as fact
if you have not seen it in the guidelines supplied to you.

- **Numeric superscript (Nature and many Nature-family titles).** In-text: superscript numerals
  after punctuation, in citation order of first appearance (`…has been reported.¹,²`). Reference
  list in the same numeric order — *not* alphabetical. Entry shape: author initials then surname,
  full article title, abbreviated journal title in italics, volume in bold, page range, year.
- **Numbered, non-superscript (Science, Cell-family, most biomedical titles).** Bracketed or
  parenthesised numerals, reference list numbered in citation order; Science-style entries carry
  abbreviated journal name, volume, page, year, and often a DOI.
- **Author-date (many ecology, evolution, and general-science titles).** In-text
  `(Surname & Surname, Year)` or `Surname et al. (Year)`; alphabetical reference list, and the
  *same* surname–year pair must disambiguate with a/b suffixes.
- **Author-count rules differ sharply** (some list all authors, some truncate to N + *et al.*).
  Apply one rule uniformly; the auditor flags inconsistent author counts within a single list.
- **Preprints** are increasingly citable but should be marked as such, and replaced by the
  peer-reviewed version once it exists. Always tell the author which entries are preprints.
- **Datasets, code, and accession numbers** get their own reference type in most current styles:
  repository, identifier, version, and access date. Never fold a dataset into a journal citation.

## Required fields (minimum for a complete entry)

| Type | Required |
|---|---|
| Journal article | Authors, year, title, journal, volume, pages **or** article number, DOI |
| Preprint | Authors, year, title, server, DOI/arXiv ID, version if relevant |
| Book | Authors/editors, year, title, edition, publisher, place |
| Chapter | Authors, year, chapter title, editors, book title, pages, publisher |
| Conference paper | Authors, year, title, proceedings name, pages, DOI if any |
| Dataset/code | Authors or organisation, year, title, repository, version, identifier |
| Web resource | Author or organisation, year, title, URL, access date |

## Citation accuracy (the part that gets papers corrected)

For every in-text citation, the cited work must actually support the sentence:

- **Claim–citation match.** Verify the cited paper's own claim, not its title. A citation to a paper
  that merely mentions a phenomenon does not support a sentence asserting it.
- **Primary over secondary.** Replace "as reviewed in X" chains with the primary source when the
  claim is empirical.
- **Attribution of methods and data.** Cite the original method paper and the specific version or
  implementation actually used; cite data sources with accession identifiers.
- **Self-citation balance.** Report the share of self-citations when the count is unusual; do not
  silently pad or prune.
- **Retracted/corrected works.** Any entry matching a retraction marker in the audit must be
  escalated to the author — citing a retracted paper as support is a serious integrity problem.
- **No citation laundering.** Do not attach citations to sentences they do not support in order to
  satisfy a reviewer; add `[AUTHOR INPUT NEEDED: supporting reference for this claim]` instead.

## Reference-manager interop

- Prefer the author's manager (Zotero/EndNote/Mendeley) as the source of truth; edit the `.bib` or
  the manager's export, not the rendered list, then regenerate.
- If you edit a `.bib`, keep the key stable — changing keys breaks `\cite` commands. Report any key
  you must change.
- For DOCX bibliographies that are field-managed, edit only the plain-text parts and tell the user
  to refresh fields in Word (Ctrl+A, F9); do not overwrite the field codes.
- Preserve the original file; write the audited bibliography to a new path unless the user asks for
  an in-place change.
