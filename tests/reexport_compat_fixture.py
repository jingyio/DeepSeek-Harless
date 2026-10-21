"""Isolated compatibility-test copies; published evidence is never rewritten."""
from pathlib import Path
import shutil


def prepare_checkout(compat, source_root, root):
    root.mkdir()
    assert root.resolve() != source_root.resolve()
    names = set(compat.ADDITIONAL_LOCKS)
    published = {}
    for old, *_ in compat.RELEASES:
        source = source_root / 'motif-libraries' / old
        published.update({path: path.read_bytes() for path in source.iterdir() if path.is_file()})
        shutil.copytree(source, root / 'motif-libraries' / old)
        names.update(compat.read(source / 'certification.json')['code_locks'])
    for name in names:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / name, destination)

    # Exercise each historical wrapper's exact allowlist independently of later
    # runtime edits. Only test-copy certificates get current unrelated locks.
    # Approved differences retain historical hashes; append harmless whitespace
    # to a copied source if a future checkout happens to match the old hash.
    for old, _, _, _, allowed in compat.RELEASES:
        locks = compat.read(root / 'motif-libraries' / old / 'certification.json')['code_locks']
        assert allowed <= set(locks)
        for name in allowed:
            path = root / name
            if compat.sha(path) == locks[name]:
                path.write_bytes(path.read_bytes() + b'\n')
    for old, _, _, _, allowed in compat.RELEASES:
        directory = root / 'motif-libraries' / old
        cert = compat.read(directory / 'certification.json')
        cert['code_locks'].update({name: compat.sha(root / name)
                                   for name in cert['code_locks'] if name not in allowed})
        compat.write(directory / 'certification.json', cert)
        entry = compat.read(directory / 'entry.json')
        entry['files']['certification.json'] = compat.sha(directory / 'certification.json')
        compat.write(directory / 'entry.json', entry)

    registry = compat.read(source_root / 'config/harless-scenes.json')
    for old, _, scene, *_ in compat.RELEASES:
        next(row for row in registry['scenes'] if row['id'] == scene)['rsi']['runtime_bundle'] = (
            'motif-libraries/' + compat.REGISTRY_SELECTED[old])
    compat.write(root / 'config/harless-scenes.json', registry)
    return published


def remove_expected_difference(compat, root, name):
    """Make one approved source equal its test-copy lock to test exact equality."""
    for old, *_ in compat.RELEASES:
        directory = root / 'motif-libraries' / old
        cert = compat.read(directory / 'certification.json')
        cert['code_locks'][name] = compat.sha(root / name)
        compat.write(directory / 'certification.json', cert)
        entry = compat.read(directory / 'entry.json')
        entry['files']['certification.json'] = compat.sha(directory / 'certification.json')
        compat.write(directory / 'entry.json', entry)
