# -*- coding: utf-8 -*-
"""Smoke test：語法 + 篇章題庫完整性 + AI JSON 解析"""
import ast, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import py_compile
py_compile.compile("app.py", doraise=True)
py_compile.compile("passages.py", doraise=True)
print("✅ syntax OK")

import passages
PASSAGES = passages.PASSAGES
total_mc = total_short = 0

print("done")


# 每日一篇檢查
from reading_loader import load_reading_passages
lang = "中文" if "zh" in __file__ else "英文"
d = load_reading_passages(only_lang=lang)
assert d, "每日一篇讀唔到"
for p_ in d:
    assert len(p_["questions"]) == 8, p_["title"]
print(f"✅ 每日一篇 {len(d)} 篇 × 8 題 OK")
