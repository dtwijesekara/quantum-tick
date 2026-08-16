"""Intermediate representation for a Deriv Bot (DBot/Blockly) XML strategy's
entry logic. parser.py turns raw XML into this; interpreter.py evaluates it
against a live candle window.

Only represents the Blockly vocabulary actually observed in the ORSTAC
corpus (see docs/research/RESEARCH_FINDINGS.md section 8) -- an
unrecognized block anywhere in a bot's entry logic makes that bot
`BotDefinition.supported = False` rather than guessing at its meaning.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---- Expressions (things that evaluate to a number or boolean) -----------


@dataclass(frozen=True)
class Number:
    value: float


@dataclass(frozen=True)
class TickValue:
    """The current/latest raw tick price."""


@dataclass(frozen=True)
class CandleField:
    """A field (open/high/low/close) of the OHLC candle series -- used as
    an indicator's input source, not a standalone comparable value on its
    own in the corpus (always feeds sma/ema/rsi/macd)."""
    field: str  # "close", "open", "high", "low"


@dataclass(frozen=True)
class TicksSeries:
    """Raw tick series -- the other common indicator input source."""


@dataclass(frozen=True)
class IndicatorCall:
    name: str  # "sma" | "ema" | "rsi" | "macd_line" | "macd_signal"
    input_source: CandleField | TicksSeries
    params: dict = field(default_factory=dict)  # e.g. {"period": 14} or {"fast":12,"slow":26,"signal":9}


@dataclass(frozen=True)
class IsCandleBlack:
    """True if the most recent closed candle is bearish (black/red)."""


Expr = Number | TickValue | CandleField | IndicatorCall | IsCandleBlack


# ---- Conditions ------------------------------------------------------------


@dataclass(frozen=True)
class Compare:
    op: str  # "GT" | "LT" | "GTE" | "LTE" | "EQ" | "NEQ"
    left: Expr
    right: Expr


@dataclass(frozen=True)
class LogicOp:
    op: str  # "AND" | "OR"
    operands: tuple["Condition", ...]


@dataclass(frozen=True)
class BoolExpr:
    """A boolean-valued expression used directly as a condition (e.g.
    IsCandleBlack), not wrapped in a Compare."""
    expr: Expr


Condition = Compare | LogicOp | BoolExpr


# ---- Actions / branches ----------------------------------------------------


@dataclass(frozen=True)
class Purchase:
    contract_type: str  # "CALL" | "PUT"


@dataclass(frozen=True)
class NoAction:
    """A branch that reaches no `purchase` block -- no trade fires."""


# An action is either a terminal decision (Purchase/NoAction) or another
# nested if/elif/else chain -- Blockly bots commonly decide CALL vs PUT via
# an if *inside* an if (e.g. "if A: (if B: PUT else: CALL) else: nothing"),
# so this has to be a tree, not a flat list of branches.
Action = "Purchase | NoAction | EntryLogic"


@dataclass(frozen=True)
class IfBranch:
    condition: Condition
    action: Action


@dataclass(frozen=True)
class EntryLogic:
    """An ordered if/elif/.../else chain -- the first branch whose
    condition is true fires its action; `default` fires if none match.
    Each action may itself be another EntryLogic (nested if)."""
    branches: tuple[IfBranch, ...]
    default: Action


# ---- Whole-bot definition ---------------------------------------------------


@dataclass(frozen=True)
class BotDefinition:
    source_path: str
    symbol: str
    trade_type: str
    market: str
    candle_interval: int  # seconds, from CANDLEINTERVAL_LIST
    duration_unit: str  # "t" | "s" | "m" | "h"
    duration_value: int
    entry_logic: EntryLogic
    supported: bool
    unsupported_reason: str = ""
