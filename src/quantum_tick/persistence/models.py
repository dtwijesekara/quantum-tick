from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CandleBar(Base):
    """Local cache of historical candles, so re-running a backtest doesn't
    re-fetch the same history from Deriv every time."""

    __tablename__ = "candle_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "granularity", "open_time", name="uq_candle_bar"),
        Index("ix_candle_bar_symbol_gran_time", "symbol", "granularity", "open_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    granularity: Mapped[int] = mapped_column(Integer)
    open_time: Mapped[int] = mapped_column(Integer)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)


class LiveTrade(Base):
    __tablename__ = "live_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    placed_at: Mapped[datetime] = mapped_column(default=_utcnow)
    symbol: Mapped[str] = mapped_column(String(20))
    contract_type: Mapped[str] = mapped_column(String(10))
    technique: Mapped[str] = mapped_column(String(50))
    entry_price: Mapped[float] = mapped_column(Float)
    stake: Mapped[float] = mapped_column(Float)
    payout: Mapped[float] = mapped_column(Float)
    duration_mins: Mapped[int] = mapped_column(Integer)
    transaction_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|won|lost
    profit: Mapped[float | None] = mapped_column(Float, nullable=True)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(default=_utcnow)
    symbols: Mapped[str] = mapped_column(String(200))
    granularity: Mapped[int] = mapped_column(Integer)
    params_json: Mapped[str] = mapped_column(String(4000))
    notes: Mapped[str] = mapped_column(String(500), default="")


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (Index("ix_backtest_trade_run_symbol", "run_id", "symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer)
    symbol: Mapped[str] = mapped_column(String(20))
    contract_type: Mapped[str] = mapped_column(String(10))
    technique: Mapped[str] = mapped_column(String(50))
    entry_open_time: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    expiry_price: Mapped[float] = mapped_column(Float)
    duration_mins: Mapped[int] = mapped_column(Integer)
    payout_ratio: Mapped[float] = mapped_column(Float)
    outcome: Mapped[str] = mapped_column(String(10))  # won|lost
    sample: Mapped[str] = mapped_column(String(20))  # in_sample|out_of_sample
