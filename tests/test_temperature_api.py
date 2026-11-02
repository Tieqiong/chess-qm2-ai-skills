"""Optional real-library smoke tests for the limited temperature API repair.

Run with the existing nxs environment and the matching library source on
PYTHONPATH. Tiny synthetic fixtures exercise complete wrappers, not mocked
TempDependence calls. These do not validate quantitative temperature analysis.
"""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "temperature-series-analysis" / "scripts"


def available_runtime():
    try:
        return all(importlib.util.find_spec(name) is not None for name in (
            "numpy", "matplotlib", "nexusformat", "lmfit",
            "nxs_analysis_tools.reciprocal",
        ))
    except (ModuleNotFoundError, ImportError):
        return False


@unittest.skipUnless(available_runtime(), "requires nxs runtime with reciprocal axis resolver")
class TemperatureApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SCRIPTS))
        cls.addClassCleanup(lambda: sys.path.remove(str(SCRIPTS)))
        import batch_temp_linecuts
        import temp_order_parameter
        import temperature_api
        cls.batch = batch_temp_linecuts
        cls.order = temp_order_parameter
        cls.api = temperature_api

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="chess-temperature-api-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)

    def make_series(self, name, reverse=False):
        import numpy as np
        from nexusformat.nexus import NXdata, NXfield, NXentry, NXroot, nxsave

        sample = self.work / name
        sample.mkdir()
        h = np.linspace(-1, 1, 41)
        k = np.linspace(-0.3, 0.3, 7)
        l = np.linspace(-0.2, 0.2, 5)
        for temperature, amplitude in ((100, 4.0), (200, 3.0)):
            signal = (2 + amplitude * np.exp(-((h[:, None, None] - 0.1) / 0.15) ** 2))
            signal = np.broadcast_to(signal, (len(h), len(k), len(l))).copy()
            if reverse:
                # Native NXRefine linked layout, with a self-contained tiny
                # signal so no external acquisition files are required.
                axes = tuple(NXfield(values, name=label) for values, label in
                             ((l, "Ql"), (k, "Qk"), (h, "Qh")))
                data = NXdata(NXfield(signal.transpose(2, 1, 0), name="data"), axes)
                root = NXroot(NXentry(transform=data))
                path = sample / f"sample_{temperature}.nxs"
            else:
                axes = tuple(NXfield(values, name=label) for values, label in
                             ((h, "H"), (k, "K"), (l, "L")))
                data = NXdata(NXfield(signal, name="counts"), axes)
                root = NXroot(NXentry(data=data))
                folder = sample / str(temperature)
                folder.mkdir()
                path = folder / "3rot_hkli_lite.nxs"
            nxsave(str(path), root)
        return sample

    def assert_png(self, path):
        import matplotlib.image as mpimg
        self.assertTrue(path.is_file(), str(path))
        pixels = mpimg.imread(path)
        self.assertGreater(pixels.size, 100)

    def test_batch_wrapper_completes_for_both_native_layouts(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                sample = self.make_series(f"batch-{reverse}", reverse)
                destination = self.work / f"plots-{reverse}"
                self.batch.run_batch_linecuts(
                    str(sample), "3rot_hkli_lite.nxs", "H", "0,0,0",
                    ".1,.2,.75" if reverse else ".75,.2,.1",
                    None, str(destination), offset=10,
                )
                self.assert_png(destination / "waterfall_linecuts.png")
                self.assert_png(destination / "linecuts_heatmap.png")

    def test_all_fitted_quantity_choices_complete_in_reversed_layout(self):
        sample = self.make_series("fitted", reverse=True)
        for quantity in ("peakheight", "area", "sigma", "center"):
            with self.subTest(quantity=quantity):
                destination = self.work / f"{quantity}.png"
                self.order.run_order_parameter_fit(
                    str(sample), "3rot_hkli_lite.nxs", "H", "0,0,0",
                    ".1,.2,.75", quantity, str(destination), model_type="gaussian",
                )
                self.assert_png(destination)

    def test_lorentzian_wrapper_completes(self):
        sample = self.make_series("lorentzian")
        destination = self.work / "lorentzian.png"
        self.order.run_order_parameter_fit(
            str(sample), "3rot_hkli_lite.nxs", "H", "0,0,0",
            ".75,.2,.1", "area", str(destination), model_type="lorentzian",
        )
        self.assert_png(destination)

    def test_mixed_native_order_is_explicitly_unsupported(self):
        from nxs_analysis_tools.chess import TempDependence

        legacy = TempDependence(str(self.make_series("legacy")))
        legacy.load_datasets(file_ending="3rot_hkli_lite.nxs", print_tree=False)
        reverse = TempDependence(str(self.make_series("reverse", reverse=True)))
        reverse.load_datasets(print_tree=False)
        self.assertEqual(self.api.resolve_temperature_axis(legacy, "H"), 0)
        self.assertEqual(self.api.resolve_temperature_axis(reverse, "H"), 2)
        legacy.datasets[200] = reverse.datasets[200]
        with self.assertRaisesRegex(ValueError, "Mixed reciprocal-axis ordering"):
            self.api.resolve_temperature_axis(legacy, "H")


if __name__ == "__main__":
    unittest.main()
