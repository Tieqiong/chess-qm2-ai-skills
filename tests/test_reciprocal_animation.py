"""Tiny NeXus/GIF regressions for native planes and reciprocal geometry."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    import numpy as np
    import nexusformat.nexus as nx
    from PIL import Image

    SCRIPTS = Path(__file__).resolve().parents[1] / "reciprocal-space-animation" / "scripts"
    sys.path.insert(0, str(SCRIPTS))
    import animate_volume as volume
    import animate_temp_series as temperature
except ImportError as error:
    raise unittest.SkipTest(f"Animation tests require the scientific environment and updated nxs_analysis_tools: {error}") from error


class CaptureAnimation:
    records = []

    def __init__(self, fig, update, frames, **kwargs):
        self.fig, self.update, self.frames = fig, update, frames

    def save(self, destination, writer):
        for index in range(self.frames):
            self.update(index)
            ax = self.fig.axes[0]
            mesh = ax.collections[0]
            self.records.append({
                "values": np.asarray(mesh.get_array()).copy(),
                "corners": mesh.get_coordinates().copy(),
                "xlabel": ax.get_xlabel(), "ylabel": ax.get_ylabel(),
                "title": ax.get_title(), "aspect": ax.get_aspect(),
            })


class AnimationGeometryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.h = np.array([-1, 0, 1])  # Int-valued native axes must not become indices.
        self.k = np.array([-2, 0, 2])
        self.l = np.array([-1, 0, 1])
        self.values = np.arange(27).reshape(3, 3, 3) + 10.0
        CaptureAnimation.records = []

    def write_volume(self, path, reversed_axes=False, offset=0.0, cell=None):
        values = self.values + offset
        axes, names = (self.h, self.k, self.l), ("H", "K", "L")
        if reversed_axes:
            values = values.transpose(2, 1, 0)
            axes, names = axes[::-1], ("Ql", "Qk", "Qh")
        data = nx.NXdata(nx.NXfield(values, name="counts"),
                         [nx.NXfield(axis, name=name) for axis, name in zip(axes, names)])
        entry = nx.NXentry()
        entry["transform" if reversed_axes else "data"] = data
        if cell is not None:
            entry["sample"] = nx.NXsample()
            entry.sample["unit_cell"] = nx.NXfield(cell)
        root = nx.NXroot(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        root.save(str(path))
        return path

    def capture_volume(self, path, axis, **kwargs):
        CaptureAnimation.records = []
        with patch.object(volume, "FuncAnimation", CaptureAnimation):
            volume.animate_volume(path, axis, self.directory / "capture.gif", stride=1,
                                  vmin=1, vmax=100, **kwargs)
        return CaptureAnimation.records.copy()

    def test_all_volume_planes_match_across_legacy_and_reversed_storage(self):
        legacy = self.write_volume(self.directory / "legacy.nxs")
        reversed_path = self.write_volume(self.directory / "reversed.nxs", reversed_axes=True)
        for axis, dim in (("H", 0), ("K", 1), ("L", 2)):
            with self.subTest(axis=axis):
                first = self.capture_volume(legacy, axis, coordinates="rlu")
                second = self.capture_volume(reversed_path, axis, coordinates="rlu")
                self.assertEqual(len(first), 3)
                for index, (left, right) in enumerate(zip(first, second)):
                    expected = np.take(self.values, index, axis=dim).T
                    np.testing.assert_array_equal(left["values"].reshape(3, 3), expected)
                    np.testing.assert_array_equal(left["values"], right["values"])
                    np.testing.assert_array_equal(left["corners"], right["corners"])
                    self.assertEqual(left["xlabel"], right["xlabel"])
                    self.assertEqual(left["ylabel"], right["ylabel"])

    def test_temperature_hk_uses_native_plane_and_canonical_orientation(self):
        first = self.write_volume(self.directory / "100" / "data.nxs")
        second = self.write_volume(self.directory / "200" / "transform.nxs", reversed_axes=True, offset=100)
        with patch.object(temperature, "FuncAnimation", CaptureAnimation):
            temperature.animate_temp_series([first, second], "HK", 0, self.directory / "capture.gif",
                                            vmin=1, vmax=200, coordinates="rlu")
        self.assertEqual(len(CaptureAnimation.records), 2)
        for index, record in enumerate(CaptureAnimation.records):
            np.testing.assert_array_equal(record["values"].reshape(3, 3),
                                          self.values[:, :, 1].T + index * 100)
            self.assertEqual(record["xlabel"], "H (r.l.u.)")
            self.assertEqual(record["ylabel"], "K (r.l.u.)")
            self.assertIn("L = 0", record["title"])

    def test_native_hexagonal_cell_uses_full_metric_not_rectangular_aspect(self):
        path = self.write_volume(self.directory / "cell.nxs", cell=(2, 2, 5, 90, 90, 120))
        record = self.capture_volume(path, "L")[0]
        corners = record["corners"]
        along_h = corners[0, 1] - corners[0, 0]
        along_k = corners[1, 0] - corners[0, 0]
        cosine = np.dot(along_h, along_k) / np.linalg.norm(along_h) / np.linalg.norm(along_k)
        self.assertAlmostEqual(cosine, 0.5, places=12)  # reciprocal gamma*=60 degrees
        self.assertIn("Å⁻¹", record["xlabel"])
        self.assertEqual(record["aspect"], 1.0)
        rlu = self.capture_volume(path, "L", coordinates="rlu")[0]
        self.assertEqual(rlu["xlabel"], "H (r.l.u.)")

    def test_physical_mode_requires_cell_and_explicit_cell_overrides_metadata(self):
        path = self.write_volume(self.directory / "no-cell.nxs")
        self.assertEqual(self.capture_volume(path, "L")[0]["xlabel"], "H (r.l.u.)")
        with self.assertRaisesRegex(ValueError, "require"):
            self.capture_volume(path, "L", coordinates="physical")
        explicit = self.capture_volume(path, "L", coordinates="physical", unit_cell="2,3,5,90,90,90")[0]
        self.assertIn("Å⁻¹", explicit["xlabel"])
        path = self.write_volume(self.directory / "native-cell.nxs", cell=(4, 6, 10, 90, 90, 90))
        override = self.capture_volume(path, "L", unit_cell="2,3,5,90,90,90")[0]
        np.testing.assert_allclose(override["corners"], explicit["corners"])

    def test_explicit_rlu_view_does_not_read_malformed_cell_metadata(self):
        path = self.write_volume(self.directory / "invalid-cell.nxs", cell=(1, 2, 3))
        with patch.object(volume, "resolve_unit_cell", side_effect=AssertionError("cell lookup is not needed")):
            record = self.capture_volume(path, "L", coordinates="rlu")[0]
        self.assertEqual(record["xlabel"], "H (r.l.u.)")

    def test_temperature_cli_passes_explicit_color_limits(self):
        arguments = ["animate_temp_series.py", "--pattern", "sample/*/data.nxs",
                     "--output", "temperatures.gif", "--vmin", "0.01", "--vmax", "0.9"]
        with patch.object(sys, "argv", arguments), \
             patch.object(temperature.glob, "glob", return_value=["sample/100/data.nxs"]), \
             patch.object(temperature, "animate_temp_series") as animate:
            temperature.main()
        self.assertEqual(animate.call_args.kwargs["vmin"], 0.01)
        self.assertEqual(animate.call_args.kwargs["vmax"], 0.9)

    def test_tiny_real_gifs_export_and_reopen(self):
        first = self.write_volume(self.directory / "100" / "data.nxs")
        second = self.write_volume(self.directory / "200" / "transform.nxs", reversed_axes=True, offset=10)
        scroll_gif = self.directory / "scroll.gif"
        temp_gif = self.directory / "temperatures.gif"
        volume.animate_volume(first, "L", scroll_gif, stride=1, fps=3, vmin=1, vmax=100,
                              coordinates="physical", unit_cell="2,2,5,90,90,120")
        temperature.animate_temp_series([first, second], "HK", 0, temp_gif, fps=2,
                                        vmin=1, vmax=100, coordinates="rlu")
        for path, expected in ((scroll_gif, 3), (temp_gif, 2)):
            with Image.open(path) as image:
                self.assertEqual(image.format, "GIF")
                self.assertEqual(image.n_frames, expected)
                for frame in range(image.n_frames):
                    image.seek(frame)
                    self.assertGreater(np.asarray(image.convert("RGB")).std(), 0)

    def test_mp4_is_rejected_before_loading_data(self):
        with self.assertRaisesRegex(ValueError, "GIF only"):
            volume.animate_volume("missing.nxs", "L", self.directory / "movie.mp4")


if __name__ == "__main__":
    unittest.main()
