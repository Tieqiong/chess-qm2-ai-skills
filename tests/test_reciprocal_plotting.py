"""Regression checks for CLI wiring, physical display, and storage-order invariance."""

import importlib.util
from pathlib import Path
import sys
import unittest

try:
    import matplotlib
    import numpy as np
    import pytest
    from nexusformat.nexus import NXdata, NXentry, NXfield, NXroot, NXsample
    from nxs_analysis_tools.reciprocal import reciprocal_slice
except ImportError as exc:
    raise unittest.SkipTest("Requires the updated analysis library and plotting test dependencies") from exc
matplotlib.use("Agg")
from matplotlib.figure import Figure

SCRIPTS = Path(__file__).resolve().parents[1] / "reciprocal-space-plotting" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"review_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


single = load_script("plot_slice")
summary = load_script("plot_summary")


def volume(tmp_path, order=(0, 1, 2), cell=None):
    coordinates = [np.array([-1., 0., 1.]), np.array([-2., 0., 2., 4.]), np.array([-3., 0., 3., 6., 9.])]
    h, k, l = np.meshgrid(*coordinates, indexing="ij")
    signal = 1000 + 100 * h + 10 * k + l
    names = ("H", "K", "L") if order == (0, 1, 2) else ("Qh", "Qk", "Ql")
    data = NXdata(NXfield(signal.transpose(order), name="counts"),
                  tuple(NXfield(coordinates[i], name=names[i]) for i in order))
    entry = NXentry()
    entry["data" if order == (0, 1, 2) else "transform"] = data
    if cell is not None:
        entry["sample"] = NXsample(unit_cell=NXfield(cell))
    path = tmp_path / f"volume_{''.join(map(str, order))}.nxs"
    NXroot(entry).save(str(path))
    return path, signal


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 1, 0), (1, 2, 0)])
@pytest.mark.parametrize("plane,index", [("HK", 2), ("HL", 1), ("KL", 0)])
def test_single_cli_preserves_named_plane(tmp_path, monkeypatch, order, plane, index):
    path, raw = volume(tmp_path, order)
    captured = []
    monkeypatch.setattr(Figure, "savefig", lambda fig, *a, **k: captured.append(fig))
    single.plot_single_slice(str(path), plane, 0., tmp_path / "out.png", coordinates="rlu")
    ax = captured[0].axes[0]
    expected = np.take(raw, 1, axis=index).T
    np.testing.assert_array_equal(ax.collections[0].get_array(), expected)
    assert ax.get_xlabel() == f"{plane[0]} (r.l.u.)"
    assert ax.get_ylabel() == f"{plane[1]} (r.l.u.)"


def test_summary_matches_single_and_uses_bin_edges(tmp_path, monkeypatch):
    path, raw = volume(tmp_path, (2, 1, 0))
    captured = []
    monkeypatch.setattr(Figure, "savefig", lambda fig, *a, **k: captured.append(fig))
    summary.generate_3panel_summary(str(path), tmp_path / "out.png", coordinates="rlu")
    axes = captured[0].axes[:3]
    for ax, index in zip(axes, (2, 1, 0)):
        np.testing.assert_array_equal(ax.collections[0].get_array(), np.take(raw, 1, axis=index).T)
    corners = axes[0].collections[0].get_coordinates()
    np.testing.assert_allclose(corners[0, :, 0], [-1.5, -0.5, 0.5, 1.5])
    np.testing.assert_allclose(corners[:, 0, 1], [-3., -1., 1., 3., 5.])


def test_native_cell_enables_physical_coordinates(tmp_path, monkeypatch):
    path, _ = volume(tmp_path, (2, 1, 0), cell=[4., 2., 6., 90., 90., 120.])
    captured = []
    monkeypatch.setattr(Figure, "savefig", lambda fig, *a, **k: captured.append(fig))
    single.plot_single_slice(str(path), "HK", 0., tmp_path / "out.png")
    ax = captured[0].axes[0]
    mesh = ax.collections[0].get_coordinates()
    dh = mesh[0, 1] - mesh[0, 0]
    dk = (mesh[1, 0] - mesh[0, 0]) / 2
    assert np.linalg.norm(dk) / np.linalg.norm(dh) == pytest.approx(2.)
    angle_cos = np.dot(dh, dk) / np.linalg.norm(dh) / np.linalg.norm(dk)
    assert angle_cos == pytest.approx(0.5)
    assert "Å⁻¹" in ax.get_xlabel()
    assert ax.get_aspect() == 1.0


def test_no_cell_is_not_fabricated(tmp_path):
    path, _ = volume(tmp_path)
    with pytest.raises(ValueError, match="require"):
        single.plot_single_slice(str(path), "HK", 0., tmp_path / "out.png", coordinates="physical")


def test_png_exports(tmp_path):
    path, _ = volume(tmp_path, (2, 1, 0), cell=[4., 2., 6., 90., 90., 120.])
    png = tmp_path / "slice.png"
    panels = tmp_path / "summary.png"
    single.plot_single_slice(str(path), "HK", 0., png)
    summary.generate_3panel_summary(str(path), panels)
    for output in (png, panels):
        assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert output.stat().st_size > 1000
