from pathlib import PurePosixPath, PureWindowsPath

import pytest

from src.adapters.trace_paths import relative_trace_path
from src.adapters.native_motif_compiler import normal, compile_read


@pytest.mark.parametrize('work,path', [
    (PurePosixPath('/work'), '/work/source/main.tex'),
    (PureWindowsPath(r'\work'), '/work/source/main.tex'),
    (PureWindowsPath(r'C:\Research\work'), r'C:\Research\work\source\main.tex'),
    (PureWindowsPath(r'C:\Research\work'), 'c:/research/work/source/main.tex'),
])
def test_read_binding_is_portable_without_losing_file_version(work,path):
    args=normal({'file_path':path,'description':'diagnostic'},work)
    assert args=={'file_path':'${WORK}/source/main.tex'}
    result=compile_read({'name':'read','arguments':args},{'source/main.tex':'a'*64})
    assert result['dependencies']=={'source/main.tex':'a'*64}


@pytest.mark.parametrize('value,roots,expected', [
    (r'C:\Task\work\variant\main.tex',['C:/Task/work'],'variant/main.tex'),
    ('/root/task/work/variant/main.tex',['/root/task/work'],'variant/main.tex'),
    ('/root/task/work-other/main.tex',['/root/task/work'],None),
    (r'D:\Task\work\main.tex',['C:/Task/work'],None),
    (r'C:\Task\work\..\outside.tex',['C:/Task/work'],None),
    ('C:main.tex',['C:/Task/work'],None),
])
def test_only_an_explicit_recorded_root_can_bind(value,roots,expected):
    assert relative_trace_path(value,roots,allow_relative=True)==expected


@pytest.mark.parametrize('outside', ['/work-other/main.tex', r'C:\Other\main.tex', r'..\outside.tex'])
def test_unbound_paths_are_not_turned_into_fake_work_dependencies(outside):
    args=normal({'file_path':outside},PurePosixPath('/work'))
    assert args['file_path']==outside
    with pytest.raises(ValueError):
        compile_read({'name':'read','arguments':args},{'main.tex':'a'*64})
