#!/usr/bin/env python3
"""Install the byte-pinned upstream skill from an already downloaded package."""
from pathlib import Path
import argparse
import json
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenarios.ppt_master.package import read_lock, read_verified, verify_installation


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--destination', type=Path, required=True)
    a = p.parse_args()
    lock = read_lock()
    # Validate every byte before creating a new installation. No overwrite.
    for name in lock['files']: read_verified(a.source, name, lock)
    a.destination.mkdir(parents=True, exist_ok=False)
    for name in lock['files']:
        dest = a.destination / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a.source / name, dest)
    verify_installation(a.destination)
    print(json.dumps({'root':str(a.destination.resolve()),'version':lock['version'],
                      'package_sha256':lock['package_sha256'],'files':len(lock['files'])}))


if __name__ == '__main__': main()
