#!/usr/bin/env python3
"""Make a GIF of one reciprocal plane across temperature files.

Native axis mapping and full reciprocal metrics are supported. Temperature
discovery, cross-temperature grid reconciliation, and streaming remain deferred;
use verified temperature directories and a common reciprocal grid.
"""

import argparse
import gc
import glob
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
import nexusformat.nexus as nx

from nxs_analysis_tools.reciprocal import reciprocal_slice, resolve_nxdata
from animate_volume import _gif_destination, _normalization, _start_mesh


def extract_temp_from_path(p):
    """Legacy heuristic; temperature discovery is a documented deferred issue."""
    dirname = os.path.basename(os.path.dirname(os.path.abspath(p)))
    fname = os.path.basename(p)
    for text in (dirname, fname):
        match = re.search(r'(\d+p\d+|\d+\.\d+|\d+)k?', text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace('p', '.'))
            except ValueError:
                pass
    return None


def animate_temp_series(files, plane, coord, out_path, fps=5, vmin=None,
                        vmax=None, cmap="viridis", coordinates="auto", unit_cell=None):
    """Slice each volume by native axis names, displaying plane axes consistently."""
    destination = _gif_destination(out_path)
    nx.nxsetmemory(20000)
    # Retained for compatibility, pending the separate discovery/grid work.
    temp_map = {}
    for filename in files:
        temperature = extract_temp_from_path(filename)
        if temperature is not None:
            temp_map[temperature] = filename
    if not temp_map:
        raise ValueError(f"Could not parse temperatures from provided files: {files}")
    sorted_temps = sorted(temp_map)
    plane, coord = plane.upper(), float(coord)
    print("Temperature discovery and grid reconciliation are not validated here; "
          "use verified temperature directories and a common reciprocal grid.")
    print(f"Found {len(sorted_temps)} temperature volumes from {sorted_temps[0]} K to {sorted_temps[-1]} K.")

    def frame(temperature):
        root = nx.nxload(temp_map[temperature])
        data = resolve_nxdata(root)
        return data, reciprocal_slice(data, plane=plane, coord=coord)

    samples = [frame(sorted_temps[i])[1].values for i in (0, len(sorted_temps) // 2, -1)]
    norm = _normalization(samples, vmin=vmin, vmax=vmax)
    first_data, first = frame(sorted_temps[0])
    fig, ax = plt.subplots(figsize=(6, 5), dpi=140)
    try:
        mesh, mode = _start_mesh(ax, first, first_data, norm, cmap, coordinates, unit_cell)
        title = ax.set_title(
            f"T = {sorted_temps[0]:g} K: {plane}, {first.fixed_axis} = {first.actual_coord:g} r.l.u. ({mode})"
        )
        fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.04, label="Intensity")

        def update(index):
            temperature = sorted_temps[index]
            _, section = frame(temperature)
            # The display mesh remains that of the first temperature. Alignment
            # or resampling of different temperature grids is explicitly deferred.
            mesh.set_array(section.values.ravel())
            title.set_text(
                f"T = {temperature:g} K: {plane}, {section.fixed_axis} = {section.actual_coord:g} r.l.u. ({mode})"
            )
            return mesh, title

        animation = FuncAnimation(fig, update, frames=len(sorted_temps), blit=True)
        animation.save(str(destination), writer=PillowWriter(fps=fps))
    finally:
        plt.close(fig)
        gc.collect()
    print(f"Exported temperature GIF: {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", required=True, help="Glob for volumes in verified temperature directories, e.g. 'sample/[0-9]*/3rot_hkli.nxs'")
    parser.add_argument("--plane", default="HK", choices=["HK", "HL", "KL"])
    parser.add_argument("--coord", type=float, default=0.0, help="Perpendicular reciprocal coordinate")
    parser.add_argument("--output", "-o", required=True, help="Destination GIF path; MP4 is not supported")
    parser.add_argument("--fps", type=int, default=5)
    parser.add_argument("--cmap", default="viridis")
    parser.add_argument("--vmin", type=float, help="Fixed LogNorm minimum intensity")
    parser.add_argument("--vmax", type=float, help="Fixed LogNorm maximum intensity")
    parser.add_argument("--coordinates", choices=["auto", "rlu", "physical"], default="auto",
                        help="auto uses a native/explicit cell for physical geometry; otherwise rlu")
    parser.add_argument("--unit-cell", help="a,b,c,alpha,beta,gamma; explicit cell overrides native metadata")
    args = parser.parse_args()
    files = sorted(glob.glob(args.pattern))
    if not files:
        print(f"No files matched pattern: {args.pattern}")
        sys.exit(1)
    animate_temp_series(files, args.plane, args.coord, args.output, fps=args.fps,
                        vmin=args.vmin, vmax=args.vmax, cmap=args.cmap,
                        coordinates=args.coordinates, unit_cell=args.unit_cell)


if __name__ == "__main__":
    main()
