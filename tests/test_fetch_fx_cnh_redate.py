"""fetch_fx_cnh 日期重标的离线测试（2026-11-16 · 风险日报 GOTCHAS NOTE-20261116-001）。
覆盖：K 线起点日 → 北京日；周五、周六残根丢弃；北京 T+1 07:00 前没走完不写；单边报价不写；
日期严格 YYYYMMDD（坏日期整批不写）；查询起点前推 3 天；与剑酒青丘 fetch_cn_liquidity.redate_fxcm 逐日一致（参考件缺失则跳过）。
不联网、不碰真实库。运行：python3 -B -m unittest discover -s <仓根>/tests -p 'test_fetch_fx_cnh_redate.py'
"""
import datetime as dt
import importlib.util
import os
import sqlite3
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)                  # config、lib.logger
SCRIPT = os.environ.get("FX_SCRIPT") or os.path.join(ROOT, "scripts", "fetch_fx_cnh.py")
REF = os.environ.get("FX_REF") or os.path.join(os.path.dirname(ROOT), "剑酒青丘", "infrastructure", "取数工具", "fetch_cn_liquidity.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


f = _load(SCRIPT, "fx_under_test")
BJ = f.BJ
FAR = dt.datetime(2030, 1, 1, tzinfo=BJ)


def bar(td, b=7.1, a=7.2):
    return {"trade_date": td, "bid_close": b, "ask_close": a}


class StrictDate(unittest.TestCase):
    def test_accepts_valid(self):
        self.assertEqual(f.parse_ymd("20261116"), dt.date(2026, 11, 16))

    def test_rejects_loose_or_bad(self):
        for bad in ["202611", "2026111", "20261301", "20260230", "2026-11-16", "２０２６１１１６",
                    " 20261116", "20261116 ", "", None, 20261116]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                f.parse_ymd(bad)

    def test_bad_date_in_batch_raises(self):
        with self.assertRaises(ValueError):
            f.redate_fxcm([bar("20261112"), bar("202611")], FAR)

    def test_missing_date_raises(self):
        with self.assertRaises(ValueError):
            f.redate_fxcm([{"trade_date": None, "bid_close": 1, "ask_close": 2}], FAR)

    def test_naive_now_rejected(self):
        with self.assertRaises(ValueError):
            f.redate_fxcm([bar("20261112")], dt.datetime(2030, 1, 1))


class Redate(unittest.TestCase):
    def test_weekday_mapping(self):
        # 2026-11-08 周日 … 11-14 周六
        rows = [bar(f"202611{d:02d}") for d in range(8, 15)]
        got = [d for d, _ in f.redate_fxcm(rows, FAR)]
        self.assertEqual(got, ["20261109", "20261110", "20261111", "20261112", "20261113"])

    def test_no_weekend_output_ever(self):
        d0 = dt.date(2024, 1, 1)
        rows = [bar((d0 + dt.timedelta(i)).strftime("%Y%m%d")) for i in range(1100)]
        for d, _ in f.redate_fxcm(rows, FAR):
            self.assertLess(f.parse_ymd(d).weekday(), 5, d)

    def test_mid_is_average(self):
        self.assertAlmostEqual(f.redate_fxcm([bar("20261112", 7.0, 7.01)], FAR)[0][1], 7.005)

    def test_one_sided_quote_not_written(self):
        rows = [{"trade_date": "20261110", "bid_close": 7.1, "ask_close": None},
                {"trade_date": "20261111", "bid_close": None, "ask_close": 7.1}]
        self.assertEqual(f.redate_fxcm(rows, FAR), [])


class Gate(unittest.TestCase):
    # 标 20261115（周日）＝北京 11-16 那根，北京 11-17 07:00 之后才算走完
    def test_unfinished_bar_skipped(self):
        now = dt.datetime(2026, 11, 17, 6, 59, 59, tzinfo=BJ)
        self.assertEqual(f.redate_fxcm([bar("20261115")], now), [])

    def test_finished_bar_written(self):
        now = dt.datetime(2026, 11, 17, 7, 0, tzinfo=BJ)
        self.assertEqual([d for d, _ in f.redate_fxcm([bar("20261115")], now)], ["20261116"])

    def test_gate_is_timezone_absolute(self):
        # 同一时刻用洛杉矶时区表示，结果不变（不依赖本机时区）
        la = dt.timezone(dt.timedelta(hours=-8))
        now = dt.datetime(2026, 11, 16, 14, 59, tzinfo=la)   # ＝北京 11-17 06:59
        self.assertEqual(f.redate_fxcm([bar("20261115")], now), [])

    def test_schedule_time_writes_previous_beijing_day(self):
        # 烛照日报班 18:04 UTC ＝ 北京次日 02:04：北京 11-17 那根（标 11-16）没走完，最新只到 11-16
        now = dt.datetime(2026, 11, 17, 18, 4, tzinfo=dt.timezone.utc)
        rows = [bar("20261113"), bar("20261114"), bar("20261115"), bar("20261116")]
        self.assertEqual([d for d, _ in f.redate_fxcm(rows, now)], ["20261116"])


class MatchesReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(REF):
            raise unittest.SkipTest(f"参考实现不在场：{REF}")
        cls.ref = _load(REF, "ref_cn_liquidity")

    def test_same_as_reference_2024_2026(self):
        d0 = dt.date(2023, 12, 25)
        rows = []
        for i in range((dt.date(2026, 12, 31) - d0).days + 1):
            td = (d0 + dt.timedelta(i)).strftime("%Y%m%d")
            k = i % 17
            b = None if k == 3 else 7.0 + i * 1e-4
            a = None if k == 5 else 7.003 + i * 1e-4
            rows.append({"trade_date": td, "bid_close": b, "ask_close": a})
        for now in [FAR, dt.datetime(2026, 11, 17, 6, 59, tzinfo=BJ), dt.datetime(2026, 11, 17, 7, 0, tzinfo=BJ),
                    dt.datetime(2026, 11, 17, 18, 4, tzinfo=dt.timezone.utc)]:
            mine = f.redate_fxcm(rows, now)
            ref = self.ref.redate_fxcm(rows, now)
            self.assertEqual([d for d, _ in mine], [d for d, _ in ref], now)
            for (d1, v1), (d2, v2) in zip(mine, ref):
                self.assertAlmostEqual(v1, v2, places=12)


class FetchTushare(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self._orig = f.tushare_call

        def fake(token, api, params, fields, retries=2):
            self.calls.append(params)
            return self.recs
        f.tushare_call = fake
        self.conn = sqlite3.connect(":memory:")
        f.ensure_table(self.conn)

    def tearDown(self):
        f.tushare_call = self._orig

    def test_query_starts_3_days_early_and_filters_start(self):
        # start 20261109 周一 → 要靠 11-08 周日标的那根
        self.recs = [bar("20261106"), bar("20261107"), bar("20261108"), bar("20261109")]
        n = f.fetch_tushare(self.conn, "tok", "20261109", "20261116", False, now_bj=FAR)
        self.assertEqual(self.calls[0]["start_date"], "20261106")
        got = self.conn.execute("select trade_date, source from fx_cnh_daily order by 1").fetchall()
        self.assertEqual(got, [("20261109", "tushare"), ("20261110", "tushare")])
        self.assertEqual(n, 2)

    def test_bad_date_writes_nothing(self):
        self.recs = [bar("20261108"), bar("2026119")]
        with self.assertRaises(ValueError):
            f.fetch_tushare(self.conn, "tok", "20261109", "20261116", False, now_bj=FAR)
        self.assertEqual(self.conn.execute("select count(*) from fx_cnh_daily").fetchone()[0], 0)

    def test_bad_from_arg_rejected_before_query(self):
        self.recs = []
        with self.assertRaises(ValueError):
            f.fetch_tushare(self.conn, "tok", "202611", "20261116", False, now_bj=FAR)
        self.assertEqual(self.calls, [])

    # —— 以下 6 条补独立复验（2026-11-16）指出的测试空档 ——
    def test_rows_before_start_are_dropped(self):
        # 标 11-05（周四）＝北京 11-06，早于 start 11-09，不得写入
        self.recs = [bar("20261105"), bar("20261108")]
        f.fetch_tushare(self.conn, "tok", "20261109", "20261116", False, now_bj=FAR)
        got = [r[0] for r in self.conn.execute("select trade_date from fx_cnh_daily order by 1")]
        self.assertEqual(got, ["20261109"])

    def test_stored_close_rounded_to_4_places(self):
        self.recs = [bar("20261108", 7.123456, 7.123478)]
        f.fetch_tushare(self.conn, "tok", "20261109", "20261116", False, now_bj=FAR)
        self.assertEqual(self.conn.execute("select close from fx_cnh_daily").fetchone()[0], 7.1235)

    def test_bad_end_arg_rejected_before_query(self):
        self.recs = []
        with self.assertRaises(ValueError):
            f.fetch_tushare(self.conn, "tok", "20261109", "2026111", False, now_bj=FAR)
        self.assertEqual(self.calls, [])

    def test_bad_date_raises_even_when_quote_is_one_sided(self):
        # 日期校验先于单边报价判断：坏日期不能因为恰好单边而被静默跳过
        self.recs = [bar("20261108"), {"trade_date": "202611", "bid_close": None, "ask_close": 7.1}]
        with self.assertRaises(ValueError):
            f.fetch_tushare(self.conn, "tok", "20261109", "20261116", False, now_bj=FAR)
        self.assertEqual(self.conn.execute("select count(*) from fx_cnh_daily").fetchone()[0], 0)

    def test_dry_run_writes_nothing(self):
        self.recs = [bar("20261108"), bar("20261109")]
        f.fetch_tushare(self.conn, "tok", "20261109", "20261116", True, now_bj=FAR)
        self.assertEqual(self.conn.execute("select count(*) from fx_cnh_daily").fetchone()[0], 0)


class Constants(unittest.TestCase):
    def test_beijing_offset_and_done_time(self):
        self.assertEqual(f.BJ.utcoffset(None), dt.timedelta(hours=8))
        self.assertEqual(f.BAR_DONE_AT, dt.time(7, 0))


if __name__ == "__main__":
    unittest.main()
