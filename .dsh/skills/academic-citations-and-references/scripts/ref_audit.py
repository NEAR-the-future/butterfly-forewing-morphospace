#!/usr/bin/env python3
"""Offline reference-list and citation auditor.

Checks form and consistency, never content veracity: DOI resolution, retraction
status and PubMed lookups require a network and are reported as UNVERIFIED.

Usage:
  ref_audit.py PATH [PATH ...] [--format text|json] [--out FILE]
                    [--style numeric|author-date|auto] [--expected-min N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, OrderedDict
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# text extraction
# ---------------------------------------------------------------------------

BIB_FIELD_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_\-]*)\s*=\s*", re.MULTILINE)
ENTRY_START_RE = re.compile(r"@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
REF_NUMBER_RE = re.compile(r"^\s*[\[\(]?(\d{1,3})[\]\)]?[.)]?\s+(?=\S)", re.MULTILINE)

PREPRINT_HOSTS = ("biorxiv", "medrxiv", "arxiv", "research square", "preprints.org", "ssrn", "osf.io")
RETRACTION_MARKERS = ("retracted", "retraction", "withdrawn", "expression of concern",
                      "corrigendum", "erratum", "author correction", "has been retracted")
DATASET_MARKERS = ("figshare", "zenodo", "dryad", "genbank", "sra", "geo accession", "pdb",
                   "protein data bank", "arrayexpress", "github.com", "osf.io", "accession")


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        try:
            from docx import Document  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise SystemExit(f"python-docx is required to read .docx files: {exc}")
        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append("\t".join(c.text for c in row.cells))
        return "\n".join(parts)
    if suffix == ".pdf":
        raise SystemExit("PDF input is not supported: supply the .docx/.tex/.bib/.txt source.")
    return path.read_text(encoding="utf-8-sig", errors="replace").lstrip("\ufeff")


# ---------------------------------------------------------------------------
# BibTeX parsing
# ---------------------------------------------------------------------------

def _strip_braces(value: str) -> str:
    value = value.strip()
    if value.startswith("{") and value.endswith("}"):
        value = value[1:-1]
    elif value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    value = re.sub(r"[{}]", "", value)
    value = re.sub(r"\\([a-zA-Z]+)\s*", r"\1", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_bib(text: str) -> list[dict]:
    """Split a .bib into entries by brace depth, then parse fields by commas at depth 1."""
    entries: list[dict] = []
    i = 0
    n = len(text)
    while i < n:
        m = ENTRY_START_RE.search(text, i)
        if not m:
            break
        kind = m.group(1).lower()
        key = m.group(2)
        depth = 1
        j = m.end()
        while j < n and depth > 0:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            j += 1
        body = text[m.end(): j - 1]
        fields: dict[str, str] = {}
        for f in _split_fields(body):
            fm = BIB_FIELD_RE.match(f)
            if not fm:
                continue
            fields[fm.group(1).lower()] = _strip_braces(f[fm.end():].rstrip().rstrip(","))
        entries.append({"kind": kind, "key": key, **fields})
        i = j
    return entries


def _split_fields(body: str) -> list[str]:
    out: list[str] = []
    depth = 0
    buf: list[str] = []
    in_quote = False
    for ch in body:
        if ch == '"' and depth == 0:
            in_quote = not in_quote
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == "," and depth == 0 and not in_quote:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        out.append("".join(buf))
    return out


# ---------------------------------------------------------------------------
# plain / LaTeX reference lists
# ---------------------------------------------------------------------------

def parse_latex_bibliography(text: str) -> list[dict]:
    out: list[dict] = []
    m = re.search(r"\\begin\{thebibliography\}(.*?)\\end\{thebibliography\}", text, re.S)
    if not m:
        return out
    for item in re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]*)\}(.*?)(?=\\bibitem|$)", m.group(1), re.S):
        out.append({"key": item[0].strip(), "raw": _clean_latex(item[1])})
    return out


def _clean_latex(s: str) -> str:
    s = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?", lambda m: m.group(1) or "", s)
    s = s.replace("~", " ").replace("\\&", "&")
    return re.sub(r"\s+", " ", s).strip()


def parse_numbered_list(text: str) -> list[dict]:
    """Entries introduced by a leading numeral: '1. ...' / '[1] ...'."""
    lines = text.splitlines()
    out: list[dict] = []
    current: dict | None = None
    for line in lines:
        m = REF_NUMBER_RE.match(line)
        if m:
            if current:
                current["raw"] = " ".join(current.pop("_buf"))
                out.append(current)
            current = {"number": int(m.group(1)), "_buf": [line[m.end():].strip()]}
        elif current is not None and line.strip():
            current["_buf"].append(line.strip())
    if current:
        current["raw"] = " ".join(current.pop("_buf"))
        out.append(current)
    return out


YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20\d{2}|19\d{2})\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
URL_RE = re.compile(r"https?://\S+")


def parse_bulleted_list(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        s = line.strip()
        if len(s) < 25:
            continue
        if not (DOI_RE.search(s) or YEAR_RE.search(s)):
            continue
        if not re.search(r"[A-Z][a-z]{2,}", s):
            continue
        out.append({"raw": s})
    return out


# ---------------------------------------------------------------------------
# in-text citations
# ---------------------------------------------------------------------------

def find_numeric_citations(text: str) -> list[int]:
    numbers: list[int] = []
    # markdown/plain-text superscript syntax: ^1  ^1,2  ^1-3
    for m in re.finditer(r"\^\{?([\d,\s\-–]+)\}?", text):
        for part in re.split(r"[,\s]+", m.group(1).strip()):
            if not part:
                continue
            rng = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", part)
            if rng:
                a, b = int(rng.group(1)), int(rng.group(2))
                if 0 < b - a < 60:
                    numbers.extend(range(a, b + 1))
                continue
            if part.isdigit():
                numbers.append(int(part))
    for m in re.finditer(r"\[([\d,\s\-–]+)\]|\(([\d,\s\-–]+)\)|[\u2070-\u209F\u00B9\u00B2\u00B3]+", text):
        token = m.group(1) or m.group(2)
        if token is None:
            sup = m.group(0)
            digits = []
            for ch in sup:
                digits.append(str(_SUPERSCRIPT.get(ch, "")))
            joined = "".join(digits)
            numbers.extend(int(d) for d in re.findall(r"\d+", joined) if d)
            continue
        if not re.fullmatch(r"[\d,\s\-–]+", token):
            continue
        for part in re.split(r"[,\s]+", token):
            if not part:
                continue
            rng = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", part)
            if rng:
                a, b = int(rng.group(1)), int(rng.group(2))
                if 0 < b - a < 60:
                    numbers.extend(range(a, b + 1))
                continue
            if part.isdigit():
                numbers.append(int(part))
    return numbers


_SUPERSCRIPT = {"\u2070": "0", "\u00b9": "1", "\u00b2": "2", "\u00b3": "3", "\u2074": "4",
                "\u2075": "5", "\u2076": "6", "\u2077": "7", "\u2078": "8", "\u2079": "9"}


def find_author_date_citations(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"\(([^()]{0,140}?)(\d{4}[a-z]?)\)", text):
        body = m.group(1)
        if not re.search(r"[A-Z][a-z]", body) and "et al" not in body:
            continue
        if re.search(r"[=<>]|Fig|Table|Eq", body):
            continue
        year = m.group(2)
        first = re.split(r"[,;]| et al| & | and ", body.strip())[0].strip()
        if first:
            out.append((first, year))
    return out


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

REQUIRED_BY_KIND = {
    "article": ["author", "title", "journal", "year"],
    "inproceedings": ["author", "title", "booktitle", "year"],
    "conference": ["author", "title", "booktitle", "year"],
    "incollection": ["author", "title", "booktitle", "publisher", "year"],
    "book": ["author", "title", "publisher", "year"],
    "phdthesis": ["author", "title", "school", "year"],
    "mastersthesis": ["author", "title", "school", "year"],
    "techreport": ["author", "title", "institution", "year"],
    "misc": ["author", "title", "year"],
    "software": ["author", "title", "year"],
    "dataset": ["author", "title", "year"],
}


@dataclass
class Audit:
    file: str = ""
    mode: str = ""
    references: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add(self, severity: str, code: str, message: str, detail: str = "") -> None:
        self.findings.append({"severity": severity, "code": code,
                              "message": message, "detail": detail})


def _looks_like_bibliography(text: str) -> bool:
    if re.search(r"\\begin\{thebibliography\}|@article\s*\{|@book\s*\{", text):
        return True
    head = "\n".join(text.splitlines()[:400])
    if re.search(r"^\s*(References|REFERENCES|Bibliography|文献|参考文献)\s*$", head, re.M):
        return True
    if len(parse_numbered_list(text)) >= 5:
        return True
    return False


def _bibliography_section(text: str) -> str:
    m = re.search(r"^\s*(?:#+\s*)?(References|REFERENCES|Bibliography|参考文献|文献)\s*$",
                  text, re.M)
    return text[m.start():] if m else text


def audit_text(text: str, path: Path, style: str, expected_min: int) -> Audit:
    a = Audit(file=str(path))
    bib_entries = parse_bib(text)
    latex_items = parse_latex_bibliography(text)
    numbered = parse_numbered_list(text)
    body = text
    if style == "auto":
        if bib_entries:
            style = "bibtex"
        elif latex_items:
            style = "latex"
        elif numbered:
            style = "numeric"
        else:
            style = "author-date"

    if style == "bibtex":
        a.mode = "bibtex"
        a.references = [{"key": e["key"], "raw": e.get("title", ""), "fields": e} for e in bib_entries]
        keys = [e["key"] for e in bib_entries]
        casefold = Counter(k.lower() for k in keys)
        for k, c in casefold.items():
            if c > 1:
                a.add("high", "DUP_KEY", f"Duplicate BibTeX key (case-insensitive): {k}")
        doidoi = Counter(("10." + e.get("doi", "").split("10.", 1)[-1]).lower()
                         for e in bib_entries if e.get("doi"))
        for d, c in doidoi.items():
            if c > 1 and d != "10.":
                a.add("high", "DUP_DOI", f"Duplicate DOI across entries: {d}")
        for e in bib_entries:
            kind = e["kind"]
            required = REQUIRED_BY_KIND.get(kind, ["author", "title", "year"])
            missing = [f for f in required if not e.get(f)]
            if missing:
                a.add("high", "MISSING_FIELD",
                      f"{kind} entry '{e['key']}' missing: {', '.join(missing)}",
                      e.get("title", ""))
            if kind in {"article", "inproceedings", "conference", "incollection"} and not e.get("doi"):
                a.add("low", "NO_DOI", f"{kind} entry '{e['key']}' has no DOI", e.get("title", ""))
            blob = json.dumps(e, ensure_ascii=False).lower()
            if any(h in blob for h in PREPRINT_HOSTS):
                a.add("medium", "PREPRINT", f"Entry '{e['key']}' is a preprint; cite the journal version once available")
            if any(h in blob for h in RETRACTION_MARKERS):
                a.add("high", "RETRACTION_FLAG",
                      f"Entry '{e['key']}' carries a retraction/correction marker; verify before citing")
            if any(h in blob for h in DATASET_MARKERS) and kind not in {"dataset", "misc", "software"}:
                a.add("low", "DATASET_TYPE", f"Entry '{e['key']}' cites a dataset/repository but is typed '{kind}'")
        cited = set()
        for m in re.finditer(r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear|autocite|parencite|textcite)\*?(?:\[[^\]]*\])*\{([^}]*)\}", text):
            for k in m.group(1).split(","):
                if k.strip():
                    cited.add(k.strip())
        if cited:
            a.stats["cited_keys"] = len(cited)
            for k in sorted(cited - set(keys)):
                a.add("high", "MISSING_REF", f"Cited but not in the bibliography: {k}")
            for k in sorted(set(keys) - cited):
                a.add("high", "UNCITED_REF", f"In the bibliography but never cited: {k}")
        a.stats["entries"] = len(bib_entries)
        return a

    if style == "latex":
        a.mode = "latex"
        a.references = [{"key": i["key"], "raw": i["raw"]} for i in latex_items]
        keys = [i["key"] for i in latex_items]
        cited = set()
        for m in re.finditer(r"\\(?:cite|citep|citet|citealp|autocite|parencite|textcite)\*?(?:\[[^\]]*\])*\{([^}]*)\}", text):
            cited.update(k.strip() for k in m.group(1).split(",") if k.strip())
        for k in sorted(cited - set(keys)):
            a.add("high", "MISSING_REF", f"Cited but not in the bibliography: {k}")
        for k in sorted(set(keys) - cited):
            a.add("high", "UNCITED_REF", f"In the bibliography but never cited: {k}")
        a.stats["entries"] = len(latex_items)
        return a

    # numeric or author-date plain-text bibliography
    body_text = body
    ref_zone = _bibliography_section(text)
    if numbered:
        a.mode = "numeric"
        a.references = [{"number": r["number"], "raw": r["raw"]} for r in numbered]
        nums = [r["number"] for r in numbered]
        a.stats["entries"] = len(nums)
        dupes = [n for n, c in Counter(nums).items() if c > 1]
        for n in sorted(dupes):
            a.add("high", "DUP_NUMBER", f"Reference number {n} appears more than once")
        expected = set(range(1, max(nums) + 1)) if nums else set()
        missing = expected - set(nums)
        for n in sorted(missing):
            a.add("high", "NUMBER_GAP", f"Reference numbering skips {n}")
        body_for_citations = body_text.replace(ref_zone, "", 1) if ref_zone else body_text
        intext = find_numeric_citations(body_for_citations)
        intext_set = set(intext)
        if intext:
            for n in sorted(intext_set - set(nums)):
                a.add("high", "MISSING_REF", f"In-text citation [{n}] has no matching reference entry")
            for n in sorted(set(nums) - intext_set):
                a.add("high", "UNCITED_REF", f"Reference {n} is never cited in the text")
            firsts = [n for n in intext if n in set(nums)]
            seen: list[int] = []
            for n in firsts:
                if n not in seen:
                    seen.append(n)
            if seen and seen != sorted(seen):
                a.add("high", "CITATION_ORDER",
                      "First-citation order is not ascending; numeric styles require citation order",
                      "first appearance: " + ", ".join(str(s) for s in seen[:20]))
            a.stats["in_text_citations"] = len(intext)

    if a.mode in {"", "author-date"} and not bib_entries:
        # author-date or unstructured list
        entries = numbered or parse_bulleted_list(ref_zone)
        if not entries:
            a.add("high", "NO_BIB", "No reference list detected. Supply the bibliography section or a .bib file.")
            return a
        a.mode = a.mode or "author-date"
        a.references = [{"raw": e.get("raw", ""), "number": e.get("number")} for e in entries]
        a.stats["entries"] = len(entries)
        for e in entries:
            raw = e.get("raw", "")
            if not DOI_RE.search(raw) and not URL_RE.search(raw):
                a.add("low", "NO_DOI", "Entry without DOI or URL", raw[:140])
            if any(h in raw.lower() for h in PREPRINT_HOSTS):
                a.add("medium", "PREPRINT", "Preprint in the reference list", raw[:140])
            if any(h in raw.lower() for h in RETRACTION_MARKERS):
                a.add("high", "RETRACTION_FLAG", "Retraction/correction marker present", raw[:140])
            if not YEAR_RE.search(raw):
                a.add("high", "MISSING_YEAR", "Entry without a recognisable year", raw[:140])
            if len(raw) < 40:
                a.add("medium", "SHORT_ENTRY", "Entry looks incomplete", raw[:140])
        intext = find_author_date_citations(body_text)
        a.stats["in_text_citations"] = len(intext)
        if len(entries) < expected_min:
            a.add("low", "FEW_ENTRIES",
                  f"Only {len(entries)} reference entries found (expected at least {expected_min})")
    return a


def normalise_surname(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z]", "", s.lower())


def format_text(audits: list[Audit]) -> str:
    lines: list[str] = []
    sev_order = {"high": 0, "medium": 1, "low": 2}
    for a in audits:
        lines.append(f"# {a.file}")
        lines.append(f"mode={a.mode} references={a.stats.get('entries', 0)} "
                     f"in_text_citations={a.stats.get('in_text_citations', 'n/a')} "
                     f"findings={len(a.findings)}")
        lines.append("NOTE: offline audit — DOI resolution, retraction status and citation "
                     "accuracy are NOT verified.")
        if a.references:
            lines.append("")
            lines.append("reference list:")
            for r in a.references[:200]:
                label = r.get("number", r.get("key", ""))
                lines.append(f"  [{label}] {r.get('raw', '')[:160]}")
        if not a.findings:
            lines.append("")
            lines.append("No structural findings.")
            lines.append("")
            continue
        lines.append("")
        for f in sorted(a.findings, key=lambda x: sev_order[x["severity"]]):
            lines.append(f"  {f['severity'].upper():6} [{f['code']}] {f['message']}")
            if f["detail"]:
                lines.append(f"          {f['detail'][:200]}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Offline reference-list and citation auditor.")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--out")
    ap.add_argument("--style", choices=["auto", "bibtex", "latex", "numeric", "author-date"],
                    default="auto")
    ap.add_argument("--expected-min", type=int, default=0,
                    help="warn when fewer than N reference entries are found")
    args = ap.parse_args(argv)

    audits: list[Audit] = []
    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            print(f"warning: not a file: {path}", file=sys.stderr)
            continue
        text = read_text(path)
        audits.append(audit_text(text, path, args.style, args.expected_min))

    if args.format == "json":
        report = json.dumps([asdict(a) for a in audits], indent=2, ensure_ascii=False)
    else:
        report = format_text(audits)

    if args.out:
        Path(args.out).write_text(report + "\n", encoding="utf-8")
        high = sum(1 for a in audits for f in a.findings if f["severity"] == "high")
        print(f"wrote {args.out} ({len(audits)} file(s), {high} high-severity finding(s))")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
