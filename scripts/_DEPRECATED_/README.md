# _DEPRECATED_ · 退役脚本（不删，留审计/回滚）

可逆优先：此目录存放经核实判定退役的脚本，**保留不删**，以备回溯或误判翻案。

## tushare_pipeline.py（2026-06-23 退役）

- **退役依据（三线核实）**：`gen_daily_report.py` 已改读 `market_data.db`（stock_daily/limit_list_daily/market_amount_daily/theme_etf_daily/us_anchor_daily），**零引用** recap 里的 `tushare_limit/north/index/stats`。这些镜像表全项目无活读者（仅 `tushare_index` 被一个回测脚本读旧存量），数据停更于 2026-05-06。
- **附带问题**：它还 UPDATE `dim3_sentiment_tech`，与「dim3 课件口径·禁行情倒灌」红线冲突。
- **影响面**：无任何调度/runner 调用它（已确认无 .sh/.plist/cron 引用）；退役不破坏任何活链路。
- **如需翻案**：`git mv scripts/_DEPRECATED_/tushare_pipeline.py scripts/` 即可恢复。
