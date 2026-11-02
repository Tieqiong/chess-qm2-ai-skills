"""Shared rendering; intensity policy remains provisional (see the analysis status)."""

import numpy as np
from matplotlib.colors import LogNorm
from matplotlib.ticker import MultipleLocator

try:
    from nxs_analysis_tools.reciprocal import physical_mesh, resolve_unit_cell
except ImportError as exc:
    raise ImportError(
        "These scripts require the reciprocal slicing API in Tieqiong/nxs_analysis_tools. "
        "Use that checkout on PYTHONPATH; see reciprocal-space-plotting/SKILL.md."
    ) from exc


def display_cell(data, unit_cell, coordinates):
    """Return a validated cell for physical rendering, or None for an r.l.u. view."""
    if coordinates not in ("auto", "physical", "rlu"):
        raise ValueError("coordinates must be auto, physical, or rlu")
    if coordinates == "rlu":
        return None
    cell = resolve_unit_cell(data, unit_cell)
    if coordinates == "physical" and cell is None:
        raise ValueError("Physical coordinates require sample/unit_cell metadata or --unit-cell")
    return cell


def provisional_norm(sections, vmin=None, vmax=None):
    """Keep the existing count-oriented limits until intensity policy is updated."""
    arrays = [np.asarray(section.values, dtype=np.float32) for section in sections]
    positive = np.concatenate([a[a > 0] for a in arrays])
    if not positive.size:
        positive = np.array([1.0, 10.0])
    low = float(vmin) if vmin is not None else max(1.0, float(np.nanpercentile(positive, 5)))
    high = float(vmax) if vmax is not None else float(np.nanpercentile(positive, 99.8))
    if high <= low and vmax is None:
        high = low * 10.0
    if not np.isfinite([low, high]).all() or not 0 < low < high:
        raise ValueError("Logarithmic limits must be finite and satisfy 0 < vmin < vmax")
    return LogNorm(vmin=low, vmax=high)


def draw_section(ax, section, cell, norm, cmap):
    """Draw the canonical (vertical, horizontal) signal on its true bin edges."""
    if cell is None:
        x, y = np.meshgrid(section.x_edges, section.y_edges)
        ax.set_xlabel(f"{section.plane[0]} (r.l.u.)")
        ax.set_ylabel(f"{section.plane[1]} (r.l.u.)")
        ax.xaxis.set_major_locator(MultipleLocator(2))
        ax.xaxis.set_minor_locator(MultipleLocator(1))
        ax.yaxis.set_major_locator(MultipleLocator(2))
        ax.yaxis.set_minor_locator(MultipleLocator(1))
        mode = "r.l.u. view"
    else:
        x, y = physical_mesh(section, cell)
        # Cartesian coordinates local to this plane, relative to its fixed-axis origin.
        ax.set_xlabel(f"q parallel to {section.plane[0]}* (Å⁻¹)")
        ax.set_ylabel(f"q perpendicular to {section.plane[0]}* in {section.plane} (Å⁻¹)")
        mode = "physical view; no 2π"
    mesh = ax.pcolormesh(x, y, section.values, shading="flat", norm=norm, cmap=cmap)
    ax.set_aspect("equal")
    ax.tick_params(direction="in", top=True, right=True, which="both")
    title = f"{section.plane}: {section.fixed_axis} = {section.actual_coord:g} r.l.u."
    if not np.isclose(section.requested_coord, section.actual_coord):
        title += f" (requested {section.requested_coord:g})"
    ax.set_title(f"{title}\n{mode}")
    return mesh
