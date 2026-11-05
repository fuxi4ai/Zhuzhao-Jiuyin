"""退役过滤不得漏 NULL（2026-11-04 · GOTCHAS ERR-20261104-002）。

`status != 'retired'` 在 SQL 三值逻辑下对 status IS NULL 的行得 NULL → 行被排除。
本测试：① 静态扫 tools/ 与 scripts/，禁止裸 `status != 'retired'`；
        ② 在内存库上确认 COALESCE 写法保留 NULL 行、仍排除 retired。
"""
import os, re, sqlite3, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 覆盖：!= / <> / NOT IN、单双引号、带表别名（s.status）；放过 COALESCE(status, '') 包裹的写法
BARE = re.compile(r"""(?<!COALESCE\()(?<![\w])(?:\w+\.)?status\s*(?:!=|<>|NOT\s+IN\s*\()\s*['"]retired['"]""", re.I)


class RetiredFilterNullTest(unittest.TestCase):
    def test_no_bare_retired_filter(self):
        hits = []
        for sub in ("tools", "scripts"):
            for dp, _, fs in os.walk(os.path.join(ROOT, sub)):
                for n in fs:
                    if n.endswith(".py"):
                        p = os.path.join(dp, n)
                        with open(p, encoding="utf-8") as fh:
                            for i, line in enumerate(fh, 1):
                                if BARE.search(line):
                                    hits.append(f"{p}:{i}: {line.strip()}")
        self.assertEqual(hits, [], "裸 status != 'retired' 会漏 NULL 行：\n" + "\n".join(hits))

    def test_coalesce_semantics(self):
        c = sqlite3.connect(":memory:")
        c.execute("create table t(id int, status text)")
        c.executemany("insert into t values(?,?)", [(1, None), (2, "new"), (3, "retired")])
        bare = {r[0] for r in c.execute("select id from t where status != 'retired'")}
        fixed = {r[0] for r in c.execute("select id from t where COALESCE(status, '') != 'retired'")}
        self.assertEqual(bare, {2})          # 旧写法漏掉 NULL 行
        self.assertEqual(fixed, {1, 2})      # 新写法保留 NULL、排除 retired


if __name__ == "__main__":
    unittest.main()
