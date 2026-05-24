"""PyInstaller entry point.

When PyInstaller runs `--onefile` against a module file, it executes
that file as `__main__` with no `__package__`, which breaks the
`from . import __version__` relative import inside `main.py`. Pointing
the build at this absolute-import shim instead keeps the rest of the
package as ordinary modules importable from both the bundle and
`python -m busylight_presence`.
"""

import sys

from busylight_presence.main import main

if __name__ == "__main__":
    sys.exit(main())
