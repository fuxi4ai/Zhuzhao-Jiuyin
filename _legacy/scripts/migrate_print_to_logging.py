#!/usr/bin/env python3
"""
自动将 print() 替换为 logger 调用

用法：
  python3 scripts/migrate_print_to_logging.py --dry-run   # 预览变更
  python3 scripts/migrate_print_to_logging.py --apply     # 执行替换
"""

import argparse
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", ".git", "archive", "dragon-palace", "node_modules"}
TARGET_FILES = []

# 收集所有活跃 Python 文件
for root, dirs, files in os.walk(PROJECT_ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        if f.endswith(".py"):
            fpath = os.path.join(root, f)
            rel = os.path.relpath(fpath, PROJECT_ROOT)
            # 排除自身和 lib/logger.py
            if rel in ("scripts/migrate_print_to_logging.py", "lib/logger.py"):
                continue
            TARGET_FILES.append(fpath)

IMPORT_LINE = 'from lib.logger import get_logger\nlogger = get_logger(__name__)\n'


def get_import_path(filepath):
    """生成相对于项目根目录的 from lib.logger import"""
    rel = os.path.relpath(filepath, PROJECT_ROOT)
    parts = Path(rel).parts
    depth = len(parts) - 1
    prefix = "." * depth if depth > 0 else ""
    return f"from {prefix}lib.logger import get_logger\nlogger = get_logger(__name__)\n"


def migrate_file(filepath, dry_run=True):
    """迁移单个文件的 print() → logger"""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    changes = []
    new_lines = []
    has_logger = any("from" in l and "logger" in l and "import" in l for l in lines)
    logger_added = False

    for i, line in enumerate(lines, 1):
        # 检查是否是纯 print() 调用（非 f-string 内的 print）
        stripped = line.lstrip()

        # 跳过已经是 logger 调用的行
        if "logger." in line:
            new_lines.append(line)
            continue

        # 匹配 print(...) 调用
        m = re.match(r'^(\s*)print\((.*)\)\s*$', line)
        if m:
            indent = m.group(1)
            content = m.group(2).strip()

            # 空 print() → logger.info("")
            if not content:
                new_line = f'{indent}logger.info("")\n'
                changes.append((i, f'print() → logger.info("")'))
            # print(f"...") 或 print("...") → logger.info(...)
            elif content.startswith('f"') or content.startswith("f'") or content.startswith('"') or content.startswith("'"):
                new_line = f'{indent}logger.info({content})\n'
                preview = content[:60]
                changes.append((i, f'print(f"...") → logger.info({preview}...)'))
            # print(x, y, z) → logger.info(f"{x} {y} {z}")
            elif "," in content:
                # 多参数 print，转换为 f-string
                args = content.split(",")
                f_str = " + ' ' + ".join(a.strip() for a in args)
                new_line = f'{indent}logger.info(str({f_str}))\n'
                changes.append((i, f'print(a,b,c) → logger.info(...)'))
            else:
                # 单变量 print(x)
                new_line = f'{indent}logger.info({content})\n'
                changes.append((i, f'print(x) → logger.info(x)'))

            # 添加 logger import（在第一行非注释/非 shebang 的 import 之前）
            if not has_logger and not logger_added:
                if stripped.startswith("import ") or stripped.startswith("from "):
                    new_lines.insert(len(new_lines) - 1 if new_lines else 0, get_import_path(filepath))
                    logger_added = True

            new_lines.append(new_line)
        else:
            new_lines.append(line)

    # 如果文件有 print 但没有添加 logger import，在顶部添加
    if changes and not has_logger and not logger_added:
        # 找到 shebang 之后的位置
        insert_at = 0
        for j, l in enumerate(new_lines):
            if l.startswith("#!") or l.startswith("#"):
                insert_at = j + 1
            else:
                break
        new_lines.insert(insert_at, get_import_path(filepath))

    return changes, new_lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="预览变更，不修改文件")
    parser.add_argument("--apply", action="store_true", help="执行替换")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("请指定 --dry-run 或 --apply")
        return

    total_changes = 0
    for fpath in sorted(TARGET_FILES):
        changes, new_lines = migrate_file(fpath, args.dry_run)
        if changes:
            rel = os.path.relpath(fpath, PROJECT_ROOT)
            total_changes += len(changes)
            if args.dry_run:
                print(f"  {rel}: {len(changes)} 处变更")
                for line_num, desc in changes[:3]:
                    print(f"    L{line_num}: {desc}")
                if len(changes) > 3:
                    print(f"    ... 等 {len(changes)} 处")
            else:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                print(f"  ✅ {rel}: {len(changes)} 处 print → logger")

    action = "预览" if args.dry_run else "已修复"
    print(f"\n总计: {total_changes} 处 {action}")


if __name__ == "__main__":
    main()
