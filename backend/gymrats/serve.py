"""Start the admin API.

    uv run --extra api python -m gymrats.serve

Listens on 0.0.0.0 and prints the address to open on the phone. The phone is
where the screenshots are, so that address is the point of the whole command.
"""

from __future__ import annotations

import argparse

import uvicorn

from .api.banner import startup_banner
from .api.config import Settings


def main(argv: list[str] | None = None) -> int:
    settings = Settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--site-port", type=int, default=5173, help="onde o Vite está")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)

    print(
        startup_banner(
            args.port,
            source=settings.source,
            engine=settings.ocr,
            site_port=args.site_port,
        )
    )

    uvicorn.run(
        "gymrats.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
