import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location('ci_annotations',
    Path(__file__).resolve().parents[1] / 'scripts/annotate-ci-failures.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_junit_errors_are_readable_and_cannot_inject_workflow_commands(tmp_path, capsys):
    path = tmp_path / 'results.xml'
    path.write_text('''<testsuites><testsuite>
      <testcase classname="controller" name="passes" />
      <testcase classname="controller" name="fails"><failure>AssertionError\n::warning::100% diagnostic</failure></testcase>
      <testcase classname="module" name="imports"><error message="ImportError" /></testcase>
    </testsuite></testsuites>''', encoding='utf-8')
    module.annotate(path)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert 'controller.fails%0AAssertionError%0A::warning::100%25 diagnostic' in lines[0]
    assert 'module.imports%0AImportError' in lines[1]


def test_missing_python_report_does_not_hide_a_node_failure(tmp_path, capsys):
    module.annotate(tmp_path / 'missing.xml')
    assert 'Node tests' in capsys.readouterr().out
