"""Regression checks for cell comparison and DIALS Bravais summaries."""
import contextlib
import importlib.util
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'chess-dials-reduction/scripts/bravais_matcher.py'
spec = importlib.util.spec_from_file_location('bravais_matcher', SCRIPT)
matcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matcher)


def record(**overrides):
    value = dict(unit_cell=[4, 5, 6, 80, 90, 100], bravais='aP',
                 max_angular_difference=0.1, rmsd=0.2, nspots=100,
                 cb_op='-c,a,-b', min_cc=None, max_cc=None, recommended=True)
    value.update(overrides)
    return value


class CellComparisonTests(unittest.TestCase):
    def test_axis_permutation_also_remaps_angles(self):
        # New (a,b,c)=(b,c,a): alpha'=beta, beta'=gamma, gamma'=alpha.
        score, axes = matcher.compare_cells([4, 5, 6, 80, 90, 100],
                                           [5, 6, 4, 90, 100, 80])
        self.assertEqual(score, 0)
        self.assertEqual(axes, (1, 2, 0))

    def test_lengths_alone_do_not_make_nonorthogonal_cells_equal(self):
        self.assertGreater(matcher.score_cell_match([4, 5, 6, 80, 90, 100],
                                                    [5, 6, 4, 80, 90, 100]), 0)

    def test_identity_is_deterministic_for_cubic_cells(self):
        self.assertEqual(matcher.compare_cells([5, 5, 5, 90, 90, 90],
                                               [5, 5, 5, 90, 90, 90]),
                         (0, (0, 1, 2)))

    def test_invalid_cells_rejected(self):
        for cell in ([0, 5, 6, 90, 90, 90], [4, 5, 6, 10, 10, 170],
                     [4, 5, math.nan, 90, 90, 90], [4, 5, 6, 90, 90]):
            with self.subTest(cell=cell), self.assertRaises(ValueError):
                matcher.validate_cell(cell)

    def test_comparison_does_not_change_reindexing_operator(self):
        source = dict(solution=1, cell=[4, 5, 6, 80, 90, 100], lattice='aP',
                      cb_op='-c,a,-b', recommended=True, metric_fit=.1, rmsd=.2)
        _, ranked = matcher.match_bravais_settings([source], [5, 6, 4, 90, 100, 80])[0]
        self.assertEqual(ranked['comparison_axes'], 'b,c,a')
        self.assertEqual(ranked['cb_op'], source['cb_op'])
        self.assertEqual(ranked['cell'], source['cell'])
        self.assertNotIn('comparison_axes', source)

    def test_space_group_is_not_a_bravais_symbol(self):
        with self.assertRaisesRegex(ValueError, 'target-space-group'):
            matcher.normalize_lattice('P6322')
        self.assertEqual(matcher.normalize_lattice('HP'), 'hP')

    def test_missing_metric_is_not_treated_as_perfect_fit(self):
        base = dict(solution=1, cell=[5, 5, 5, 90, 90, 90], lattice='cP',
                    cb_op='a,b,c', recommended=True, metric_fit=None, rmsd=.2)
        valid = dict(base, solution=2, metric_fit=.1)
        rows = matcher.match_bravais_settings([base, valid], target_lattice='cP')
        self.assertEqual(rows[0][1]['solution'], 2)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / 'dials.refine_bravais_settings.log'

    def write_summary(self, data):
        (self.root / 'bravais_summary.json').write_text(json.dumps(data))

    def test_nullable_cc_and_diagnostics_do_not_discard_valid_rows(self):
        self.write_summary({'1': record(max_cc=.9, max_angular_difference=None,
                                        rmsd=float('nan'), nspots=None)})
        row = matcher.parse_bravais_log(self.log)[0]
        self.assertEqual(row['cc'], '-/0.900')
        self.assertIsNone(row['metric_fit'])
        self.assertIsNone(row['rmsd'])
        self.assertIsNone(row['spots'])

    def test_malformed_row_does_not_discard_other_rows(self):
        self.write_summary({'1': record(), 'bad': None, '2': record(unit_cell=None),
                            '3': record(cb_op=None)})
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            rows = matcher.parse_bravais_log(self.log)
        self.assertEqual([row['solution'] for row in rows], [1])
        self.assertIn('skipping invalid Bravais setting', errors.getvalue())

    def test_invalid_json_falls_back_to_log(self):
        (self.root / 'bravais_summary.json').write_text('{invalid')
        self.log.write_text('| * 12 | 0 | 0.288 | 0.288/0.356 | 133 | hP | '
                            '5.22 5.22 13.27 90.00 90.00 120.00 | 314 | a,b,c |\n')
        with contextlib.redirect_stderr(io.StringIO()):
            rows = matcher.parse_bravais_log(self.log)
        self.assertEqual(rows[0]['solution'], 12)
        self.assertEqual(rows[0]['lattice'], 'hP')

    def test_json_output_never_claims_symmetry_selected(self):
        self.write_summary({'1': record()})
        result = subprocess.run([sys.executable, str(SCRIPT), '--log', str(self.log), '--json'],
                                check=True, text=True, capture_output=True)
        value = json.loads(result.stdout)
        self.assertIsNone(value['best_match'])
        self.assertIn('not a symmetry score', value['interpretation'])
        self.assertNotIn('RECOMMENDED SOLUTION', result.stdout)

    def test_best_reference_match_retains_dials_recommendation_flag(self):
        self.write_summary({'1': record(recommended=False)})
        result = subprocess.run([sys.executable, str(SCRIPT), '--log', str(self.log),
                                 '--target-cell', '5 6 4 90 100 80', '--json'],
                                check=True, text=True, capture_output=True)
        value = json.loads(result.stdout)
        self.assertEqual(value['best_score'], 0)
        self.assertFalse(value['best_match']['recommended'])
        self.assertEqual(value['best_match']['comparison_axes'], 'b,c,a')


class SpaceGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import cctbx  # noqa: F401
        except ImportError:
            raise unittest.SkipTest('Run with dials.python for cctbx space-group checks')

    def test_space_group_to_bravais(self):
        for group, lattice in [('P6322', 'hP'), ('P m -3 n', 'cP'),
                               ('P 42/m m c', 'tP'), ('A 1 2 1', 'mC'),
                               ('R 3 :R', 'hR')]:
            with self.subTest(group=group):
                self.assertEqual(matcher.lattice_from_space_group(group), lattice)

    def test_invalid_group_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, 'Invalid space group'):
            matcher.lattice_from_space_group('not-a-space-group')


if __name__ == '__main__':
    unittest.main()
