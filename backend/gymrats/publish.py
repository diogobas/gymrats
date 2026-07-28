"""Generate the JSON the static site reads.

    uv run python -m gymrats.publish
    uv run python -m gymrats.publish --out /tmp/preview

Recomputes every month and season from ``data/`` and writes
``frontend/public/data/``. Commit what it produces -- that is what the site
serves. Use ``report`` to look at a tally without writing anything.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .storage.publisher import DEFAULT_OUTPUT, Publisher
from .storage.repository import Repository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data", type=Path)
    parser.add_argument("--out", default=DEFAULT_OUTPUT, type=Path)
    parser.add_argument(
        "--generated-at",
        default=None,
        help="override the timestamp, to compare two runs byte for byte",
    )
    args = parser.parse_args(argv)

    repo = Repository(args.data)
    if not repo.months() and not repo.history_years():
        parser.error(f"nothing to publish: {args.data} has no months and no history")

    written = Publisher(repo, args.out).publish(generated_at=args.generated_at)
    for path in written:
        print(path)
    print(f"\n{len(written)} arquivos em {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
