"""排盘和太阳时换算的确定性回归测试，可用 python -m unittest discover 运行。"""

from datetime import datetime, timedelta, timezone
import unittest

from bazi import (
    calculate_chart,
    calculate_lunar_chart,
    convert_to_true_solar_time,
    equation_of_time_minutes,
)


class EquationOfTimeTests(unittest.TestCase):
    def test_noaa_reference_vectors(self):
        # 固定向量按 NOAA 公布的均时差近似公式计算，防止公式或单位变化。
        # 来源公式：https://gml.noaa.gov/grad/solcalc/solareqns.PDF
        vectors = [
            (datetime(1990, 1, 1, 4, tzinfo=timezone.utc), -2.754338, 0.000001),
            (datetime(2024, 3, 20, 12, tzinfo=timezone.utc), -7.924412, 0.000001),
            (datetime(2024, 6, 21, 12, tzinfo=timezone.utc), -1.444437, 0.000001),
            (datetime(2024, 12, 21, 12, tzinfo=timezone.utc), 2.156550, 0.000001),
        ]
        for instant, expected, tolerance in vectors:
            with self.subTest(instant=instant):
                self.assertAlmostEqual(
                    equation_of_time_minutes(instant), expected, delta=tolerance
                )

    def test_equation_of_time_normalizes_aware_input_to_utc(self):
        utc = datetime(2024, 3, 20, 12, tzinfo=timezone.utc)
        shanghai = datetime(2024, 3, 20, 20, tzinfo=timezone(timedelta(hours=8)))
        self.assertAlmostEqual(
            equation_of_time_minutes(utc), equation_of_time_minutes(shanghai), places=12
        )

    def test_rejects_naive_instant(self):
        with self.assertRaisesRegex(ValueError, "带时区"):
            equation_of_time_minutes(datetime(2024, 3, 20, 12))


class TrueSolarTimeTests(unittest.TestCase):
    def test_sample_conversion_golden_value(self):
        corrected, utc_offset, equation = convert_to_true_solar_time(
            datetime(1990, 1, 1, 12), 116.4, "Asia/Shanghai"
        )
        expected = datetime(1990, 1, 1, 11, 42, 50, 739711)
        self.assertAlmostEqual(
            (corrected - expected).total_seconds(), 0, delta=0.000001
        )
        self.assertEqual(utc_offset, 8)
        self.assertAlmostEqual(equation, -2.754338, places=6)

    def test_one_degree_east_adds_four_minutes(self):
        birth = datetime(2024, 3, 20, 12)
        at_120, *_ = convert_to_true_solar_time(birth, 120, "Asia/Shanghai")
        at_121, *_ = convert_to_true_solar_time(birth, 121, "Asia/Shanghai")
        self.assertEqual(at_121 - at_120, timedelta(minutes=4))

    def test_timezone_central_meridian_leaves_only_equation_of_time(self):
        birth = datetime(2024, 3, 20, 12)
        corrected, _, equation = convert_to_true_solar_time(
            birth, 120, "Asia/Shanghai"
        )
        self.assertAlmostEqual(
            (corrected - birth).total_seconds() / 60, equation, places=8
        )

    def test_longitude_correction_can_cross_to_previous_date(self):
        corrected, *_ = convert_to_true_solar_time(
            datetime(2024, 1, 1, 0, 30), 100, "Asia/Shanghai"
        )
        self.assertEqual(corrected.date(), datetime(2023, 12, 31).date())

    def test_rejects_nonexistent_daylight_saving_time(self):
        with self.assertRaisesRegex(ValueError, "跳时而不存在"):
            convert_to_true_solar_time(
                datetime(2024, 3, 10, 2, 30), -74, "America/New_York"
            )

    def test_requires_fold_for_repeated_daylight_saving_time(self):
        birth = datetime(2024, 11, 3, 1, 30)
        with self.assertRaisesRegex(ValueError, "回拨出现两次"):
            convert_to_true_solar_time(birth, -74, "America/New_York")
        first, first_offset, _ = convert_to_true_solar_time(
            birth, -74, "America/New_York", fold=0
        )
        second, second_offset, _ = convert_to_true_solar_time(
            birth, -74, "America/New_York", fold=1
        )
        self.assertEqual(first_offset, -4)
        self.assertEqual(second_offset, -5)
        self.assertAlmostEqual((second - first).total_seconds() / 60, 60, delta=0.01)

    def test_rejects_bad_location_and_timezone(self):
        for longitude in (-180.01, 180.01, float("nan")):
            with self.subTest(longitude=longitude):
                with self.assertRaisesRegex(ValueError, "经度范围"):
                    convert_to_true_solar_time(
                        datetime(2024, 1, 1), longitude, "Asia/Shanghai"
                    )
        with self.assertRaisesRegex(ValueError, "找不到时区"):
            convert_to_true_solar_time(
                datetime(2024, 1, 1), 120, "Not/A_Real_Zone"
            )
        with self.assertRaisesRegex(ValueError, "不要附带 UTC 偏移"):
            convert_to_true_solar_time(
                datetime(2024, 1, 1, tzinfo=timezone.utc), 120, "Asia/Shanghai"
            )


class ChartIntegrationTests(unittest.TestCase):
    def test_matches_upstream_lunar_python_chart_fixture(self):
        # lunar-python 的 EightCharTest.py 使用了同一公历时刻及四柱预期值。
        # https://github.com/6tail/lunar-python/blob/master/test/EightCharTest.py
        result = calculate_chart(datetime(2022, 8, 28, 1, 50), sect=2)
        self.assertEqual(
            result["四柱"],
            {"年柱": "壬寅", "月柱": "戊申", "日柱": "癸丑", "时柱": "癸丑"},
        )
        self.assertEqual(
            result["检索条件"],
            {
                "day_master": "癸",
                "month_branch": "申",
                "exposed_stems": ["壬", "戊", "癸"],
                "hidden_stems": ["丙", "壬", "己", "庚", "戊", "甲", "癸", "辛"],
            },
        )

    def test_day_boundary_rule_is_explicit(self):
        birth = datetime(1988, 2, 15, 23, 30)
        sect1 = calculate_chart(birth, sect=1)
        sect2 = calculate_chart(birth, sect=2)
        self.assertEqual(sect1["四柱"]["日柱"], "辛丑")
        self.assertEqual(sect2["四柱"]["日柱"], "庚子")
        with self.assertRaisesRegex(ValueError, "sect"):
            calculate_chart(birth, sect=3)

    def test_time_basis_is_preserved_for_downstream_provenance(self):
        result = calculate_chart(
            datetime(2024, 1, 1), time_basis="真太阳时修正后的公历时刻"
        )
        self.assertEqual(result["时间说明"], "真太阳时修正后的公历时刻")

    def test_solar_term_boundary_changes_year_and_month_pillars(self):
        # lunar-python 的 2024 立春时刻为 16:27:07；两侧各取有余量的时间。
        before = calculate_chart(datetime(2024, 2, 4, 16, 26))
        after = calculate_chart(datetime(2024, 2, 4, 16, 28))
        self.assertEqual((before["四柱"]["年柱"], before["四柱"]["月柱"]), ("癸卯", "乙丑"))
        self.assertEqual((after["四柱"]["年柱"], after["四柱"]["月柱"]), ("甲辰", "丙寅"))

    def test_leap_lunar_month_is_not_confused_with_regular_month(self):
        leap = calculate_lunar_chart(2023, 2, 1, 12, 0, is_leap_month=True)
        regular = calculate_lunar_chart(2023, 2, 1, 12, 0, is_leap_month=False)
        self.assertEqual(leap["公历"], "2023-03-22 12:00:00")
        self.assertEqual(leap["输入历法"], "农历")
        self.assertIn("闰二月", leap["输入农历日期"])
        self.assertNotEqual(leap["公历"], regular["公历"])

    def test_daylight_saving_fold_flows_through_to_different_hour_pillar(self):
        birth = datetime(2024, 11, 3, 1, 30)
        expected_hour_pillars = {0: "戊子", 1: "己丑"}
        for fold, expected in expected_hour_pillars.items():
            with self.subTest(fold=fold):
                corrected, *_ = convert_to_true_solar_time(
                    birth, -74, "America/New_York", fold=fold
                )
                self.assertEqual(calculate_chart(corrected)["四柱"]["时柱"], expected)


if __name__ == "__main__":
    unittest.main()
