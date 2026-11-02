# Reciprocal analysis status

| Area | Status | Scope |
| --- | --- | --- |
| Native slices and physical geometry | **IMPLEMENTED** | Shared NeXus axis-name resolution, lazy canonical planes, selected-bin labels, real bin edges, and full reciprocal-metric geometry in the analysis-library fork. |
| Volume and temperature GIF rendering | **IMPLEMENTED within stated scope** | Both use the shared slicer and physical mesh. Volume integer-coordinate selection is corrected. Temperature identity/alignment and streaming remain deferred below. |
| Standalone linecuts | **TO BE UPDATED — all work deferred** | Recipes and the existing CLI are retained as historical examples. Window meaning, backend equivalence, integration, background and uncertainty handling are not validated. |
| Temperature wrapper API calls | **Compatibility repaired** | Explicit cut arguments, supported waterfall plotting, fitted-parameter names, and axis-name resolution. Mixed native axis orderings are rejected. This is not quantitative validation. |
| Detailed temperature analysis | **TO BE UPDATED** | Peak interpretation, fit quality and uncertainty treatment remain pending. Existing plots are exploratory. |
| Temperature discovery and cross-temperature grid checks | **ON HOLD — TO BE UPDATED** | Acquisition selection, repeated temperatures, normalization comparability, grid alignment and interpolation remain pending. |
| Masks and logarithmic display handling | **ON HOLD — TO BE UPDATED** | No new mask, missing-data or logarithmic-display policy is introduced by the API repair. |
| Export and memory work | **ON HOLD — TO BE UPDATED** | No new result-table export, streaming or memory redesign is included. The temperature scripts currently save figures only. |

See the [temperature skill](../temperature-series-analysis/SKILL.md) and the
[deferred linecut skill](../reciprocal-space-linecuts/SKILL.md). API smoke tests
use tiny synthetic data and do not establish scientific validity for a real
temperature series.

## Runtime for the updated scripts

The slice/GIF scripts and temperature API adapter require
`nxs_analysis_tools.reciprocal` from
[the library fork branch](https://github.com/Tieqiong/nxs_analysis_tools/tree/codex/reciprocal-slicing).
Installing that checkout in a chosen local environment prepares its generated
version module normally. A source-only checkout also needs that ignored module;
with `setuptools_scm` already available, prepare it without changing installed packages:

```bash
cd /path/to/nxs_analysis_tools
python -m setuptools_scm --force-write-version-files
export PYTHONPATH="/path/to/nxs_analysis_tools/src${PYTHONPATH:+:$PYTHONPATH}"
```

Use an environment with the library's dependencies. Do not install packages into
shared immutable beamline environments. Verification used tiny synthetic data with
the declared compatible `nexusformat` 1.0.8 and additionally the local 2.0.2 runtime;
this does not change the library's declared dependency range.
