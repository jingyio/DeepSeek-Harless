"""Fixed, read-only JSON calculation used by the public protocol diagnostic."""
import json
import sys


def group_count(rows):
    result = {}
    for row in rows:
        group = row['group']
        if not isinstance(group, str) or not group:
            raise ValueError('group must be a nonempty string')
        result[group] = result.get(group, 0) + 1
    return dict(sorted(result.items()))


if __name__ == '__main__':
    value = json.load(sys.stdin)
    print(json.dumps({'counts': group_count(value['rows'])}, ensure_ascii=False, separators=(',', ':')))
