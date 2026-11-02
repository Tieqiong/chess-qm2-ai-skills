#!/usr/bin/env python3
"""
bravais_matcher.py: Parse dials.refine_bravais_settings.log and match candidate
Bravais settings against target crystallographic unit cell parameters.

Author: Steven Gomez-Alvarado / CHESS Data Reduction Skills
"""

import argparse
import itertools
import json
import math
import os
import re
import sys


BRAVAIS_LATTICES = ("aP", "mP", "mC", "oP", "oC", "oF", "oI",
                    "tP", "tI", "hP", "hR", "cP", "cI", "cF")


def _optional_float(value):
    """Missing diagnostics stay missing instead of becoming perfect zero fits."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validate_cell(cell):
    if len(cell) != 6:
        raise ValueError("A unit cell needs a,b,c,alpha,beta,gamma")
    cell = tuple(float(value) for value in cell)
    if not all(math.isfinite(value) for value in cell):
        raise ValueError("Unit-cell parameters must be finite")
    if any(value <= 0 for value in cell[:3]):
        raise ValueError("Unit-cell lengths must be positive")
    if any(not 0 < angle < 180 for angle in cell[3:]):
        raise ValueError("Unit-cell angles must lie between 0 and 180 degrees")
    ca, cb, cg = (math.cos(math.radians(angle)) for angle in cell[3:])
    determinant = 1 - ca * ca - cb * cb - cg * cg + 2 * ca * cb * cg
    if determinant <= 0:
        raise ValueError("Unit-cell metric must have positive volume")
    return cell


def _cell_volume(cell):
    a, b, c, alpha, beta, gamma = validate_cell(cell)
    ca, cb, cg = (math.cos(math.radians(angle)) for angle in (alpha, beta, gamma))
    return a * b * c * math.sqrt(1 - ca * ca - cb * cb - cg * cg + 2 * ca * cb * cg)


def normalize_lattice(symbol):
    lookup = {lattice.lower(): lattice for lattice in BRAVAIS_LATTICES}
    try:
        return lookup[symbol.strip().lower()]
    except (AttributeError, KeyError):
        raise ValueError("Expected a Bravais symbol such as hP or cP; "
                         "use --target-space-group for a space-group symbol") from None


def lattice_from_space_group(symbol):
    """Resolve the standard Bravais type, including nonstandard SG settings."""
    try:
        from cctbx import sgtbx
        from cctbx.sgtbx import bravais_types
    except ImportError as exc:
        raise RuntimeError("--target-space-group requires cctbx; run with dials.python") from exc
    try:
        info = sgtbx.space_group_info(symbol=symbol)
        reference = info.change_basis(info.type().cb_op())
        return normalize_lattice(str(bravais_types.bravais_lattice(group=reference.group())))
    except (RuntimeError, ValueError) as exc:
        raise ValueError(f"Invalid space group {symbol!r}: {exc}") from exc


def parse_bravais_log(log_path):
    """Prefer structured DIALS output; retain usable rows if one row is malformed."""
    json_path = os.path.join(os.path.dirname(log_path) or ".", "bravais_summary.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Bravais summary must be a mapping of setting IDs")
        except (OSError, ValueError) as exc:
            print(f"Warning: cannot read {json_path}: {exc}; trying the log", file=sys.stderr)
        else:
            solutions = []
            for sol_key, record in data.items():
                try:
                    sol_id = int(sol_key)
                    if sol_id <= 0 or not isinstance(record, dict):
                        raise ValueError("Expected a positive setting ID and record")
                    cell = validate_cell(record["unit_cell"])
                    lattice = normalize_lattice(record["bravais"])
                    cb_op = record.get("cb_op")
                    if not isinstance(cb_op, str) or not cb_op.strip():
                        raise ValueError("Missing DIALS change-of-basis operator")
                    min_cc = _optional_float(record.get("min_cc"))
                    max_cc = _optional_float(record.get("max_cc"))
                    cc = "/".join("-" if value is None else f"{value:.3f}"
                                  for value in (min_cc, max_cc))
                    spots = _optional_float(record.get("nspots"))
                    solutions.append({
                        "solution": sol_id,
                        "recommended": record.get("recommended") is True,
                        "metric_fit": _optional_float(record.get("max_angular_difference")),
                        "rmsd": _optional_float(record.get("rmsd")),
                        "cc": cc,
                        "spots": int(spots) if spots is not None else None,
                        "lattice": lattice,
                        "cell": list(cell),
                        "volume": _cell_volume(cell),
                        "cb_op": cb_op,
                        "file": f"bravais_setting_{sol_id}.expt",
                    })
                except (KeyError, TypeError, ValueError) as exc:
                    print(f"Warning: skipping invalid Bravais setting {sol_key!r}: {exc}",
                          file=sys.stderr)
            if solutions:
                return sorted(solutions, key=lambda row: row["solution"], reverse=True)
            print(f"Warning: no usable settings in {json_path}; trying the log", file=sys.stderr)

    if not os.path.exists(log_path):
        raise FileNotFoundError(f"Log file not found: {log_path}")

    with open(log_path, "r") as f:
        content = f.read()

    solutions = []
    # Match pipe-separated or whitespace-separated lines
    # E.g.: |   *     12 |            0 | 17.809 | 0.288/0.356   |      133 | hP        | 5.22   5.22  13.27  90.00  90.00 120.00 |      314 | a,b,c      |
    pipe_pattern = re.compile(
        r"\|\s*([*]?)\s*(\d+)\s*\|\s*([\d\.]+)\s*\|\s*([\d\.]+)\s*\|\s*([-\d\./]+|-/-)\s*\|\s*(\d+)\s*\|\s*([a-zA-Z]+)\s*\|\s*"
        r"([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s*\|\s*([\d\.]+)\s*\|\s*(\S+)\s*\|"
    )

    for match in pipe_pattern.finditer(content):
        recommended = match.group(1) == "*"
        sol_id = int(match.group(2))
        metric_fit = float(match.group(3))
        rmsd = float(match.group(4))
        cc = match.group(5)
        n_spots = int(match.group(6))
        bravais_lattice = match.group(7)
        a = float(match.group(8))
        b = float(match.group(9))
        c = float(match.group(10))
        alpha = float(match.group(11))
        beta = float(match.group(12))
        gamma = float(match.group(13))
        volume = float(match.group(14))
        cb_op = match.group(15)

        solutions.append({
            "solution": sol_id,
            "recommended": recommended,
            "metric_fit": metric_fit,
            "rmsd": rmsd,
            "cc": cc,
            "spots": n_spots,
            "lattice": bravais_lattice,
            "cell": [a, b, c, alpha, beta, gamma],
            "volume": volume,
            "cb_op": cb_op,
            "file": f"bravais_setting_{sol_id}.expt"
        })

    return solutions


def compare_cells(sol_cell, target_cell):
    """Return the best metric score and axis permutation, for comparison only.

    A permutation remaps the three interaxial angles along with the lengths.
    It is not a reindexing operator and never replaces DIALS' cb_op. Signed
    basis changes, conventional-cell conversions and supercells are not searched.
    """
    solution = validate_cell(sol_cell)
    target = validate_cell(target_cell)
    angle_for_pair = {(1, 2): solution[3], (0, 2): solution[4], (0, 1): solution[5]}
    candidates = []
    for axes in itertools.permutations(range(3)):
        lengths = tuple(solution[index] for index in axes)
        angles = tuple(angle_for_pair[tuple(sorted((axes[i], axes[j])))]
                       for i, j in ((1, 2), (0, 2), (0, 1)))
        score = sum(abs(actual - expected) / expected
                    for actual, expected in zip(lengths, target[:3]))
        score += sum(abs(actual - expected) / 90.0
                     for actual, expected in zip(angles, target[3:]))
        candidates.append((score, axes))
    return min(candidates)


def score_cell_match(sol_cell, target_cell):
    """Normalized reference-cell mismatch after an exact axis permutation."""
    return compare_cells(sol_cell, target_cell)[0]


def match_bravais_settings(solutions, target_cell=None, target_lattice=None):
    """Order reference matches; this heuristic does not determine symmetry."""
    if target_lattice is not None:
        target_lattice = normalize_lattice(target_lattice)
    ranked = []
    for original in solutions:
        sol = dict(original)
        score, axes = (0.0, (0, 1, 2))
        if target_cell is not None:
            score, axes = compare_cells(sol["cell"], target_cell)
        sol["comparison_axes"] = ",".join("abc"[index] for index in axes)
        sol["lattice_match"] = (None if target_lattice is None else
                                sol["lattice"].lower() == target_lattice.lower())
        if sol["lattice_match"] is False:
            score += 5.0
        ranked.append((score, sol))

    def diagnostic(value):
        return float("inf") if value is None else value

    ranked.sort(key=lambda item: (item[0], not item[1]["recommended"],
                                 diagnostic(item[1]["metric_fit"]),
                                 diagnostic(item[1]["rmsd"])))
    return ranked


def main():
    parser = argparse.ArgumentParser(description="Compare DIALS Bravais settings with a reference cell.")
    parser.add_argument("--log", default="dials.refine_bravais_settings.log", help="Path to Bravais log file")
    parser.add_argument("--target-cell", help="Reference cell as a,b,c,alpha,beta,gamma")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--target-lattice", help="Bravais symbol (e.g. hP, hR, oP, mP, tP)")
    target.add_argument("--target-space-group", help="Reference space group (e.g. P6322); requires dials.python")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    try:
        target_cell = (validate_cell(re.split(r"[\s,]+", args.target_cell.strip()))
                       if args.target_cell else None)
        target_lattice = (lattice_from_space_group(args.target_space_group)
                          if args.target_space_group else
                          normalize_lattice(args.target_lattice) if args.target_lattice else None)
        solutions = parse_bravais_log(args.log)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    if not solutions:
        parser.error("No Bravais solutions parsed from log file")

    ranked = match_bravais_settings(solutions, target_cell, target_lattice)
    has_reference = target_cell is not None or target_lattice is not None
    best = ranked[0][1] if has_reference else None
    interpretation = ("Reference mismatch is a heuristic, not a symmetry score. Review DIALS "
                      "recommendation (*), RMSD, metric fit and intensity evidence before selection. "
                      "Comparison axes do not modify the DIALS change-of-basis operator.")
    if args.json:
        out = {
            "solutions": [solution for _, solution in ranked],
            "best_match": best,
            "best_score": ranked[0][0] if has_reference else None,
            "target_lattice": target_lattice,
            "interpretation": interpretation,
        }
        print(json.dumps(out, indent=2, allow_nan=False))
        return

    print("=== DIALS Bravais Reference Comparison ===")
    print(f"Total candidate solutions: {len(solutions)}")
    if target_cell:
        print(f"Reference Unit Cell: {target_cell}")
    if target_lattice:
        print(f"Reference Bravais Lattice: {target_lattice}")
    print(interpretation)
    print()
    print(f"{'Sol':<4} {'Fit':<8} {'RMSD':<6} {'CC':<12} {'Lattice':<8} {'Unit Cell':<42} "
          f"{'cb_op':<15} {'Compare axes':<13} {'Mismatch':<8}")
    print("-" * 122)
    for score, sol in ranked:
        c = sol["cell"]
        cell_str = f"{c[0]:.2f} {c[1]:.2f} {c[2]:.2f} {c[3]:.1f} {c[4]:.1f} {c[5]:.1f}"
        rec = "*" if sol["recommended"] else " "
        fit = "-" if sol["metric_fit"] is None else f"{sol['metric_fit']:.4f}"
        rmsd = "-" if sol["rmsd"] is None else f"{sol['rmsd']:.3f}"
        print(f"{rec}{sol['solution']:<3} {fit:<8} {rmsd:<6} {sol['cc']:<12} "
              f"{sol['lattice']:<8} {cell_str:<42} {sol['cb_op']:<15} "
              f"{sol['comparison_axes']:<13} {score:<8.3f}")
    if best:
        print(f"\nClosest reference match: setting {best['solution']} ({best['lattice']})")
        print(f"DIALS recommends this setting: {best['recommended']}")
        print(f"After reviewing the diagnostics, use experiment {best['file']} "
              f"with DIALS change_of_basis_op={best['cb_op']}.")
    else:
        print("\nNo reference supplied; select from the DIALS diagnostics above.")


if __name__ == "__main__":
    main()
