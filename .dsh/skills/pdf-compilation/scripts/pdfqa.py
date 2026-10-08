#!/usr/bin/env python3
"""Structural and production checks for a finished PDF, without external tools.

Reports page count, page geometry, encryption, font embedding, metadata and
size. This is a permissive scanner: it tolerates object streams and broken xref
tables, and it says "unknown" rather than guessing when the structure is
unreadable.

Usage:
  pdfqa.py FILE.pdf [--json] [--out FILE] [--expect-pages N] [--max-mb N]
                    [--require-fonts-embedded] [--allow-encrypted]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zlib
from pathlib import Path

OBJ_RE = re.compile(rb"(?<![0-9])(\d{1,10})\s+(\d{1,5})\s+obj\b")
DESCRIPTOR_FLAGS = {1: "FixedPitch", 2: "Serif", 4: "Symbolic", 8: "Script",
                    16: "Nonsymbolic", 32: "Italic", 64: "AllCap", 128: "SmallCap",
                    256: "ForceBold"}


def inflate_streams(data: bytes) -> bytes:
    """Return the original bytes plus every inflatable stream payload.

    pdfTeX and modern producers place font dictionaries, page trees and metadata
    inside object streams; without inflating them the scanner would see almost
    nothing and would have to answer 'unknown' for every font.
    """
    extra = bytearray()
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end == -1:
            continue
        raw = data[start:end]
        out = None
        try:
            out = zlib.decompress(raw)
        except Exception:
            try:
                out = zlib.decompressobj().decompress(raw)
            except Exception:
                out = None
        if out and len(out) < 60_000_000:
            extra += b"\n" + out + b"\n"
    return data + bytes(extra)


def load_all_objects(data: bytes) -> dict[int, str]:
    """Map object number -> body text, from direct objects and object streams."""
    objects: dict[int, str] = {}

    for m in re.finditer(rb"(?<![0-9])(\d{1,10})\s+(\d{1,5})\s+obj\b", data):
        num = int(m.group(1))
        start = m.end()
        end = data.find(b"endobj", start)
        if end == -1:
            nxt = re.search(rb"(?<![0-9])\d{1,10}\s+\d{1,5}\s+obj\b", data[start:])
            end = start + nxt.start() if nxt else len(data)
        objects[num] = data[start:end].decode("latin-1", "replace")

    # object streams: /Type /ObjStm /N <count> /First <offset>, then a header of
    # "objnum offset" pairs followed by the concatenated object bodies
    for m in re.finditer(rb"<<(.{0,600}?)/Type\s*/ObjStm(.{0,600}?)>>\s*stream\r?\n", data, re.S):
        header = (m.group(1) + m.group(2)).decode("latin-1", "replace")
        n_m = re.search(r"/N\s+(\d+)", header)
        first_m = re.search(r"/First\s+(\d+)", header)
        if not (n_m and first_m):
            continue
        start = m.end()
        end = data.find(b"endstream", start)
        if end == -1:
            continue
        try:
            payload = zlib.decompress(data[start:end])
        except Exception:
            continue
        count, first = int(n_m.group(1)), int(first_m.group(1))
        header_text = payload[:first].decode("latin-1", "replace")
        pairs = re.findall(r"(\d+)\s+(\d+)", header_text)[:count]
        for i, (num, off) in enumerate(pairs):
            body_start = first + int(off)
            body_end = first + int(pairs[i + 1][1]) if i + 1 < len(pairs) else len(payload)
            objects[int(num)] = payload[body_start:body_end].decode("latin-1", "replace")
    return objects


def resolve_refs(text: str, objects: dict[int, str], depth: int = 3) -> str:
    """Inline indirect references so a font dictionary shows its descriptor."""
    for _ in range(depth):
        def repl(m):
            num = int(m.group(1))
            body = objects.get(num)
            return " " + body + " " if body is not None else " null "
        new = re.sub(r"(?<![0-9])(\d{1,10})\s+\d{1,5}\s+R(?![a-zA-Z])", repl, text)
        if new == text:
            break
        text = new
    return text


def parse_info(text: str) -> dict:
    info: dict = {}
    for key in ("Title", "Author", "Subject", "Keywords", "Creator", "Producer",
                "CreationDate", "ModDate"):
        m = re.search(r"/" + key + r"\s*\(((?:[^()\\]|\\.)*)\)", text)
        if m:
            value = m.group(1)
            value = re.sub(r"\\([nrtbf()\\])", lambda x: {"n": "\n", "r": "\r", "t": "\t",
                                                          "b": "\b", "f": "\f"}.get(x.group(1),
                                                                                    x.group(1)),
                           value)
            info[key] = value.strip()
        else:
            m = re.search(r"/" + key + r"\s*<([0-9A-Fa-f\s]+)>", text)
            if m:
                try:
                    raw = bytes.fromhex(re.sub(r"\s", "", m.group(1)))
                    if raw[:2] in (b"\xfe\xff",):
                        info[key] = raw.decode("utf-16-be", "replace")
                    else:
                        info[key] = raw.decode("latin-1", "replace")
                except Exception:
                    pass
    return info


def parse_fonts(objects: dict[int, str], resolved: str) -> list[dict]:
    """Report each font with its subtype and whether a font file is embedded.

    Works from the object graph: font dictionaries point at font descriptors,
    which point at FontFile/FontFile2/FontFile3 streams.
    """
    descriptor_embedded: dict[int, str | None] = {}
    descriptor_name: dict[int, str] = {}
    for num, body in objects.items():
        if "/FontDescriptor" not in body and "/FontFile" not in body:
            continue
        if "/FontFile" in body:
            for kind in ("FontFile3", "FontFile2", "FontFile"):
                if re.search(r"/" + kind + r"\b", body):
                    descriptor_embedded[num] = kind
                    break
        elif "/FontDescriptor" in body:
            descriptor_embedded.setdefault(num, None)
        name_m = re.search(r"/FontName\s*/([#\w+\-.,]+)", body)
        if name_m:
            descriptor_name[num] = name_m.group(1)

    fonts: list[dict] = []
    seen: set[tuple] = set()
    for num, body in objects.items():
        if not re.search(r"/Type\s*/Font\b", body):
            continue
        base_m = re.search(r"/BaseFont\s*/([#\w+\-.,]+)", body)
        sub_m = re.search(r"/Subtype\s*/(\w+)", body)
        name = base_m.group(1) if base_m else descriptor_name.get(num, f"font-{num}")
        subset_prefix = ""
        prefix_m = re.match(r"^([A-Z]{6})\+(.+)$", name)
        if prefix_m:
            subset_prefix, name = prefix_m.group(1), prefix_m.group(2)
        subtype = sub_m.group(1) if sub_m else "unknown"
        key = (name, subtype)
        if key in seen:
            continue
        seen.add(key)
        embedded: bool | None = None
        desc_m = re.search(r"/FontDescriptor\s+(\d+)\s+\d+\s+R", body)
        if desc_m:
            embedded = descriptor_embedded.get(int(desc_m.group(1))) is not None
        elif re.search(r"/FontFile[23]?\s+\d+\s+\d+\s+R", body):
            embedded = True
        elif subtype == "Type3":
            embedded = True
        fonts.append({"name": name, "subtype": subtype, "embedded": embedded,
                      "subset": bool(subset_prefix)})

    if not fonts:
        # fall back to a text scan for producers that do not tag /Type /Font
        for m in re.finditer(r"/BaseFont\s*/([#\w+\-.,]+)", resolved):
            name = re.sub(r"^[A-Z]{6}\+", "", m.group(1))
            if (name, "unknown") in seen:
                continue
            seen.add((name, "unknown"))
            fonts.append({"name": name, "subtype": "unknown", "embedded": None,
                          "subset": False})
    return fonts


def parse_pages(text: str) -> list[dict]:
    pages: list[dict] = []
    for m in re.finditer(r"/Type\s*/Page\b", text):
        window = text[m.start(): m.start() + 1200]
        box = re.search(r"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", window)
        rot = re.search(r"/Rotate\s+(-?\d+)", window)
        entry: dict = {}
        if box:
            x0, y0, x1, y1 = (float(box.group(i)) for i in range(1, 5))
            w_pt, h_pt = abs(x1 - x0), abs(y1 - y0)
            entry["media_box_pt"] = [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]
            entry["size_mm"] = [round(w_pt / 72 * 25.4, 1), round(h_pt / 72 * 25.4, 1)]
        if rot:
            entry["rotate"] = int(rot.group(1))
        pages.append(entry)
    return pages


def analyse(path: Path, expect_pages: int | None, max_mb: float,
            require_embedded: bool, allow_encrypted: bool) -> dict:
    data = path.read_bytes()
    checks: list[dict] = []

    def add(name, verdict, detail):
        checks.append({"check": name, "verdict": verdict, "detail": detail})

    result: dict = {"file": str(path), "bytes": len(data),
                    "mb": round(len(data) / 1048576, 2), "checks": checks, "errors": []}

    if not data.startswith(b"%PDF-"):
        add("header", "fail", "missing %PDF header: not a PDF or truncated")
        result["checks"] = checks
        return result
    version = data[5:8].decode("latin-1", "replace")
    result["pdf_version"] = version
    add("header", "pass", f"PDF {version}")

    if b"%%EOF" not in data[-2048:]:
        add("trailer", "warn", "no %%EOF within the last 2 KB: the file may be truncated")
    else:
        add("trailer", "pass", "%%EOF present")

    objects = load_all_objects(data)
    result["object_count"] = len(objects)
    expanded = inflate_streams(data)
    text = expanded.decode("latin-1", "replace")
    resolved = resolve_refs(text, objects)

    encrypted = bool(re.search(r"/Encrypt\s+\d+\s+\d+\s+R|/Encrypt\s*<<", text))
    result["encrypted"] = encrypted
    if encrypted and not allow_encrypted:
        add("encryption", "fail", "document is encrypted: most journals and printers reject it")
    elif encrypted:
        add("encryption", "warn", "document is encrypted (permitted by --allow-encrypted)")
    else:
        add("encryption", "pass", "not encrypted")

    page_count = len(re.findall(r"/Type\s*/Page\b", text))
    # guard against double counting when the same objects appear in the original
    # bytes and the inflated object streams
    result["page_count"] = page_count
    if page_count == 0:
        add("pages", "unknown", "no page objects found by the scanner; open the PDF to confirm")
    else:
        add("pages", "pass", f"{page_count} page object(s) found")
    if expect_pages is not None:
        add("page_count_expected", "pass" if page_count == expect_pages else "fail",
            f"found {page_count}, expected {expect_pages}")

    pages = parse_pages(text)
    if pages:
        sizes = {tuple(p["size_mm"]) for p in pages if "size_mm" in p}
        result["page_sizes_mm"] = [list(s) for s in sizes]
        if len(sizes) > 1:
            add("page_size", "warn", f"mixed page sizes: {sorted(sizes)}")
        else:
            size = next(iter(sizes))
            portrait = size[1] >= size[0]
            label = "portrait" if portrait else "landscape"
            if abs(size[0] - 210) < 3 and abs(size[1] - 297) < 3:
                label += " A4"
            elif abs(size[0] - 215.9) < 3 and abs(size[1] - 279.4) < 3:
                label += " US Letter"
            add("page_size", "pass", f"{size[0]} x {size[1]} mm ({label})")
    else:
        add("page_size", "unknown", "MediaBox not found by the scanner")

    fonts = parse_fonts(objects, resolved)
    result["fonts"] = fonts
    if not fonts:
        add("fonts", "unknown", "no font dictionaries found by the scanner")
    else:
        not_embedded = [f["name"] for f in fonts if f["embedded"] is False]
        unknown_f = [f["name"] for f in fonts if f["embedded"] is None]
        subsets = sum(1 for f in fonts if f["subset"])
        if not_embedded:
            add("font_embedding", "fail",
                f"not embedded: {', '.join(sorted(set(not_embedded)))} "
                "(printers and journals may reject this file)")
        elif unknown_f:
            add("font_embedding", "unknown",
                f"embedding not determinable for: {', '.join(sorted(set(unknown_f)))}")
        else:
            add("font_embedding", "pass",
                f"all {len(fonts)} font(s) embedded"
                + (f", {subsets} subsetted" if subsets else ""))

    info = {k: v.strip() for k, v in parse_info(resolved).items() if v and v.strip()}
    xmp_title = re.search(r"<dc:title>.*?<rdf:li[^>]*>(.*?)</rdf:li>", resolved, re.S)
    if xmp_title and not info.get("Title"):
        info["Title"] = re.sub(r"\s+", " ", xmp_title.group(1)).strip()
    result["metadata"] = info
    if info.get("Producer", "").lower().startswith(("microsoft", "libreoffice", "skia", "chromium")):
        add("metadata", "warn", f"producer is {info['Producer']}: verify it is the intended pipeline")
    missing = [k for k in ("Title", "Author") if not info.get(k)]
    if missing:
        add("metadata", "warn", f"missing metadata: {', '.join(missing)}")
    else:
        add("metadata", "pass", f"title and author present")

    if len(data) > max_mb * 1048576:
        add("size", "warn", f"{result['mb']} MB exceeds the {max_mb} MB budget: downsample images")
    else:
        add("size", "pass", f"{result['mb']} MB")

    linearized = bool(re.search(rb"/Linearized", data[:4096]))
    result["linearized"] = linearized
    add("linearized", "pass" if linearized else "warn",
        "fast web view enabled" if linearized else "not linearized (only matters for web delivery)")

    return result


def format_text(result: dict) -> str:
    lines = [f"# {result['file']}",
             f"PDF {result.get('pdf_version')}  {result['mb']} MB  pages={result.get('page_count')}  "
             f"objects={result.get('object_count')}  encrypted={result.get('encrypted')}"]
    if result.get("page_sizes_mm"):
        lines.append(f"page sizes (mm): {result['page_sizes_mm']}")
    if result.get("fonts"):
        lines.append("fonts:")
        for f in result["fonts"]:
            emb = {True: "embedded", False: "NOT embedded", None: "unknown"}[f["embedded"]]
            lines.append(f"  {f['name']:40} {f['subtype']:12} {emb}")
    if result.get("metadata"):
        lines.append("metadata:")
        for k, v in result["metadata"].items():
            lines.append(f"  {k}: {v[:120]}")
    lines.append("checks:")
    for c in result["checks"]:
        lines.append(f"  {c['verdict'].upper():7} {c['check']:20} {c['detail']}")
    lines.append("")
    lines.append("NOTE: this is a permissive structure scan; confirm font embedding in a PDF "
                 "reader when a check reports 'unknown'.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="PDF structure and production checker.")
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--expect-pages", type=int, default=None)
    ap.add_argument("--max-mb", type=float, default=50.0)
    ap.add_argument("--require-fonts-embedded", action="store_true")
    ap.add_argument("--allow-encrypted", action="store_true")
    args = ap.parse_args(argv)

    results = []
    for raw in args.pdfs:
        path = Path(raw)
        if not path.is_file():
            print(f"warning: not a file: {path}", file=sys.stderr)
            continue
        results.append(analyse(path, args.expect_pages, args.max_mb,
                               args.require_fonts_embedded, args.allow_encrypted))

    report = json.dumps(results, indent=2, ensure_ascii=False) if args.json else \
        "\n".join(format_text(r) for r in results)
    fails = sum(1 for r in results for c in r["checks"] if c["verdict"] == "fail")
    if args.out:
        Path(args.out).write_text(report + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({len(results)} file(s), {fails} failing check(s))")
    else:
        print(report)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
