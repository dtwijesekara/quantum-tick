"""Minimal, isolated auth diagnostic.

Does nothing but authenticate and hit the simplest possible endpoint
(a 5-candle history request), printing the raw result. Run this before
trusting anything else in the stack -- per
docs/postmortem/PROJECT_POSTMORTEM.md Checklist A item 7.

Usage: python scripts/diagnose_auth.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quantum_tick.config import get_settings  # noqa: E402
from quantum_tick.infrastructure.deriv.auth import AccountBootstrap  # noqa: E402
from quantum_tick.infrastructure.deriv.client import DerivClient  # noqa: E402


async def main() -> None:
    settings = get_settings()
    print(f"App ID       : {settings.deriv_app_id}")
    print(f"Account type : {settings.deriv_account_type}")
    print(f"Token        : {settings.deriv_api_token[:6]}...{settings.deriv_api_token[-4:]} "
          f"(len={len(settings.deriv_api_token)})")

    bootstrap = AccountBootstrap(
        app_id=settings.deriv_app_id,
        api_token=settings.deriv_api_token,
        account_type=settings.deriv_account_type,
        currency=settings.deriv_currency,
    )

    print("\n[1/3] REST account bootstrap + OTP...")
    ws_url = await bootstrap.get_websocket_url()
    print(f"      OK - websocket URL obtained ({ws_url.split('?')[0]}?otp=<redacted>)")

    print("[2/3] Connecting WebSocket...")
    async with DerivClient(ws_url) as client:
        print("      OK - connected")

        print("[3/3] ticks_history smoke test (R_10, 5 candles)...")
        resp = await client.request({
            "ticks_history": "R_10",
            "end": "latest",
            "count": 5,
            "style": "candles",
            "granularity": 60,
        })
        candles = resp.get("candles", [])
        print(f"      OK - received {len(candles)} candles")
        for c in candles:
            print(f"        {c}")

    print("\nAll checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
