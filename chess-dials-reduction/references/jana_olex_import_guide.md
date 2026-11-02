# Jana2020 & Olex2 Import Guide for DIALS Refinement Bundles

This document explains how to import reflection data exported from the `chess-dials-reduction` workflow into **Jana2020** and **Olex2 / SHELXL**.

---

## 1. Directory Structure of Refinement Files

Upon completion of Stage 2, the pipeline creates a standardized folder:
```text
<work_dir>/for_refinement/
├── unmerged.hkl    # Unmerged reflections (HKLF 4) with all symmetry-equivalent observations
├── unmerged.ins    # SHELX instruction header matching unmerged reflections
├── merged.hkl      # Merged reflections (HKLF 4) with symmetry-averaged F^2 and sigmas
├── merged.ins      # SHELX instruction header matching merged reflections
├── merged.mtz      # Mean and, when requested, anomalous merged arrays
└── README.txt      # Processing choices and output interpretation
```

---

## 2. Importing into Jana2020

Jana2020 is designed for advanced crystallographic refinement, including standard 3D periodic structures, modulated incommensurate/commensurate structures, composite crystals, and multipole refinements.

### Recommended Input: Unmerged Reflections (`unmerged.ins` + `unmerged.hkl`)
Unmerged HKLF 4 retains individual intensities and original indices for appropriate refinement. It does not contain the measurement geometry needed for a new analytical absorption correction, nor general satellite-order indices. Preserve the DIALS experiment/reflection files and export richer geometry or modulation data when required. Avoid applying an additional absorption correction blindly to already corrected data.

### Step-by-Step Import:
1. **Create New Project**:
   - Open Jana2020.
   - Go to **File $\rightarrow$ New Structure**.
   - Set project directory and structure title.
2. **Select Reflection Format**:
   - In the import dialog, select **SHELX format (*.ins, *.hkl)**.
   - Browse to `for_refinement/unmerged.ins` (Jana automatically pairs with `unmerged.hkl`).
3. **Verify Cell and Symmetry**:
   - Jana2020 reads unit cell parameters and space group symmetry from `unmerged.ins`.
   - Confirm or adjust the space group if non-standard settings or alternate origins were chosen.
4. **Modulated / Commensurate Structures (Optional)**:
   - Only after indexing/integrating the relevant satellites or supercell reflections and preparing the appropriate Jana input:
     - Under **Basic Parameters $\rightarrow$ Symmetry**, change dimension from $3\text{D}$ to $(3+d)\text{D}$.
     - Define the modulation vectors $\mathbf{q}$ (e.g. $\mathbf{q} = (\frac{1}{12}, 0, 0)$ or similar modulation coordinates).
     - Verify main/satellite assignments against the supplied indices. Changing the project dimension or entering q cannot recover satellite intensities missing from a parent-lattice reduction.
5. **Solve / Refine**:
   - Proceed to **Tools $\rightarrow$ Solve** (Superflip) or import starting atomic coordinates.

---

## 3. Importing into Olex2 / SHELXL

Olex2 is optimized for rapid molecular and small-molecule crystal structure solution and SHELXL refinement.

### Input Choice
Both unmerged and merged reflections can be used with SHELXL. Use `unmerged.ins`/`unmerged.hkl` when preserving anomalous information or comparing alternative symmetry. The convenience `merged.hkl` averages symmetry equivalents and Friedel mates through MTZ IMEAN/SIGIMEAN; it is appropriate for an adopted mean structure. The source `merged.mtz` is kept in `for_refinement/`.

### Step-by-Step Import:
1. **Open Structure in Olex2**:
   - Launch Olex2.
   - Open file: `File -> Open` and select `for_refinement/merged.ins`.
   - Alternatively, from the terminal:
     ```bash
     olex2 for_refinement/merged.ins
     ```
2. **Structure Solution**:
   - In the Olex2 GUI, open the **Solve** panel.
   - Method: Select **SHELXT** (default, automatic space group and heavy atom assignment) or **ShelxS**.
   - Click **Solve**.
3. **Structure Refinement**:
   - Open the **Refine** panel.
   - Engine: **SHELXL**.
   - Refine isotropic displacement parameters, assign atom types, and convert to anisotropic ADPs (`aniso`).

## Before Refinement

Confirm wavelength, cell, symmetry, element assignment, UNIT and ZERR/Z. DIALS interprets composition as asymmetric-unit contents; an element-only list produces placeholder UNIT counts that must be replaced. A bulk formula is not automatically the asymmetric-unit composition, especially with atoms on special positions. Use wavelength-appropriate anomalous scattering corrections at synchrotron energies.

Inspect the fixed-width HKLF 4 fields for overflow or loss of weak sigma values. If rescaling is needed, multiply intensities and their sigmas by the same positive factor. Keep weak/negative observations and assess important absence violations rather than silently removing them to improve a residual.

Follow the [working-assumption and validation guide](refinement_decisions.md) to refine a useful model and choose additional checks according to the result being claimed.
