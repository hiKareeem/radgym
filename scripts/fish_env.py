#!/usr/bin/env python3
"""Extract fish universal --export vars and print as KEY=VALUE lines.

Used by the baseline-runner launch pipeline because the shell-based
approach (`fish -c 'echo $VAR'` or grep+sed+python pipes) was corrupting
long keys. This reads fish_variables directly with proper hex decoding.

Usage:
    python scripts/fish_env.py OPENAI_API_KEY ANTHROPIC_API_KEY ...
    # Prints one KEY=value line per name found.

    # In bash:
    eval "$(python scripts/fish_env.py OPENAI_API_KEY | sed 's/^/export /')"
"""
import re
import sys
from pathlib import Path


def main() -> int:
    fv_path = Path.home() / ".config" / "fish" / "fish_variables"
    if not fv_path.exists():
        print(f"ERROR: {fv_path} not found", file=sys.stderr)
        return 1
    wanted = set(sys.argv[1:])
    if not wanted:
        print("usage: fish_env.py VAR1 [VAR2 ...]", file=sys.stderr)
        return 2

    found: dict[str, str] = {}
    for line in fv_path.read_text().splitlines():
        m = re.match(r"SETUVAR --export ([^:]+):(.*)$", line)
        if not m:
            continue
        name, raw = m.group(1), m.group(2)
        if name not in wanted:
            continue
        decoded = re.sub(
            r"\\x([0-9a-f]{2})", lambda mm: chr(int(mm.group(1), 16)), raw
        )
        found[name] = decoded

    missing = wanted - set(found)
    if missing:
        print(f"WARN: missing in fish_variables: {sorted(missing)}", file=sys.stderr)

    for name in sys.argv[1:]:
        if name in found:
            # Print raw KEY=value — no quoting; caller is responsible
            print(f"{name}={found[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
