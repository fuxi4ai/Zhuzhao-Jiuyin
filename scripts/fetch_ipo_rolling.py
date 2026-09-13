#!/usr/bin/env python3.13
# -*- coding: utf-8 -*-
"""IPO 滚动覆盖采集 [D-29, D]（北京日 D）· Mac 原生 / launchd 执行
目的（ERR-20260911-002 生产闭环 · 2026-09-13 · VV 复核定案 · 第八轮）：
  - 消费合同要求「单条覆盖证明完整包含目标十日窗 (D-10, D]」——滚动 30 日窗
    每天重扫，单条覆盖 [D-29, D] 天然满足；漏跑一天，次日补扫仍覆盖。
  - 北京日 D 显式传入（不取主机 PT 日，避免落后消费者一天）。
  - 直写 market_data.db 自己的两张表（ipo_daily / ipo_coverage），不做整库
    放回——SQLite 行级锁并发安全，不覆盖其他写入方（整库快照放回已被 VV
    实测证伪：integrity ok 但丢他人新行）。
  - 固定 Python 3.13 解释器（VV 复核：系统 python3 缺 tushare；本文件不依赖
    bash/date 环境，只依赖 python3.13 与 fetch_ipo.py 同目录）。
失败语义：任何异常非零退出；消费端按现有覆盖证明如实显示可评/不可判。
"""
import os
import sys
from datetime import date, timedelta, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_ipo  # noqa: E402  同目录采集器（token 链：env → Keychain → ~/.tushare/token）


def main():
    BJTZ = timezone(timedelta(hours=8))
    d = datetime.now(BJTZ).date()
    start = d - timedelta(days=29)
    print(f"IPO 滚动采集 [{start.strftime('%Y%m%d')}, {d.strftime('%Y%m%d')}]（北京日）")
    fetch_ipo.fetch(start.strftime("%Y%m%d"), d.strftime("%Y%m%d"))
    print("✅ 滚动采集完成（ipo_daily + ipo_coverage 覆盖证明已落）")


if __name__ == "__main__":
    main()
