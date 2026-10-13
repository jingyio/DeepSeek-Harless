"""仅检查薄启动器的凭证隔离；不是模型、MCP 或渲染效果证据。"""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from scenarios.research_ppt.direct_edit import ROOT, SCENE, command, launch


class DirectEditLauncherTests(unittest.TestCase):
    def test_no_node_or_no_build_rejects_before_launch(self):
        with patch('scenarios.research_ppt.direct_edit.shutil.which', return_value=None):
            with self.assertRaises(RuntimeError):
                command(['--help'])

    def test_thin_launcher_keeps_interpreter_and_font_without_secrets(self):
        supplied = {'PATH': '/safe/path', 'FONTCONFIG_FILE': '/safe/fonts.conf',
                    'FONTCONFIG_PATH': '/safe/fonts', 'DEEPSEEK_API_KEY': 'must-not-copy',
                    'OPENAI_API_KEY': 'must-not-copy', 'NODE_OPTIONS': '--require forbidden.js'}
        with patch.dict(os.environ, supplied, clear=True), \
                patch('scenarios.research_ppt.direct_edit.command', return_value=['node', 'fixed.js', '--help']), \
                patch('scenarios.research_ppt.direct_edit.subprocess.call', return_value=0) as invoke:
            self.assertEqual(launch(['--help']), 0)
        called = invoke.call_args
        self.assertEqual(called.kwargs['cwd'], ROOT)
        env = called.kwargs['env']
        self.assertEqual(env['SSS_PPT_DELIVERY_PYTHON'], sys.executable)
        self.assertEqual(env['FONTCONFIG_FILE'], supplied['FONTCONFIG_FILE'])
        self.assertEqual(env['FONTCONFIG_PATH'], supplied['FONTCONFIG_PATH'])
        self.assertEqual(env['PATH'], supplied['PATH'])
        for secret in ('DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'NODE_OPTIONS'):
            self.assertNotIn(secret, env)


if __name__ == '__main__':
    unittest.main()
