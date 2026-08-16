"""Live trading orchestration -- the modularized equivalent of dt_bot_v8's
run_bot() loop, built on DerivClient + SignalService + an injected trade
repository instead of module globals.

Safety interlock: real orders only fire when both
`settings.dry_run is False` AND `settings.deriv_account_type == "real"`.
Anything else (the default) logs what *would* have been traded. This
project's own backtests (docs/research/RESEARCH_FINDINGS.md) found no
statistically validated edge for this v8 ruleset, so real-money trading
should stay opt-in.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from quantum_tick.config import Settings
from quantum_tick.domain.models import StrategyParams
from quantum_tick.infrastructure.deriv.auth import AccountBootstrap
from quantum_tick.infrastructure.deriv.client import DerivClient
from quantum_tick.infrastructure.deriv.exceptions import DerivApiError
from quantum_tick.persistence.models import LiveTrade
from quantum_tick.persistence.repository import LiveTradeRepository
from quantum_tick.services.signal_service import SignalService

log = logging.getLogger("quantum_tick.live")


class LiveTradingService:
    def __init__(
        self,
        settings: Settings,
        params: StrategyParams,
        trade_repo: LiveTradeRepository,
    ):
        self._settings = settings
        self._params = params
        self._trade_repo = trade_repo
        self._signal_service = SignalService(params)

        self._session_pnl = 0.0
        self._trades_today = 0

        self._live_enabled = (not settings.dry_run) and settings.deriv_account_type == "real"
        if not self._live_enabled:
            log.warning("DRY RUN — no real orders will be placed (dry_run=%s, account_type=%s)",
                        settings.dry_run, settings.deriv_account_type)

    async def run(self) -> None:
        bootstrap = AccountBootstrap(
            app_id=self._settings.deriv_app_id,
            api_token=self._settings.deriv_api_token,
            account_type=self._settings.deriv_account_type,
            currency=self._settings.deriv_currency,
        )

        candle_count = self._params.min_candles_needed() + 14

        while True:
            try:
                ws_url = await bootstrap.get_websocket_url()
                async with DerivClient(ws_url) as client:
                    log.info("Connected to Deriv (%s account)", self._settings.deriv_account_type)
                    await self._scan_loop(client, candle_count)
                    return  # daily limit hit inside _scan_loop
            except (ConnectionError, OSError) as exc:
                log.warning("Connection dropped (%s). Reconnecting in 5s...", exc)
                await asyncio.sleep(5)
            except Exception as exc:  # noqa: BLE001 - keep the bot alive across unexpected API hiccups
                log.error("Error: %s", exc)
                await asyncio.sleep(5)

    async def _scan_loop(self, client: DerivClient, candle_count: int) -> None:
        symbols = self._settings.symbol_list

        while True:
            if self._session_pnl <= -self._settings.max_daily_loss:
                log.warning("Daily loss limit reached. Stopping.")
                self._print_summary()
                return
            if self._trades_today >= self._settings.max_trades_per_day:
                log.warning("Max %d trades reached.", self._settings.max_trades_per_day)
                self._print_summary()
                return

            trade_executed = False
            last_duration = 10

            for symbol in symbols:
                if trade_executed:
                    break

                try:
                    resp = await client.request({
                        "ticks_history": symbol,
                        "end": "latest",
                        "count": candle_count,
                        "style": "candles",
                        "granularity": self._settings.timeframe_seconds,
                    })
                except DerivApiError as exc:
                    log.error("[%s] history fetch failed: %s", symbol, exc)
                    await asyncio.sleep(1)
                    continue

                candles = resp.get("candles", [])
                signal = self._signal_service.evaluate(candles, symbol)
                if signal:
                    success = await self._execute_trade(client, signal)
                    if success:
                        trade_executed = True
                        last_duration = signal.duration_mins

                await asyncio.sleep(1)

            if trade_executed:
                wait = last_duration * 60 + 15
                log.info("  Waiting %ds (%dmin + buffer)...", wait, last_duration)
                await asyncio.sleep(wait)
            else:
                log.info("  [%s] No setup — next scan in 10s", datetime.now().strftime("%H:%M:%S"))
                await asyncio.sleep(10)

    async def _execute_trade(self, client: DerivClient, signal) -> bool:
        tech = " + ".join(signal.entries)
        log.info("=" * 57)
        log.info(f"  TRADE #{self._trades_today + 1}  [{signal.symbol}] {signal.contract_type}")
        log.info(f"  Trend      : {signal.trend}  |  Structure : {signal.structure}")
        log.info(f"  Technique  : {tech}")
        log.info(f"  Entry price: {signal.price:.4f}")
        log.info(f"  Target     : {signal.target:.4f}  ({signal.distance:.4f} away)")
        log.info(f"  Avg body   : {signal.avg_body:.4f}  =>  Duration: {signal.duration_mins} min")

        try:
            prop = await client.request({
                "proposal": 1,
                "amount": self._settings.stake,
                "basis": "stake",
                "contract_type": signal.contract_type,
                "currency": self._settings.deriv_currency,
                "duration": signal.duration_mins,
                "duration_unit": "m",
                "underlying_symbol": signal.symbol,
            })
        except DerivApiError as exc:
            log.error("Proposal error: %s", exc)
            return False

        payout = prop["proposal"]["payout"]
        pid = prop["proposal"]["id"]
        log.info(f"  Payout     : ${payout:.2f}  |  Stake: ${self._settings.stake:.2f}")

        if not self._live_enabled:
            log.info("  [DRY RUN]  Would BUY here — no order placed.")
            log.info("=" * 57)
            return False

        try:
            buy = await client.request({"buy": pid, "price": self._settings.stake})
        except DerivApiError as exc:
            log.error("Buy error: %s", exc)
            return False

        self._trades_today += 1
        tx = buy["buy"]["transaction_id"]
        log.info(f"  [PLACED]   TX: {tx}")
        log.info(f"  Trades     : {self._trades_today}/{self._settings.max_trades_per_day}  "
                  f"|  Session P&L: ${self._session_pnl:.2f}")
        log.info("=" * 57)

        self._trade_repo.add(LiveTrade(
            symbol=signal.symbol,
            contract_type=signal.contract_type,
            technique=tech,
            entry_price=signal.price,
            stake=self._settings.stake,
            payout=payout,
            duration_mins=signal.duration_mins,
            transaction_id=str(tx),
            status="open",
        ))
        return True

    def _print_summary(self) -> None:
        log.info("-" * 57)
        log.info("  SESSION SUMMARY")
        log.info(f"  Trades placed : {self._trades_today}")
        log.info(f"  Techniques    : {self._signal_service.technique_counts}")
        log.info(f"  Skip reasons  : {self._signal_service.skip_counts}")
        log.info("-" * 57)
