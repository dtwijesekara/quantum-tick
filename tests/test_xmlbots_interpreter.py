import pytest

from tests.conftest import candle
from quantum_tick.xmlbots.interpreter import RequiresTickData, bot_requires_tick_data, evaluate_entry_logic
from quantum_tick.xmlbots.ir import (
    BoolExpr,
    BotDefinition,
    CandleField,
    Compare,
    EntryLogic,
    IfBranch,
    IndicatorCall,
    IsCandleBlack,
    LogicOp,
    Number,
    NoAction,
    Purchase,
    TicksSeries,
    TickValue,
)


def _bot(entry_logic: EntryLogic) -> BotDefinition:
    return BotDefinition(
        source_path="test", symbol="R_50", trade_type="risefall", market="volidx",
        candle_interval=60, duration_unit="m", duration_value=3,
        entry_logic=entry_logic, supported=True,
    )


def _rising_candles(n: int) -> list[dict]:
    return [candle(100 + i, 100 + i + 1, 100 + i - 0.5, 100 + i + 0.5, i * 60) for i in range(n)]


def test_evaluates_simple_number_compare_to_call():
    logic = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", Number(2), Number(1)), action=Purchase("CALL")),),
        default=NoAction(),
    )
    result = evaluate_entry_logic(_bot(logic), _rising_candles(10))
    assert result == Purchase("CALL")


def test_false_condition_falls_through_to_default():
    logic = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", Number(1), Number(2)), action=Purchase("CALL")),),
        default=Purchase("PUT"),
    )
    result = evaluate_entry_logic(_bot(logic), _rising_candles(10))
    assert result == Purchase("PUT")


def test_no_matching_branch_and_no_default_means_no_trade():
    logic = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", Number(1), Number(2)), action=Purchase("CALL")),),
        default=NoAction(),
    )
    result = evaluate_entry_logic(_bot(logic), _rising_candles(10))
    assert result is None


def test_sma_crossover_fires_on_rising_series():
    # a rising series -> the shorter SMA sits above the longer SMA
    sma_short = IndicatorCall("sma", CandleField("close"), {"period": 3})
    sma_long = IndicatorCall("sma", CandleField("close"), {"period": 8})
    logic = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", sma_short, sma_long), action=Purchase("CALL")),),
        default=NoAction(),
    )
    result = evaluate_entry_logic(_bot(logic), _rising_candles(20))
    assert result == Purchase("CALL")


def test_indicator_without_enough_history_does_not_fire():
    sma_50 = IndicatorCall("sma", CandleField("close"), {"period": 50})
    logic = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", sma_50, Number(0)), action=Purchase("CALL")),),
        default=NoAction(),
    )
    result = evaluate_entry_logic(_bot(logic), _rising_candles(10))  # only 10 candles, needs 50
    assert result is None


def test_logic_operation_and_requires_both_true():
    logic = EntryLogic(
        branches=(
            IfBranch(
                condition=LogicOp("AND", (Compare("GT", Number(2), Number(1)), Compare("LT", Number(1), Number(2)))),
                action=Purchase("CALL"),
            ),
        ),
        default=NoAction(),
    )
    assert evaluate_entry_logic(_bot(logic), _rising_candles(10)) == Purchase("CALL")

    logic_false = EntryLogic(
        branches=(
            IfBranch(
                condition=LogicOp("AND", (Compare("GT", Number(2), Number(1)), Compare("GT", Number(1), Number(2)))),
                action=Purchase("CALL"),
            ),
        ),
        default=NoAction(),
    )
    assert evaluate_entry_logic(_bot(logic_false), _rising_candles(10)) is None


def test_is_candle_black_reads_last_closed_candle():
    logic = EntryLogic(
        branches=(IfBranch(condition=BoolExpr(IsCandleBlack()), action=Purchase("PUT")),),
        default=Purchase("CALL"),
    )
    # rising series -> every candle is green -> IsCandleBlack is false -> default fires
    result = evaluate_entry_logic(_bot(logic), _rising_candles(10))
    assert result == Purchase("CALL")


def test_tick_series_input_raises_requires_tick_data():
    sma_ticks = IndicatorCall("sma", TicksSeries(), {"period": 5})
    logic = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", TickValue(), sma_ticks), action=Purchase("CALL")),),
        default=NoAction(),
    )
    with pytest.raises(RequiresTickData):
        evaluate_entry_logic(_bot(logic), _rising_candles(10))


def test_bot_requires_tick_data_detects_ticks_input_statically():
    sma_ticks = IndicatorCall("sma", TicksSeries(), {"period": 5})
    logic = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", TickValue(), sma_ticks), action=Purchase("CALL")),),
        default=NoAction(),
    )
    assert bot_requires_tick_data(_bot(logic)) is True


def test_bot_requires_tick_data_false_for_candle_based_bot():
    sma_close = IndicatorCall("sma", CandleField("close"), {"period": 5})
    logic = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", sma_close, Number(0)), action=Purchase("CALL")),),
        default=NoAction(),
    )
    assert bot_requires_tick_data(_bot(logic)) is False
