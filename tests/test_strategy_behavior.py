import unittest

import swing_strategy


def indicators(score_shape="aggressive"):
    return {
        "current": 12.0,
        "ma": {"ma5": 11.8, "ma10": 11.5, "ma20": 11.0, "ma60": 10.5},
        "ma_alignment": "bullish",
        "rsi": {"rsi14": 72.0 if score_shape == "aggressive" else 62.0},
        "macd": {
            "dif": 0.4,
            "dea": 0.2,
            "is_golden_cross": True,
            "is_death_cross": False,
            "macd_hist": 0.2,
            "macd_hist_prev": 0.1,
        },
        "bollinger": {"position": 75, "lower": 10.5, "upper": 13.0},
        "volume_ratio": 1.8,
        "range_20d": {"low": 10.8, "high": 13.2},
    }


class StrategyBehaviorTests(unittest.TestCase):
    def test_aggressive_profile_allows_strong_trend_with_rsi_below_75(self):
        result = swing_strategy.analyze_swing_signals(
            indicators("aggressive"),
            [{"date": "2026-09-21", "main_net": 12000000}],
        )
        self.assertEqual(result["signal"], "strong_buy")
        self.assertIn("激进", result["action"])

    def test_buy_signal_explains_small_position_entry(self):
        data = indicators("conservative")
        data["ma_alignment"] = "mixed"
        result = swing_strategy.analyze_swing_signals(
            data,
            [{"date": "2026-09-21", "main_net": 5000000}],
        )
        self.assertEqual(result["signal"], "buy")
        self.assertIn("小仓", result["action"])


if __name__ == "__main__":
    unittest.main()
