#!/usr/bin/env python3
"""Reduce one calibrated CHESS rotation sweep and prepare refinement inputs.

Stage 1: import, mask, find spots, index, assess Bravais settings.
Stage 2: refine, integrate, choose intensity symmetry, scale, export.
Different spindle settings must be imported/reduced separately; combine their
integrated observations with dials.cosym/dials.scale after checking geometry.
"""

import argparse
import glob
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile


def parse_poni_origin(poni_path):
    """Convert an untilted PONI calibration in the documented QM2 frame.

    This shortcut assumes the existing detector fast/slow axes already match
    that frame. A rotated PONI needs a full detector model, not just an origin.
    """
    values = {}
    with open(poni_path) as handle:
        for line in handle:
            key, separator, value = line.partition(":")
            if separator and key.strip().lower() in {
                "distance", "poni1", "poni2", "rot1", "rot2", "rot3"
            }:
                values[key.strip().lower()] = float(value.strip())
    if not {"distance", "poni1", "poni2"} <= values.keys():
        raise ValueError(f"Could not parse Distance, Poni1, and Poni2 from {poni_path}")
    if not all(math.isfinite(value) for value in values.values()) or values["distance"] <= 0:
        raise ValueError("PONI calibration requires finite values and positive Distance")
    if any(abs(values.get(key, 0.0)) > 1e-12 for key in ("rot1", "rot2", "rot3")):
        raise ValueError(
            "PONI has nonzero detector rotations; an origin-only conversion would lose "
            "the tilt. Supply --geometry-phil with validated detector origin, fast_axis "
            "and slow_axis instead of --poni-file."
        )
    return f"{-values['poni2'] * 1000:.6f},{values['poni1'] * 1000:.6f},{-values['distance'] * 1000:.6f}"


def run_cmd(argv, cwd=None, log_file=None, dials_env=None):
    """Run literal arguments, optionally sourcing DIALS in bash first.

    Pass data as positional arguments to bash; neither paths nor PHIL values
    are interpolated into shell source. This also works when /bin/sh is dash.
    """
    if isinstance(argv, str):
        raise TypeError("run_cmd requires an argument sequence, not shell source")
    argv = [str(arg) for arg in argv]
    command = argv
    if dials_env:
        command = ["bash", "-c", 'source "$1" && shift && exec "$@"',
                   "dials-run", os.path.abspath(dials_env), *argv]
    print(f"\n[RUNNING]: {shlex.join(argv)}", flush=True)
    if cwd:
        print(f"[WORKING DIR]: {cwd}", flush=True)
    process = subprocess.Popen(
        command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, bufsize=1,
    )
    output_lines = []
    log_handle = open(log_file, "a") if log_file else None
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
            output_lines.append(line)
            if log_handle:
                log_handle.write(line)
                log_handle.flush()
    finally:
        process.stdout.close()
        if log_handle:
            log_handle.close()
    return_code = process.wait()
    if return_code:
        raise RuntimeError(f"Command failed with exit code {return_code}: {shlex.join(argv)}")
    return "".join(output_lines)


def discover_sweep(raw_dir=None, cbf_pattern=None):
    """Discover a single CBF filename series, refusing mixed sweep geometry."""
    if bool(raw_dir) == bool(cbf_pattern):
        raise ValueError("Provide exactly one of --raw-dir or --cbf-pattern")
    if raw_dir:
        directory = Path(raw_dir).expanduser().resolve()
        files = list(directory.glob("*.cbf")) + list(directory.glob("*/*.cbf"))
    else:
        files = [Path(path).resolve() for path in glob.glob(os.path.expanduser(cbf_pattern))]
    files = sorted({path for path in files if path.is_file()})
    if not files:
        raise ValueError("No CBF files matched the supplied input")
    # DIALS identifies rotation series by a numeric image suffix. Conservatively
    # reject multiple directories or prefixes rather than reuse one spindle axis.
    series = {(path.parent, re.sub(r"\d+(?=\.cbf$)", "#", path.name)) for path in files}
    if len(series) != 1:
        raise ValueError(
            "Input contains multiple CBF sweeps. Run stage1/stage2 in a separate "
            "work directory for each sweep with its calibrated --goniometer-axes; "
            "then align integrated sweeps with dials.cosym and scale them jointly."
        )
    return [str(path) for path in files]


def normalized_cell(value):
    """Accept comma- or whitespace-separated cell parameters consistently."""
    if not value:
        return None
    numbers = [float(part) for part in re.split(r"[,\s]+", value.strip())]
    if len(numbers) != 6 or not all(math.isfinite(x) and x > 0 for x in numbers):
        raise ValueError("Unit cell requires six finite positive parameters: a,b,c,alpha,beta,gamma")
    if any(angle >= 180 for angle in numbers[3:]):
        raise ValueError("Unit-cell angles must be smaller than 180 degrees")
    return ",".join(str(number) for number in numbers)


def stage_1(args):
    """Import and index one sweep, then report candidate lattice settings."""
    if args.constrain_symmetry and not (args.unit_cell and args.space_group):
        raise ValueError("--constrain-symmetry requires both --unit-cell and --space-group")
    cell = normalized_cell(args.unit_cell)
    files = discover_sweep(args.raw_dir, args.cbf_pattern)
    origin = args.detector_origin
    if args.poni_file:
        origin = parse_poni_origin(args.poni_file)
    for label, path in (("EDF mask", args.edf_mask), ("geometry PHIL", args.geometry_phil)):
        if path and not Path(path).is_file():
            raise FileNotFoundError(f"{label} not found: {path}")
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    def run(argv):
        return run_cmd(argv, cwd=str(work_dir), dials_env=args.dials_env)

    import_args = ["dials.import", *files]
    if args.geometry_phil:
        import_args.append(str(Path(args.geometry_phil).resolve()))
    import_args.append(f"geometry.goniometer.axes={args.goniometer_axes}")
    if origin:
        import_args.append(f"geometry.detector.panel.origin={origin}")
    run(import_args)

    mask_file = work_dir / "pixels.mask"
    run(["dials.generate_mask", "imported.expt", f"output.mask={mask_file}"])
    script_dir = Path(__file__).resolve().parent
    if args.edf_mask:
        run(["dials.python", script_dir / "mask_to_dials.py", "--edf",
             str(Path(args.edf_mask).resolve()), "--out", mask_file, "--combine-with", mask_file])

    # Preserve optional user settings; explicit CLI threshold values take
    # precedence on every run instead of silently reusing stale generated values.
    phil_path = work_dir / "find_spots.phil"
    spot_args = ["dials.find_spots"]
    if phil_path.is_file():
        spot_args.append(phil_path)
    spot_args += ["imported.expt", f"mask={mask_file}",
                  f"spotfinder.threshold.dispersion.gain={args.gain}",
                  f"spotfinder.threshold.dispersion.global_threshold={args.global_threshold}",
                  f"spotfinder.filter.d_min={args.d_min}", f"mp.nproc={args.nproc}"]
    run(spot_args)
    index_args = ["dials.index", "imported.expt", "strong.refl"]
    if args.constrain_symmetry:
        index_args += [f"indexing.known_symmetry.unit_cell={cell}",
                       f"indexing.known_symmetry.space_group={args.space_group}"]
    run(index_args)
    run(["dials.refine_bravais_settings", "indexed.expt", "indexed.refl"])
    matcher_args = ["dials.python", script_dir / "bravais_matcher.py",
                    "--log", "dials.refine_bravais_settings.log"]
    if cell:
        matcher_args += ["--target-cell", cell]
    if args.space_group:
        matcher_args += ["--target-space-group", args.space_group]
    run(matcher_args)
    print("\nStage 1 complete. Review the lattice fit and reported cb_op before stage2.")


def stage_2(args):
    """Refine/integrate, scale under a stated symmetry choice, and export."""
    work_dir = Path(args.work_dir).resolve()
    bravais_expt = f"bravais_setting_{args.bravais_setting}.expt"
    if not (work_dir / bravais_expt).is_file():
        raise FileNotFoundError(f"Experiment file {bravais_expt} not found in {work_dir}")

    def run(argv):
        return run_cmd(argv, cwd=str(work_dir), dials_env=args.dials_env)

    refl_file = "indexed.refl"
    if args.cb_op != "a,b,c":
        run(["dials.reindex", refl_file, f"change_of_basis_op={args.cb_op}",
             "output.reflections=reindexed.refl"])
        refl_file = "reindexed.refl"
    refine_args = ["dials.refine", bravais_expt, refl_file, f"scan_varying={args.scan_varying}"]
    if args.fix_cell:
        refine_args.append("refinement.parameterisation.crystal.fix=cell")
    run(refine_args)
    run(["dials.integrate", "refined.expt", "refined.refl", f"nproc={args.nproc}"])

    scale_inputs = ["integrated.expt", "integrated.refl"]
    if args.space_group:
        run(["dials.reindex", *scale_inputs, f"space_group={args.space_group}",
             "output.experiments=candidate.expt", "output.reflections=candidate.refl"])
        scale_inputs = ["candidate.expt", "candidate.refl"]
    elif not args.keep_input_symmetry:
        run(["dials.symmetry", *scale_inputs])
        scale_inputs = ["symmetrized.expt", "symmetrized.refl"]
    scale_args = ["dials.scale", *scale_inputs,
                  "overwrite_existing_models=True", f"anomalous={args.anomalous}"]
    if args.scaling_model == "scale-only":
        # KB with its B/decay term disabled is one scalar per dataset. A physical
        # model without absorption/decay still fits a smooth scale versus phi.
        scale_args += ["model=KB", "KB.decay_correction=False"]
    else:
        scale_args.append("model=physical")
        if args.absorption_level == "none":
            scale_args.append("physical.absorption_correction=False")
        else:
            scale_args += ["physical.absorption_correction=True",
                           f"physical.absorption_level={args.absorption_level}"]
    run(scale_args)

    refinement_dir = work_dir / "for_refinement"
    refinement_dir.mkdir(exist_ok=True)
    unmerged_hkl, unmerged_ins = refinement_dir / "unmerged.hkl", refinement_dir / "unmerged.ins"
    run(["dials.export", "scaled.expt", "scaled.refl", "format=shelx", "intensity=scale", "mtz.min_isigi=None",
         f"shelx.composition={args.composition}", f"shelx.scale={args.shelx_scale}",
         f"shelx.hklout={unmerged_hkl}", f"shelx.ins={unmerged_ins}"])
    merged_mtz = refinement_dir / "merged.mtz"
    # Keep the chosen symmetry unchanged while merging. IMEAN is explicitly a
    # Friedel average; original observations and anomalous MTZ arrays remain.
    run(["dials.merge", "scaled.expt", "scaled.refl", "output.html=None",
         f"output.mtz={merged_mtz}", "assess_space_group=False", "truncate=False",
         f"anomalous={args.anomalous}"])
    merged_hkl = refinement_dir / "merged.hkl"
    # The converter entry point can print some errors without a nonzero status.
    # Verify a fresh temporary output before replacing an earlier derived file.
    with tempfile.TemporaryDirectory(prefix=".shelx-merge-", dir=refinement_dir) as temporary:
        candidate_hkl = Path(temporary) / "merged.hkl"
        run(["iotbx.reflection_file_converter", merged_mtz, f"--shelx={candidate_hkl}",
             "--label=IMEAN,SIGIMEAN"])
        if not candidate_hkl.is_file() or not candidate_hkl.stat().st_size:
            raise RuntimeError("MTZ-to-SHELX conversion did not produce a nonempty merged.hkl")
        os.replace(candidate_hkl, merged_hkl)
    shutil.copyfile(unmerged_ins, refinement_dir / "merged.ins")
    (refinement_dir / "README.txt").write_text(
        "unmerged.hkl: scaled observations, original Miller indices (HKLF 4).\n"
        "merged.hkl: IMEAN/SIGIMEAN, symmetry- and Friedel-averaged intensities.\n"
        "merged.mtz: merged means and anomalous arrays when anomalous=True.\n"
        "Use unmerged observations/anomalous arrays for anomalous differences;\n"
        "the mean merged.hkl does not retain Bijvoet differences.\n"
        f"Composition supplied to the SHELX exporter: {args.composition}\n"
        "The .ins files are starting headers: review SFAC/UNIT, symmetry and chemistry.\n"
        f"Geometry: scan_varying={args.scan_varying}, fix_cell={args.fix_cell}\n"
        f"Scaling: {args.scaling_model}, absorption_level={args.absorption_level}\n"
        f"SHELX format rescaling: {args.shelx_scale}; inspect intensity/sigma precision.\n"
        "Good merging statistics alone do not determine whether anisotropy is structural.\n"
    )
    print(f"\nStage 2 complete: {refinement_dir}. Review README.txt and SHELX headers.")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--work-dir", required=True)
    common.add_argument("--dials-env", default="/nfs/chess/sw/dials_sgomezalvarado/dials_env.sh",
                        help="Bash activation script for the DIALS environment")
    p1 = subparsers.add_parser("stage1", parents=[common], help="Import/index one sweep")
    source = p1.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw-dir", help="Single CBF sweep directory (or parent containing exactly one sweep)")
    source.add_argument("--cbf-pattern", help="Glob matching one CBF filename series")
    p1.add_argument("--goniometer-axes", default="0,-1,0", help="Calibrated axis for this sweep; nominal default 0,-1,0")
    geometry = p1.add_mutually_exclusive_group()
    geometry.add_argument("--detector-origin", help="Validated DIALS origin in mm; existing panel axes must already be correct")
    geometry.add_argument("--poni-file", help="Untilted PONI calibration in the documented QM2 frame")
    geometry.add_argument("--geometry-phil", help="Validated DIALS import PHIL with full detector origin and fast/slow axes")
    p1.add_argument("--edf-mask")
    p1.add_argument("--gain", type=float, default=1.0)
    p1.add_argument("--global-threshold", type=int, default=5000, help="Starting spot threshold; adjust for the dataset")
    p1.add_argument("--d-min", type=float, default=0.75, help="Spot-finding cutoff in Angstroms")
    p1.add_argument("--nproc", type=int, default=32)
    p1.add_argument("--unit-cell", help="Target cell: a,b,c,alpha,beta,gamma (spaces also accepted)")
    p1.add_argument("--space-group", help="Target group for Bravais ranking; not imposed unless --constrain-symmetry")
    p1.add_argument("--constrain-symmetry", action="store_true")
    p2 = subparsers.add_parser("stage2", parents=[common], help="Refine/integrate/scale/export")
    p2.add_argument("--bravais-setting", type=int, required=True)
    p2.add_argument("--cb-op", default="a,b,c")
    p2.add_argument("--nproc", type=int, default=32)
    fixed = p2.add_mutually_exclusive_group()
    fixed.add_argument("--fix-cell", dest="fix_cell", action="store_true", help="Keep the selected cell fixed (default)")
    fixed.add_argument("--no-fix-cell", dest="fix_cell", action="store_false", help="Allow cell refinement")
    p2.set_defaults(fix_cell=True)
    p2.add_argument("--scan-varying", choices=["False", "True", "Auto"], default="False",
                    help="Static starting model by default; test variation when residuals justify it")
    symmetry = p2.add_mutually_exclusive_group()
    symmetry.add_argument("--keep-input-symmetry", action="store_true", help="Scale in selected Bravais model symmetry without automatic reassignment")
    symmetry.add_argument("--space-group", help="Explicit compatible candidate space group for scaling")
    p2.add_argument("--scaling-model", choices=["physical", "scale-only"], default="physical",
                    help="scale-only uses KB with decay disabled: one scalar per dataset, no absorption")
    p2.add_argument("--absorption-level", default="medium", choices=["none", "low", "medium", "high"])
    p2.add_argument("--anomalous", default="True", choices=["True", "False"])
    p2.add_argument("--composition", default="FeTe", help="SHELX asymmetric-unit contents or element list; review generated SFAC/UNIT (default elements: Fe, Te)")
    p2.add_argument("--shelx-scale", default="False", choices=["True", "False"],
                    help="Export-format rescaling only; False avoids the DIALS 3.30.1 sign bug, but check output precision")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.nproc < 1:
        parser.error("--nproc must be positive")
    if args.subcommand == "stage1":
        stage_1(args)
    else:
        stage_2(args)


if __name__ == "__main__":
    main()
