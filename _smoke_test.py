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
assert isinstance(PASSAGES, list) and len(PASSAGES) >= 4, f"應該至少 4 篇，實際 {len(PASSAGES)}"
total_mc = total_short = 0
for p in PASSAGES:
    assert p["title"] and p["article"] and p["source"], f"{p['title']}: 缺欄位"
    assert p["questions"], f"{p['title']}: 冇題目"
    n_mc = n_sh = 0
    for q in p["questions"]:
        assert q.get("q") and q.get("hint") and q.get("trap"), f"{p['title']}: 題目缺 hint/trap"
        t = q.get("type")
        if t == "mcq":
            opts = q.get("options", [])
            assert len(opts) == 4, f"{p['title']}: MCQ 選項唔夠 4 個"
            assert q.get("answer") in opts, f"{p['title']}: 答案唔喺選項入面: {q['answer']} | {opts}"
            n_mc += 1
        elif t == "short":
            assert q.get("answer"), f"{p['title']}: 短答缺答案"
            n_sh += 1
        else:
            assert False, f"{p['title']}: 未知題型 {t}"
    total_mc += n_mc
    total_short += n_sh
    print(f"✅ {p['title']} — {n_mc} MCQ + {n_sh} 短答")

print(f"共 {len(PASSAGES)} 篇，{total_mc} MCQ + {total_short} 短答")
print("done")
