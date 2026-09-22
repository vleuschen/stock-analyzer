import unittest
import os
import subprocess
import sys

import push_format
import run_daily


class PushBehaviorTests(unittest.TestCase):
    def test_layout_checker_handles_windows_console_encoding(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "gbk"
        result = subprocess.run(
            [sys.executable, "scripts/check_push_layout.py", "--body-only"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_code_push_cannot_consume_scheduled_push_deduplication(self):
        self.assertFalse(
            run_daily.should_skip_duplicate(
                data_date="2026-09-21",
                sent_before="2026-09-21",
                trigger="push",
            )
        )

    def test_scheduled_run_skips_only_after_same_date_was_sent(self):
        self.assertTrue(
            run_daily.should_skip_duplicate(
                data_date="2026-09-21",
                sent_before="2026-09-21",
                trigger="schedule",
            )
        )
        self.assertFalse(
            run_daily.should_skip_duplicate(
                data_date="2026-09-22",
                sent_before="2026-09-21",
                trigger="schedule",
            )
        )

    def test_required_push_mode_is_strict_about_missing_sendkey(self):
        self.assertTrue(run_daily.push_requires_sendkey("schedule"))
        self.assertTrue(run_daily.push_requires_sendkey("workflow_dispatch"))
        self.assertFalse(run_daily.push_requires_sendkey("push"))
        self.assertFalse(run_daily.push_requires_sendkey("local"))

    def test_push_body_contains_actionable_summary_and_table_columns(self):
        stock = {
            "config": {"name": "测试股份", "code": "600000"},
            "quote": {"price": 12.34, "pct_change": 3.21, "volume_ratio": 1.8},
            "indicators": {"rsi": {"rsi14": 63.2}, "volume_ratio": 1.2},
            "swing": {
                "signal": "buy",
                "score": 42,
                "action": "偏强，激进者可小仓试错；确认后再加仓",
                "reasons": ["✅ 站上 MA5 / MA10"],
                "flow": {"main_net": 12000000, "label": "主力", "consec_in": 3},
                "support_levels": [],
                "resistance_levels": [],
            },
        }
        body = push_format.build_push_body(
            "2026-09-21",
            [stock],
            indices=[("上证", 3950, 0.97)],
        )
        self.assertIn("一句话", body)
        self.assertIn("试仓", body)
        self.assertIn("资金", body)
        self.assertIn("总分", body)

    def test_push_body_uses_box_drawing_tables_and_explains_score(self):
        stock = {
            "config": {"name": "测试股份", "code": "600000"},
            "quote": {"price": 12.34, "pct_change": 3.21, "volume_ratio": 1.8},
            "indicators": {"rsi": {"rsi14": 63.2}, "volume_ratio": 1.2},
            "swing": {
                "signal": "buy",
                "score": 42,
                "confidence": "medium",
                "action": "偏强，激进者可小仓试错；确认后再加仓",
                "reasons": ["✅ 站上 MA5 / MA10"],
                "flow": {"main_net": 12000000, "label": "主力", "consec_in": 3},
                "dimensions": {"trend": 28, "momentum": 20, "position": 4,
                               "volume": 3, "flow": -13},
                "support_levels": [],
                "resistance_levels": [],
            },
        }
        body = push_format.build_push_body("2026-09-21", [stock])
        self.assertIn("┌", body)
        self.assertIn("┼", body)
        self.assertIn("└", body)
        self.assertIn("趋势", body)
        self.assertIn("总分=五项相加", body)

    def test_focus_card_never_truncates_a_money_amount(self):
        stock = {
            "config": {"name": "测试股份甲乙"},
            "quote": {"price": 12.34, "pct_change": 3.21},
            "swing": {
                "signal": "buy",
                "score": 42,
                "confidence": "medium",
                "reasons": ["🟡 高分但确认不足（均线未多头排列）"],
                "flow": {"main_net": 17350000, "label": "超大单"},
            },
        }
        lines = push_format._focus_card(stock, "2026-09-21")
        detail = lines[1]
        self.assertNotIn("+173…", detail)
        self.assertTrue("+1735万" in detail or "主力" not in detail)


if __name__ == "__main__":
    unittest.main()
