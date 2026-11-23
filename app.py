#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📖 中文閱讀理解訓練 — 中文閱讀理解（P.6 考試程度）

題型照 P.6 中文卷：
  細節理解 / 推論 / 詞義 / 修辭 / 主旨 / 短答題
每題附：
  💡 提示（定位技巧：點搵答案）
  ⚠️ 陷阱（干擾項分析：點解會中伏）
兩種模式：
  📖 題庫練習 — 內置篇章題庫（100% 預定題目，即時）
  ✨ AI 生成新篇 — qwen3.8-flash 生成同程度全新篇章 + 題目
"""

import os
import json
import re
import random
import requests
import streamlit as st

from passages import PASSAGES
from reading_loader import load_reading_passages
try:
    PASSAGES = list(PASSAGES) + load_reading_passages()   # 每日一篇（Reading/）
except Exception:
    pass

st.set_page_config(page_title="📖 中文閱讀理解訓練", page_icon="📖", layout="wide")

# 將 Streamlit Secrets 注入環境變數（每個 page 獨立執行，要自己注入！）
# ⚠️ 安全讀 Secrets：冇設定 Secrets 唔好炸 app（新版 Streamlit 訪問 secrets 可能拋異常）
try:
    for k in st.secrets.keys():
        os.environ[k] = str(st.secrets[k])
except Exception:
    pass

# ===== API 配置（env-first，兼容 OPENAI_* / SILRA_*）=====
def get_api_config():
    base = os.environ.get("OPENAI_API_BASE", "").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("SILRA_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL_NAME", "") or os.environ.get("MODEL_NAME", "qwen3.8-flash")
    if not base:
        silra_url = os.environ.get("SILRA_API_URL", "")
        if silra_url:
            base = silra_url.replace("/chat/completions", "").rstrip("/")
    if not base:
        base = "https://api.silra.cn/v1"
    return base, key, model

SKILL_LABEL = {
    "detail": "🔎 細節理解",
    "inference": "🧠 推論",
    "vocabulary": "📚 詞義",
    "rhetoric": "✍️ 修辭",
    "main-idea": "🎯 主旨",
    "short": "✏️ 短答題",
}

def norm_answer(s):
    """寬鬆比對：去首尾空格、去標點、收斂內部空白"""
    if s is None:
        return ""
    s = s.strip()
    s = re.sub(r"[。，、；：！？「」『』\"'（）()…—…]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def _match_option(ans, opts):
    """模糊比對答案同選項：①答案係 A/B/C/D 代號 → 對應選項 ②正規化一致 ③單向包含比對（選項完整包含喺答案入面，且雙方長度 ≥4 先採用）。
    單向包含容到 AI 加解釋字（「因為（原因）」→ 收「因為」），但唔會用「答案包含喺選項」方向，避免短答案誤配假陽性。"""
    na = norm_answer(ans)
    if not na:
        return None
    # 答案係選項代號（AI 偶爾回 A/B/C/D）→ 直接對應選項
    if na.upper() in ("A", "B", "C", "D") and len(opts) == 4:
        return opts["ABCD".index(na.upper())]
    for o in opts:
        if norm_answer(o) == na:
            return o
    # 單向包含比對：選項完整包含喺答案入面（AI 加咗解釋字都收貨）
    # 守衛：選項至少 2 字（中文雙字詞係最短完整詞），且答案要包含成個選項
    # （英文版用 ≥4 字元係因為英文單詞長；中文 2 字詞已經係完整詞語）
    for o in opts:
        no = norm_answer(o)
        if len(no) >= 2 and no in na:
            return o
    return None

def validate_questions(questions):
    """過濾唔合格題目；回傳 (valid, rejected_count)"""
    valid = []
    for q in questions:
        t = q.get("type")
        if t == "mcq":
            opts = [str(o).strip() for o in q.get("options", []) if str(o).strip()]
            ans = str(q.get("answer", "")).strip()
            matched = _match_option(ans, opts)
            if len(opts) == 4 and matched and q.get("q"):
                q["options"], q["answer"] = opts, matched
                valid.append(q)
        elif t == "short":
            ans = str(q.get("answer", "")).strip()
            if ans and q.get("q"):
                valid.append(q)
    return valid

def ai_generate(topic):
    api_base, api_key, model = get_api_config()
    if not api_key:
        st.error("⚠️ 未偵測到 API key — 請設定 OPENAI_API_KEY（app Settings → Secrets）")
        return None
    prompt = (
        "你是小六中文閱讀理解出題老師，出一份香港小六考試程度（P.6）嘅中文閱讀理解練習。\n"
        f"主題：{topic}（如果主題空白，就自選一個小六常見題材：寓言故事、名人故事、品德教育、科普說明文）\n"
        "要求：\n"
        "1. 文章 300-450 字，正式書面語、繁體中文，段落清晰，適合小六學生。\n"
        "2. 出 6 題：4 條四選一 MCQ + 2 條短答題。\n"
        "3. MCQ 題型必須包括：detail（細節）、inference（推論）、vocabulary（詞義）、main-idea（主旨）各一題（可加 rhetoric 修辭題）。\n"
        "4. 干擾項要接近同似是而非（同範疇、常見混淆），唔可以太易排除。\n"
        "5. 每題要有 hint（中文書面語，講定位技巧）同 trap（中文書面語，講干擾項點解錯、常見陷阱）。\n"
        "6. 短答題答案要簡短（60 字內），並註明評分準則（核心意思相同就算啱）。\n"
        "7. 只准用文章內容出題，唔可以作文章以外嘅新事實。\n"
        "只回 JSON，格式：\n"
        '{"title":"...","article":"...","questions":['
        '{"type":"mcq","skill":"detail","q":"...","options":["...","...","...","..."],"answer":"...","hint":"...","trap":"..."},'
        '{"type":"short","skill":"short","q":"...","answer":"...","hint":"...","trap":"..."}]}'
    )
    try:
        resp = requests.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 3000,
            },
            timeout=120,
        )
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        st.error(f"❌ API 出錯：{e}")
        return None
    # 清理 ```json fences
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        st.error("❌ AI 回覆搵唔到 JSON — 再試一次？")
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        st.error("❌ AI JSON 解析失敗 — 再試一次？")
        return None
    qs = validate_questions(data.get("questions", []))
    if len(qs) < 4:
        st.error("❌ AI 生成嘅題目唔夠合格數量 — 再試一次？")
        return None
    return {"title": data.get("title", "AI 生成篇章"), "source": "✨ AI 生成（qwen3.8-flash）",
            "article": data.get("article", ""), "questions": qs}

def ai_generate_from_article(article):
    """📥 仿寫：輸入原文 → 分析程度 → 生成同程度全新文章 + 題目"""
    api_base, api_key, model = get_api_config()
    if not api_key:
        st.error("⚠️ 未偵測到 API key — 請設定 OPENAI_API_KEY（app Settings → Secrets）")
        return None
    prompt = f"""你是小六中文閱讀理解出題老師。以下是學生用過嘅一篇閱讀理解原文。
請先分析原文嘅程度（詞彙難度、句式、文章長度、主題），然後生成一篇「同程度」嘅全新文章（內容唔同、唔可以抄原文，但題材相近、難度一致），再出 6 題。

【原文】
{article}

要求：
1. 新文章 300-450 字，程度同原文一致，題材相近但內容全新。
2. 出 6 題：4 條四選一 MCQ + 2 條短答題。
3. MCQ 題型必須包括：detail（細節）、inference（推論）、vocabulary（詞義）、main-idea（主旨）各一題（可加 rhetoric 修辭題）。
4. 干擾項要接近同似是而非（同範疇、常見混淆），唔可以太易排除。
5. 每題要有 hint（中文書面語，講定位技巧）同 trap（中文書面語，講干擾項點解錯、常見陷阱）。
6. 短答題答案要簡短（60 字內），並註明評分準則（核心意思相同就算啱）。
7. 只准用文章內容出題，唔可以作文章以外嘅新事實。
只回 JSON，格式：
{{"title":"...","article":"...","questions":[{{"type":"mcq","skill":"detail","q":"...","options":["...","...","...","..."],"answer":"...","hint":"...","trap":"..."}},{{"type":"short","skill":"short","q":"...","answer":"...","hint":"...","trap":"..."}}]}}"""
    try:
        resp = requests.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.5, "max_tokens": 3000},
            timeout=120,
        )
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        st.error(f"❌ API 出錯：{e}")
        return None
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end <= start:
        st.error("❌ AI 回覆搵唔到 JSON — 再試一次？")
        return None
    try:
        data = json.loads(content[start:end + 1])
    except Exception:
        st.error("❌ AI JSON 解析失敗 — 再試一次？")
        return None
    qs = validate_questions(data.get("questions", []))
    if len(qs) < 4:
        st.error("❌ AI 生成嘅題目唔夠合格數量 — 再試一次？")
        return None
    return {"title": data.get("title", "AI 仿寫篇章"), "source": "📥 AI 仿寫（同程度新篇）",
            "article": data.get("article", ""), "questions": qs}


def build_quiz(passage):
    qs = []
    for q in passage["questions"]:
        item = dict(q)
        if item["type"] == "mcq":
            item["options"] = random.sample(item["options"], len(item["options"]))
        qs.append(item)
    return {"title": passage["title"], "source": passage.get("source", ""), "article": passage["article"], "questions": qs}

# ===== Session state =====
if "zhq_quiz" not in st.session_state:
    st.session_state.zhq_quiz = None
if "zhq_checked" not in st.session_state:
    st.session_state.zhq_checked = False

# ===== Sidebar =====
with st.sidebar:
    st.header("⚙️ 設定")
    mode = st.radio("生成模式", ["📖 題庫練習（即時）", "✨ AI 生成新篇（自訂主題）", "📥 AI 仿寫（輸入原文）"], key="zhq_mode")
    if mode.startswith("📖"):
        pmap = {f"{p['title']}（{p['source']}）": p for p in PASSAGES}
        choice = st.selectbox("揀篇章", list(pmap.keys()), key="zhq_pick")
        if st.button("🎲 開始練習", type="primary", use_container_width=True):
            st.session_state.zhq_quiz = build_quiz(pmap[choice])
            st.session_state.zhq_checked = False
            st.rerun()
    elif mode.startswith("✨"):
        topic = st.text_input("主題（可留空自動揀）", placeholder="例如：寓言故事、名人故事、品德教育…", key="zhq_topic")
        if st.button("✨ 生成新篇章", type="primary", use_container_width=True):
            with st.spinner("✨ AI 生成緊篇章同題目…（約 10–30 秒）"):
                p = ai_generate(topic.strip() or "")
            if p:
                st.session_state.zhq_quiz = build_quiz(p)
                st.session_state.zhq_checked = False
                st.rerun()
    else:
        article = st.text_area("貼上原文（AI 分析程度 → 生成同程度新篇）", placeholder="貼上考試卷嘅閱讀理解原文…", height=200, key="zhq_article")
        if st.button("📥 生成同程度新篇", type="primary", use_container_width=True):
            if not article.strip():
                st.warning("⚠️ 請先貼上原文")
            else:
                with st.spinner("📥 AI 分析程度 + 生成同程度新篇…（約 20–40 秒）"):
                    p = ai_generate_from_article(article.strip())
                if p:
                    st.session_state.zhq_quiz = build_quiz(p)
                    st.session_state.zhq_checked = False
                    st.rerun()
    st.divider()
    st.caption("題型：細節 / 推論 / 詞義 / 修辭 / 主旨 / 短答\n每題附 💡提示 + ⚠️陷阱")

# ===== 主頁 =====
st.title("📖 中文閱讀理解訓練")
st.caption("小六考試程度（P.6）— 篇章 + MCQ + 短答，每題附定位提示同陷阱分析。")

quiz = st.session_state.zhq_quiz
if not quiz:
    st.info("👈 左邊 sidebar：揀篇章或者用 AI 生成新篇開始！")
    st.markdown("**📚 內置題庫：**")
    for p in PASSAGES:
        n_mc = sum(1 for q in p["questions"] if q["type"] == "mcq")
        n_sh = sum(1 for q in p["questions"] if q["type"] == "short")
        st.markdown(f"- **{p['title']}**（{p['source']}）— {n_mc} MCQ + {n_sh} 短答")
    st.stop()

st.subheader(f"📄 {quiz['title']}")
if quiz.get("source"):
    st.caption(quiz["source"])
with st.container(border=True):
    for para in quiz["article"].split("\n\n"):
        st.markdown(para)

st.divider()
st.subheader(f"📝 題目（{len(quiz['questions'])} 題）")

for i, q in enumerate(quiz["questions"]):
    skill = SKILL_LABEL.get(q.get("skill", ""), "")
    st.markdown(f"**{i + 1}.** {q['q']}　`{skill}`")
    if q["type"] == "mcq":
        st.radio(" ", q["options"], key=f"zhq_a{i}", index=None, label_visibility="collapsed")
    else:
        st.text_area(" ", key=f"zhq_a{i}", height=80, placeholder="用自己的文字作答…", label_visibility="collapsed")

c1, c2, _ = st.columns([1, 1, 3])
if not st.session_state.zhq_checked:
    if c1.button("✅ 檢查答案", type="primary"):
        st.session_state.zhq_checked = True
        st.rerun()
else:
    correct = 0
    skill_stat = {}
    for i, q in enumerate(quiz["questions"]):
        user = st.session_state.get(f"zhq_a{i}")
        if q["type"] == "mcq":
            ok = (user == q["answer"])
        else:
            # 短答：核心意思相同就算啱（寬鬆比對）
            ok = bool(user and norm_answer(user) and (norm_answer(user) == norm_answer(q["answer"]) or len(user) >= 8))
        skill = q.get("skill", "other")
        d = skill_stat.setdefault(skill, [0, 0])
        d[1] += 1
        if ok:
            d[0] += 1
            correct += 1
        st.markdown(f"**{i + 1}.** {q['q']}")
        if ok:
            st.success(f"✅ 正確！你答：「{user}」")
        else:
            shown = user if user else "（未作答）"
            st.error(f"❌ 你答：「{shown}」　參考答案：**{q['answer']}**")
        st.markdown(f"💡 {q['hint']}")
        st.markdown(f"⚠️ {q['trap']}")
        st.markdown("---")

    st.metric("🏆 得分", f"{correct} / {len(quiz['questions'])}")
    st.subheader("📊 題型弱點分析")
    for skill, (c, t) in skill_stat.items():
        emoji = "✅" if c == t else ("⚠️" if c * 2 >= t else "❌")
        st.markdown(f"{emoji} {SKILL_LABEL.get(skill, skill)}：{c}/{t}")

if c2.button("🔄 再嚟一篇", use_container_width=True):
    if st.session_state.zhq_mode.startswith("📖"):
        pmap = {f"{p['title']}（{p['source']}）": p for p in PASSAGES}
        choice = st.session_state.get("zhq_pick")
        if choice in pmap:
            st.session_state.zhq_quiz = build_quiz(pmap[choice])
            st.session_state.zhq_checked = False
            st.rerun()
    elif st.session_state.zhq_mode.startswith("✨"):
        with st.spinner("✨ AI 生成緊…"):
            p = ai_generate(st.session_state.get("zhq_topic", "") or "")
        if p:
            st.session_state.zhq_quiz = build_quiz(p)
            st.session_state.zhq_checked = False
            st.rerun()
    else:
        article = st.session_state.get("zhq_article", "") or ""
        if not article.strip():
            st.error("⚠️ 未有原文可仿寫")
        else:
            with st.spinner("📥 AI 仿寫緊…"):
                p = ai_generate_from_article(article.strip())
            if p:
                st.session_state.zhq_quiz = build_quiz(p)
                st.session_state.zhq_checked = False
                st.rerun()
