import hashlib
import json
import unittest

from benchmarks.research_report_agent_v2.matched_protocol import fixed_decisions, validate_fixed_decision


class MatchedProtocolTests(unittest.TestCase):
    def study(self):
        decisions = {'plan': {'interpretation_mode': 'standard', 'allow_deterministic_continuation': True}}
        encoded = json.dumps(decisions, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return {'benchmark_frozen_decisions': {'protocol_version': 1, **decisions,
                  'decision_sha256': hashlib.sha256(encoded.encode()).hexdigest()}}

    def test_natural_request_is_unconstrained(self):
        self.assertIsNone(fixed_decisions({}))
        validate_fixed_decision({}, 'plan', {'any': 'value'})

    def test_drift_is_rejected_not_silently_replaced(self):
        study = self.study()
        plan = fixed_decisions(study)['plan']
        validate_fixed_decision(study, 'plan', plan)
        plan['allow_deterministic_continuation'] = False
        with self.assertRaisesRegex(ValueError, 'differs'):
            validate_fixed_decision(study, 'plan', plan)
        self.assertTrue(study['benchmark_frozen_decisions']['plan']['allow_deterministic_continuation'])

    def test_modified_frozen_input_and_missing_custom_text_rejected(self):
        study = self.study()
        study['benchmark_frozen_decisions']['plan']['title'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'changed'):
            fixed_decisions(study)
        study = self.study()
        study['benchmark_frozen_decisions']['plan']['interpretation_mode'] = 'custom'
        with self.assertRaisesRegex(ValueError, 'commentary'):
            fixed_decisions(study)

