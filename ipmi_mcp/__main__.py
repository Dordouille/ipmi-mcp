"""Entry point: run the MCP server over stdio transport."""

from __future__ import annotations

from .server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
