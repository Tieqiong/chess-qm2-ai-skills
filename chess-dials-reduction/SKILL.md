---
name: chess-dials-reduction
description: Single-crystal diffraction data reduction and integration pipeline using DIALS at CHESS ID4B/QM2. Converts raw Pilatus 6M CBF frame sweeps into crystallographic reflection datasets (.ins, .hkl) ready for structural refinement in Jana2020 or Olex2/SHELXL.
---

# CHESS DIALS Data Reduction & Crystallographic Refinement Pipeline (`chess-dials-reduction`)

This skill automates the data reduction of single-crystal synchrotron X-ray diffraction datasets collected on the Pilatus 6M detector at the **CHESS ID4B/QM2 beamline** using the **DIALS** (Diffraction Integration for Advanced Light Sources) processing framework.

The output of this pipeline is a dual reflection bundle (`for_refinement/`) containing:
1. **Unmerged SHELX (`unmerged.ins`, `unmerged.hkl`)**: Suitable for **Jana2020** (absorption modeling, twin refinement, modulated structures).
2. **Merged SHELX (`merged.ins`, `merged.hkl`)**: Suitable for **Olex2 / SHELXL** (rapid structure solution and standard least-squares refinement).

---

## 1. Environment & Remote Compute Etiquette

### 1.0 First-Use SSH Access Check (Mandatory Pre-Flight)
Before the first remote DIALS reduction task, establish the user's CLASSE username and login host (`lnx201.classe.cornell.edu`). Test an existing connection with `BatchMode=yes` and a short connection timeout:
```bash
ssh -o BatchMode=yes -o ConnectTimeout=15 <username>@lnx201.classe.cornell.edu 'echo CHESS_SSH_OK'
```
*(On Windows PowerShell: `ssh -o BatchMode=yes -o ConnectTimeout=15 "${classeUser}@lnx201.classe.cornell.edu" 'echo CHESS_SSH_OK'`)*.

If unattended authentication fails:
1. Explain that a password or Duo login in a separate terminal will **not** automatically authenticate later commands run by the agent or background subprocesses.
2. Offer to set up a dedicated local Ed25519 SSH key (`~/.ssh/id_ed25519_classe`), or use another authentication method approved by the facility. Consult the [SSH First-Time Setup & Non-Interactive Access Guide](references/ssh-first-use.md) before creating a key or installing its public half.
3. Obtain the user's choice of passphrase protection. Prefer an existing, supported SSH agent for a protected key; use a key without a passphrase only when the user explicitly chooses that option. Reuse suitable existing keys and configuration rather than overwriting them.
4. Keep the private key on the user's computer. Install only the public key on the user's remote account, preserving all existing authorized-key entries. Have the user enter any password or second factor directly in an interactive terminal, rather than in chat or a script. (For Windows users, use the safe Base64-encoded installation script in the guide to avoid PowerShell quoting bugs and CRLF line ending corruption).
5. Complete setup only after a fresh `BatchMode=yes` connection succeeds and returns `CHESS_SSH_OK`. Key creation, an installation-success message, or a working interactive login alone is insufficient.
6. Once access is verified, resume the user's scientific task immediately. SSH authentication does not replace compute-node allocation rules or any required job-submission approval.

### 1.1 Cluster Etiquette: ZERO Compute on Login Node (`lnx201`)
> [!CAUTION]
> **STRICT PROHIBITION ON DATA PROCESSING ON `lnx201` (LOGIN NODE)**
>
> `lnx201` is a shared interactive login gateway for all CLASSE/CHESS beamline users. **NO data processing, spot finding (`dials.find_spots`), indexing (`dials.index`), mask conversions, refinement, or integration may be run directly on `lnx201`.**
> 
> - **Permitted on `lnx201`**: Filesystem navigation, reading/editing scripts, checking logs (`tail -f`), monitoring queues (`qstat`), and submitting jobs (`qsub`).
> - **Mandatory Compute Pattern**:
>   - **Batch Execution (`qsub`)**: BOTH Stage 1 (pilot import, spotfinding, indexing, Bravais settings) and Stage 2 (reindexing, refinement, integration, scaling, export) **MUST be submitted as SGE batch jobs** to compute nodes (`all.q@lnx307*`, `lnx311*`, `lnx312*`, `lnx313*`).
>   - **Interactive Compute (`qrsh`)**: If interactive debugging or inspection is strictly required, the user or agent must request an interactive allocation via `qrsh -q interactive.q -l mem_free=64G -pe sge_pe 8` and execute commands **only after the shell transitions to the allocated compute worker node**.

### 1.2 Software & Environment
On CLASSE cluster compute nodes (`lnx307`, `lnx311`, `lnx312`, `lnx313`), DIALS is activated via:
```bash
source /nfs/chess/sw/dials_sgomezalvarado/dials_env.sh
```
* Python tools interacting with DIALS internal C++ data structures (`scitbx.array_family.flex`, `dxtbx`) must be executed via `dials.python`.

### 1.3 Laboratory Frame and Per-Sweep Geometry

For nominal transmission geometry (theta=0, chi=90 degrees), the verified downward spindle convention is `geometry.goniometer.axes=0,-1,0`. For tilted sweeps, derive the axis from that run's motor conventions and verify predicted versus observed spots. Do not reuse the nominal vector for every sweep. The former Eulerian formula and numerical examples disagreed and have been removed; no unverified replacement convention is assumed.

The wrapper processes **one CBF sweep per working directory**. Reduce tilted sweeps separately using their calibrated axes; align their indexing and scale jointly afterward (section 4.4). Directory grouping alone is not evidence of common geometry or one crystal.

### 1.4 Detector Calibration

Check the run's CBF headers against its calibration, energy, detector position and raster convention. A stale beam centre can ruin indexing/profile estimation, but neither a header nor a calibration from a different run is automatically correct.

`--poni-file` implements the restricted, **zero-rotation** conversion
`origin=(-1000*Poni2, +1000*Poni1, -1000*Distance)` for panel fast=+X, slow=-Y, incident beam toward -Z. PONI lengths are metres; DIALS lengths are millimetres. The wrapper now rejects nonzero Rot1/Rot2/Rot3 instead of silently discarding them.

For a tilted detector, supply `--geometry-phil` containing the validated full detector origin and fast/slow axes in the image reader's convention. This is mutually exclusive with `--poni-file` and `--detector-origin`. Confirm the imported panel frame and beam direction. These options describe starting geometry; subsequent refinement can change it. Retain calibration-fixed controls when the absolute cell or geometry matters. See [refinement decisions](references/refinement_decisions.md).

## 2. Directory Conventions

- Raw: `/nfs/chess/id4b/{cycle}/{experiment}/raw6M/{sample}/{mount}/{temp}/{scan}/`
- Calibration: `/nfs/chess/id4baux/{cycle}/{experiment}/calibrations/`
- Output: `/nfs/chess/id4baux/{cycle}/{experiment}/dials/{sample}/{mount}/{temp}/{scan}/`
- Refinement bundle: `<work_dir>/for_refinement/`

Use a new working directory for each processing choice and preserve the baseline. A pilot's threshold, resolution cutoff, cell and calibration are dataset-specific inputs, not beamline constants.

## 3. Workflow and Working Assumptions

Raw sweep -> calibrated import/mask -> spot finding -> indexing/Bravais assessment -> geometry refinement -> integration -> symmetry/scaling -> unmerged observations and merged export -> atomic solution/refinement.

Start with a plausible lattice and the simplest stable geometry/scaling model. Proceed with a documented working structure; unresolved mechanism or exact symmetry does not prevent a useful refinement. Add complexity when residuals or structural interpretation warrant it. The [decision guide](references/refinement_decisions.md) explains how to choose and test assumptions without turning every uncertainty into a stop condition.

## 4. Execution

### 4.1 Stage 1: Import, Index and Assess the Lattice

Run inside the allocated compute job:

```bash
python3 scripts/orchestrate_dials.py stage1 \
    --work-dir /path/to/new/sweep1 \
    --raw-dir /path/to/raw/sweep1 \
    --poni-file /path/to/zero_rotation_calibration.poni \
    --edf-mask /path/to/mask.edf \
    --goniometer-axes=0,-1,0 \
    --unit-cell 'a,b,c,alpha,beta,gamma' \
    --space-group 'P 63 2 2' --nproc 24
```

Replace symbolic cell values with six numbers. Use `--geometry-phil` instead of `--poni-file` when rotations or a different panel convention are required. Missing explicitly requested inputs are errors.

The wrapper generates/combines detector masks, finds spots, indexes and runs `dials.refine_bravais_settings`. Its historical spot-finding defaults (`--global-threshold 5000`, `--d-min 0.75`) are pilot settings: lower the threshold or expand resolution when weak/superlattice reflections are part of the task. A high-threshold spot list cannot establish the absence of weak scattering.

Indexing is unconstrained by default. `--constrain-symmetry` requires both cell and space group and is appropriate for a reliable known lattice. Reference cell/space group otherwise guide Bravais ranking only. The matcher accepts a space-group symbol through `--target-space-group` or a Bravais label such as `hP` through `--target-lattice`. It compares axis permutations as a reference-matching heuristic, preserving DIALS' actual change-of-basis operator. A matching metric does not determine intensity symmetry or the atomic space group.

### 4.2 Review the Bravais Setting

Inspect candidate metric fit, centroid residuals, indexed fraction and consistency with the intended lattice. Present the proposed setting and its DIALS `cb_op` for confirmation before Stage 2. Respect any existing authorization for that exact choice. A reference-match ranking does not override poor fits or extra lattices.

### 4.3 Stage 2: Integrate, Scale and Export

A stable first-pass example:

```bash
python3 scripts/orchestrate_dials.py stage2 \
    --work-dir /path/to/sweep1 \
    --bravais-setting 12 --cb-op b,c,a \
    --scan-varying False --fix-cell \
    --scaling-model physical --absorption-level medium \
    --composition 'K Co Te O' --nproc 24
```

Choose the setting and chemistry for the actual sample. The default fixed-cell/static fit is a conservative starting choice, **not a universal requirement**. `--no-fix-cell` allows cell refinement; `--scan-varying True` or `Auto` allows crystal scan variation. A cell kept constant through a scan (`unit_cell.force_static=True` in DIALS) can still be refined and is different from `crystal.fix=cell`. The wrapper is not a detector-motion/window-integration implementation; use a validated specialized workflow when residuals demonstrate that need.

Scaling choices:

- `--scaling-model scale-only`: one KB scale per input dataset, no KB decay term.
- `--scaling-model physical --absorption-level none|low|medium|high`: choose absorption flexibility according to data and correction magnitude. Medium is the wrapper default; high is an explicit stronger correction, not an automatic improvement.
- Default symmetry handling calls `dials.symmetry`. `--keep-input-symmetry` preserves the selected model; `--space-group 'P 1'` explicitly resets scaling symmetry for a lower-symmetry comparison. These alternatives are mutually exclusive.
- `--anomalous True` keeps Bijvoet distinctions during scaling. It does not make a Friedel-averaged merged export anomalous.

Testing high-symmetry scaling when raw correlations look poor is reasonable. A clean result supports a **working high-symmetry average structure**; it does not prove that lower-symmetry intensity differences were instrumental. For sequential lower-symmetry tests, keep unmerged original indices and use the same minimally assumed scaling symmetry, corrections, observations and weights. Compare structural improvements against parameter cost, physicality and prediction; see the [decision guide](references/refinement_decisions.md).

The corrected export path is:

```bash
dials.export scaled.expt scaled.refl format=shelx intensity=scale mtz.min_isigi=None \
    shelx.composition='K Co Te O' shelx.scale=False \
    shelx.hklout=for_refinement/unmerged.hkl \
    shelx.ins=for_refinement/unmerged.ins
dials.merge scaled.expt scaled.refl output.html=None output.mtz=for_refinement/merged.mtz assess_space_group=False truncate=False
iotbx.reflection_file_converter for_refinement/merged.mtz \
    --shelx=for_refinement/merged.hkl --label=IMEAN,SIGIMEAN
cp for_refinement/unmerged.ins for_refinement/merged.ins
```

`dials.merge` writes MTZ, not `.expt`/`.refl`. `merged.hkl` contains mean intensities averaged over Friedel pairs; keep the unmerged bundle and MTZ for anomalous or alternate-symmetry work. Merging in a higher group loses differences that later lowering the atomic symmetry cannot recover.

**Composition and numerical precision:** DIALS `shelx.composition` means asymmetric-unit contents, not necessarily the bulk chemical formula. An element list writes placeholder UNIT counts; verify UNIT, ZERR/Z, occupancy and special-position multiplicities before refinement. `--shelx-scale True` enables DIALS' intensity-field rescaling where supported; audit weak/negative intensities and sigmas for rounding or overflow under either choice. The multiplicative output scale must apply equally to I and sigma(I).

### 4.4 Multiple Sweeps

Import and integrate each tilted sweep with its own validated geometry. Resolve indexing ambiguity before combining intensities, for example:

```bash
dials.cosym sweep1/integrated.expt sweep1/integrated.refl \
    sweep2/integrated.expt sweep2/integrated.refl \
    sweep3/integrated.expt sweep3/integrated.refl \
    space_group='P 63 2 2'
dials.scale symmetrized.expt symmetrized.refl \
    model=physical absorption_level=medium anomalous=True
```

Use the justified common group for the task, not the example group blindly. Check shared-reflection agreement across geometries, unit-cell compatibility and scaling connectivity. The wrapper itself does not execute this multi-sweep alignment stage.

### 4.5 Batch Templates and Local Verification

The three scripts under `example_job_scripts/` remain CLASSE SGE wrappers. Set `DIALS_ENV` and `SKILLS_DIR` for your installation. Extra CLI arguments may be passed after the documented positional arguments. Show the concrete job and obey the repository's submission authorization rules; do not submit compute as part of a source-code review.

Run regression tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
# Also run with the installed DIALS interpreter for cctbx/interface checks:
dials.python -m unittest discover -s tests -v
```

Tests exercise command construction and small synthetic data; they do not establish scientific accuracy for a new beamline dataset.

## 5. Refinement Handoff

Both Jana2020 and Olex2/SHELXL can use appropriate unmerged data. The merged bundle is a convenience for an adopted average structure, not a requirement of SHELXL. HKLF 4 alone does not carry measurement geometry for a fresh analytical absorption correction or satellite indices for general superspace refinement. Retain original experiment/reflection files and appropriate richer exports for those tasks.

Follow the [import guide](references/jana_olex_import_guide.md), then refine the atomic model with wavelength-specific scattering corrections, sensible displacement parameters, controlled occupancy/extinction choices and residual-density review. Use stronger comparisons when choosing between models; routine validation should help obtain a usable refinement rather than postpone it indefinitely.
