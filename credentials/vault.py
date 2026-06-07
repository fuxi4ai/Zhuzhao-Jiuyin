#!/usr/bin/env python3
"""
烛照九阴 — 凭证保险箱

安全存储 API 密钥、Token、Cookie。
优先级：环境变量 > 本地 JSON > 默认值

用法:
    from credentials.vault import get_api_key, get_cookie
    tushare_key = get_api_key("tushare")
    caixin_cookie = get_cookie("caixin")

环境变量:
    TUSHARE_API_KEY=xxx
    GANGTISE_API_KEY=xxx
    CAIXIN_COOKIE=xxx
"""

import os
import json
import stat
from pathlib import Path

CREDENTIALS_DIR = Path(__file__).parent
API_KEYS_FILE = CREDENTIALS_DIR / "api_keys.json"
COOKIES_FILE = CREDENTIALS_DIR / "cookies.json"


def _load_json(filepath):
    if not filepath.exists():
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 权限 600（仅 owner 可读写）
    os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)


def get_api_key(service, default=None):
    """获取 API Key（环境变量优先）"""
    env_key = f"{service.upper()}_API_KEY"
    # 1. 环境变量
    val = os.environ.get(env_key)
    if val:
        return val
    # 2. 本地文件
    keys = _load_json(API_KEYS_FILE)
    return keys.get(service.lower(), keys.get(service.upper(), default))


def get_cookie(service, default=None):
    """获取 Cookie（环境变量优先）"""
    env_key = f"{service.upper()}_COOKIE"
    val = os.environ.get(env_key)
    if val:
        return val
    cookies = _load_json(COOKIES_FILE)
    return cookies.get(service.lower(), cookies.get(service.upper(), default))


def save_api_key(service, key):
    """保存 API Key 到本地文件"""
    keys = _load_json(API_KEYS_FILE)
    keys[service.lower()] = key
    _save_json(API_KEYS_FILE, keys)


def save_cookie(service, cookie):
    """保存 Cookie 到本地文件"""
    cookies = _load_json(COOKIES_FILE)
    cookies[service.lower()] = cookie
    _save_json(COOKIES_FILE, cookies)


def audit_credentials(services=None):
    """审计凭证状态"""
    if services is None:
        services = ["tushare", "gangtise", "caixin"]

    report = {}
    for svc in services:
        report[svc] = {
            "api_key": "✅" if get_api_key(svc) else "❌",
            "cookie": "✅" if get_cookie(svc) else "❌",
        }
    return report
