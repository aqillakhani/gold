"""Entry point: python -m gold"""

from __future__ import annotations

import argparse
import asyncio
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gold",
        description="Gold — Autonomous Social Media Content Automation",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate and render content but do not post",
    )
    parser.add_argument(
        "--generate", metavar="ACCOUNT_ID", nargs="?", const="all",
        help="Generate content now for an account (or all accounts)",
    )
    parser.add_argument(
        "--dashboard-only", action="store_true",
        help="Only run the monitoring dashboard",
    )
    args = parser.parse_args()

    # Import here to avoid circular imports and allow --help without deps
    from .app import GoldApp
    from .config import Config

    config = Config()

    # Override dry_run if flag is passed
    if args.dry_run:
        config.settings.setdefault("app", {})["dry_run"] = True

    app = GoldApp(config)

    if args.generate:
        account_id = None if args.generate == "all" else args.generate
        asyncio.run(app.generate_now(account_id))
    elif args.dashboard_only:
        import uvicorn
        port = config.get("monitoring.dashboard_port", 8420)
        print(f"Dashboard at http://localhost:{port}")
        uvicorn.run(app.dashboard, host="0.0.0.0", port=port, log_level="info")
    else:
        app.run()


if __name__ == "__main__":
    main()
