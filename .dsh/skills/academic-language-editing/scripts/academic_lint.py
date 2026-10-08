#!/usr/bin/env python3
"""Rule-based academic English linter.

Offline, dependency-free (python-docx optional for .docx input).
Treats every hit as a question to review, not a verdict.

Usage:
  academic_lint.py PATH [PATH ...] [--format text|json] [--out FILE]
                          [--severity high|medium|low] [--max-words N]
                          [--only RULE[,RULE]] [--ignore RULE[,RULE]]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Rule:
    rid: str
    severity: str
    pattern: str
    message: str
    suggestion: str = ""
    flags: int = re.IGNORECASE | re.MULTILINE
    kind: str = "regex"  # regex | line


RULES: list[Rule] = [
    # ---- grammar / agreement -------------------------------------------------
    Rule("GRM001", "high", r"\b(?:data|criteria|phenomena|analyses|indices|matrices|spectra)\s+(?:is|was|has)\b",
         "Plural Latin/Greek form used with a singular verb.", "data are / criteria are / analyses are"),
    Rule("GRM002", "high", r"\b(?:a|an)\s+(?:analyses|data|criteria|hypotheses|phenomena)\b",
         "Singular article with a plural noun.", "an analysis / a hypothesis"),
    Rule("GRM003", "high", r"\bcomprise[sd]?\s+of\b", "'comprise of' is not idiomatic.",
         "use 'comprise' or 'consist of' / 'be composed of'"),
    Rule("GRM004", "high", r"\b(?:is|are|was|were)\n?\s?(?:comprised of|consisted of)\b",
         "Check the verb form for the intended meaning.", "consists of / comprises"),
    Rule("GRM005", "high", r"\bthe\s+(?:amount|number)\s+of\s+\w+\s+(?:are|were|is|was)\b",
         "Possible agreement error in 'amount/number of' clause.", "match the verb to the head noun"),
    Rule("GRM006", "high", r"\b(?:e\.g|i\.e|et al|vs)\.?(?!\s*[,\)\]])",
         "Missing comma after a Latin abbreviation.", "e.g., / i.e., / et al., / vs."),
    Rule("GRM007", "high", r"\b(?:different|similar|identical|comparable)\s+than\b",
         "'different than' is non-standard in formal writing.", "different from / similar to"),
    Rule("GRM008", "high", r"\b(?:less|fewer)\s+(?:amount|number)\s+of\b",
         "Mismatched quantifier.", "fewer + count nouns; less + mass nouns"),
    Rule("GRM009", "high", r"\b(?:can|could|may|might|must|should|will|would)\s+\w+ed\b",
         "Possible modal + past-tense error (e.g. 'can observed').", "use the base form after a modal"),
    Rule("GRM010", "high", r"\b(?:we|this study|the results)\s+(?:is|are|was|were)\s+(?:shown|found|observed)\b",
         "Check passive/agreement construction.", "we show / the results show"),
    Rule("GRM011", "high", r"\b(?:one of the|some of the)\s+\w+\s+(?:that|which)\s+\w+s\b",
         "Possible number agreement in a relative clause.", "verify singular/plural agreement"),
    Rule("GRM012", "high", r"\b(?:this|these|those)\s+(?:results?|data|findings?)\s+(?:suggest|suggests)\b",
         "Check subject-verb agreement with a demonstrative.", "these results suggest / this result suggests"),

    # ---- hedging and overclaiming -------------------------------------------
    Rule("HDG001", "high", r"\b(?:proves?|disproves?)\b(?!\s+that\s+the\s+former)",
         "Overclaim: empirical work demonstrates, it does not prove.", "demonstrate / show / strongly indicate"),
    Rule("HDG002", "high", r"\b(?:obviously|clearly|undoubtedly|certainly|of course|as is well known)\b",
         "Assertion of obviousness adds nothing and invites disagreement.", "delete, or supply the evidence"),
    Rule("HDG003", "medium", r"\b(?:may|might|could|possibly|perhaps)\s+(?:possibly|perhaps|potentially)\b",
         "Stacked hedges weaken the sentence.", "keep exactly one hedge"),
    Rule("HDG004", "medium", r"\b(?:we believe|we feel|we think|in our opinion|it seems to us)\b",
         "Opinion framing where evidence should speak.", "state the claim, then the evidence"),
    Rule("HDG005", "medium", r"\b(?:it is (?:important|interesting|worth)\s+(?:to note|noting)|it should be (?:noted|emphasi[sz]ed)|note that)\b",
         "Throat-clearing phrase; the content follows it anyway.", "delete the frame, keep the content"),
    Rule("HDG006", "medium", r"\b(?:very|quite|rather|somewhat|relatively|fairly|really|extremely)\s+\w+",
         "Empty intensifier.", "delete, or replace with a quantity"),
    Rule("HDG007", "high", r"\b(?:affects?|causes?|leads? to|results? in|due to)\b(?=[^.]{0,80}\b(?:correlat|associat))",
         "Causal language near correlational evidence.", "use 'is associated with' unless causation is established"),
    Rule("HDG008", "medium", r"\b(?:novel|first ever|unprecedented|paradigm[- ]shifting|groundbreaking|revolutionary)\b",
         "Self-assessed novelty is judged by the reader, not asserted.", "describe what is new, let the claim carry it"),

    # ---- word choice / diction ----------------------------------------------
    Rule("DIC001", "medium", r"\b(?:utilize[sd]?|utilization|utilization of)\b", "'utilize' for 'use'.",
         "use / employ"),
    Rule("DIC002", "medium", r"\b(?:in order to)\b", "Wordy infinitive marker.", "to"),
    Rule("DIC003", "medium", r"\b(?:due to the fact that|owing to the fact that|for the reason that)\b",
         "Wordy causal phrase.", "because / since"),
    Rule("DIC004", "medium", r"\b(?:a large number of|a great many|a majority of)\b", "Vague quantifier.",
         "give the count or proportion"),
    Rule("DIC005", "medium", r"\b(?:prior to)\b", "Formal padding.", "before"),
    Rule("DIC006", "medium", r"\b(?:subsequent to)\b", "Formal padding.", "after"),
    Rule("DIC007", "medium", r"\b(?:in the event that)\b", "Wordy conditional.", "if"),
    Rule("DIC008", "medium", r"\b(?:with regard to|with respect to|in terms of|when it comes to)\b",
         "Wordy prepositional frame.", "regarding / for / in"),
    Rule("DIC009", "medium", r"\b(?:a variety of|a range of|various)\b", "Vague scope.",
         "specify the categories or count"),
    Rule("DIC010", "low", r"\b(?:etc\.|and so on|and so forth)\b", "Open-ended list in formal prose.",
         "complete the list or state the inclusion rule"),
    Rule("DIC011", "medium", r"\b(?:the fact that)\b", "Nominalized clause.", "that"),
    Rule("DIC012", "medium", r"\b(?:plays? an? (?:important|key|critical|significant) role)\b",
         "Vague importance claim.", "state what the factor does mechanistically"),
    Rule("DIC013", "medium", r"\b(?:is able to|are able to|was able to|were able to)\b", "Wordy modal.",
         "can / could"),
    Rule("DIC014", "medium", r"\b(?:conducted an experiment|performed an experiment)\b",
         "Vague method statement.", "name the measurement or assay"),
    Rule("DIC015", "low", r"\b(?:obtain|obtained|obtaining)\b(?=[^.]{0,40}\b(?:result|data|value))",
         "Check whether a more precise verb applies.", "measure / record / derive"),

    # ---- AI-flavoured and informal register ---------------------------------
    Rule("REG001", "high", r"\b(?:delve[sd]? into|delving into)\b", "AI-flavoured phrasing.", "examine / investigate"),
    Rule("REG002", "high", r"\b(?:in today's rapidly evolving|ever-evolving|in the realm of|tapestry|landscape of)\b",
         "AI-flavoured or promotional phrasing.", "state the field and time plainly"),
    Rule("REG003", "high", r"\b(?:it is worth noting that|it should be emphasized that|needless to say)\b",
         "Filler frame.", "delete"),
    Rule("REG004", "high", r"\b(?:a testament to|stands as a|serves as a testament)\b",
         "AI-flavoured promotional phrasing.", "state the evidence"),
    Rule("REG005", "medium", r"\b(?:notably|importantly|significantly)\s*,", "Sentence-opening filler.",
         "delete, or explain why it matters"),
    Rule("REG006", "high", r"\b(?:can't|don't|doesn't|isn't|wasn't|won't|it's|we're|didn't|hasn't|aren't)\b",
         "Contraction in formal prose.", "expand the contraction"),
    Rule("REG007", "medium", r"\b(?:a lot of|lots of|pretty|huge|big|great deal)\b", "Informal register.",
         "use a measured quantifier"),
    Rule("REG008", "high", r"[!]", "Exclamation mark in academic prose.", "delete"),
    Rule("REG009", "medium", r"\b(?:unfortunately|surprisingly|interestingly|remarkably)\s*,",
         "Editorializing adverb.", "report the fact and let the reader react"),
    Rule("REG010", "medium", r"\b(?:I think|I believe|my opinion|in my view)\b",
         "First-person opinion in a scientific manuscript.", "use impersonal evidence language"),

    # ---- nominalization / verbosity -----------------------------------------
    Rule("NOM001", "medium", r"\b(?:perform(?:ed|s)?|conduct(?:ed|s)?|carry out|carr(?:y|ied) out)\s+(?:an?\s+)?(?:analysis|analyses|measurement|measurements|evaluation|assessment|investigation|comparison|calculation|simulation)\b",
         "Nominalization: a verb is hiding in the noun.", "analyse / measure / evaluate / compare / calculate / simulate"),
    Rule("NOM002", "medium", r"\b(?:the\s+)?(?:implementation|utilization|quantification|identification|characterization|determination|estimation|validation|optimization|demonstration)\s+of\b",
         "Nominalization: prefer the verb form.", "implement / quantify / identify / characterise / determine"),
    Rule("NOM003", "medium", r"\b(?:make|makes|made)\s+(?:a\s+)?(?:decision|comparison|contribution|assumption|measurement)\b",
         "Light verb + noun.", "decide / compare / contribute / assume / measure"),
    Rule("NOM004", "medium", r"\b(?:is|are|was|were)\s+(?:in\s+)?(?:agreement|accordance)\s+with\b",
         "Wordy agreement construction.", "agree with / match / be consistent with"),
    Rule("NOM005", "medium", r"\b(?:has|have|had)\s+the\s+(?:ability|capacity|potential)\s+to\b",
         "Wordy modal.", "can / could / may"),

    # ---- typography, units, statistics --------------------------------------
    Rule("TYP001", "high", r"\d\s*(?:mL|ml|µL|uL|L|kg|g|mg|µg|ug|nm|µm|um|mm|cm|m|km|s|min|h|Hz|kHz|MHz|GHz|V|mV|mA|A|W|kW|Pa|kPa|MPa|kDa|Da|M|mM|µM|uM|nM|pM|°C|K|mol|mmol|rpm|bps|kb|Mb|Gb|GB|MB|kB|ms|ns|ps|fs)\b",
         "Missing space between number and unit.", "5 mL, 37 °C, 3 h (non-breaking space in print)"),
    Rule("TYP002", "high", r"\b(?:uL|ug|um|uM|uA|us)\b(?=\s|\d|$)", "ASCII substitute for a micro sign.",
         "µL, µg, µm, µM (U+00B5)"),
    Rule("TYP003", "medium", r"\b\d+\s*[xX]\s*\d+\b", "Letter x used as a multiplication sign.",
         "× (U+00D7)"),
    Rule("TYP004", "high", r"\bP\s*[<>=]\s*0?\.\d+", "Unitalicised P value.", "italic *P*"),
    Rule("TYP005", "high", r"\bp\s*[<>=]\s*0?\.\d+", "Lowercase p for a P value.", "italic uppercase *P*"),
    Rule("TYP006", "medium", r"\b(?:SE|SD|SEM)\b(?=[\s,;]?\d)", "Define the error term once at first use.",
         "state mean ± SD or mean ± SEM explicitly"),
    Rule("TYP007", "medium", r"\bp\s*<\s*0\.05\b", "Check the journal's P-value reporting convention.",
         "report the exact value where permitted"),
    Rule("TYP008", "low", r"\b\d+\.\d+\s*±\s*\d+\.\d+\b", "Confirm the error term and its precision.",
         "match decimal places to the measurement precision"),
    Rule("TYP009", "medium", r"[^\x00-\x7F]?[–—][^\x00-\x7F]", "Check dash usage and spacing.",
         "en dash for ranges; em dash unspaced for interruption"),
    Rule("TYP010", "medium", r"\b\d{1,3}(?:,\d{3})+\b", "Thousands separators vary by journal.",
         "confirm the venue's convention (comma vs thin space)"),
    Rule("TYP011", "low", r"\b(?:Fig\.|Figure)\s*\d+\s*(?:and|,)\s*(?:Fig\.|Figure)?\s*\d+",
         "Check figure-citation formatting consistency.", "Fig. 1a, b or Figure 1A and B per the venue"),
    Rule("TYP012", "high", r"\b(?:C°|° C|degrees C)\b", "Incorrect degree-Celsius form.", "°C"),
    Rule("TYP013", "medium", r"\b(?:%|percent)\s*(?:of)?\b(?=[^.]{0,30}\b\d)", "Check percentage vs proportion wording.",
         "use 'percentage points' for differences in percentages"),
    Rule("TYP014", "low", r"\bet al\b(?!\.)", "Missing full stop after 'al'.", "et al."),
    Rule("TYP015", "low", r"  +", "Multiple consecutive spaces.", "single space (or a non-breaking space in print)"),

    # ---- cohesion and structure signals -------------------------------------
    Rule("COH001", "low", r"\b(?:In conclusion|To sum up|In summary)\s*,", "Signposting in a manuscript section.",
         "let the argument close itself in a journal article"),
    Rule("COH002", "medium", r"^\s*(?:Introduction|Results|Discussion|Methods)\s*:", "Heading style inconsistency.",
         "use the journal's heading conventions"),
    Rule("COH003", "low", r"\b(?:As mentioned (?:above|before|earlier)|As stated (?:above|previously))\b",
         "Backward reference instead of a forward-moving argument.", "repeat the essential point briefly"),
    Rule("COH004", "low", r"\b(?:It is well known that|It has long been established that)\b",
         "Claim of consensus without a citation.", "cite the source or drop the claim"),
    Rule("COH005", "medium", r"\bthis\s+(?:is|was|means|suggests|indicates)\b",
         "Ambiguous 'this' without a noun.", "name the referent: 'this reduction…'"),
    Rule("COH006", "medium", r"\b(?:respectively)\b", "Check that the order of items matches the order of values.",
         "name the pairing explicitly when the lists are long"),
]

RULE_INDEX = {r.rid: r for r in RULES}


def _force_utf8_console() -> None:
    """Windows consoles default to a legacy code page; reports contain Unicode."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        try:
            from docx import Document  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise SystemExit(f"python-docx is required to lint .docx files: {exc}")
        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append("\t".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    if suffix in {".pdf"}:
        raise SystemExit("PDF input is not supported: extract the text or supply the source file.")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return text.lstrip("\ufeff")


def split_sentences(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for m in re.finditer(r"[^.!?\n]+[.!?]*", text):
        s = m.group(0).strip()
        if not s:
            continue
        if re.fullmatch(r"[\d\W]+", s):
            continue
        out.append((text[: m.start()].count("\n") + 1, s))
    return out


def lint(text: str, max_words: int, ignore: set[str], only: set[str]) -> list[dict]:
    findings: list[dict] = []
    lines = text.splitlines()

    for rule in RULES:
        if rule.rid in ignore:
            continue
        if only and rule.rid not in only:
            continue
        if rule.kind == "line":
            continue
        for m in re.finditer(rule.pattern, text, rule.flags):
            start = m.start()
            line_no = text.count("\n", 0, start) + 1
            col = start - (text.rfind("\n", 0, start) + 1) + 1
            snippet = m.group(0)
            findings.append({
                "rule": rule.rid,
                "severity": rule.severity,
                "line": line_no,
                "column": col,
                "match": snippet[:120],
                "message": rule.message,
                "suggestion": rule.suggestion,
                "context": (lines[line_no - 1] if 0 < line_no <= len(lines) else "")[:240],
            })

    # sentence length: high above 1.5x budget, medium above budget
    for line_no, sentence in split_sentences(text):
        words = re.findall(r"[\w'’\-]+", sentence)
        n = len(words)
        if n <= max_words:
            continue
        severity = "high" if n > int(max_words * 1.5) else "medium"
        findings.append({
            "rule": "LEN001",
            "severity": severity,
            "line": line_no,
            "column": 1,
            "match": " ".join(words[:14]) + ("…" if n > 14 else ""),
            "message": f"Sentence of {n} words exceeds the {max_words}-word budget.",
            "suggestion": "split at the first independent clause boundary",
            "context": sentence[:240],
        })

    # repeated sentence openings (a real cohesion smell)
    openings: dict[str, int] = {}
    for line_no, sentence in split_sentences(text):
        first = re.findall(r"[\w'’\-]+", sentence)
        if not first:
            continue
        key = " ".join(w.lower() for w in first[:3])
        openings[key] = openings.get(key, 0) + 1
    for key, count in openings.items():
        if count >= 4:
            findings.append({
                "rule": "COH007",
                "severity": "low",
                "line": 1,
                "column": 1,
                "match": key,
                "message": f"{count} sentences open with the same word pattern.",
                "suggestion": "vary the openings or merge the sentences",
                "context": "",
            })

    findings.sort(key=lambda f: (SEV_ORDER[f["severity"]], f["line"], f["column"]))
    return findings


def format_text(findings: list[dict], path: Path, stats: dict) -> str:
    lines = [f"# {path}", f"words={stats['words']} sentences={stats['sentences']} "
             f"mean_sentence_length={stats['mean_sentence_length']} findings={len(findings)}", ""]
    if not findings:
        lines.append("No rule hits. This is not a clean bill of health — the linter is mechanical.")
        return "\n".join(lines)
    by_rule: dict[str, int] = {}
    for f in findings:
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
    lines.append("counts: " + ", ".join(f"{k}={v}" for k, v in sorted(by_rule.items())))
    lines.append("")
    current = None
    for f in findings:
        if f["severity"] != current:
            current = f["severity"]
            lines.append(f"== {current.upper()} ==")
        lines.append(f"  L{f['line']}:{f['column']} [{f['rule']}] {f['message']}")
        lines.append(f"      hit: {f['match']!r}")
        if f["suggestion"]:
            lines.append(f"      fix: {f['suggestion']}")
        if f["context"]:
            lines.append(f"      ctx: {f['context']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _force_utf8_console()
    ap = argparse.ArgumentParser(description="Rule-based academic English linter (offline).")
    ap.add_argument("paths", nargs="*", help="files to lint (.txt .md .tex .docx)")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--out", help="write the report to this file instead of stdout")
    ap.add_argument("--severity", choices=["high", "medium", "low"], default="low",
                    help="minimum severity to report (default: low)")
    ap.add_argument("--max-words", type=int, default=30, help="sentence word budget (default 30)")
    ap.add_argument("--only", default="", help="comma-separated rule ids to keep")
    ap.add_argument("--ignore", default="", help="comma-separated rule ids to drop")
    ap.add_argument("--list-rules", action="store_true", help="print the rule catalogue and exit")
    args = ap.parse_args(argv)

    if args.list_rules:
        for r in RULES:
            print(f"{r.rid}\t{r.severity}\t{r.message}\t{r.suggestion}")
        return 0

    if not args.paths:
        ap.error("at least one file is required unless --list-rules is used")

    ignore = {s.strip() for s in args.ignore.split(",") if s.strip()}
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    unknown = (ignore | only) - set(RULE_INDEX) - {"LEN001", "COH007"}
    if unknown:
        print(f"warning: unknown rule ids ignored: {sorted(unknown)}", file=sys.stderr)

    results = []
    total = 0
    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            print(f"warning: not a file: {path}", file=sys.stderr)
            continue
        text = read_text(path)
        findings = [f for f in lint(text, args.max_words, ignore, only)
                    if SEV_ORDER[f["severity"]] <= SEV_ORDER[args.severity]]
        words = re.findall(r"\S+", text)
        sentences = split_sentences(text)
        stats = {
            "words": len(words),
            "sentences": len(sentences),
            "mean_sentence_length": round(
                sum(len(re.findall(r"[\w'’\-]+", s)) for _, s in sentences) / max(1, len(sentences)), 1),
            "high": sum(1 for f in findings if f["severity"] == "high"),
            "medium": sum(1 for f in findings if f["severity"] == "medium"),
            "low": sum(1 for f in findings if f["severity"] == "low"),
        }
        total += stats["high"]
        results.append({"file": str(path), "stats": stats, "findings": findings})

    if args.format == "json":
        report = json.dumps(results, indent=2, ensure_ascii=False)
    else:
        report = "\n\n".join(format_text(r["findings"], Path(r["file"]), r["stats"]) for r in results)

    if args.out:
        Path(args.out).write_text(report + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({len(results)} file(s), {total} high-severity finding(s))")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
