# CAD kernel setup (tier 3)

Tier 1 (text/entity graph) and tier 2 (kernel-free bounds) work offline with Python only. Tier 3 —
true tessellation, STL export, volume, surface area, mass properties, booleans, fillets, protocol
conversion — requires a real geometry kernel.

**This machine currently has no kernel and no network access**, so tier 3 operations fail with an
explicit message rather than an approximation. That is deliberate: an approximated volume or a fake
STL is worse than an honest refusal, because the number looks authoritative and gets published.

## Check the current state first

```powershell
& "C:\Users\16240\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" `
  "<skill-dir>\scripts\cad_bridge.py" --probe
```

The output reports the tier, every candidate module, the capability table, and the install commands.

## Option A — OpenCASCADE through cadquery (recommended for scripting)

```powershell
& "<python>" -m pip install --upgrade cadquery
& "<python>" -m pip install cadquery-ocp        # bundles the OpenCASCADE binaries
```

Then, with the kernel present, `cad_bridge.py` performs real operations:

```powershell
& "<python>" "<skill-dir>\scripts\cad_bridge.py" to-stl model.step --linear-deflection 0.1 --out model.stl
& "<python>" "<skill-dir>\scripts\cad_bridge.py" info model.step --json
```

Direct cadquery equivalents, if the bridge is not what you need:

```python
from cadquery import importers, exporters
shape = importers.importStep("model.step")
solids = shape.solids().vals()
print("volume mm^3:", sum(s.Volume() for s in solids))
print("area mm^2:  ", sum(s.Area() for s in solids))
exporters.export(shape, "model.stl", exportType="STL", opt={"linearDeflection": 0.1})
exporters.export(shape, "model_ap242.step", exportType="STEP")
```

Notes that prevent surprises:

- Units: cadquery interprets STEP lengths in millimetres by default and does **not** convert a file
  authored in inches — check the unit complex first with tier 1 and convert deliberately.
- `linearDeflection` trades file size for fidelity; 0.05–0.2 mm is typical for mechanical parts.
- Boolean operations require valid, closed solids. Check `shape.val().isValid()` before cutting, and
  expect failures on sliver faces from a bad import.
- Mass properties need a density; the kernel gives volume and area, not mass.

## Option B — FreeCAD (GUI plus headless scripting)

Install FreeCAD 1.0 or newer. `cad_bridge.py` probes
`C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe` and `freecadcmd` on `PATH`.

```powershell
& "C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe" -c @"
import FreeCAD, Part
shape = Part.Shape()
shape.read('model.step')
print('valid:', shape.isValid())
print('volume mm^3:', shape.Volume)
print('area mm^2:', shape.Area)
print('bbox:', shape.BoundBox)
mesh = FreeCAD.getDocument if False else None
import Mesh, MeshPart
m = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.1, AngularDeflection=0.3)
m.write('model.stl')
"@
```

FreeCAD is also the practical route for STEP ↔ IGES conversion, drawing extraction, and repairing a
model that OpenCASCADE rejects.

## Option C — other kernels

| Tool | Install | Use |
|---|---|---|
| `pythonocc-core` | conda-forge only (`conda install -c conda-forge pythonocc-core`) | full OCCT API from Python |
| `gmsh` | `pip install gmsh` | meshing, then FEA export |
| `trimesh` | `pip install trimesh` | mesh formats only; it cannot read B-rep STEP geometry |
| `steputils` | `pip install steputils` | Part 21 parsing conveniences (this skill already covers it) |

`trimesh` will not evaluate a STEP B-rep. Do not present a trimesh result as STEP geometry.

## What to do while offline

1. Use tier 1 for metadata, naming, BOM, unit inspection, colour edits, validation and redaction.
2. Use tier 2 for bounding boxes, extents and centroids, labelled with the point-selection mode and
   the confidence verdict.
3. Tell the user plainly that volume, area, STL and booleans require the kernel, and provide the
   exact command to run once network access is available.
4. If the deliverable must be a mesh today, ask the user to export STL/OBJ from their CAD system —
   that produces a real tessellation, whereas reconstructing one from control points does not.

## Verifying a kernel result

- `validate` the exported STEP with tier 1: entity count should be plausible and no reference should
  dangle.
- Check the bounding box from the kernel against the tier-2 bounds. The kernel box must lie inside
  (or equal) the control-net box; a kernel box larger than the control-net box means a unit or
  transform mistake.
- For STL, check the triangle count and the file size you actually need: an over-tessellated part
  produces files that downstream tools cannot open.
