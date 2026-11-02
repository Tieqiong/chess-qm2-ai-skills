"""Optional real-DIALS CLI smoke tests using fabricated scaled observations.

Run with a Python belonging to a DIALS installation, for example:
    dials.python -m unittest discover -s tests -p test_dials_export_integration.py

No diffraction images, user datasets, network, or installed-package edits are
used. These tests validate export semantics, not reduction/scaling accuracy.
"""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


def _command(name):
    adjacent = Path(sys.executable).parent / name
    return str(adjacent) if adjacent.is_file() else shutil.which(name)


_COMMANDS = {name: _command(name) for name in (
    "dials.export", "dials.merge", "iotbx.reflection_file_converter"
)}
_HAS_DIALS = importlib.util.find_spec("dials") is not None and all(_COMMANDS.values())


def _hkl_rows(path):
    rows = []
    for line in path.read_text().splitlines():
        index = tuple(int(line[start:start + 4]) for start in (0, 4, 8))
        if index != (0, 0, 0):
            rows.append((index, float(line[12:20]), float(line[20:28])))
    return rows


@unittest.skipUnless(_HAS_DIALS, "requires DIALS Python and export/merge/converter CLIs")
class DialsExportIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="chess-dials-export-")
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)

    def run_cli(self, name, *args):
        result = subprocess.run(
            [_COMMANDS[name], *args], cwd=self.work, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def fabricate_scaled_data(self, space_group="P 1"):
        from cctbx import sgtbx
        from dials.array_family import flex
        from dxtbx.model import Beam, Crystal, Experiment, ExperimentList

        experiment = Experiment(
            identifier="synthetic-export-test",
            beam=Beam((0, 0, 1), wavelength=0.27552),
            crystal=Crystal((10, 0, 0), (0, 11, 0), (0, 0, 12),
                            space_group=sgtbx.space_group_info(symbol=space_group).group()),
        )
        ExperimentList([experiment]).as_file(str(self.work / "scaled.expt"))
        base_indices = [(h, k, l) for h in range(1, 6)
                        for k in range(1, 6) for l in range(1, 6)]
        # 010 is forbidden in P21; retain it to test the unmerged export.
        base_indices.extend([(0, 1, 0), (0, 2, 0), (1, 0, 0)])
        rows = []
        for hkl in base_indices:
            for sign in (1, -1):
                index = tuple(sign * component for component in hkl)
                for repeat in range(4):
                    value = 100 + 13 * hkl[0] + 3 * hkl[1] + hkl[2]
                    value += 10 * (sign == -1) + repeat - 1.5
                    if hkl == (1, 1, 1):
                        value = -1.5 + repeat * 0.1  # weak negative observations
                    elif hkl == (1, 1, 2):
                        value = -12 + repeat * 0.1  # below the default export I/sigma cut
                    rows.append((index, value, 2.0))
        table = flex.reflection_table()
        table["miller_index"] = flex.miller_index([row[0] for row in rows])
        table["id"] = flex.int(len(rows), 0)
        table.experiment_identifiers()[0] = experiment.identifier
        table["flags"] = flex.size_t(len(rows), 0)
        table.set_flags(flex.bool(len(rows), True), table.flags.scaled)
        table["intensity.scale.value"] = flex.double([row[1] for row in rows])
        table["intensity.scale.variance"] = flex.double(len(rows), 4.0)
        table["inverse_scale_factor"] = flex.double(len(rows), 1.0)
        table.as_file(str(self.work / "scaled.refl"))
        return rows

    def export_unmerged(self):
        self.run_cli(
            "dials.export", "scaled.expt", "scaled.refl", "format=shelx",
            "intensity=scale", "shelx.composition=FeTe2", "shelx.scale=False",
            "mtz.min_isigi=None", "shelx.hklout=unmerged.hkl",
            "shelx.ins=unmerged.ins",
        )
        self.assertTrue((self.work / "unmerged.ins").is_file())
        text = (self.work / "unmerged.ins").read_text()
        self.assertIn("SFAC", text)
        self.assertIn("HKLF 4", text)
        return _hkl_rows(self.work / "unmerged.hkl")

    def test_unmerged_retains_original_indices_friedel_pairs_and_absence_violations(self):
        from cctbx import sgtbx
        self.assertTrue(sgtbx.space_group_info(symbol="P 21").group().is_sys_absent((0, 1, 0)))
        expected = self.fabricate_scaled_data(space_group="P 21")
        actual = self.export_unmerged()
        self.assertEqual(actual, expected)
        self.assertTrue(any(row[1] < 0 for row in actual))
        self.assertIn((0, 1, 0), [row[0] for row in actual])
        self.assertIn((0, -1, 0), [row[0] for row in actual])

    def test_merge_mtz_then_converter_writes_mean_intensities(self):
        original = self.fabricate_scaled_data()
        self.export_unmerged()
        self.run_cli(
            "dials.merge", "scaled.expt", "scaled.refl",
            "output.mtz=merged.mtz", "output.html=None",
            "assess_space_group=False", "truncate=False",
        )
        self.assertTrue((self.work / "merged.mtz").is_file())
        self.assertFalse((self.work / "merged.expt").exists())
        self.assertFalse((self.work / "merged.refl").exists())
        self.run_cli(
            "iotbx.reflection_file_converter", "merged.mtz",
            "--label=IMEAN,SIGIMEAN", "--shelx=merged.hkl",
        )
        shutil.copyfile(self.work / "unmerged.ins", self.work / "merged.ins")
        actual = _hkl_rows(self.work / "merged.hkl")
        # IMEAN averages Bijvoet mates, so it is intentionally a convenience
        # product, not the source for later lower-symmetry/anomalous testing.
        self.assertEqual(len(actual), len(original) // 8)
        self.assertTrue(any(row[1] < 0 for row in actual))
        self.assertTrue(all(row[2] > 0 for row in actual))
        expected = {}
        for index, value, sigma in original:
            key = min(index, tuple(-component for component in index))
            expected.setdefault(key, []).append(value)
        for index, value, sigma in actual:
            key = min(index, tuple(-component for component in index))
            self.assertAlmostEqual(value, sum(expected[key]) / 8, places=3)
            self.assertAlmostEqual(sigma, 2.0 / (8 ** 0.5), places=4)


if __name__ == "__main__":
    unittest.main()
