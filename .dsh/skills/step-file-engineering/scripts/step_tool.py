#!/usr/bin/env python3
"""Dependency-free toolkit for STEP files (ISO 10303-21).

Tier 1 of the step-file-engineering skill: parse, inspect, validate and edit the
entity graph as text. It never evaluates geometry, and it never renumbers entity
ids. Mutating commands write to a new file unless --in-place --force is given
(which also writes a timestamped backup).

Usage:
  step_tool.py summary   FILE [--json]
  step_tool.py validate  FILE [--strict] [--json]
  step_tool.py header    FILE [--json]
  step_tool.py entities  FILE [--type TYPE] [--limit N] [--json]
  step_tool.py get       FILE --id N [--json]
  step_tool.py refs      FILE --id N [--depth K] [--direction out|in|both] [--json]
  step_tool.py bom       FILE [--out FILE.csv] [--json]
  step_tool.py units     FILE [--json]
  step_tool.py rename    FILE --product OLD --to NEW --out FILE2
  step_tool.py replace   FILE --from TEXT --to TEXT --out FILE2
  step_tool.py set-header FILE --field NAME --value TEXT --out FILE2
  step_tool.py strip-metadata FILE --keep FILE_SCHEMA ... --out FILE2
  step_tool.py params    FILE --type TYPE [--out FILE.csv]
  step_tool.py set-params FILE --id N --index I --value V --out FILE2 [--type TYPE]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ENTITY_RE = re.compile(r"^(\s*)#(\d+)\s*=\s*(.*)$", re.S)
HEADER_FIELDS = ("FILE_DESCRIPTION", "FILE_NAME", "FILE_SCHEMA")


# ---------------------------------------------------------------------------
# STEP string encoding
# ---------------------------------------------------------------------------

def decode_step_string(s: str) -> str:
    """Decode a STEP string body: '' quotes, \\X2\\..\\X0\\ UTF-16, \\S\\c, \\X\\hh."""
    out: list[str] = []
    i = 0
    while i < len(s):
        if s.startswith("''", i):
            out.append("'")
            i += 2
            continue
        m = re.match(r"\\X2\\((?:[0-9A-Fa-f]{4})*)\\X0\\", s[i:])
        if m:
            hexs = m.group(1)
            try:
                out.append(bytes.fromhex(hexs).decode("utf-16-be", "replace"))
            except Exception:
                out.append(m.group(0))
            i += m.end()
            continue
        m = re.match(r"\\X\\([0-9A-Fa-f]{2})", s[i:])
        if m:
            out.append(chr(int(m.group(1), 16)))
            i += m.end()
            continue
        m = re.match(r"\\S\\(.)", s[i:])
        if m:
            out.append(chr(ord(m.group(1)) + 128))
            i += m.end()
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def encode_step_string(s: str) -> str:
    """Encode to the STEP string alphabet.

    Printable ASCII stays verbatim, a single quote is doubled, Latin-1 becomes
    \\X\\hh, and every other character is collected into one \\X2\\....\\X0\\
    run per contiguous non-ASCII span (the ISO 10303-21 control directive).
    """
    out: list[str] = []
    hexbuf: list[str] = []

    def flush() -> None:
        if hexbuf:
            out.append("\\X2\\" + "".join(hexbuf) + "\\X0\\")
            hexbuf.clear()

    for ch in s:
        code = ord(ch)
        if 0x20 <= code <= 0x7E:
            flush()
            out.append("''" if ch == "'" else ch)
        elif code <= 0xFF:
            flush()
            out.append(f"\\X\\{code:02X}")
        else:
            hexbuf.append(f"{code:04X}")
    flush()
    return "".join(out)


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

@dataclass
class Entity:
    eid: int
    type: str
    params: list = field(default_factory=list)
    leading_ws: str = ""
    trailing_ws: str = ""
    raw_declaration: str | None = None

    @property
    def is_complex(self) -> bool:
        """A complex instance packs several named types into one entity.

        Its parameters cannot be split by position, so the original declaration
        has to be preserved verbatim on write-back.
        """
        return self.type.startswith("(")


@dataclass
class StepFile:
    path: Path
    text: str
    line_ending: str
    header_fields: dict[str, tuple[str, list[str]]]
    entities: dict[int, Entity]
    order: list[int]
    header_originals: dict[str, str] = field(default_factory=dict)
    header_order: list[str] = field(default_factory=list)
    ends_with_newline: bool = True

    @classmethod
    def load(cls, path: Path) -> "StepFile":
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        # detect the line ending from the raw bytes: reading as text already
        # normalised newlines to "\n", so the text alone cannot tell us
        crlf = raw.count(b"\r\n")
        line_ending = "\r\n" if crlf > raw.count(b"\n") / 2 else "\n"
        ends_with_newline = raw.endswith(b"\n") or raw.endswith(b"\r")
        plain = text.replace("\r\n", "\n")
        if not re.match(r"^\s*ISO-10303-21\s*;", plain):
            raise SystemExit(f"{path} does not start with 'ISO-10303-21;' — not a Part 21 file")
        header_fields: dict[str, tuple[str, list[str]]] = {}
        header_originals: dict[str, str] = {}
        header_order: list[str] = []
        h = re.search(r"HEADER\s*;(.*?)ENDSEC\s*;", plain, re.S)
        if h:
            for m in re.finditer(r"(FILE_DESCRIPTION|FILE_NAME|FILE_SCHEMA)\s*\((.*?)\)\s*;",
                                 h.group(1), re.S):
                name = m.group(1)
                args = split_top_level(m.group(2))
                header_originals[name] = m.group(0)
                header_fields[name] = (m.group(0), args)
                header_order.append(name)
        entities: dict[int, Entity] = {}
        order: list[int] = []
        d = re.search(r"\bDATA\s*;(.*?)\bENDSEC\s*;", plain, re.S)
        body = d.group(1) if d else ""
        for chunk in _split_entities(body):
            m = ENTITY_RE.match(chunk)
            if not m:
                continue
            eid = int(m.group(2))
            rest = m.group(3).strip()
            if not rest.endswith(";"):
                rest += ";"
            core = rest[:-1].strip()
            etype_m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", core)
            etype = etype_m.group(1).upper() if etype_m else "(UNPARSED)"
            params_text = core[etype_m.end():].strip() if etype_m else core
            if etype_m and not (params_text == "" or params_text.startswith("(")):
                # complex instance, e.g. (LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.))
                etype = "(UNPARSED)"
                params_text = core
            if params_text.startswith("(") and params_text.endswith(")"):
                params_text = params_text[1:-1]
            params = split_top_level(params_text) if params_text.strip() else []
            ent = Entity(eid=eid, type=etype, params=params,
                         leading_ws=m.group(1),
                         raw_declaration=f"#{eid}={core};")
            entities[eid] = ent
            order.append(eid)
        return cls(path=path, text=text, line_ending=line_ending,
                   ends_with_newline=ends_with_newline, header_fields=header_fields,
                   entities=entities, order=order, header_originals=header_originals,
                   header_order=header_order)

    # -- rendering ---------------------------------------------------------
    def render_entity(self, ent: Entity) -> str:
        """Unchanged entities keep their original declaration byte for byte;
        edited entities are re-rendered from their parameters."""
        if ent.raw_declaration is not None:
            return ent.raw_declaration
        params = ",".join(ent.params)
        if params:
            return f"#{ent.eid}={ent.type}({params});"
        return f"#{ent.eid}={ent.type};"

    @staticmethod
    def touch(ent: Entity) -> None:
        """Mark an entity as edited so it is re-rendered from its parameters."""
        ent.raw_declaration = None

    def render(self) -> str:
        """Re-render the whole file.

        An unedited header field and every unedited entity keep their original
        text, so an edit produces a diff containing only the intended change.
        """
        def fmt(key: str, args: list[str]) -> str:
            return f"{key}({','.join(args)});"

        lines = ["ISO-10303-21;", "HEADER;"]
        emitted: set[str] = set()
        for key in self.header_order or list(HEADER_FIELDS):
            if key in self.header_fields:
                original, values = self.header_fields[key]
                lines.append(original if original else fmt(key, values))
                emitted.add(key)
        for key in HEADER_FIELDS:
            if key in self.header_fields and key not in emitted:
                original, values = self.header_fields[key]
                lines.append(original if original else fmt(key, values))
        lines.append("ENDSEC;")
        lines.append("DATA;")
        for eid in self.order:
            lines.append(self.render_entity(self.entities[eid]))
        lines.append("ENDSEC;")
        lines.append("END-ISO-10303-21;")
        rendered = self.line_ending.join(lines)
        return rendered + self.line_ending if self.ends_with_newline else rendered

    # -- access ------------------------------------------------------------
    def refs_out(self, eid: int) -> list[int]:
        out = []
        for p in self.entities[eid].params:
            out.extend(_refs_in(p))
        return out

    def refs_in(self, eid: int) -> list[int]:
        return [e.eid for e in self.entities.values() if eid in self.refs_out(e.eid)]

    def by_type(self, etype: str) -> list[Entity]:
        want = etype.upper()
        return [e for e in self.entities.values() if e.type == want]

    def strings(self, ent: Entity) -> list[str]:
        """All top-level string parameters, decoded."""
        out = []
        for p in ent.params:
            if p.startswith("'") and p.endswith("'"):
                out.append(decode_step_string(p[1:-1]))
        return out

    def products(self) -> list[dict]:
        entries = []
        for e in self.by_type("PRODUCT"):
            names = self.strings(e)
            entries.append({"entity": e.eid, "id": names[0] if names else "",
                            "name": names[1] if len(names) > 1 else "",
                            "description": names[2] if len(names) > 2 else ""})
        return entries

    def product_names_for_definition(self, pd_eid: int) -> tuple[str, str]:
        """Resolve a PRODUCT_DEFINITION to its PRODUCT id and name.

        PRODUCT_DEFINITION('design','',#8,#11) references the
        PRODUCT_DEFINITION_FORMATION, which references the PRODUCT, so the
        formation is found by entity type rather than by parameter position.
        """
        pd = self.entities.get(pd_eid)
        if pd is None:
            return "", ""
        formation = None
        for ref in self.refs_out(pd_eid):
            ent = self.entities.get(ref)
            if ent is not None and ent.type in {"PRODUCT_DEFINITION_FORMATION",
                                                "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE"}:
                formation = ent
                break
        if formation is None:
            return "", ""
        for ref in self.refs_out(formation.eid):
            ent = self.entities.get(ref)
            if ent is not None and ent.type == "PRODUCT":
                names = self.strings(ent)
                return ((names[0] if names else ""), (names[1] if len(names) > 1 else ""))
        return "", ""

    def assembly_tree(self) -> list[dict]:
        """Walk NEXT_ASSEMBLY_USAGE_OCCURRENCE relations into a flat tree.

        The relation's parameters carry referenced components before the two
        product definitions, so the definitions are selected by entity type
        rather than by position.
        """
        relations = []
        for e in self.by_type("NEXT_ASSEMBLY_USAGE_OCCURRENCE"):
            refs = [int(p[1:]) for p in e.params if p.startswith("#")]
            defs = [r for r in refs if self.entities.get(r)
                    and self.entities[r].type == "PRODUCT_DEFINITION"]
            names = self.strings(e)
            if len(defs) >= 2:
                relations.append({"entity": e.eid, "parent": defs[-2], "child": defs[-1],
                                  "id": names[0] if names else "",
                                  "name": names[1] if len(names) > 1 else ""})
        children_by_parent: dict[int, list[dict]] = {}
        for r in relations:
            children_by_parent.setdefault(r["parent"], []).append(r)
        roots = {r["parent"] for r in relations} - {r["child"] for r in relations}
        rows: list[dict] = []

        def walk(pd: int, depth: int, path: str) -> None:
            pid, pname = self.product_names_for_definition(pd)
            rows.append({"level": depth, "product_id": pid, "product_name": pname,
                         "product_definition": pd, "path": path or pname,
                         "is_assembly": pd in children_by_parent})
            for child in children_by_parent.get(pd, []):
                walk(child["child"], depth + 1, f"{path or pname} / {child['name'] or child['child']}")

        for root in sorted(roots):
            walk(root, 0, "")
        if not rows:
            for pdef in self.by_type("PRODUCT_DEFINITION"):
                pid, pname = self.product_names_for_definition(pdef.eid)
                if pid:
                    rows.append({"level": 0, "product_id": pid, "product_name": pname,
                                 "product_definition": pdef.eid, "path": pname,
                                 "is_assembly": False})
        return rows

    def units(self) -> list[dict]:
        out = []
        for e in self.by_type("SI_UNIT"):
            out.append(self._si_unit_entry(e.eid, e.params, complex_instance=False))
        for e in self.entities.values():
            if e.type != "(UNPARSED)":
                continue
            raw = ",".join(e.params)
            if "SI_UNIT" not in raw:
                continue
            m = re.search(r"SI_UNIT\s*\(([^)]*)\)", raw)
            args = split_top_level(m.group(1)) if m else []
            out.append(self._si_unit_entry(e.eid, args, complex_instance=True))
        for e in self.by_type("CONVERSION_BASED_UNIT"):
            names = self.strings(e)
            refs = [int(p[1:]) for p in e.params if p.startswith("#")]
            factor = None
            for p in e.params:
                m = re.search(r"LENGTH_MEASURE\(([-0-9.eE+]+)\)", p)
                if m:
                    factor = float(m.group(1))
            out.append({"entity": e.eid, "kind": f"conversion({names[0] if names else '?'})",
                        "prefix": names[0] if names else "", "to_metre": factor,
                        "base_unit": refs[0] if refs else None})
        return out

    @staticmethod
    def _si_unit_entry(eid: int, args: list[str], complex_instance: bool) -> dict:
        args = [a.strip() for a in args]
        prefix = next((a for a in args if a.startswith(".") and a.endswith(".") and
                       a not in {".METRE.", ".RADIAN.", ".STERADIAN."}), "$")
        if ".METRE." in args:
            kind = "length"
            factor = {"$": 1.0, ".MILLI.": 1e-3, ".CENTI.": 1e-2, ".MICRO.": 1e-6,
                      ".DECI.": 1e-1, ".KILO.": 1e3, ".NANO.": 1e-9}.get(prefix, None)
        elif ".RADIAN." in args:
            kind, factor = "plane-angle", None
        elif ".STERADIAN." in args:
            kind, factor = "solid-angle", None
        else:
            kind, factor = "unknown", None
        return {"entity": eid, "kind": kind, "prefix": prefix, "to_metre": factor,
                "complex_instance": complex_instance}

    def validation(self, strict: bool = False) -> list[dict]:
        findings: list[dict] = []

        def add(sev, code, msg, detail=""):
            findings.append({"severity": sev, "code": code, "message": msg, "detail": detail})

        for key in HEADER_FIELDS:
            if key not in self.header_fields:
                add("high" if strict else "medium", "MISSING_HEADER",
                    f"HEADER is missing {key}")
        name_args = self.header_fields.get("FILE_NAME", ("", []))[1]
        if name_args:
            fname = name_args[0].strip("'")
            if Path(fname).name != fname:
                add("medium", "HEADER_PATH", "FILE_NAME contains a directory path",
                    "some importers reject an absolute or relative path")
        ids = list(self.entities)
        if len(ids) != len(set(ids)):
            add("high", "DUP_ID", "duplicate entity ids detected")
        gaps = [i for i in range(1, max(ids) + 1) if i not in self.entities] if ids else []
        if gaps:
            add("low", "ID_GAPS",
                f"{len(gaps)} unused entity id(s) between 1 and {max(ids)}",
                "not an error: ids may legitimately have been deleted")
        dangling: list[str] = []
        referenced: Counter = Counter()
        for e in self.entities.values():
            for r in self.refs_out(e.eid):
                referenced[r] += 1
                if r not in self.entities:
                    dangling.append(f"#{e.eid} ({e.type}) -> #{r}")
        for d in dangling[:40]:
            add("high", "DANGLING_REF", "reference to a non-existent entity", d)
        if len(dangling) > 40:
            add("high", "DANGLING_REF", f"{len(dangling) - 40} further dangling references")
        orphans = [e for e in self.entities.values()
                   if referenced[e.eid] == 0 and e.type not in
                   {"APPLICATION_CONTEXT", "PRODUCT", "PRODUCT_DEFINITION",
                    "PRODUCT_DEFINITION_FORMATION", "SHAPE_REPRESENTATION",
                    "ADVANCED_BREP_SHAPE_REPRESENTATION", "PRODUCT_DEFINITION_SHAPE"}]
        if orphans:
            add("low", "UNREFERENCED",
                f"{len(orphans)} entities are never referenced",
                ", ".join(f"#{o.eid} {o.type}" for o in orphans[:12]))
        if not self.units():
            add("high", "NO_UNITS", "no SI_UNIT or CONVERSION_BASED_UNIT found: units are unspecified")
        if not self.by_type("CARTESIAN_POINT"):
            add("medium", "NO_GEOMETRY", "no CARTESIAN_POINT entities: the file carries no geometry")
        for e in self.entities.values():
            for p in e.params:
                if p.startswith("'") and not p.endswith("'"):
                    add("high", "BAD_STRING", f"unterminated string in #{e.eid}", p[:80])
        return findings


# ---------------------------------------------------------------------------
# lexing helpers
# ---------------------------------------------------------------------------

def split_top_level(text: str) -> list[str]:
    """Split on commas that are not inside parentheses, strings, or enums."""
    parts: list[str] = []
    depth = 0
    in_str = False
    buf: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    buf.append("''")
                    i += 2
                    continue
                in_str = False
            buf.append(ch)
        elif ch == "'":
            in_str = True
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p != ""]


def _split_entities(body: str) -> list[str]:
    """Split the DATA section into ';'-terminated entity chunks, ignoring ';'
    inside strings."""
    chunks: list[str] = []
    buf: list[str] = []
    in_str = False
    for ch in body:
        if in_str:
            buf.append(ch)
            if ch == "'":
                in_str = False
            continue
        if ch == "'":
            in_str = True
            buf.append(ch)
        elif ch == ";":
            buf.append(ch)
            chunk = "".join(buf)
            if chunk.strip():
                chunks.append(chunk)
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        chunks.append("".join(buf))
    return chunks


def _refs_in(param: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r"#(\d+)", param)]


def _clean_header_token(token: str) -> str:
    """Unwrap one header element: 'text' -> text, ('a') -> a, 2;1 -> 2;1."""
    text = token.strip()
    while (text.startswith("(") and text.endswith(")")) or \
          (text.startswith("'") and text.endswith("'") and len(text) >= 2):
        if text.startswith("'") and text.endswith("'"):
            return decode_step_string(text[1:-1])
        text = text[1:-1].strip()
    return decode_step_string(text)


def _aggregate_elements(raw: str) -> list[str]:
    """Split the top level of a STEP aggregate and strip one layer of quotes.

    Header values arrive as `('text')` or `('a','b','c')`; the naive split on
    commas keeps the surrounding parentheses and quotes in the element text.
    """
    text = raw.strip()
    while text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    out = []
    for element in split_top_level(text):
        element = element.strip()
        if element.startswith("'") and element.endswith("'") and len(element) >= 2:
            out.append(decode_step_string(element[1:-1]))
        else:
            out.append(element)
    return out


def find_entity_by_id(model: StepFile, eid: int) -> Entity:
    ent = model.entities.get(eid)
    if ent is None:
        raise SystemExit(f"entity #{eid} not found")
    return ent


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_summary(args) -> int:
    model = StepFile.load(Path(args.file))
    counts = Counter(e.type for e in model.entities.values())
    units = model.units()
    tree = model.assembly_tree()
    name_args = model.header_fields.get("FILE_NAME", ("", []))[1]
    header = {
        "description": [_clean_header_token(t) for t in
                        model.header_fields.get("FILE_DESCRIPTION", ("", []))[1]],
        "file_name": [_clean_header_token(t) for t in name_args],
        "schema": model.header_fields.get("FILE_SCHEMA", ("", []))[1],
    }
    schema_raw = " ".join(header["schema"]).strip("'")
    ap = "unknown"
    if "AUTOMOTIVE_DESIGN" in schema_raw:
        ap = "AP214"
    elif "CONFIG_CONTROL_DESIGN" in schema_raw:
        ap = "AP203"
    elif "MANAGED_MODEL_BASED_3D_ENGINEERING" in schema_raw:
        ap = "AP242"
    else:
        m = re.search(r"10303\s+(\d{2,4})", schema_raw)
        if m:
            ap = f"AP{m.group(1)}"
    summary = {
        "file": str(model.path),
        "bytes": model.path.stat().st_size,
        "line_ending": "CRLF" if model.line_ending == "\r\n" else "LF",
        "schema": {"raw": schema_raw, "protocol": ap},
        "header": {
            "description": header["description"],
            "file_name": header["file_name"],
        },
        "entity_count": len(model.entities),
        "type_counts": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "products": model.products(),
        "assembly": tree,
        "units": units,
        "geometry": {
            "cartesian_points": counts.get("CARTESIAN_POINT", 0),
            "directions": counts.get("DIRECTION", 0),
            "advanced_faces": counts.get("ADVANCED_FACE", 0),
            "manifold_solid_breps": counts.get("MANIFOLD_SOLID_BREP", 0),
            "closed_shells": counts.get("CLOSED_SHELL", 0),
            "has_brep": bool(counts.get("ADVANCED_BREP_SHAPE_REPRESENTATION")
                             or counts.get("MANIFOLD_SOLID_BREP")),
        },
        "presentation": {
            "styled_items": counts.get("STYLED_ITEM", 0),
            "colours": [decode_step_string(model.strings(e)[0]) if model.strings(e) else ""
                        for e in model.by_type("COLOUR_RGB")],
        },
        "confidentiality_markers": _confidential_markers(model),
    }
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"{summary['file']}  {summary['bytes']} bytes  {summary['entity_count']} entities")
        print(f"schema: {ap}  ({schema_raw[:70]})")
        print(f"header: {summary['header']}")
        print(f"units: {json.dumps(units, ensure_ascii=False)}")
        print("products:")
        for p in summary["products"]:
            print(f"  #{p['entity']:5} {p['id']:12} {p['name']}")
        print("assembly tree:")
        for row in tree:
            print(f"  {'  ' * row['level']}[{row['level']}] {row['product_id']}  {row['product_name']}"
                  + ("  (assembly)" if row["is_assembly"] else ""))
        print(f"geometry: {json.dumps(summary['geometry'], ensure_ascii=False)}")
        print(f"presentation: {json.dumps(summary['presentation'], ensure_ascii=False)}")
        if summary["confidentiality_markers"]:
            print(f"possible confidential strings: {summary['confidentiality_markers']}")
        print("top entity types:")
        for t, c in list(summary["type_counts"].items())[:18]:
            print(f"  {t:45} {c}")
    return 0


def _confidential_markers(model: StepFile) -> list[str]:
    hits = []
    pattern = re.compile(r"confidential|proprietary|internal only|do not distribute|"
                         r"secret|password|licence key|license key", re.I)
    for e in model.entities.values():
        for s in model.strings(e):
            if pattern.search(s):
                hits.append(f"#{e.eid} {e.type}: {s[:80]}")
    for key in ("FILE_NAME", "FILE_DESCRIPTION"):
        for s in model.header_fields.get(key, ("", []))[1]:
            plain = decode_step_string(s.strip("'"))
            if pattern.search(plain):
                hits.append(f"HEADER {key}: {plain[:80]}")
    return hits


def cmd_validate(args) -> int:
    model = StepFile.load(Path(args.file))
    findings = model.validation(strict=args.strict)
    high = sum(1 for f in findings if f["severity"] == "high")
    report = {"file": str(model.path), "strict": bool(args.strict),
              "entities": len(model.entities), "findings": findings,
              "high": high, "valid_enough_to_edit": high == 0}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"{report['file']}: {report['entities']} entities, {len(findings)} finding(s), "
              f"{high} high-severity")
        order = {"high": 0, "medium": 1, "low": 2}
        for f in sorted(findings, key=lambda x: order[x["severity"]]):
            print(f"  {f['severity'].upper():6} [{f['code']}] {f['message']}")
            if f["detail"]:
                print(f"         {f['detail'][:160]}")
    return 1 if high else 0


def cmd_header(args) -> int:
    model = StepFile.load(Path(args.file))
    out = {}
    for key in HEADER_FIELDS:
        if key in model.header_fields:
            original, values = model.header_fields[key]
            out[key] = [_clean_header_token(v) for v in values]
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        for k, v in out.items():
            print(f"{k}:")
            for item in v:
                print(f"  {item}")
    return 0


def cmd_entities(args) -> int:
    model = StepFile.load(Path(args.file))
    ents = list(model.entities.values())
    if args.type:
        ents = [e for e in ents if e.type == args.type.upper()]
    if args.limit:
        ents = ents[: args.limit]
    if args.json:
        print(json.dumps([{"id": e.eid, "type": e.type, "params": e.params} for e in ents],
                         indent=2, ensure_ascii=False))
    else:
        for e in ents:
            print(model.render_entity(e))
    return 0


def cmd_get(args) -> int:
    model = StepFile.load(Path(args.file))
    ent = find_entity_by_id(model, args.id)
    out = {"id": ent.eid, "type": ent.type, "params": ent.params,
           "strings": model.strings(ent), "refs_out": model.refs_out(ent.eid),
           "refs_in": model.refs_in(ent.eid),
           "rendered": model.render_entity(ent)}
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        for k, v in out.items():
            print(f"{k}: {v}")
    return 0


def cmd_refs(args) -> int:
    model = StepFile.load(Path(args.file))
    find_entity_by_id(model, args.id)
    seen: dict[int, int] = {}
    frontier = [args.id]
    edges: list[tuple[int, int]] = []
    for depth in range(1, args.depth + 1):
        nxt: list[int] = []
        for eid in frontier:
            neighbours = set()
            if args.direction in {"out", "both"}:
                neighbours |= set(model.refs_out(eid))
            if args.direction in {"in", "both"}:
                neighbours |= set(model.refs_in(eid))
            for n in sorted(neighbours):
                edges.append((eid, n))
                if n not in seen:
                    seen[n] = depth
                    nxt.append(n)
        frontier = nxt
    rows = []
    for n, d in sorted(seen.items(), key=lambda kv: (kv[1], kv[0])):
        ent = model.entities.get(n)
        rows.append({"id": n, "depth": d, "type": ent.type if ent else "(missing)",
                     "rendered": model.render_entity(ent)[:200] if ent else ""})
    if args.json:
        print(json.dumps({"root": args.id, "direction": args.direction,
                          "edges": edges, "nodes": rows}, indent=2, ensure_ascii=False))
    else:
        print(f"#{args.id} ({model.entities[args.id].type}) — {len(rows)} related entity/ies")
        for r in rows:
            print(f"  d{r['depth']} #{r['id']:6} {r['type']:35} {r['rendered'][:110]}")
    return 0


def cmd_bom(args) -> int:
    model = StepFile.load(Path(args.file))
    rows = model.assembly_tree()
    counts: Counter = Counter(r["product_id"] for r in rows)
    for r in rows:
        r["quantity_total"] = counts[r["product_id"]]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=["level", "product_id", "product_name",
                                                    "product_definition", "path", "is_assembly",
                                                    "quantity_total"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {args.out} ({len(rows)} row(s))")
    if not args.json and not args.out:
        for r in rows:
            print(f"{'  ' * r['level']}{r['product_id']:12} {r['product_name'][:34]:34} "
                  f"level={r['level']} qty={r['quantity_total']}")
    return 0


def cmd_units(args) -> int:
    model = StepFile.load(Path(args.file))
    units = model.units()
    if args.json:
        print(json.dumps(units, indent=2, ensure_ascii=False))
    else:
        for u in units:
            print(f"#{u['entity']:5} {u['kind']:18} prefix={u['prefix']:10} "
                  f"to_metre={u['to_metre']}")
        if not any(u["kind"] == "length" for u in units):
            print("WARNING: no length unit found — do not assume millimetres")
    return 0


def cmd_params(args) -> int:
    model = StepFile.load(Path(args.file))
    ents = model.by_type(args.type) if args.type else list(model.entities.values())
    rows = []
    for e in ents:
        for i, p in enumerate(e.params):
            rows.append({"entity": e.eid, "type": e.type, "index": i,
                         "value": p, "literal": p.startswith("'")})
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=["entity", "type", "index", "value", "literal"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {args.out} ({len(rows)} parameter(s) from {len(ents)} entities)")
    else:
        for r in rows[:400]:
            print(f"#{r['entity']:6} {r['type']:32} [{r['index']}] {r['value'][:110]}")
        if len(rows) > 400:
            print(f"... {len(rows) - 400} more (use --out to export all)")
    return 0


def _write(model: StepFile, out_path: str, args, changes: list[dict]) -> int:
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(model.render(), encoding="utf-8", newline="")
    log = {"source": str(model.path), "output": str(target),
           "bytes_before": model.path.stat().st_size, "bytes_after": target.stat().st_size,
           "changes": changes,
           "note": "entity ids and ordering preserved; only the intended values changed"}
    log_path = target.with_suffix(target.suffix + ".changelog.json")
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target} ({len(changes)} change(s))")
    print(f"change log: {log_path}")
    print("validate the output before using it: "
          f"step_tool.py validate \"{target}\" --strict")
    return 0


def cmd_rename(args) -> int:
    model = StepFile.load(Path(args.file))
    changes: list[dict] = []
    needle = args.product
    for e in model.by_type("PRODUCT"):
        names = model.strings(e)
        if not names:
            continue
        if names[0] == needle or (args.match_name and len(names) > 1 and names[1] == needle):
            index = 0 if names[0] == needle else 1
            old = e.params[index]
            e.params[index] = "'" + encode_step_string(args.to) + "'"
            StepFile.touch(e)
            changes.append({"entity": e.eid, "type": "PRODUCT", "field": "id" if index == 0 else "name",
                            "before": decode_step_string(old.strip("'")), "after": args.to})
    if not changes:
        raise SystemExit(f"no PRODUCT matched {needle!r} (use --json summary to list them)")
    return _write(model, args.out, args, changes)


def cmd_replace(args) -> int:
    model = StepFile.load(Path(args.file))
    changes: list[dict] = []
    pattern = args.from_text
    encoded_old = encode_step_string(pattern)
    for e in model.entities.values():
        for i, p in enumerate(e.params):
            if not (p.startswith("'") and p.endswith("'")):
                continue
            plain = decode_step_string(p[1:-1])
            if pattern in plain or encoded_old in p:
                new_plain = plain.replace(pattern, args.to_text)
                e.params[i] = "'" + encode_step_string(new_plain) + "'"
                StepFile.touch(e)
                changes.append({"entity": e.eid, "type": e.type, "field": f"param[{i}]",
                                "before": plain[:120], "after": new_plain[:120]})
    for key in ("FILE_NAME", "FILE_DESCRIPTION"):
        if key in model.header_fields:
            original, values = model.header_fields[key]
            new_values = [v.replace(encoded_old, encode_step_string(args.to_text))
                          if pattern in decode_step_string(v) else v for v in values]
            if new_values != values:
                model.header_fields[key] = (original, new_values)
                changes.append({"entity": "HEADER", "type": key, "field": "header",
                                "before": pattern, "after": args.to_text})
    if not changes:
        raise SystemExit(f"no string contained {pattern!r}")
    return _write(model, args.out, args, changes)


def cmd_set_header(args) -> int:
    model = StepFile.load(Path(args.file))
    field = args.field.upper()
    if field not in HEADER_FIELDS:
        raise SystemExit(f"--field must be one of {', '.join(HEADER_FIELDS)}")
    if field == "FILE_NAME":
        values = [v.strip() for v in args.value.split(";")]
        values = [f"'{encode_step_string(v)}'" if not v.startswith("'") else v for v in values]
    else:
        values = [f"'{encode_step_string(args.value)}'"]
    before = model.header_fields.get(field, ("", []))[1]
    model.header_fields[field] = ("", values)
    changes = [{"entity": "HEADER", "type": field, "field": "header",
                "before": before, "after": values}]
    if not args.out:
        raise SystemExit("--out is required (editing in place is not supported for safety)")
    return _write(model, args.out, args, changes)


def cmd_strip_metadata(args) -> int:
    model = StepFile.load(Path(args.file))
    keep = {k.upper() for k in args.keep}
    removed: list[dict] = []
    for key in ("FILE_NAME", "FILE_DESCRIPTION"):
        if key in keep or key not in model.header_fields:
            continue
        original, values = model.header_fields[key]
        removed.append({"where": f"HEADER {key}", "before": values})
        if key == "FILE_NAME":
            model.header_fields[key] = (original, ["''", "''", "''", "''", "''", "''", "''"])
        else:
            model.header_fields[key] = (original, ["''"])
    patterns = [p for p in args.patterns.split("|") if p] if args.patterns else \
        [r"confidential", r"proprietary", r"internal", r"secret", r"do not distribute"]
    regex = re.compile("|".join(patterns), re.I)
    for e in list(model.entities.values()):
        if e.type in {"DESCRIPTIVE_REPRESENTATION_ITEM", "PRODUCT"}:
            for i, p in enumerate(e.params):
                if p.startswith("'") and regex.search(decode_step_string(p[1:-1])):
                    removed.append({"where": f"#{e.eid} {e.type}", "before": p})
                    e.params[i] = "''"
                    StepFile.touch(e)
    if args.drop_entities:
        drop_types = {t.upper() for t in args.drop_entities.split(",") if t}
        for eid in [e.eid for e in model.entities.values() if e.type in drop_types]:
            del model.entities[eid]
            model.order.remove(eid)
            removed.append({"where": f"#{eid}", "before": drop_types})
    if not removed:
        raise SystemExit("nothing matched: check --keep / --patterns / --drop-entities")
    return _write(model, args.out, args, removed)


def cmd_set_params(args) -> int:
    model = StepFile.load(Path(args.file))
    ent = find_entity_by_id(model, args.id)
    if args.index < 0 or args.index >= len(ent.params):
        raise SystemExit(f"#{args.id} has {len(ent.params)} parameter(s); index {args.index} is out of range")
    before = ent.params[args.index]
    ent.params[args.index] = args.value
    StepFile.touch(ent)
    changes = [{"entity": ent.eid, "type": ent.type, "field": f"param[{args.index}]",
                "before": before, "after": args.value}]
    return _write(model, args.out, args, changes)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Dependency-free STEP (ISO 10303-21) toolkit.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("summary"); p.add_argument("file"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("validate"); p.add_argument("file")
    p.add_argument("--strict", action="store_true"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("header"); p.add_argument("file"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_header)

    p = sub.add_parser("entities"); p.add_argument("file")
    p.add_argument("--type"); p.add_argument("--limit", type=int); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_entities)

    p = sub.add_parser("get"); p.add_argument("file"); p.add_argument("--id", type=int, required=True)
    p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_get)

    p = sub.add_parser("refs"); p.add_argument("file"); p.add_argument("--id", type=int, required=True)
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--direction", choices=["out", "in", "both"], default="both")
    p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_refs)

    p = sub.add_parser("bom"); p.add_argument("file"); p.add_argument("--out")
    p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_bom)

    p = sub.add_parser("units"); p.add_argument("file"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_units)

    p = sub.add_parser("params"); p.add_argument("file"); p.add_argument("--type"); p.add_argument("--out")
    p.set_defaults(func=cmd_params)

    p = sub.add_parser("rename"); p.add_argument("file")
    p.add_argument("--product", required=True); p.add_argument("--to", required=True)
    p.add_argument("--match-name", action="store_true", help="match the product name rather than the id")
    p.add_argument("--out", required=True); p.set_defaults(func=cmd_rename)

    p = sub.add_parser("replace"); p.add_argument("file")
    p.add_argument("--from", dest="from_text", required=True); p.add_argument("--to", dest="to_text", required=True)
    p.add_argument("--out", required=True); p.set_defaults(func=cmd_replace)

    p = sub.add_parser("set-header"); p.add_argument("file")
    p.add_argument("--field", required=True); p.add_argument("--value", required=True)
    p.add_argument("--out", required=True); p.set_defaults(func=cmd_set_header)

    p = sub.add_parser("strip-metadata"); p.add_argument("file")
    p.add_argument("--keep", nargs="*", default=[])
    p.add_argument("--patterns", default="")
    p.add_argument("--drop-entities", default="")
    p.add_argument("--out", required=True); p.set_defaults(func=cmd_strip_metadata)

    p = sub.add_parser("set-params"); p.add_argument("file"); p.add_argument("--id", type=int, required=True)
    p.add_argument("--index", type=int, required=True); p.add_argument("--value", required=True)
    p.add_argument("--out", required=True); p.set_defaults(func=cmd_set_params)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
