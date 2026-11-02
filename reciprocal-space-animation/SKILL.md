---
name: reciprocal-space-animation
description: >-
  Generate GIFs that scroll through native reciprocal H/K/L slices or show a
  verified temperature series. Use metadata-based plane selection and optional
  physical reciprocal geometry. MP4 and bounded-memory streaming are not yet
  implemented; temperature discovery, grid reconciliation and log/mask handling
  have documented remaining limitations.
---

# Reciprocal-space GIFs

Use the standalone scripts below with an environment containing the updated
`nxs_analysis_tools.reciprocal` module, `nexusformat`, Matplotlib and Pillow.
The scripts read each plane lazily; they do not need the entire 3D signal in memory.
Run beamline work on an allocated compute worker, following the repository's
[compute rules](../GEMINI.md).

## Native planes and coordinates

Both scripts use `resolve_nxdata` and `reciprocal_slice` from
`nxs_analysis_tools.reciprocal`. Native axis metadata determines storage order:
legacy `[H,K,L]`, NXRefine `[Ql,Qk,Qh]`, and other valid permutations resolve to
the same canonical display. HK fixes L, HL fixes K, and KL fixes H. Frame titles
show the actual selected reciprocal-bin center, which may differ slightly from
the requested coordinate.

The scripts render bin edges with `pcolormesh`, so the plot geometry comes from
native coordinates rather than a square image with assumed axis order. Volume
scans iterate the named axis's bin centers; integer-valued axis arrays are not
interpreted as raw array indices.

## Reciprocal metric

Both CLIs accept `--coordinates auto|rlu|physical` and
`--unit-cell a,b,c,alpha,beta,gamma`:

- `auto` is the default. A native or explicit unit cell selects physical geometry;
  otherwise the display remains in r.l.u.
- `rlu` shows named H/K/L coordinates on a rectangular schematic grid.
- `physical` requires a valid cell and uses its full reciprocal metric, including
  unequal reciprocal lengths and non-right inter-axis angles. No cubic fallback
  is invented. An explicit cell overrides native metadata.

Physical axes are plane-local Cartesian reciprocal coordinates in Å⁻¹, using the
crystallographic convention without a factor of 2π. The horizontal direction is
parallel to the first reciprocal basis vector in the plane; the vertical direction
is perpendicular to it within that plane. The origin is the point where the two
free indices are zero at the fixed index of the slice. These axes are not H/K/L
in r.l.u.; equal plot aspect preserves physical lengths and angles.

## Scroll through a volume

```bash
python scripts/animate_volume.py \
  --nxs path/to/volume.nxs --axis L --stride 2 --fps 12 \
  --coordinates auto --output scroll_L.gif
```

For explicit physical geometry:

```bash
python scripts/animate_volume.py \
  --nxs path/to/volume.nxs --axis L \
  --coordinates physical --unit-cell 4,4,6,90,90,120 \
  --vmin 1 --vmax 10000 --output scroll_L_physical.gif
```

`--vmin`, `--vmax`, and `--cmap` control the existing fixed color scale. Bounds are
sampled before rendering and remain unchanged between frames. This is useful for
comparing intensities, but does not by itself establish intensity normalization
between datasets.

## Animate a verified temperature series

```bash
python scripts/animate_temp_series.py \
  --pattern 'path/to/sample/[0-9]*/3rot_hkli.nxs' \
  --plane HK --coord 0.0 --coordinates auto \
  --output temperature_evolution.gif
```

Use already verified temperature directories and a common reciprocal grid. Native
storage order may differ between files; the slicer handles that. The display mesh
and physical cell are taken from the first temperature. Grid registration,
resampling and comparison of changing cells are not implemented here.

## Deferred work and known limits

The following issues are intentionally left for separate work:

- **Temperature discovery and grid reconciliation:** the retained filename
  heuristic can mistake digits in sample names for temperatures, and duplicate
  temperatures overwrite one another. Inspect the selected temperatures and use
  numeric temperature directories. Differing grids can still be displayed on the
  first frame's mesh; these scripts do not validate or repair cross-temperature
  registration, coverage, exposure or normalization.
- **Masks and log normalization:** masks are passed through the shared slicer,
  but the animation's sampled color-limit calculation has not been revised. Its
  automatic lower bound is still at least 1, which is unsuitable for normalized
  intensities below 1. Nonfinite values and mask-aware statistics need follow-up.
  Both CLIs accept explicit `--vmin` and `--vmax` limits as a practical override;
  this does not change the deferred automatic-normalization behavior.
- **Export and memory:** only GIF is supported. A `.mp4` path is rejected before
  loading data. Pillow keeps rendered frames in memory, so figure reuse does not
  make long GIFs bounded-memory. MP4/streaming export and frame-budget handling
  remain deferred. No scan-range or integration-window interface is added here.

The figure and mesh are reused within each movie and closed even if saving fails.
Do not describe that cleanup as a solution to Pillow's frame-buffer memory growth.

## Related tools

- [Static reciprocal slices](../reciprocal-space-plotting/SKILL.md)
- [Linecuts](../reciprocal-space-linecuts/SKILL.md)
- [Temperature-series analysis](../temperature-series-analysis/SKILL.md)

Focused tests in [test_reciprocal_animation.py](../tests/test_reciprocal_animation.py)
compare native axis orders, validate oblique physical geometry, and save/reopen
tiny real GIFs. They do not validate a particular experimental dataset.
