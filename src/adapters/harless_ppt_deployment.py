"""Resolve fixed optional rendering installations at server startup, per MCP env."""
import hashlib
import os
from pathlib import Path


def configure_ppt_rendering(scene):
    renderer=os.environ.get('HARLESS_PPT_RENDERER_ROOT')
    font=os.environ.get('HARLESS_PPT_FONT_ROOT')
    if not renderer or not font:
        scene['output_unavailable_reason']='ppt_rendering_dependencies_not_deployed';return
    program=Path(renderer).resolve(strict=True)/'program'
    fonts=Path(font).resolve(strict=True)
    files=[program/'soffice.bin',program/'soffice',fonts/'fonts-static.conf',fonts/'NotoSansCJKsc-Regular.otf']
    if any(not p.is_file() or p.is_symlink() for p in files):raise ValueError('invalid fixed PPT rendering installation')
    scene['renderer_root']=str(program.parent);scene['font_root']=str(fonts)
    scene['runtime_file_locks']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    for row in scene['mcp_rows']:
        row['config']['env'].update(PATH=str(program)+os.pathsep+os.environ.get('PATH',''),
            FONTCONFIG_FILE=str(fonts/'fonts-static.conf'),FONTCONFIG_PATH=str(fonts))
    scene['config_sha256']=hashlib.sha256(str((scene['config_sha256'],scene['runtime_file_locks'])).encode()).hexdigest()
