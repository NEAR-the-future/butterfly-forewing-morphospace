---
name: step-file-engineering
description: "Read, edit, validate, and convert STEP files (ISO 10303-21 / AP203 / AP214 / AP242, .step and .stp). Ships a dependency-free Python toolkit: step_tool.py for header and entity-graph analysis, product/BOM extraction, metadata and unit inspection, safe parameter and string edits with a change log, and round-trip writing; step_geom.py for geometric facts available without a CAD kernel (bounding boxes, extents, centroids, point clouds, SVG/CSV projections); and cad_bridge.py to detect and delegate to OpenCASCADE/cadquery/FreeCAD when a real kernel is installed. Use for any STEP file task: inspection, metadata or naming edits, BOM or parameter tables, unit conversion, integrity checks, or preparation for downstream CAD."
whenToUse: "Load whenever a .step/.stp file is an input or an output, or when the task involves STEP metadata, assembly structure, entity edits, or CAD-kernel operations."
---

# STEP file engineering

STEP (ISO 10303-21, "Part 21") is a **plain-text** exchange format. This is the single most important
fact for the work: the entity graph can be parsed, queried, and edited as text with no CAD kernel,
losslessly and deterministically. What text editing *cannot* do is evaluate geometry — booleans,
fillet, mass properties of a true B-rep, or a faithful STL tessellation.

This skill therefore works in three tiers and always states which tier produced a result.

| Tier | Tool | Capability | Requirements |
|---|---|---|---|
| 1. Text / entity graph | `scripts/step_tool.py` | header, entities, products, BOM, units, colours, metadata edits, renames, validation, round-trip write | Python 3 only, no dependencies |
| 2. Geometric facts | `scripts/step_geom.py` | bounding boxes from control/cartesian points, extents, centroids, point clouds, SVG/CSV projections, size estimates | Python 3 + numpy (present) |
| 3. Real CAD kernel | `scripts/cad_bridge.py` | true tessellation, STL/glTF export, volume, area, booleans, modelling | OpenCASCADE/cadquery or FreeCAD, **not installed here** |

Read `references/step-format.md` for the entity-graph primer and the edit-safety rules, and
`references/cad-kernel-setup.md` for installing tier 3 and what to do while offline.

## Tier detection — run this first

```powershell
& "C:\Users\16240\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" `
  "<skill-dir>\scripts\cad_bridge.py" --probe
```

Report the detected tier to the user **before** promising any geometric result. Never present a
tier-1 or tier-2 result as if a kernel computed it.

## Workflow

1. **Summarise before editing.**
   ```powershell
   & "<python>" "<skill-dir>\scripts\step_tool.py" summary "<model.step>" --json
   ```
   Gives schema (AP203/AP214/AP242), originating system, author/org/date, entity count by type,
   product names and their assembly nesting, units and their conversion factors, and file size.
2. **Validate** the file's structural integrity (balanced parentheses, unique IDs, every reference
   resolvable, required header fields, well-formed strings):
   ```powershell
   & "<python>" "<skill-dir>\scripts\step_tool.py" validate "<model.step>" --strict
   ```
3. **Extract** what the task needs: BOM/assembly tree, entity listings, a parameter table, colours,
   or a projection:
   ```powershell
   & "<python>" "<skill-dir>\scripts\step_tool.py" entities "<model.step>" --type PRODUCT --limit 50
   & "<python>" "<skill-dir>\scripts\step_tool.py" bom "<model.step>" --out "<workspace>\bom.csv"
   & "<python>" "<skill-dir>\scripts\step_tool.py" refs "<model.step>" --id 1234 --depth 3
   & "<python>" "<skill-dir>\scripts\step_tool.py" params "<model.step>" --type PRODUCT --out "<workspace>\products.csv"
   & "<python>" "<skill-dir>\scripts\step_geom.py" bounds "<model.step>" --json
   & "<python>" "<skill-dir>\scripts\step_geom.py" groups "<model.step>" --json
   & "<python>" "<skill-dir>\scripts\step_geom.py" project "<model.step>" --view xz --out "<workspace>\front.svg"
   ```
4. **Edit on a copy, never in place.** Every mutating command writes to `--out` and emits a change
   log; if `--in-place` is genuinely required, the tool refuses without `--force` and writes a
   timestamped backup first.
   ```powershell
   & "<python>" "<skill-dir>\scripts\step_tool.py" rename "<model.step>" `
       --product "PART-001" --to "Bracket-A" --out "<workspace>\model_named.step"
   & "<python>" "<skill-dir>\scripts\step_tool.py" set-header "<model.step>" `
       --field FILE_NAME --value "1.0;2026-01-01;Engineer;Org;AP242;step_tool;system;authorization" `
       --out "<workspace>\model_hdr.step"
   & "<python>" "<skill-dir>\scripts\step_tool.py" strip-metadata "<model.step>" `
       --keep "FILE_SCHEMA" --out "<workspace>\model_clean.step"
   & "<python>" "<skill-dir>\scripts\step_tool.py" replace "<model.step>" `
       --from "ACME-CONFIDENTIAL" --to "INTERNAL" --out "<workspace>\model_redacted.step"
   ```
5. **Validate the output again** and confirm the entity count changed only as intended. A rename
   must not alter geometry-bearing entities; report the exact diff.
6. **Report**: schema, tier used, operations applied with their entity-level effect, files written,
   and every operation you declined to perform.

## Edit-safety rules

- **Never re-number entity IDs** to "tidy" a file. `#123` references are positional; renumbering
  breaks downstream tools and diffability. Add new entities with `max_id + 1`.
- **Preserve the original whitespace, line ordering, and header formatting** where possible. Minimal
  diffs are how a reviewer verifies an edit. The writer keeps the original bytes of untouched lines.
- **Text in STEP is literal.** Strings are single-quoted, embedded quotes are doubled (`''`), and
  non-ASCII is encoded as `\X2\....\X0\` or `\S\c`. Encode and decode properly; a Chinese product
  name must be written as `\X2\...` rather than raw bytes, and read back correctly when inspecting.
- **Units are explicit.** Length units come from `(LENGTH_UNIT)` complexes with
  `SI_UNIT(.MILLI.,.METRE.)` or `CONVERSION_BASED_UNIT`. Never assume millimetres: read the unit
  and its factor, and always state the unit with every number you report.
- **Geometry-bearing entities are off-limits for casual edits** (`CARTESIAN_POINT`, `DIRECTION`,
  `AXIS2_PLACEMENT_3D`, `CURVE`, `SURFACE`, `SHELL`, `SOLID`, `MANIFOLD_SOLID_BREP`). Editing them
  changes shape. If the user asks for a shape change, that is a tier-3 job — say so.
- **Do not convert between schema versions by hand.** AP203 ↔ AP214 ↔ AP242 conversion changes the
  entity set and must go through a CAD kernel.
- **Colours and layers** live in `STYLED_ITEM`, `PRESENTATION_STYLE_ASSIGNMENT`, `COLOUR_RGB`,
  `MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION`. Read them; changing them is safe and
  often exactly what the user wants.
- **Confidentiality edits** (removing author, organisation, originating system, or custom
  properties) are legitimate, but always tell the user what was removed, because some workflows
  require provenance.

## Geometry without a kernel — know the boundary

`step_geom.py` computes facts from the *control points* present in the file. Choose the point set
deliberately, because the three modes answer three different questions:

| `--mode` | Points used | When to use |
|---|---|---|
| `vertices` (default) | only `CARTESIAN_POINT`s referenced by a `VERTEX_POINT` | the shape's real corners; safest default |
| `all` | every `CARTESIAN_POINT` in the file | widest, most conservative box; includes construction aids and points orphaned by a deletion |
| `referenced` | points reachable from a `SHAPE_REPRESENTATION` item | strictly the geometry the file still presents |

The tool reports which mode produced the number and labels the confidence:

- **exact** when the model has no `B_SPLINE_CURVE`, `B_SPLINE_SURFACE`, `CYLINDRICAL_SURFACE` or
  `TOROIDAL_SURFACE` — the box of the control points is the box of the solid;
- **bounds of the control net** otherwise: the box *contains* the true surface and may exceed it.
  Never present such a number as the part's exact size.

It must refuse, not approximate, when asked for: volume, surface area, mass properties, STL from a
curved B-rep, booleans, fillets, shells, or "convert to OBJ/3MF". State the reason (no kernel) and
give the install path from `references/cad-kernel-setup.md`.

Assembly placement transforms (`ITEM_DEFINED_TRANSFORMATION`,
`REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION`, `CONTEXT_DEPENDENT_SHAPE_REPRESENTATION`) are
detected and reported: per-product boxes are in **local part coordinates**, not assembled position.
Without a kernel, do not attempt to compose the transforms by hand.

For a true STL, use tier 3 when available:
```powershell
& "<python>" "<skill-dir>\scripts\cad_bridge.py" to-stl "<model.step>" --linear-deflection 0.1 --out "<workspace>\model.stl"
```

## What to report for every STEP task

- the schema and originating system, and the entity/type census;
- units with their conversion factor, and the bounding box **with units**;
- the tier used for each claim, and any claim that is a bound rather than an exact value;
- the exact operations applied and the files written, with the change log;
- validation status of the output, including any dangling reference or duplicate ID;
- what was not done and why (typically: geometry evaluation without a kernel).
