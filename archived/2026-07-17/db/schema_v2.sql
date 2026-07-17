-- 复盘数据库完整 Schema v2.0
-- 生成时间: 2026-05-09 23:53
-- 表数: 19

-- recap_daily (10 列, 122 行)
CREATE TABLE IF NOT EXISTS recap_daily (
  date TEXT,
  source TEXT,
  speaker TEXT,
  cycle_stage TEXT,
  cycle_number INTEGER,
  market_summary TEXT,
  key_themes TEXT,
  created_at TEXT,
  updated_at TEXT,
  confidence TEXT
);

-- dim1_external_pricing (15 列, 36 行)
CREATE TABLE IF NOT EXISTS dim1_external_pricing (
  id INTEGER,
  date TEXT,
  nasdaq REAL,
  hang_seng REAL,
  usd_cny REAL,
  forex_swap INTEGER,
  brent_oil REAL,
  bitcoin REAL,
  key_signals TEXT,
  pricing_direction TEXT,
  created_at TEXT,
  market_linkage TEXT,
  nasdaq_change_pct REAL,
  usd_direction TEXT,
  usd_summary TEXT
);

-- dim2_sector_themes (19 列, 129 行)
CREATE TABLE IF NOT EXISTS dim2_sector_themes (
  id INTEGER,
  date TEXT,
  main_line TEXT,
  sector_logic TEXT,
  sectors_bullish TEXT,
  sectors_bearish TEXT,
  yuantu_ref TEXT,
  price_catalyst TEXT,
  sub_themes TEXT,
  created_at TEXT,
  supply_demand_pattern TEXT,
  main_line_2 TEXT,
  main_line_logic TEXT,
  main_line_sustainability INTEGER,
  limit_up_count INTEGER,
  limit_down_count INTEGER,
  hot_sectors TEXT,
  supply_demand TEXT,
  price_chain TEXT
);

-- dim2p_supply_demand (7 列, 0 行)
CREATE TABLE IF NOT EXISTS dim2p_supply_demand (
  date TEXT,
  industry TEXT,
  supply_demand TEXT,
  price_chain TEXT,
  beneficiary TEXT,
  sustainability TEXT,
  updated_at DATETIME
);

-- dim3_sentiment_tech (25 列, 345 行)
CREATE TABLE IF NOT EXISTS dim3_sentiment_tech (
  id INTEGER,
  date TEXT,
  emotion_stage TEXT,
  limit_up INTEGER,
  limit_down INTEGER,
  consecutive_boards INTEGER,
  volume_trillion REAL,
  ma60 REAL,
  support_level TEXT,
  resistance_level TEXT,
  tech_indicators TEXT,
  news_catalysts TEXT,
  created_at TEXT,
  event_impact_analysis TEXT,
  sentiment_description TEXT,
  support_level_detail TEXT,
  resistance_level_detail TEXT,
  trend_description TEXT,
  up_down_ratio TEXT,
  trading_amount TEXT,
  volume_description TEXT,
  policy_news TEXT,
  industry_logic TEXT,
  price_driver TEXT,
  supply_demand_info TEXT
);

-- dim4_trade_plan (17 列, 342 行)
CREATE TABLE IF NOT EXISTS dim4_trade_plan (
  id INTEGER,
  date TEXT,
  plan TEXT,
  entry_conditions TEXT,
  exit_conditions TEXT,
  position_guidance TEXT,
  key_stocks TEXT,
  risk_warnings TEXT,
  key_levels TEXT,
  plan_accuracy TEXT,
  actual_outcome TEXT,
  plan_window TEXT,
  created_at TEXT,
  strategy_framework TEXT,
  strategy_idea TEXT,
  prediction TEXT,
  operation_advice TEXT
);

-- dim4_stock_analysis (12 列, 0 行)
CREATE TABLE IF NOT EXISTS dim4_stock_analysis (
  date TEXT,
  stock_name TEXT,
  stock_code TEXT,
  sector TEXT,
  bull_reason TEXT,
  bear_reason TEXT,
  position_suggestion TEXT,
  confidence TEXT,
  source TEXT,
  related_news TEXT,
  price_target TEXT,
  updated_at DATETIME
);

-- cycle_quant (20 列, 178 行)
CREATE TABLE IF NOT EXISTS cycle_quant (
  date TEXT,
  total_score INTEGER,
  cycle_stage TEXT,
  score_consecutive_limit INTEGER,
  score_limit_up INTEGER,
  score_limit_down INTEGER,
  score_up_down_ratio INTEGER,
  score_volume INTEGER,
  score_north_flow INTEGER,
  score_theme_continuity INTEGER,
  available_indicators INTEGER,
  confidence REAL,
  consecutive_limit INTEGER,
  limit_up INTEGER,
  limit_down INTEGER,
  up_down_ratio REAL,
  volume_trillion REAL,
  north_flow_billion REAL,
  theme_continuity_days INTEGER,
  calculated_at DATETIME
);

-- cycle_comparison (9 列, 91 行)
CREATE TABLE IF NOT EXISTS cycle_comparison (
  date TEXT,
  bao_stage TEXT,
  quant_stage TEXT,
  quant_score INTEGER,
  match BOOLEAN,
  next_day_return REAL,
  bao_correct BOOLEAN,
  quant_correct BOOLEAN,
  verified_at DATETIME
);

-- sector_alias (5 列, 30 行)
CREATE TABLE IF NOT EXISTS sector_alias (
  id INTEGER,
  canonical_name TEXT,
  aliases TEXT,
  category TEXT,
  created_at TEXT
);

-- stock_master (5 列, 5 行)
CREATE TABLE IF NOT EXISTS stock_master (
  code TEXT,
  name TEXT,
  aliases TEXT,
  sector TEXT,
  created_at TEXT
);

-- stock_tracking (16 列, 0 行)
CREATE TABLE IF NOT EXISTS stock_tracking (
  id INTEGER,
  signal_date TEXT,
  stock_name TEXT,
  stock_code TEXT,
  sector TEXT,
  bull_reason TEXT,
  source TEXT,
  initial_confidence TEXT,
  next_day_return REAL,
  next_3d_return REAL,
  next_5d_return REAL,
  next_10d_return REAL,
  max_return REAL,
  max_drawdown REAL,
  current_status TEXT,
  updated_at DATETIME
);

-- prediction_log (10 列, 0 行)
CREATE TABLE IF NOT EXISTS prediction_log (
  id INTEGER,
  recap_date TEXT,
  plan TEXT,
  verify_date TEXT,
  result TEXT,
  actual_market TEXT,
  actual_sector TEXT,
  notes TEXT,
  verified_by TEXT,
  created_at TEXT
);

-- recap_summary (6 列, 0 行)
CREATE TABLE IF NOT EXISTS recap_summary (
  id INTEGER,
  date TEXT,
  source_file TEXT,
  section TEXT,
  content TEXT,
  created_at TEXT
);

-- recap_guide (7 列, 0 行)
CREATE TABLE IF NOT EXISTS recap_guide (
  id INTEGER,
  date TEXT,
  source_file TEXT,
  keywords TEXT,
  chapters TEXT,
  full_summary TEXT,
  created_at TEXT
);

-- tushare_stats (4 列, 200 行)
CREATE TABLE IF NOT EXISTS tushare_stats (
  date TEXT,
  limit_up INTEGER,
  limit_down INTEGER,
  consecutive_limit INTEGER
);

-- tushare_limit (1 列, 6000 行)
CREATE TABLE IF NOT EXISTS tushare_limit (
  trade_date TEXT
);

-- tushare_north (2 列, 300 行)
CREATE TABLE IF NOT EXISTS tushare_north (
  trade_date TEXT,
  north_money TEXT
);

-- tushare_index (6 列, 535 行)
CREATE TABLE IF NOT EXISTS tushare_index (
  ts_code TEXT,
  trade_date TEXT,
  close REAL,
  pct_chg REAL,
  vol REAL,
  amount REAL
);

