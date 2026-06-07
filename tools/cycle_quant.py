#!/usr/bin/env python3
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config
from lib.logger import get_logger
logger = get_logger(__name__)
"""
🐲 量化情绪周期计算器
基于 6 指标评分体系，将主观情绪转化为量化分数

指标体系 (满分50):
  1. 涨停家数 (0-10): ≥80家=10, 50-79=7, 30-49=5, 15-29=3
  2. 跌停家数 (0-10): <3=10, 3-10=7, 11-20=5, 21-40=3
  3. 连板高度 (0-10): ≥7板=10, 4-6=5, 3=3
  4. 成交量 (0-10): ≥1.2万亿=10, 0.8-1.2=5
  5. 北向资金 (0-10): ≥50亿=10, 0-50=5
  6. 主线持续性 (0-10): 按板块最长连续天数计算

阶段阈值:
  冰点 ≤10 | 复苏 11-20 | 火热 21-30 | 退潮 >30
"""

from typing import Optional

def score_limit_up(count: Optional[int]) -> int:
    """涨停家数打分"""
    if count is None: return 0
    if count >= 80: return 10
    if count >= 50: return 7
    if count >= 30: return 5
    if count >= 15: return 3
    return 0

def score_limit_down(count: Optional[int]) -> int:
    """跌停家数打分（越少越好）"""
    if count is None: return 0
    if count < 3: return 10
    if count <= 10: return 7
    if count <= 20: return 5
    if count <= 40: return 3
    return 0

def score_consecutive(high: Optional[int]) -> int:
    """连板高度打分"""
    if high is None: return 0
    if high >= 7: return 10
    if high >= 4: return 5
    if high >= 3: return 3
    return 0

def score_volume(trillion: Optional[float]) -> int:
    """成交量打分"""
    if trillion is None: return 0
    if trillion >= 1.2: return 10
    if trillion >= 0.8: return 5
    return 0

def score_north(billion: Optional[float]) -> int:
    """北向资金打分"""
    if billion is None: return 0
    if billion >= 50: return 10
    if billion >= 0: return 5
    return 0

def score_theme_continuity(days: Optional[int]) -> int:
    """主线持续性打分（板块最长连续出现天数）"""
    if days is None: return 0
    if days >= 500: return 10  # 长期主线
    if days >= 300: return 7
    if days >= 100: return 5
    return 3

def calculate_score(**kwargs) -> dict:
    """
    计算量化情绪周期评分
    
    参数:
        limit_up: 涨停家数
        limit_down: 跌停家数
        consecutive: 连板高度
        volume: 成交量(万亿)
        north: 北向资金(亿)
        theme_days: 主线持续天数
    
    返回:
        {total_score, cycle_stage, details}
    """
    scores = {
        'limit_up': score_limit_up(kwargs.get('limit_up')),
        'limit_down': score_limit_down(kwargs.get('limit_down')),
        'consecutive': score_consecutive(kwargs.get('consecutive')),
        'volume': score_volume(kwargs.get('volume')),
        'north': score_north(kwargs.get('north')),
        'theme_continuity': score_theme_continuity(kwargs.get('theme_days')),
    }
    
    total = sum(scores.values())
    
    # 判断阶段
    if total <= 10:
        stage = '冰点'
    elif total <= 20:
        stage = '复苏'
    elif total <= 30:
        stage = '火热'
    else:
        stage = '退潮'
    
    return {
        'total_score': total,
        'cycle_stage': stage,
        'details': scores,
    }


# ─── 双轨对比（小鲍标注 vs 量化阶段）─────────────────────────
# 把两套词汇归一到 4 大类：冰点 / 复苏 / 火热 / 退潮
_STAGE_CANON = {
    "冰点": "冰点", "底部": "冰点", "冰封": "冰点",
    "复苏": "复苏", "修复": "复苏", "回升": "复苏", "调整": "复苏",
    "震荡": "复苏", "分歧": "复苏",
    "火热": "火热", "主升": "火热", "亢奋": "火热", "高潮": "火热", "加速": "火热",
    "退潮": "退潮", "退烧": "退潮", "衰退": "退潮", "降温": "退潮",
}


def normalize_stage(stage: Optional[str]) -> Optional[str]:
    """把小鲍/量化的阶段标签归一到 4 大类（冰点/复苏/火热/退潮）。
    采用子串匹配以兼容小鲍的自由文本（如『风险偏好回升(估值修复)』→ 复苏）。
    无法识别时返回原值。"""
    if not stage:
        return None
    s = str(stage)
    for key, canon in _STAGE_CANON.items():
        if key in s:
            return canon
    return s


def compare_cycles(bao_stage: Optional[str], quant_stage: Optional[str]) -> dict:
    """双轨对比：归一到大类后比较小鲍标注与量化阶段是否一致。
    返回 {bao, quant, bao_canon, quant_canon, match}"""
    bc = normalize_stage(bao_stage)
    qc = normalize_stage(quant_stage)
    return {
        "bao": bao_stage,
        "quant": quant_stage,
        "bao_canon": bc,
        "quant_canon": qc,
        "match": bool(bc and qc and bc == qc),
    }


if __name__ == "__main__":
    # 测试
    result = calculate_score(
        limit_up=92, limit_down=7, consecutive=6,
        volume=2.3, north=68.2, theme_days=532
    )
    logger.info(f"测试: 总分={result['total_score']} 阶段={result['cycle_stage']}")
    for k, v in result['details'].items():
        logger.info(f"  {k}: {v}")
