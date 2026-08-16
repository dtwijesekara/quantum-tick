from pathlib import Path

from quantum_tick.xmlbots.ir import (
    BoolExpr,
    CandleField,
    Compare,
    IfBranch,
    IndicatorCall,
    IsCandleBlack,
    LogicOp,
    NoAction,
    Purchase,
)
from quantum_tick.xmlbots.parser import parse_file

NS = 'xmlns="http://www.w3.org/1999/xhtml"'

# Mirrors the real structure of a Deriv Bot XML export closely enough to
# exercise the parser the same way a real corpus file would, without
# depending on any file outside this repo.
SMA_CROSSOVER_XML = f"""<xml {NS} collection="false">
  <block type="trade" id="t1" x="0" y="0">
    <field name="MARKET_LIST">volidx</field>
    <field name="SYMBOL_LIST">R_50</field>
    <field name="TRADETYPECAT_LIST">callput</field>
    <field name="TRADETYPE_LIST">risefall</field>
    <field name="CANDLEINTERVAL_LIST">60</field>
    <statement name="SUBMARKET">
      <block type="tradeOptions" id="to1">
        <field name="DURATIONTYPE_LIST">m</field>
        <value name="DURATION">
          <block type="math_number" id="d1"><field name="NUM">3</field></block>
        </value>
      </block>
    </statement>
  </block>
  <block type="before_purchase" id="bp1">
    <statement name="BEFOREPURCHASE_STACK">
      <block type="controls_if" id="if1">
        <mutation else="1"></mutation>
        <value name="IF0">
          <block type="logic_compare" id="cmp1">
            <field name="OP">GT</field>
            <value name="A">
              <block type="sma" id="sma1">
                <value name="INPUT"><block type="ohlc_values" id="ov1">
                  <field name="OHLCFIELD_LIST">close</field></block></value>
                <value name="PERIOD"><block type="math_number" id="p1"><field name="NUM">5</field></block></value>
              </block>
            </value>
            <value name="B">
              <block type="sma" id="sma2">
                <value name="INPUT"><block type="ohlc_values" id="ov2">
                  <field name="OHLCFIELD_LIST">close</field></block></value>
                <value name="PERIOD"><block type="math_number" id="p2"><field name="NUM">20</field></block></value>
              </block>
            </value>
          </block>
        </value>
        <statement name="DO0">
          <block type="purchase" id="pu1"><field name="PURCHASE_LIST">CALL</field></block>
        </statement>
        <statement name="ELSE">
          <block type="purchase" id="pu2"><field name="PURCHASE_LIST">PUT</field></block>
        </statement>
      </block>
    </statement>
  </block>
</xml>"""

MACD_RSI_XML = f"""<xml {NS} collection="false">
  <block type="trade" id="t1" x="0" y="0">
    <field name="MARKET_LIST">volidx</field>
    <field name="SYMBOL_LIST">R_100</field>
    <field name="TRADETYPECAT_LIST">callput</field>
    <field name="TRADETYPE_LIST">risefall</field>
    <field name="CANDLEINTERVAL_LIST">60</field>
    <statement name="SUBMARKET">
      <block type="tradeOptions" id="to1">
        <field name="DURATIONTYPE_LIST">m</field>
        <value name="DURATION"><shadow type="math_number" id="d1"><field name="NUM">1</field></shadow></value>
      </block>
    </statement>
  </block>
  <block type="before_purchase" id="bp1">
    <statement name="BEFOREPURCHASE_STACK">
      <block type="controls_if" id="if1">
        <value name="IF0">
          <block type="logic_operation" id="lo1">
            <field name="OP">AND</field>
            <value name="A">
              <block type="logic_compare" id="cmp1">
                <field name="OP">GT</field>
                <value name="A">
                  <block type="macda" id="m1">
                    <field name="MACDFIELDS_LIST">1</field>
                    <value name="INPUT"><block type="ohlc_values" id="ov1">
                      <field name="OHLCFIELD_LIST">close</field></block></value>
                    <value name="FAST_EMA_PERIOD"><shadow type="math_number" id="f1"><field name="NUM">12</field></shadow></value>
                    <value name="SLOW_EMA_PERIOD"><shadow type="math_number" id="s1"><field name="NUM">26</field></shadow></value>
                    <value name="SMA_PERIOD"><shadow type="math_number" id="sm1"><field name="NUM">9</field></shadow></value>
                  </block>
                </value>
                <value name="B">
                  <block type="macda" id="m2">
                    <field name="MACDFIELDS_LIST">2</field>
                    <value name="INPUT"><block type="ohlc_values" id="ov2">
                      <field name="OHLCFIELD_LIST">close</field></block></value>
                    <value name="FAST_EMA_PERIOD"><shadow type="math_number" id="f2"><field name="NUM">12</field></shadow></value>
                    <value name="SLOW_EMA_PERIOD"><shadow type="math_number" id="s2"><field name="NUM">26</field></shadow></value>
                    <value name="SMA_PERIOD"><shadow type="math_number" id="sm2"><field name="NUM">9</field></shadow></value>
                  </block>
                </value>
              </block>
            </value>
            <value name="B">
              <block type="logic_compare" id="cmp2">
                <field name="OP">GT</field>
                <value name="A">
                  <block type="rsi" id="r1">
                    <value name="INPUT"><block type="ohlc_values" id="ov3">
                      <field name="OHLCFIELD_LIST">close</field></block></value>
                    <value name="PERIOD"><shadow type="math_number" id="rp1"><field name="NUM">14</field></shadow></value>
                  </block>
                </value>
                <value name="B"><block type="math_number" id="n1"><field name="NUM">70</field></block></value>
              </block>
            </value>
          </block>
        </value>
        <statement name="DO0">
          <block type="purchase" id="pu1"><field name="PURCHASE_LIST">PUT</field></block>
        </statement>
      </block>
    </statement>
  </block>
</xml>"""

CANDLE_COLOR_XML = f"""<xml {NS} collection="false">
  <block type="trade" id="t1" x="0" y="0">
    <field name="MARKET_LIST">volidx</field>
    <field name="SYMBOL_LIST">R_25</field>
    <field name="TRADETYPE_LIST">risefall</field>
    <field name="CANDLEINTERVAL_LIST">60</field>
    <statement name="SUBMARKET">
      <block type="tradeOptions" id="to1">
        <field name="DURATIONTYPE_LIST">s</field>
        <value name="DURATION"><block type="math_number" id="d1"><field name="NUM">60</field></block></value>
      </block>
    </statement>
  </block>
  <block type="before_purchase" id="bp1">
    <statement name="BEFOREPURCHASE_STACK">
      <block type="controls_if" id="if1">
        <value name="IF0"><block type="is_candle_black" id="icb1"></block></value>
        <statement name="DO0">
          <block type="purchase" id="pu1"><field name="PURCHASE_LIST">PUT</field></block>
        </statement>
      </block>
    </statement>
  </block>
</xml>"""

UNSUPPORTED_XML = f"""<xml {NS} collection="false">
  <block type="trade" id="t1" x="0" y="0">
    <field name="MARKET_LIST">volidx</field>
    <field name="SYMBOL_LIST">R_10</field>
    <field name="TRADETYPE_LIST">risefall</field>
    <field name="CANDLEINTERVAL_LIST">60</field>
    <statement name="SUBMARKET">
      <block type="tradeOptions" id="to1">
        <field name="DURATIONTYPE_LIST">m</field>
        <value name="DURATION"><block type="math_number" id="d1"><field name="NUM">1</field></block></value>
      </block>
    </statement>
  </block>
  <block type="before_purchase" id="bp1">
    <statement name="BEFOREPURCHASE_STACK">
      <block type="controls_if" id="if1">
        <value name="IF0">
          <block type="some_exotic_custom_block" id="x1"></block>
        </value>
        <statement name="DO0">
          <block type="purchase" id="pu1"><field name="PURCHASE_LIST">CALL</field></block>
        </statement>
      </block>
    </statement>
  </block>
</xml>"""


def _write(tmp_path: Path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_parses_sma_crossover_with_else_branch(tmp_path):
    bot = parse_file(_write(tmp_path, "sma.xml", SMA_CROSSOVER_XML))

    assert bot.supported
    assert bot.symbol == "R_50"
    assert bot.trade_type == "risefall"
    assert bot.duration_unit == "m"
    assert bot.duration_value == 3

    assert len(bot.entry_logic.branches) == 1
    branch = bot.entry_logic.branches[0]
    assert isinstance(branch.condition, Compare)
    assert branch.condition.op == "GT"
    assert isinstance(branch.condition.left, IndicatorCall)
    assert branch.condition.left.name == "sma"
    assert branch.condition.left.params == {"period": 5}
    assert isinstance(branch.condition.left.input_source, CandleField)
    assert branch.condition.left.input_source.field == "close"
    assert branch.action == Purchase("CALL")
    assert bot.entry_logic.default == Purchase("PUT")


def test_parses_macd_rsi_confluence_with_no_default_action(tmp_path):
    bot = parse_file(_write(tmp_path, "macd_rsi.xml", MACD_RSI_XML))

    assert bot.supported
    assert bot.symbol == "R_100"
    assert len(bot.entry_logic.branches) == 1
    branch = bot.entry_logic.branches[0]
    assert isinstance(branch.condition, LogicOp)
    assert branch.condition.op == "AND"

    macd_cmp, rsi_cmp = branch.condition.operands
    assert isinstance(macd_cmp, Compare) and macd_cmp.op == "GT"
    assert macd_cmp.left.name == "macd_line"
    assert macd_cmp.right.name == "macd_signal"
    assert macd_cmp.left.params == {"fast": 12, "slow": 26, "signal": 9}

    assert isinstance(rsi_cmp, Compare) and rsi_cmp.op == "GT"
    assert rsi_cmp.left.name == "rsi"
    assert rsi_cmp.left.params == {"period": 14}

    assert branch.action == Purchase("PUT")
    assert bot.entry_logic.default == NoAction()


def test_parses_is_candle_black_condition(tmp_path):
    bot = parse_file(_write(tmp_path, "candle.xml", CANDLE_COLOR_XML))
    assert bot.supported
    branch = bot.entry_logic.branches[0]
    assert branch.condition == BoolExpr(IsCandleBlack())
    assert branch.action == Purchase("PUT")


def test_unsupported_block_marks_bot_unsupported_not_a_crash(tmp_path):
    bot = parse_file(_write(tmp_path, "unsupported.xml", UNSUPPORTED_XML))
    assert bot.supported is False
    assert "some_exotic_custom_block" in bot.unsupported_reason


def test_malformed_xml_is_reported_not_raised(tmp_path):
    bot = parse_file(_write(tmp_path, "broken.xml", "<xml><not closed"))
    assert bot.supported is False
    assert "parse error" in bot.unsupported_reason
