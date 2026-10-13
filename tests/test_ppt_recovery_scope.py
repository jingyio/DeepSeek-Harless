"""Checkpoint report path diagnostics; no rendering or model quality claim."""
from pathlib import Path
import tempfile
import unittest

from scenarios.research_ppt.recovery import CheckpointPPTService, CheckpointRejected
from scenarios.research_ppt.service import ROOT


class RecoveryScopeTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / '.local/recovery-scope-tests'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.area = Path(self.temp.name)
        self.service = object.__new__(CheckpointPPTService)
        self.service.job_path = self.area / 'job.json'
        self.service.job = {'slides': 1}
        self.service.input_version = 'current'
        self.service.decks = {'deck': self.area / 'outputs/deck/presentation.pptx'}
        self.service.deck_records = {'deck': {'sha256': 'a' * 64}}

    def tearDown(self):
        self.temp.cleanup()

    def report(self, root):
        return {'validation_id': 'validation-test', 'deck_id': 'deck', 'passed': False,
                'input_version': 'current', 'file_sha256': 'a' * 64,
                'pptx_path': str(self.service.decks['deck']), 'artifacts': [],
                'report_path': str(root / 'diagnostic/report.json')}

    def test_current_task_and_historical_cli_report_locations_reach_file_guard(self):
        for root in (self.area / 'validation', ROOT / '.local/research-ppt/validation'):
            # Missing bytes revoke validation, rather than authorizing delivery.
            self.assertEqual(self.service._validation_check('validation-test', self.report(root)),
                             'preview_artifact_missing_or_changed')

    def test_foreign_task_report_and_symlink_to_foreign_root_are_rejected(self):
        foreign = self.area / 'other-task/validation'
        foreign.mkdir(parents=True)
        for root in (foreign, self.area / 'validation'):
            if root != foreign:
                root.symlink_to(foreign, target_is_directory=True)
            with self.assertRaisesRegex(CheckpointRejected, '路径越界'):
                self.service._validation_check('validation-test', self.report(root))


if __name__ == '__main__':
    unittest.main()
