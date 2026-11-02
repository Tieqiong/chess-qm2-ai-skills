#!/usr/bin/env python3
"""Make a GIF of native-coordinate reciprocal slices; MP4 is not supported.

Slice selection and reciprocal geometry come from nxs_analysis_tools.reciprocal.
Pillow retains rendered frames, so long GIFs still require substantial memory.
"""

import argparse
import gc
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.colors import LogNorm
import numpy as np
import nexusformat.nexus as nx

from nxs_analysis_tools.reciprocal import (
    physical_mesh,
    reciprocal_axis_coordinates,
    reciprocal_slice,
    resolve_nxdata,
    resolve_unit_cell,
)


def _gif_destination(out_path):
    """Fail early for the currently unsupported movie formats."""
    destination = Path(out_path)
    if destination.suffix.lower() != ".gif":
        raise ValueError("This script currently exports GIF only; MP4/streaming export is deferred.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _normalization(slices, vmin=None, vmax=None):
    """Keep the existing sampled log normalization pending the separate review."""
    positive = np.concatenate([np.asarray(s)[np.asarray(s) > 0] for s in slices])
    if not len(positive):
        positive = np.array([1.0, 10.0], dtype=np.float32)
    lower = float(vmin) if vmin is not None else max(1.0, float(np.nanpercentile(positive, 5)))
    upper = float(vmax) if vmax is not None else float(np.nanpercentile(positive, 99.8))
    return LogNorm(vmin=lower, vmax=upper)


def _display_geometry(section, data, coordinates="auto", unit_cell=None):
    """Use the library's complete metric, or explicitly display native r.l.u."""
    if coordinates not in {"auto", "rlu", "physical"}:
        raise ValueError("coordinates must be auto, rlu, or physical")
    # A requested schematic r.l.u. view does not depend on cell metadata.
    cell = None if coordinates == "rlu" else resolve_unit_cell(data, unit_cell=unit_cell)
    mode = "physical" if coordinates == "auto" and cell is not None else coordinates
    if mode == "auto":
        mode = "rlu"
    horizontal, vertical = section.plane
    if mode == "physical":
        if cell is None:
            raise ValueError("Physical coordinates require a native unit cell or --unit-cell a,b,c,alpha,beta,gamma")
        x_mesh, y_mesh = physical_mesh(section, cell)
        x_label = f"q parallel to {horizontal}* (Å⁻¹; no 2π)"
        y_label = f"q perpendicular to {horizontal}* in {section.plane} plane (Å⁻¹)"
    else:
        x_mesh, y_mesh = np.meshgrid(section.x_edges, section.y_edges)
        x_label, y_label = f"{horizontal} (r.l.u.)", f"{vertical} (r.l.u.)"
    return x_mesh, y_mesh, x_label, y_label, mode


def _start_mesh(ax, section, data, norm, cmap, coordinates="auto", unit_cell=None):
    x_mesh, y_mesh, x_label, y_label, mode = _display_geometry(
        section, data, coordinates=coordinates, unit_cell=unit_cell
    )
    mesh = ax.pcolormesh(x_mesh, y_mesh, section.values, shading="flat", norm=norm, cmap=cmap)
    ax.set_aspect("equal")
    ax.set_xlabel(x_label, fontsize=11)
    ax.set_ylabel(y_label, fontsize=11)
    return mesh, mode


def animate_volume(nxs_path, axis_name, out_path, fps=12, stride=2,
                   vmin=None, vmax=None, cmap="viridis", coordinates="auto", unit_cell=None):
    """Scroll through bin centers of H, K, or L, independent of storage order."""
    destination = _gif_destination(out_path)
    nx.nxsetmemory(20000)
    root = nx.nxload(nxs_path)
    data = resolve_nxdata(root)
    axis_name = axis_name.upper()
    planes = {"H": "KL", "K": "HL", "L": "HK"}
    if axis_name not in planes:
        raise ValueError("axis_name must be H, K, or L")
    centers, _ = reciprocal_axis_coordinates(data, axis_name)
    coord_arr = centers[::max(1, int(stride))]
    if not len(coord_arr):
        raise ValueError("No reciprocal coordinate bins to animate")
    plane = planes[axis_name]

    def frame(index):
        return reciprocal_slice(data, plane=plane, coord=float(coord_arr[index]))

    n_frames = len(coord_arr)
    samples = [frame(i).values for i in range(0, n_frames, max(1, n_frames // 4))]
    norm = _normalization(samples, vmin=vmin, vmax=vmax)
    first = frame(0)
    fig, ax = plt.subplots(figsize=(6, 5), dpi=140)
    try:
        mesh, mode = _start_mesh(ax, first, data, norm, cmap, coordinates, unit_cell)
        title = ax.set_title(f"{plane} slice: {axis_name} = {first.actual_coord:g} r.l.u. ({mode})")
        fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.04, label="Intensity")

        def update(index):
            section = frame(index)
            mesh.set_array(section.values.ravel())
            title.set_text(f"{plane} slice: {axis_name} = {section.actual_coord:g} r.l.u. ({mode})")
            return mesh, title

        animation = FuncAnimation(fig, update, frames=n_frames, blit=True)
        animation.save(str(destination), writer=PillowWriter(fps=fps))
    finally:
        plt.close(fig)
        gc.collect()
    print(f"Exported {n_frames} {plane} slices along {axis_name}: {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nxs", required=True, help="3D reciprocal NeXus volume")
    parser.add_argument("--axis", default="L", choices=["H", "K", "L"])
    parser.add_argument("--output", "-o", required=True, help="Destination GIF path; MP4 is not supported")
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--vmin", type=float)
    parser.add_argument("--vmax", type=float)
    parser.add_argument("--cmap", default="viridis")
    parser.add_argument("--coordinates", choices=["auto", "rlu", "physical"], default="auto",
                        help="auto uses a native/explicit cell for physical geometry; otherwise rlu")
    parser.add_argument("--unit-cell", help="a,b,c,alpha,beta,gamma; explicit cell overrides native metadata")
    args = parser.parse_args()
    animate_volume(args.nxs, args.axis, args.output, fps=args.fps, stride=args.stride,
                   vmin=args.vmin, vmax=args.vmax, cmap=args.cmap,
                   coordinates=args.coordinates, unit_cell=args.unit_cell)


if __name__ == "__main__":
    main()
