"""Check trusted-pixel polarity and prevent accidental array broadcasting."""
import importlib.util
from pathlib import Path
import pickle
import tempfile
import types
import unittest
from unittest.mock import patch

try:
    import numpy as np
    from scitbx.array_family import flex
except ImportError:
    flex = None

SCRIPT = Path(__file__).resolve().parents[1] / "chess-dials-reduction/scripts/mask_to_dials.py"
spec = importlib.util.spec_from_file_location("mask_to_dials", SCRIPT)
mask_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mask_module)


@unittest.skipIf(flex is None, "Run with dials.python for flex mask checks")
class MaskConversionTests(unittest.TestCase):
    def convert(self, data, base):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, existing = root / "mask's.edf", root / "out.mask", root / "base.mask"
            source.write_bytes(b"mock EDF reader input")
            with existing.open("wb") as stream:
                pickle.dump(tuple(flex.bool(panel) for panel in base), stream)
            fake_fabio = types.SimpleNamespace(open=lambda _: types.SimpleNamespace(data=data))
            with patch.dict("sys.modules", {"fabio": fake_fabio}):
                mask_module.convert_edf_to_dials_mask(str(source), str(target), str(existing))
            with target.open("rb") as stream:
                return pickle.load(stream)[0].as_numpy_array().copy()

    def test_masks_are_intersected_with_correct_polarity(self):
        data = np.array([[0, 1], [0, 0]])
        base = np.array([[True, True], [False, True]])
        np.testing.assert_array_equal(self.convert(data, [base]), [[True, False], [False, True]])

    def test_broadcastable_wrong_shape_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "shape"):
            self.convert(np.zeros((1, 2)), [np.ones((2, 2), dtype=bool)])

    def test_multiple_panels_are_not_silently_truncated(self):
        with self.assertRaisesRegex(ValueError, "single detector panel"):
            self.convert(np.zeros((2, 2)), [np.ones((2, 2), dtype=bool)] * 2)


if __name__ == "__main__":
    unittest.main()
