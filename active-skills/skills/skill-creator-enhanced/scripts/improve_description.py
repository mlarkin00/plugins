#!/usr/bin/env python3
"""Deprecated shim. Use `scripts.propose` instead.

This module used to call the Anthropic API directly through the `anthropic` SDK,
which required `ANTHROPIC_API_KEY` and therefore did not work on any machine
authenticating Claude Code through OAuth. The implementation moved to
`scripts/propose.py`, which shells out to `claude -p` and inherits the user's
existing auth.

Kept for one release because `SKILL.md` and existing scripts reference this name.
The `client` argument is accepted and ignored.
"""

import sys
import warnings

from scripts.propose import (  # noqa: F401  (re-exported for compatibility)
    ProposeError,
    build_prompt,
    call_claude,
    extract_description,
    improve_description,
)
from scripts.propose import main as _main

__all__ = [
    "improve_description",
    "build_prompt",
    "call_claude",
    "extract_description",
    "ProposeError",
]

warnings.warn(
    "scripts.improve_description is deprecated; import scripts.propose instead",
    DeprecationWarning,
    stacklevel=2,
)


def main() -> None:
    print(
        "note: improve_description.py is deprecated; use `python -m scripts.propose`",
        file=sys.stderr,
    )
    _main()


if __name__ == "__main__":
    main()
