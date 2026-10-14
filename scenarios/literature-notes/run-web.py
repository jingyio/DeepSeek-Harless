"""Reject the old Web launcher until its task-scoped binding is ported.

The current product Web uses a server-owned Scene Registry. Passing the old
--papers-dir to it would start an unrelated scene or fail after startup.
"""
import sys

if __name__ == '__main__':
    print('literature_web_not_integrated: the literature PDF Web task binding is '
          'not registered in the current product Web; use the explicit '
          'literature CLI until a task-scoped adapter is implemented.', file=sys.stderr)
    raise SystemExit(2)
