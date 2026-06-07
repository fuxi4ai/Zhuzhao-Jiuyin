#!/usr/bin/env python3
"""
烛照九阴 — 统一日志模块

用法：
    from lib.logger import get_logger
    logger = get_logger(__name__)
    logger.info("正常信息")
    logger.warning("警告")
    logger.error("错误")
    logger.debug("调试信息")

配置：
    环境变量 LOG_LEVEL 控制全局日志级别（DEBUG/INFO/WARNING/ERROR）
    默认级别：INFO
"""

import logging
import os
import sys

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 日志级别（可通过环境变量覆盖）
_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}
LOG_LEVEL = LEVEL_MAP.get(_LOG_LEVEL, logging.INFO)

# 是否输出到控制台（默认输出）
LOG_TO_CONSOLE = os.environ.get("LOG_TO_CONSOLE", "1") == "1"

# 日志文件格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 全局 handlers 缓存（避免重复添加）
_handlers_setup = {}


def get_logger(name, log_file=None):
    """获取 logger 实例

    Args:
        name: logger 名称（通常用 __name__）
        log_file: 可选，额外写入指定文件。None 时自动写入 logs/app.log
    """
    if name in _handlers_setup:
        return logging.getLogger(name)

    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # 文件 handler（默认 app.log）
    log_path = log_file or os.path.join(LOG_DIR, "app.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(LOG_LEVEL)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # 控制台 handler
    if LOG_TO_CONSOLE:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(LOG_LEVEL)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    _handlers_setup[name] = True
    return logger
