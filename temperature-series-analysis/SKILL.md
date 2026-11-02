---
name: temperature-series-analysis
description: >-
  API compatibility repaired; detailed temperature analysis is TO BE UPDATED.
  Outputs remain exploratory, not quantitatively validated. Discovery/grid,
  masks/log, and export/memory work are on hold.
  Analyze CHESS temperature-dependent diffraction datasets using TempDependence and
  TempDict from nxs_analysis_tools. Use when performing batch operations across an entire
  temperature series at once (e.g., batch Scissors linecuts), generating waterfall plots,
  (Q, T) false-color intensity heatmaps, multi-temperature peak fitting, tracking order
  parameters across phase transitions, or exporting 4D datasets (to_xtec) for clustering.
---

# CHESS Temperature-Dependent Data Analysis Skill (`temperature-series-analysis`)

> **Status: API compatibility repaired; detailed analysis TO BE UPDATED.**
> The wrappers now pass explicit cut arguments, use supported plotting calls,
> resolve physical cut axes, and map the fitted parameter names correctly.
> This does not make their results ready for quantitative interpretation.
> Temperature discovery/grid validation, masks/log handling, and exports/memory
> work are on hold. All standalone linecut work is also **TO BE UPDATED**.
> See [analysis status](../docs/reciprocal-analysis-status.md).

This skill provides operational workflows, API runbooks, and reference scripts for analyzing multi-temperature reciprocal space series at the CHESS ID4B/QM2 beamline using `nxs_analysis_tools.chess.TempDependence`.

---

## 1. Key Capabilities of `TempDependence`

The `TempDependence` class wraps a collection of temperature datasets into a unified analysis object:

1. **Polymorphic Temperature Indexing (`TempDict`)**:
   Temperatures can be queried transparently using numeric floats, integers, or string path conventions without key errors:
   ```python
   td.datasets[15.5] == td.datasets['15.5'] == td.datasets['15p5']
   ```
2. **Automated Discovery & Lazy Loading**:
   Scans sample directories, discovers all temperature subdirectories or files, and mounts NeXus volumes lazily ($O(1)$ memory).
3. **Batch Operations Across All Temperatures in One Call**:
   Operations like `Scissors` linecuts are applied across **all loaded temperatures simultaneously**, eliminating tedious manual temperature loops.
4. **Built-in Thermal Evolution Visualizations**:
   Native methods generate waterfall linecut plots, $(Q, T)$ false-color heatmaps, integration window diagnostic overlays, and peak fitting comparisons.
5. **Phase Transition Order Parameters**:
   Fit reflection peaks across temperatures and automatically plot peak height, integrated area, or FWHM as a function of temperature ($I(T)$).

---

## 2. Standard Workflow & API Runbook

### Step 1: Initialization & Temperature Discovery — validation ON HOLD / TO BE UPDATED

```python
from nxs_analysis_tools.chess import TempDependence

# Initialize pointing to sample root directory
# e.g. /nfs/chess/id4baux/2026-3/yi-4791-b/processed_old_way/FeGeSb/sample1A/
sample_dir = "/path/to/sample_root"
td = TempDependence(sample_dir)

# 1. Discover all temperature scans
td.find_temperatures()
print("Discovered temperatures:", td.temperatures)

# 2. Lazy load all datasets matching a specific pattern (e.g. streaming lite volumes)
td.load_datasets(file_ending="3rot_hkli_lite.nxs", print_tree=False)
```

---

### Step 2: Batch Linecut Extraction (`td.cut_data()`)

Instead of iterating through temperatures with a for-loop, configure the lattice and cut window once on `TempDependence`:

```python
# 1. Set unit cell (a, b, c, alpha, beta, gamma)
td.set_lattice_params((5.0027, 5.0027, 4.0548, 90.0, 90.0, 120.0))

# 2. Resolve H from the actual stored axis labels; require one native layout.
from nxs_analysis_tools.reciprocal import resolve_reciprocal_axes
axis_maps = [resolve_reciprocal_axes(td.datasets[T]) for T in td.temperatures]
if not axis_maps or any(m != axis_maps[0] for m in axis_maps):
    raise ValueError("No loaded data or mixed native axis ordering; process separately")

# 3. These center/window tuples are for native (H,K,L) order only.
# For native (Ql,Qk,Qh), use center=(0,0,1), window=(0.1,0.1,0.5).
# Scissors window values are half-widths. Pass them explicitly to cut_data.
center = (1.0, 0.0, 0.0)
window = (0.5, 0.1, 0.1)
if tuple(axis_maps[0][a] for a in ("H", "K", "L")) != (0, 1, 2):
    raise ValueError("Adapt the native-order tuples before running this HKL example")
td.cut_data(center=center, window=window, axis=axis_maps[0]["H"])
```

---

### Step 3: Multi-Temperature Visualizations

#### A. Waterfall Linecut Plot
Visualizes the evolution of the 1D linecut profile stacked vertically across temperatures:
```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(7, 8), dpi=200)
td.plot_linecuts(
    ax=ax,
    vertical_offset=500.0,  # Vertical spacing between temperature traces
)
# TempDependence supplies its supported line colors; cmap is not accepted here.
ax.set_title(r"Temperature Evolution through $(1, 0, 0)$ Reflection")
plt.tight_layout()
plt.savefig("waterfall_linecuts.png", dpi=300)
plt.close(fig)
```

#### B. $(Q, T)$ 2D False-Color Heatmap — grid validation ON HOLD
Renders a continuous intensity surface where the x-axis is reciprocal coordinate $Q$, the y-axis is temperature $T$, and color represents scattering intensity:
the current plotting API assumes matching cut coordinates across temperatures.
It does not check or align grids; that validation remains **TO BE UPDATED**.
```python
fig, ax = plt.subplots(figsize=(6, 5), dpi=200)
td.plot_linecuts_heatmap(ax=ax, cmap="inferno")
ax.set_xlabel(r"$H$ (r.l.u.)")
ax.set_ylabel(r"Temperature (K)")
ax.set_title(r"$(Q, T)$ Intensity Heatmap")
plt.tight_layout()
plt.savefig("linecuts_heatmap.png", dpi=300)
plt.close(fig)
```

#### C. Integration Window Overlay Diagnostic
Verifies the integration bounds superimposed on a real reciprocal space slice:
```python
fig, ax = plt.subplots(figsize=(6, 5), dpi=200)
td.plot_integration_window(temperature=300, ax=ax)
plt.savefig("window_diagnostic.png", dpi=300)
plt.close(fig)
```

---

### Step 4: Exploratory Peak Fitting — quantitative analysis TO BE UPDATED

```python
# 1. Define model components (e.g. Gaussian peak + Linear background)
from lmfit.models import GaussianModel, LinearModel

model = GaussianModel(prefix="peak_") + LinearModel(prefix="bg_")
td.set_model_components(model)

# 2. Generate parameter hints and fit across all temperatures
td.guess()
td.fit(verbose=False)

# 3. Print fit report
td.print_fit_report()

# 4. Plot order parameter (peak height vs temperature)
fig, ax = plt.subplots(figsize=(6, 4), dpi=200)
td.plot_order_parameter(param_name="peak_height", ax=ax, marker="o", color="crimson")
ax.set_xlabel("Temperature (K)", fontsize=11)
ax.set_ylabel("Peak Intensity (counts)", fontsize=11)
ax.set_title("Exploratory fitted peak height vs temperature", fontsize=12)
ax.grid(True, linestyle="--", alpha=0.5)
plt.tight_layout()
plt.savefig("order_parameter.png", dpi=300)
plt.close(fig)
```

---

### Step 5: Downstream Export to 4D NeXus (`td.to_xtec()`) — ON HOLD / TO BE UPDATED

When preparing a complete temperature series for unsupervised clustering in `xtec-gpu-analysis`:
the following historical example has not received the deferred grid, export or
memory review. Do not infer streaming behavior or validated series alignment.
```python
# Compiles a 4D NeXus array (shape: N_T x N_H x N_K x N_L)
td.to_xtec(
    filepath="/path/to/sample/xtec_data.nxs",
    overwrite=False,
)
```

---

## 3. Standalone CLI Reference Scripts

This skill includes exploratory CLI tools in [`scripts/`](./scripts/). Only the
API compatibility repair is complete. Both require the updated
`nxs_analysis_tools.reciprocal.resolve_reciprocal_axes` helper. Center/window
tuples follow the data's native axis order; mixed ordering across temperatures
is explicitly unsupported. Equal axes alone do not validate equal grids.

1. **`batch_temp_linecuts.py`**:
   Discovers all temperatures in a sample folder, extracts a batch `Scissors` cut, and exports both a waterfall plot and a $(Q, T)$ heatmap:
   ```bash
   python scripts/batch_temp_linecuts.py \
     --sample-dir /path/to/sample_root \
     --file-ending "3rot_hkli_lite.nxs" \
     --axis H \
     --center "1.0, 0.0, 0.0" \
     --window "0.5, 0.1, 0.1" \
     --outdir ./temperature_cuts/
   ```

2. **`temp_order_parameter.py`**:
   Fits a reflection across temperatures and plots a selected peak parameter:
   ```bash
   python scripts/temp_order_parameter.py \
     --sample-dir /path/to/sample_root \
     --file-ending "3rot_hkli_lite.nxs" \
     --axis H \
     --center "1.0, 0.0, 0.0" \
     --window "0.5, 0.1, 0.1" \
     --output order_parameter.png
   ```

   CLI quantities map to lmfit parameters: `peakheight` → `peak_height`,
   `area` → `peak_amplitude`, `sigma` → `peak_sigma`, `center` → `peak_center`.
   The default height is width-dependent; neither height nor area alone is a
   validated thermodynamic order parameter. Fit quality, uncertainties and
   quantitative interpretation remain **TO BE UPDATED**. Figures are the only
   current outputs; numerical result exports remain on hold.

---

## 4. Sister Skills & Integration

- For **Single-Volume Slicing & Plotting**: Consult [`reciprocal-space-plotting`](../reciprocal-space-plotting/SKILL.md).
- For **Animations (GIF/MP4)**: Consult [`reciprocal-space-animation`](../reciprocal-space-animation/SKILL.md).
- For **Single-Volume 1D Linecuts — ALL TO BE UPDATED**: See the deferred [`reciprocal-space-linecuts`](../reciprocal-space-linecuts/SKILL.md).
- For **GPU Clustering (XTEC)**: Consult [`xtec-gpu-analysis`](../xtec-gpu-analysis/SKILL.md) after running `td.to_xtec()`.
