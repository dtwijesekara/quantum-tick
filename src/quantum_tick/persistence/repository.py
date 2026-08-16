from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from quantum_tick.persistence.models import BacktestRun, BacktestTrade, CandleBar, LiveTrade


class CandleRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def upsert_many(self, symbol: str, granularity: int, candles: list[dict]) -> int:
        if not candles:
            return 0
        with self._session_factory() as session:
            existing = {
                row.open_time
                for row in session.execute(
                    select(CandleBar.open_time).where(
                        CandleBar.symbol == symbol, CandleBar.granularity == granularity
                    )
                ).all()
            }
            new_rows = [
                CandleBar(
                    symbol=symbol,
                    granularity=granularity,
                    open_time=c.get("open_time", c.get("epoch")),
                    open=c["open"],
                    high=c["high"],
                    low=c["low"],
                    close=c["close"],
                )
                for c in candles
                if c.get("open_time", c.get("epoch")) not in existing
            ]
            session.add_all(new_rows)
            session.commit()
            return len(new_rows)

    def load(self, symbol: str, granularity: int) -> list[dict]:
        with self._session_factory() as session:
            rows = session.execute(
                select(CandleBar)
                .where(CandleBar.symbol == symbol, CandleBar.granularity == granularity)
                .order_by(CandleBar.open_time.asc())
            ).scalars().all()
            return [
                {"open": r.open, "high": r.high, "low": r.low, "close": r.close, "epoch": r.open_time}
                for r in rows
            ]

    def count(self, symbol: str, granularity: int) -> int:
        with self._session_factory() as session:
            return len(
                session.execute(
                    select(CandleBar.id).where(
                        CandleBar.symbol == symbol, CandleBar.granularity == granularity
                    )
                ).all()
            )


class LiveTradeRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def add(self, trade: LiveTrade) -> None:
        with self._session_factory() as session:
            session.add(trade)
            session.commit()


class BacktestRepository:
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def create_run(self, symbols: list[str], granularity: int, params: dict, notes: str = "") -> int:
        with self._session_factory() as session:
            run = BacktestRun(
                symbols=",".join(symbols),
                granularity=granularity,
                params_json=json.dumps(params),
                notes=notes,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.id

    def add_trades(self, trades: list[BacktestTrade]) -> None:
        if not trades:
            return
        with self._session_factory() as session:
            session.add_all(trades)
            session.commit()

    def trades_for_run(self, run_id: int) -> list[BacktestTrade]:
        with self._session_factory() as session:
            return session.execute(
                select(BacktestTrade).where(BacktestTrade.run_id == run_id)
            ).scalars().all()
