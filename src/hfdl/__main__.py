"""`python -m hfdl` - what the launcher runs.

A module rather than a console script on purpose: a `uv sync` right after the
project is rebuilt leaves the trampolines in `.venv\\Scripts` pointing at a path
that has not been rewritten yet, and the entry point fails with "uv trampoline
failed to canonicalize script path". Running a module does not go near that.
"""

from __future__ import annotations

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
