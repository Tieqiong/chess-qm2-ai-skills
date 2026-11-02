# Working assumptions for useful diffraction refinement

The objective is a reliable, usable structural model. Adopt a physically plausible baseline, state what is fixed, and continue. Uncertainty about the exact instrument mechanism or space group need not prevent average-structure refinement. Investigate alternatives when they change coordinates, displacement parameters, occupancies, residual density or the scientific interpretation.

## Symmetry, absorption and empirical corrections

A high-symmetry parent structure with moderate absorption correction is a reasonable first-pass model when chemistry, lattice metrics and intensity evidence support it. Good merging after correction supports its practical use. It does not uniquely identify absorption as the source of every directional discrepancy, because both structural anisotropy and experimental effects can change direction-dependent intensity.

For a sequence of lower-symmetry tests:

1. Keep unmerged observations in their original indexing. Use the common least-assumed scaling group needed by the candidate set (P1 if necessary); do not first merge away the differences being tested. Keep weak/negative intensities and absence violations for a common structural score.
2. Choose a baseline correction from repeated measurements and residual diagnostics. Compare scale-only with a restrained physical absorption model when the difference matters. Correction estimates in P1 require adequate repeated observations and geometric overlap; P1 is not automatically informative or optimal.
3. Give every structural candidate the same correction family, observation set, weights and resolution range. Either hold the correction fixed across candidates or refit the same nuisance parameters for every candidate, counting that flexibility and fitting it on training data within each predictive comparison.
4. An empirical directional factor is useful as a shared diagnostic or nuisance model. Compare parent-plus-factor with subgroup-plus-the-same-factor to ask whether the subgroup explains additional structure. Also retain a comparison without the factor: the factor itself can absorb genuine symmetry breaking. A correction fitted only to the parent and then frozen can favor the parent.
5. Prefer a lower-symmetry model when its gain is reproducible, exceeds its parameter cost, survives meaningful prediction/sensitivity checks and yields physical atoms/ADPs. Hamilton-type comparisons require nested models and comparable weights/data; held-out residuals are useful when that premise does not hold. Correlated repeats and relevant symmetry families should stay together in validation folds.

A global factor `exp(-4*pi^2*q.T*T*q)` can mathematically mimic adding a common displacement tensor T to all atoms (q in reciprocal-length units). Thus it is a compact model of directional intensity differences, not uniquely an absorption correction. Interpret it as atomic motion only if the resulting atomic displacement tensors are positive and plausible. A positive multiplicative scale alone does not establish physicality of an atomic interpretation.

If the freely refined atomic ADPs already span the same common tensor, adding T creates an exact redundancy: the intensities determine the sums U_i+T, not their decomposition. Constrain the overlapping freedoms or estimate/fix the correction separately, count only identifiable parameters, and examine the effective tensors. Do not add a free global tensor on top of unrestricted overlapping ADPs and treat the nominal parameter count as an independent test.

Select and report a working model rather than ending with an undifferentiated list of possibilities. State which conclusions are robust to plausible correction choices and which remain conditional. When a structural distinction matters, overlapping measurements of the same hkl in different geometries can separate measurement-dependent effects from intrinsic intensity without assuming the disputed symmetry.

## Geometry before intensity refinement

Establish a stable lattice and static detector/beam geometry from spot centroids. Add smooth crystal-orientation variation if systematic residuals warrant it. Add restricted relative sample/detector displacement only when the simpler model leaves relevant structured errors. Integrate with the accepted geometry, then scale intensities and refine atoms.

Geometry least squares measures spot positions; atomic refinement measures intensities. A lower geometry residual is useful but does not automatically give better atomic parameters. Confirm that a correction survives model save/reload and is actually used by integration. Reintegrate after a material geometry change; record and justify any approximation used to reuse existing intensities.

`crystal.unit_cell.force_static=True` means one cell throughout the scan, which can still be refined. `crystal.fix=cell` fixes that cell against refinement. Keeping the cell constant while allowing orientation variation is often a useful intermediate model. Static refinement is a stable starting point, not a universal remedy for bad initial geometry.

### Why use short integration windows?

Some DIALS versions can fit scan-dependent detector translations but do not retain that series in the ordinary `.expt` representation. A specialized workaround is to fit one smooth full-scan model, evaluate the detector translation at each short-window midpoint, and integrate serializable static-detector windows while preserving the smooth crystal orientation series. The wrapper in this repository does not implement that workaround.

Five degrees is a numerical choice, not a physical constant or a separate fit at every five degrees. Set the width from the maximum difference between the smooth model and its midpoint approximation. For a local displacement slope v in pixels per degree, the first-order within-core error is approximately bounded by `|v| * width / 2`; evaluate the actual curve, especially if it varies rapidly. Inspect padded contexts too, where the approximation may be less accurate.

Each integration window needs enough overlapping context to contain complete reflection profiles. Retain events by nonoverlapping predicted-rotation cores, preserving partial components. Check that no artificial boundary truncates a profile or duplicates an event. Compare boundary/interior intensities and a narrower window on representative regions when the approximation is consequential.

Downsides include extra runtime, changing local profile estimates, numerical boundary effects and too many independent scale parameters. Short windows may have insufficient overlap to determine independent absorption or decay models. Share/limit corrections as appropriate. The geometry is evaluated from the same global fit, so integration-job scheduling order is immaterial; changing the fitting sequence, window width or profile context need not be.

A smooth transverse correction represents relative scattering-origin/detector displacement. It can approximate an off-centre rotating crystal even when the physical detector is fixed, but it can also absorb other geometric errors. It is not a unique measurement of sample x/y/z or longitudinal motion. A rigid rotating-offset model is a more specific alternative when justified by the instrument. Motion correction is optional: retain it when it improves relevant prediction/integration without unstable parameters or boundary artifacts.

## Detector calibration and parameter meaning

A rigid detector plane has six pose degrees of freedom: a normal distance, two transverse offsets and three rotations. A full PONI conversion maps distance, Poni1/Poni2 and Rot1/Rot2/Rot3 into the detector origin and fast/slow axes using the actual image-raster/laboratory convention. The zero-rotation shortcut is a subset of that model.

A general static detector fit can cover that rigid-pose space, but not every detector effect: panel distortions, incorrect pixel size/material/parallax, energy errors and scan-dependent longitudinal motion require other models or calibration. Detector displacement parameters describe positions relative to the scattering origin. They must not automatically be interpreted as actual detector motor movement.

Cell scale and detector distance are strongly correlated, particularly at small scattering angles. Beam, detector and crystal rotations can also compensate for one another. Fix well-known wavelength and appropriate gauge freedoms; introduce flexibility in stages or profile one parameter while fitting the others. Compare a calibration-fixed control when absolute lattice dimensions matter. A fit-preferred distance is a useful conditional integration geometry even before its mechanical cause is established; fitted statistical cell errors exclude uncertainty in a fixed calibration/model.

## Validation proportional to the decision

| Decision | Useful checks |
|---|---|
| Accept a first-pass reduction | Prediction overlays, indexed fraction, profile/background diagnostics, overload/overlap handling, completeness and scaling residuals by angle/resolution |
| Add geometry/motion flexibility | Matched centroid comparisons, plausible parameter curves, saved-model predictions, effect on integrated intensities |
| Adopt an atomic model | Correct chemistry/UNIT/Z, energy-specific scattering factors, stable convergence, positive/plausible ADPs, occupancy correlations, residual density and important outliers |
| Choose a subgroup or empirical correction | Same observations and weights, comparable nuisance freedom, parameter-cost-aware and predictive comparisons, sensitivity to correction choice |
| Report absolute cell or composition | Calibration uncertainty and geometry sensitivity; occupancy/scale/ADP correlations and independent constraints where available |

Stop expanding checks when the intended result is stable and useful at the required precision. Preserve a simpler reference and record material assumptions. More checks are warranted by a concrete discrepancy, not merely by the existence of a more elaborate model.

## Primary references

- [DIALS geometry refinement](https://dials.github.io/documentation/programs/dials_refine.html)
- [DIALS small-molecule workflow](https://dials.github.io/documentation/tutorials/small_molecule_tutorial.html)
- [DIALS scaling options](https://dials.github.io/dials_scale_user_guide.html)
- [Scaling algorithms and validation](https://doi.org/10.1107/S2059798320003198)
- [DIALS SHELX export and asymmetric-unit composition](https://dials.github.io/documentation/programs/dials_export.html)
