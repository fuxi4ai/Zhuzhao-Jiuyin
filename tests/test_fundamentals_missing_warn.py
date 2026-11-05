"""六维缺件告警（2026-11-05 · GOTCHAS ERR-20261008-003）。

副本根缺 `龙鱼-标的分析库` / `宏观-大宗商品` 时，fundamentals_lookup 不得静默回退：
① 缺件根 → stderr 恰一行 `[fundamentals_lookup] ⚠ 缺件`（多次查询不刷屏），返回值仍为 None/回退；
② 齐件根（空库空目录占位）→ 零告警。
均以子进程 + ZZJY_DATABASE_ROOT 隔离，不读真库。
"""
import os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = ("import sys; sys.path.insert(0, sys.argv[1] + '/tools'); import fundamentals_lookup as fl; "
        "print(fl.lookup('300502.SZ'), fl.lookup('002463.SZ'), repr(fl.fmt('300502.SZ')))")
TAG = "[fundamentals_lookup] ⚠ 缺件"


def run(db_root):
    env = dict(os.environ, ZZJY_DATABASE_ROOT=db_root)
    return subprocess.run([sys.executable, "-c", CODE, ROOT], env=env,
                          capture_output=True, text=True, timeout=60)


class MissingWarnTest(unittest.TestCase):
    def test_missing_root_warns_once(self):
        with tempfile.TemporaryDirectory() as t:
            r = run(t)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stderr.count(TAG), 1, r.stderr)
            self.assertIn("龙鱼-标的分析库", r.stderr)
            self.assertIn("None None ''", r.stdout)

    def test_complete_root_silent(self):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(os.path.join(t, "龙鱼-标的分析库", "records"))
            os.makedirs(os.path.join(t, "宏观-大宗商品"))
            open(os.path.join(t, "宏观-大宗商品", "business_breakdown.db"), "wb").close()
            r = run(t)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn(TAG, r.stderr)


if __name__ == "__main__":
    unittest.main()
