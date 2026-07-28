"""What to open on the phone.

The whole admin flow happens on a phone that is not this machine, so the one
thing the terminal must print at boot is the address to type into it. Working
that out by hand -- ifconfig, guess the interface, guess the port -- is the
kind of small friction that makes a monthly task feel like a chore.
"""

from __future__ import annotations

import socket

__all__ = ["lan_address", "startup_banner"]

BOLD, DIM, GREEN, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[0m"

#: Vite's default. The site and the API run side by side during a tally.
SITE_PORT = 5173


def lan_address() -> str | None:
    """This machine's address on the local network.

    Opening a UDP socket toward a public address picks the interface the
    router is on without sending a packet. Nothing leaves the machine, and it
    works offline -- it just returns nothing.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.168.1.1", 9))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def startup_banner(
    port: int, *, source: str, engine: str, site_port: int = SITE_PORT
) -> str:
    host = lan_address()
    lines = [
        "",
        f"{BOLD}GymRats — apuração{RESET}",
        f"{DIM}fonte: {source} · OCR: {engine}{RESET}",
        "",
    ]

    if host:
        lines += [
            f"  no celular:  {GREEN}{BOLD}http://{host}:{site_port}{RESET}",
            f"{DIM}  API:         http://{host}:{port}/api/health{RESET}",
            "",
            f"{DIM}  (o site precisa estar rodando: npm run dev:local){RESET}",
        ]
    else:
        lines += [
            f"{DIM}  sem rede local detectada — só dá para abrir aqui:{RESET}",
            f"  http://localhost:{site_port}",
        ]

    lines.append("")
    return "\n".join(lines)
