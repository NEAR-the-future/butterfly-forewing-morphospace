# STEP format primer and edit-safety rules

## What a STEP file is

A STEP file exchanged between CAD systems is an **ISO 10303-21** ("Part 21") clear-text file with
three parts:

```
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('...'),'2;1');
FILE_NAME('part.step','2026-01-15T09:30:00',('Author'),('Org'),
  'preprocessor','originating system','authorisation','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1=APPLICATION_CONTEXT('...');
...
ENDSEC;
END-ISO-10303-21;
```

Everything after `DATA;` is a flat list of **entity instances**:

```
#<id> = <TYPE>(<parameter>, <parameter>, ...);
```

- `#<id>` — a positive integer, unique within the file. References are written `#123`.
- `<TYPE>` — an EXPRESS entity name in upper case (`CARTESIAN_POINT`, `PRODUCT`, …).
- Parameters are one of: a number (`12.5`, `1.E-3`), an enum (`.T.`, `.MILLI.`, `.METRE.`), a string
  (`'text'`), a reference (`#45`), an aggregate (`(1.,2.,3.)`, `(#1,#2)`), `$` (unset), `*` (derived),
  or a **complex instance** that packs several types into one entity:
  `#20=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));`

Complex instances are the single most important parsing trap: their parameters cannot be indexed by
position, so a tool that treats them as ordinary entities will corrupt the file on write-back. The
bundled `step_tool.py` preserves their original declaration text instead.

## Schemas (application protocols)

| Schema string | Protocol | Typical content |
|---|---|---|
| `CONFIG_CONTROL_DESIGN` | AP203 | geometry and configuration control, the classic exchange format |
| `AUTOMOTIVE_DESIGN` | AP214 | adds colours, layers, presentation, GD&T; automotive/mechanical default |
| `MANIFOLD_SURFACE_DESIGN_WITH_COLOR` | AP242 (surface) | tessellated/surface data with PMI |
| `MANIFOLD_SOLID_BREP` | AP242 | solids, PMI, model-based definition |

AP242 is the current target for model-based definition (PMI, GD&T, tessellation). Converting between
protocols changes the entity set and must be done by a CAD kernel — never by hand.

## The entity graph you will actually meet

**Product structure**

```
PRODUCT ─ PRODUCT_DEFINITION_FORMATION ─ PRODUCT_DEFINITION ─ (shape)
   └─ NEXT_ASSEMBLY_USAGE_OCCURRENCE(parent PD, child PD) — the assembly relation
   └─ PRODUCT_DEFINITION_SHAPE ─ SHAPE_DEFINITION_REPRESENTATION ─ SHAPE_REPRESENTATION
```

`NEXT_ASSEMBLY_USAGE_OCCURRENCE` usually carries referenced components and transformations before
its two `PRODUCT_DEFINITION` references, so identify the definitions by **entity type**, not by
parameter position.

**Geometry**

```
CARTESIAN_POINT, DIRECTION, VECTOR
AXIS2_PLACEMENT_3D                     placement (origin, axis, ref direction)
VERTEX_POINT ─ CARTESIAN_POINT
EDGE_CURVE ─ VERTEX_POINT, LINE / CIRCLE / B_SPLINE_CURVE_WITH_KNOTS, .T./.F.
EDGE_LOOP ─ FACE_OUTER_BOUND / FACE_BOUND ─ ADVANCED_FACE ─ PLANE / CYLINDRICAL_SURFACE / ...
CLOSED_SHELL ─ MANIFOLD_SOLID_BREP ─ ADVANCED_BREP_SHAPE_REPRESENTATION
```

Tessellated geometry (AP242) uses `TESSELLATED_SOLID`, `TRIANGULATED_FACE`, `COORDINATES_LIST`.

**Units**

```
#20=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));
#25=(CONVERSION_BASED_UNIT('INCH',#26)LENGTH_UNIT()NAMED_UNIT(*));
#27=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(25.4),#20);
```

Always read the unit. `SI_UNIT(.MILLI.,.METRE.)` means millimetres; a bare number is meaningless.

**Presentation**

`STYLED_ITEM`, `PRESENTATION_STYLE_ASSIGNMENT`, `SURFACE_STYLE_USAGE`, `SURFACE_SIDE_STYLE`,
`FILL_AREA_STYLE`, `COLOUR_RGB`, `MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION`,
`DRAUGHTING_PRE_DEFINED_COLOUR`, and layers via `PRESENTATION_LAYER_ASSIGNMENT`.

**Placement in assemblies**

`ITEM_DEFINED_TRANSFORMATION`, `REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION`,
`CONTEXT_DEPENDENT_SHAPE_REPRESENTATION`. Their presence means component geometry is stored in local
part coordinates and the assembled position requires composing 4×4 transforms — a kernel job.

## String encoding

STEP strings are single-quoted, ASCII-oriented, and use control directives for anything else:

| Form | Meaning |
|---|---|
| `''` | one literal apostrophe |
| `\X\hh` | one byte, hexadecimal (e.g. `\X\B5` is µ) |
| `\X2\hhhh…\X0\` | a run of UTF-16BE code units (CJK, symbols) |
| `\S\c` | a single byte `ord(c) + 128` (ISO 8859-1 upper half, legacy) |
| `\N\` / `\F\` | newline / form feed inside a string |

Write Chinese product names as `\X2\7D2756FA4EF6\X0\`, never as raw UTF-8 bytes: a raw byte sequence
inside a quoted string is not valid Part 21 and some importers reject the whole file. Decode on read
and report the human-readable text; encode on write.

## Edit-safety rules

1. **Never renumber entity ids.** References are positional; renumbering breaks every downstream
   consumer and destroys diffability. Add new entities at `max_id + 1`.
2. **Preserve untouched text byte for byte.** A minimal diff is how a reviewer verifies that only the
   intended change happened. The bundled writer keeps the original declaration text of every entity
   it did not edit.
3. **Never edit geometry-bearing entities casually**: `CARTESIAN_POINT`, `DIRECTION`,
   `AXIS2_PLACEMENT_3D`, `VECTOR`, `LINE`, `CIRCLE`, `B_SPLINE_*`, `PLANE`, `*_SURFACE`, `EDGE_*`,
   `FACE_*`, `*_SHELL`, `*_BREP`, `TESSELLATED_*`. Changing them changes shape. Name edits, metadata
   edits, colour edits and parameter-table edits are safe; shape edits belong to a kernel.
4. **Do not convert protocol versions by hand.** AP203 ↔ AP214 ↔ AP242 changes the entity set.
5. **Keep the file balanced.** Every entity ends with `;`, strings are closed, parentheses balance,
   and the file ends with `END-ISO-10303-21;`. Run `validate` after every edit.
6. **Write to a new file.** Name the output explicitly and let the tool emit a change log. If the
   user demands in-place editing, keep a timestamped backup and say what was overwritten.
7. **Watch the header.** `FILE_NAME` encodes the file name, timestamp, authors, organisation,
   preprocessor, originating system and authorisation. Redacting it changes provenance; report what
   was removed and why.
8. **Encoding on write.** Choose UTF-8 or the file's original encoding deliberately, and never mix a
   BOM into the middle of a file. Some legacy systems expect ASCII-only with `\X2\` escapes.

## Validation checklist

| Check | Severity | Why it matters |
|---|---|---|
| `ISO-10303-21;` start and `END-ISO-10303-21;` end | high | truncated transfers are common |
| every `#ref` resolves to an existing id | high | dangling references break importers |
| unique ids | high | duplicate ids silently shadow geometry |
| balanced parentheses and closed strings | high | a single unbalanced quote corrupts the rest of the file |
| `FILE_SCHEMA` present | medium | the protocol tells the importer what to expect |
| a length unit exists | high | numbers without a unit cannot be interpreted |
| no geometry at all | medium | a "model" with no `CARTESIAN_POINT` is metadata only |
| unused ids | low | informational: deleted geometry leaves holes by design |
