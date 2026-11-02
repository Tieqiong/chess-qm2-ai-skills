---
name: reciprocal-space-plotting
description: >-
  Generate HK, HL and KL slices or three-panel summaries from 3D NeXus reciprocal
  volumes using native axis metadata and optional full reciprocal-metric geometry.
  Use for diagnostic PNG figures; intensity normalization and coverage validation
  remain pending.
---

# Reciprocal space slices

Use the shared `nxs_analysis_tools.reciprocal` API from the
[analysis-library fork](https://github.com/Tieqiong/nxs_analysis_tools/tree/codex/reciprocal-slicing).
The scripts require this API; they do not silently substitute older positional slicing.
Use the updated source checkout on `PYTHONPATH` after preparing its generated
version module, or install the fork in an environment chosen for this work.
See [runtime setup](../docs/reciprocal-analysis-status.md#runtime-for-the-updated-scripts).
Do not change shared cluster environments.

## Current scope

Native coordinate resolution, lazy plane extraction, actual selected-bin labels,
bin-edge plotting, and nonorthogonal physical geometry are implemented.
Mask/coverage handling and automatic intensity normalization are **TO BE UPDATED**;
see [analysis status](../docs/reciprocal-analysis-status.md). The current automatic
logarithmic limits retain the count-oriented lower floor of 1. For normalized
sub-unit data, provide explicit `--vmin` and `--vmax`; signed-intensity views are deferred.

## Coordinates and physical geometry

- Resolve axes from `NXdata.nxaxes`: H/K/L and Qh/Qk/Ql are accepted regardless of
  native storage order. Unknown or ambiguous mappings fail explicitly.
- HK fixes L, HL fixes K, and KL fixes H. `--coord` always means a physical r.l.u.
  coordinate, including integer-valued arguments. Extraction reads one plane.
- Selection uses the bin containing the requested coordinate. The figure labels
  its actual center and records the requested value if different. Out-of-range
  coordinates fail instead of silently taking an edge plane.
- `--coordinates auto` uses native `NXentry/sample/unit_cell` metadata when available,
  or `--unit-cell` as an explicit override. Without a cell it draws a labeled r.l.u. view.
- `--coordinates physical` requires a valid cell; `--coordinates rlu` requests
  rectangular H/K/L coordinate axes. Missing cells are never replaced by an invented cubic cell.

Physical rendering uses the reciprocal metric including all cell angles. For an
HK plane, its Cartesian mesh is
`X = a* H + b* cos(gamma*) K`, `Y = b* sin(gamma*) K`, with equal display aspect.
HL/KL use the corresponding reciprocal basis. The physical axes are plane-local
coordinates in Å⁻¹ **without a 2π factor**, relative to the fixed-coordinate origin.
They are not mislabeled H/K/L indices. A length-ratio aspect adjustment after a
fixed shear is insufficient for unequal, oblique reciprocal axes.

## CLI examples

Run from this skill directory with the updated library available:

```bash
python scripts/plot_slice.py --nxs volume.nxs --plane HK --coord 0.0 --output slice.png
python scripts/plot_slice.py --nxs volume.nxs --plane HL --coord 0.0 --coordinates rlu --vmin 0.01 --vmax 10 --output slice_HL.png
python scripts/plot_summary.py --nxs volume.nxs --unit-cell "5.0027,5.0027,4.0548,90,90,120" --coordinates physical --output summary.png
```

The summary uses shared intensity limits across its three planes. Physical
panels preserve angles and relative lengths within each plane; independently
laid-out panels do not promise identical pixels per Å⁻¹ across the whole figure.

## Python extraction and rendering

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nexusformat.nexus as nx
from nxs_analysis_tools.reciprocal import (
    resolve_nxdata, reciprocal_slice, resolve_unit_cell, physical_mesh,
)

root = nx.nxload("volume.nxs")
data = resolve_nxdata(root)
section = reciprocal_slice(data, "HK", 0.0)
cell = resolve_unit_cell(data)
if cell is None:
    raise ValueError("Supply a measured unit cell for this physical-coordinate example")
x, y = physical_mesh(section, cell)
fig, ax = plt.subplots()
mesh = ax.pcolormesh(x, y, section.values, shading="flat")
ax.set_aspect("equal")
ax.set_xlabel("q parallel to H* (Å⁻¹)")
ax.set_ylabel("q perpendicular to H* in HK (Å⁻¹)")
ax.set_title(f"HK at L={section.actual_coord:g} r.l.u.")
fig.colorbar(mesh, ax=ax, label="Intensity (input units)")
fig.savefig("slice_physical.png")
plt.close(fig)
```

Keep headless rendering and lazy slicing. Integer locators apply to the r.l.u.
view; physical Cartesian axes use physical-coordinate ticks, not Miller-index labels.

## Related work

- [GIF scans](../reciprocal-space-animation/SKILL.md).
- [Linecuts — TO BE UPDATED](../reciprocal-space-linecuts/SKILL.md).
- [Temperature analysis — detailed validation TO BE UPDATED](../temperature-series-analysis/SKILL.md).
- [Master guide and cluster execution](../reciprocal-space-analysis/SKILL.md).
