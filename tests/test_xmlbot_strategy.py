from tests.conftest import candle
from quantum_tick.domain.strategies.xmlbot_strategy import XmlBotStrategy, _max_period
from quantum_tick.xmlbots.ir import (
    BotDefinition,
    CandleField,
    Compare,
    EntryLogic,
    IfBranch,
    IndicatorCall,
    Number,
    NoAction,
    Purchase,
)


def _bot(entry_logic: EntryLogic, duration_unit="m", duration_value=3) -> BotDefinition:
    return BotDefinition(
        source_path="test.xml", symbol="R_50", trade_type="risefall", market="volidx",
        candle_interval=60, duration_unit=duration_unit, duration_value=duration_value,
        entry_logic=entry_logic, supported=True,
    )


def test_max_period_finds_largest_sma_period():
    sma20 = IndicatorCall("sma", CandleField("close"), {"period": 20})
    sma5 = IndicatorCall("sma", CandleField("close"), {"period": 5})
    logic = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", sma5, sma20), action=Purchase("CALL")),),
        default=NoAction(),
    )
    assert _max_period(_bot(logic)) == 20


def test_max_period_uses_slow_plus_signal_for_macd():
    macd_line = IndicatorCall("macd_line", CandleField("close"), {"fast": 12, "slow": 26, "signal": 9})
    logic = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", macd_line, Number(0)), action=Purchase("CALL")),),
        default=NoAction(),
    )
    assert _max_period(_bot(logic)) == 35  # 26 + 9


def test_max_period_recurses_into_nested_entry_logic():
    sma50 = IndicatorCall("sma", CandleField("close"), {"period": 50})
    inner = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", sma50, Number(0)), action=Purchase("PUT")),),
        default=NoAction(),
    )
    outer = EntryLogic(
        branches=(IfBranch(condition=Compare("GT", Number(1), Number(0)), action=inner),),
        default=NoAction(),
    )
    assert _max_period(_bot(outer)) == 50


def test_xmlbot_strategy_duration_conversion():
    logic = EntryLogic(branches=(), default=Purchase("CALL"))
    assert XmlBotStrategy(_bot(logic, "m", 5)).duration_mins == 5
    assert XmlBotStrategy(_bot(logic, "h", 1)).duration_mins == 60
    assert XmlBotStrategy(_bot(logic, "s", 30)).duration_mins == 1  # floored to finest candle granularity


def test_xmlbot_strategy_detect_fires_and_returns_technique():
    logic = EntryLogic(branches=(), default=Purchase("CALL"))
    strategy = XmlBotStrategy(_bot(logic))
    candles = [candle(100, 101, 99, 100, i * 60) for i in range(35)]
    signal = strategy.detect(candles, "R_50")
    assert signal is not None
    assert signal.contract_type == "CALL"
    assert signal.technique == "xmlbot"
