import azure.functions as func
import logging
import json
import requests
from bs4 import BeautifulSoup
import re

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# -------------------------
# 補助関数
# -------------------------
def extract_race_id(url: str):
    m = re.search(r"race_id=(\d{12,13})", url)
    return m.group(1) if m else None

def extract_shutuba_table(html_bytes: bytes):
    soup = BeautifulSoup(html_bytes, "lxml")

    table = soup.find("table", class_="Shutuba_Table")
    if table:
        return table

    table = soup.find("table", class_="RaceTable01 RaceTable01-Shutuba")
    if table:
        return table

    return None

def parse_shutuba_table(table):
    rows = table.find_all("tr")[1:]
    horses = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 10:
            continue

        horse_name = ""
        horse_id = None

        tag = row.find("span", class_="HorseName")
        if tag:
            horse_name = tag.get_text(strip=True)

        a = row.select_one("a[href*='/horse/']")
        if a:
            m = re.search(r"/horse/(\d+)", a.get("href", ""))
            if m:
                horse_id = m.group(1)

        if not horse_name and a:
            horse_name = a.text.strip()

        odds_span = row.find("span", class_="Odds_Ninki")
        odds = odds_span.get_text(strip=True) if odds_span else None

        horses.append({
            "waku": cols[0].text.strip(),
            "umaban": cols[1].text.strip(),
            "horse_name": horse_name,
            "horse_id": horse_id,
            "sex_age": cols[4].text.strip(),
            "weight": cols[5].text.strip(),
            "jockey": cols[6].text.strip(),
            "odds": odds,
        })

    return horses

# -------------------------
# shutuba 関数（最小構成）
# -------------------------
@app.route(route="shutuba")
def shutuba(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("shutuba function triggered")

    url = req.params.get("url")
    if not url:
        return func.HttpResponse(
            json.dumps({"error": "url パラメータが必要です"}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json"
        )

    race_id = extract_race_id(url)
    if not race_id:
        return func.HttpResponse(
            json.dumps({"error": "race_id を URL から抽出できません"}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json"
        )

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        html_bytes = res.content
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": f"HTML 取得エラー: {e}"}, ensure_ascii=False),
            status_code=500,
            mimetype="application/json"
        )

    table = extract_shutuba_table(html_bytes)
    if not table:
        return func.HttpResponse(
            json.dumps({"error": "出馬表テーブルが見つかりません"}, ensure_ascii=False),
            status_code=500,
            mimetype="application/json"
        )

    horses = parse_shutuba_table(table)

    return func.HttpResponse(
        json.dumps({"race_id": race_id, "horses": horses}, ensure_ascii=False),
        mimetype="application/json"
    )

# -------------------------
# scoring 関数
# -------------------------
@app.route(route="scoring")
def scoring(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("scoring function triggered")

    try:
        body = req.get_json()
    except:
        return func.HttpResponse(
            json.dumps({"error": "JSON ボディが必要です"}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json"
        )

    horses = body.get("horses")
    if not horses:
        return func.HttpResponse(
            json.dumps({"error": "horses が必要です"}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json"
        )

    scored = []

    for h in horses:
        score = 0

        # -------------------------
        # ① 枠順スコア（1〜8枠）
        # -------------------------
        try:
            waku = int(h.get("waku", 0))
            # 内枠有利（例：1枠=+20、8枠=+5）
            waku_score = max(5, 25 - waku * 3)
            score += waku_score
        except:
            pass

        # -------------------------
        # ② 騎手スコア（簡易）
        # -------------------------
        jockey = h.get("jockey", "")
        jockey_score_map = {
            "川田": 25, "ルメール": 25, "戸崎": 20, "横山武": 20,
            "松山": 18, "坂井": 18, "武豊": 18,
        }
        for key, val in jockey_score_map.items():
            if key in jockey:
                score += val
                break

        # -------------------------
        # ③ 斤量スコア（軽いほど有利）
        # -------------------------
        try:
            weight = float(h.get("weight", "0").replace("kg", "").strip())
            # 55kg を基準に、1kg 重いごとに -1.5
            score += max(0, 20 - (weight - 55) * 1.5)
        except:
            pass

        # -------------------------
        # ④ オッズスコア（人気馬を加点）
        # -------------------------
        odds = h.get("odds")
        if odds:
            try:
                odds_val = float(odds)
                # 1番人気（1.0〜2.0）なら +25、10倍なら +5
                odds_score = max(0, 30 - odds_val * 2)
                score += odds_score
            except:
                pass

        # -------------------------
        # ⑤ 馬番スコア（軽量）
        # -------------------------
        try:
            umaban = int(h.get("umaban", 0))
            score += max(0, 15 - umaban * 0.5)
        except:
            pass

        # -------------------------
        # 最終スコア（0〜100に丸める）
        # -------------------------
        score = max(0, min(100, round(score, 2)))

        scored.append({
            **h,
            "score": score
        })

    return func.HttpResponse(
        json.dumps({"horses": scored}, ensure_ascii=False),
        mimetype="application/json"
    )

# -------------------------
# ranking 関数
# -------------------------
@app.route(route="ranking")
def ranking(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("ranking function triggered")

    try:
        body = req.get_json()
    except:
        return func.HttpResponse(
            json.dumps({"error": "JSON ボディが必要です"}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json"
        )

    horses = body.get("horses")
    if not horses:
        return func.HttpResponse(
            json.dumps({"error": "horses が必要です"}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json"
        )

    ranked = []

    for h in horses:
        base_score = h.get("score", 0)
        total = base_score

        # -------------------------
        # ① 枠順補正（1枠が最も有利）
        # -------------------------
        try:
            waku = int(h.get("waku", 0))
            waku_bonus = max(0, 10 - (waku - 1) * 1.2)
            total += waku_bonus
        except:
            pass

        # -------------------------
        # ② 騎手補正（scoring と同じ基準）
        # -------------------------
        jockey = h.get("jockey", "")
        jockey_score_map = {
            "川田": 8, "ルメール": 8, "戸崎": 6, "横山武": 6,
            "松山": 5, "坂井": 5, "武豊": 5,
        }
        for key, val in jockey_score_map.items():
            if key in jockey:
                total += val
                break

        # -------------------------
        # ③ オッズ補正（人気馬を加点）
        # -------------------------
        odds = h.get("odds")
        if odds:
            try:
                odds_val = float(odds)
                odds_bonus = max(0, 15 - odds_val * 1.5)
                total += odds_bonus
            except:
                pass

        # -------------------------
        # ④ 馬番補正（内寄りが有利）
        # -------------------------
        try:
            umaban = int(h.get("umaban", 0))
            umaban_bonus = max(0, 8 - umaban * 0.3)
            total += umaban_bonus
        except:
            pass

        # -------------------------
        # 最終スコア
        # -------------------------
        total = round(total, 2)

        ranked.append({
            **h,
            "ranking_score": total
        })

    # -------------------------
    # 降順で並べ替え
    # -------------------------
    ranked_sorted = sorted(ranked, key=lambda x: x["ranking_score"], reverse=True)

    return func.HttpResponse(
        json.dumps({"horses": ranked_sorted}, ensure_ascii=False),
        mimetype="application/json"
    )

# =========================================================
# process_past（調子分析 + AI要約）
# =========================================================

from openai import AzureOpenAI
import os

# Azure OpenAI クライアント
client = AzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2024-02-01",
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"]
)

# -------------------------
# 過去走 Ajax 取得
# -------------------------
def fetch_past_runs_html(horse_id: str) -> bytes:
    url = f"https://db.netkeiba.com/horse/ajax/{horse_id}/"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()
    return res.content

# -------------------------
# 過去走テーブル抽出
# -------------------------
def extract_past_table(html_bytes: bytes):
    soup = BeautifulSoup(html_bytes, "lxml")
    return soup.find("table")

# -------------------------
# 過去5走パース
# -------------------------
def parse_past_5runs(table):
    rows = table.find_all("tr")[1:6]
    results = []

    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) < 10:
            continue

        results.append({
            "date": tds[0].text.strip(),
            "race_name": tds[4].text.strip(),
            "rank": tds[11].text.strip(),
            "time": tds[12].text.strip(),
            "margin": tds[13].text.strip(),
            "pop": tds[14].text.strip(),
            "odds": tds[15].text.strip()
        })

    return results

# -------------------------
# 特徴量抽出
# -------------------------
def extract_features(past_runs):
    ranks, pops, margins = [], [], []

    for r in past_runs:
        try: ranks.append(int(r["rank"]))
        except: pass
        try: pops.append(int(r["pop"]))
        except: pass
        try: margins.append(float(r["margin"]))
        except: pass

    return {
        "avg_rank": sum(ranks)/len(ranks) if ranks else 99,
        "avg_pop": sum(pops)/len(pops) if pops else 99,
        "avg_margin": sum(margins)/len(margins) if margins else 9.9
    }

# -------------------------
# 調子スコア
# -------------------------
def calc_condition_score(f):
    score = 100
    score -= f["avg_rank"] * 2
    score -= f["avg_pop"] * 1.5
    score -= f["avg_margin"] * 5
    return max(0, min(100, score))

# -------------------------
# 血統テキスト取得
# -------------------------
def fetch_pedigree_text(horse_id: str) -> str:
    url = f"https://db.netkeiba.com/horse/ped/{horse_id}/"
    html = requests.get(url, timeout=10).content
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(" ", strip=True)

# -------------------------
# LLM 要約
# -------------------------
def generate_summary(context: str) -> str:
    prompt = f"""
以下は競走馬の過去走データと血統情報です。
これを基に、競走馬の特徴・強み・弱み・適性を200字以内で要約してください。

{context}
"""
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    return res.choices[0].message.content

# -------------------------
# HTML カード
# -------------------------
def render_card(h, score, summary):
    return f"""
<div style="border:1px solid #ccc; padding:10px; margin:10px; border-radius:8px;">
  <h3>{h["horse_name"]}（{h["jockey"]}）</h3>
  <p><b>調子スコア:</b> {score}</p>
  <p>{summary}</p>
</div>
"""

# -------------------------
# HTML 全体
# -------------------------
def wrap_html(race_id, body):
    return f"""
<html>
<head>
<meta charset="UTF-8">
<title>調子分析 {race_id}</title>
</head>
<body>
<h2>調子分析レポート（race_id: {race_id}）</h2>
{body}
</body>
</html>
"""

# -------------------------
# process_past 本体
# -------------------------
@app.route(route="process_past")
def process_past(req: func.HttpRequest) -> func.HttpResponse:
    url = req.params.get("url")
    if not url:
        return func.HttpResponse("url パラメータが必要です", status_code=400)

    race_id = extract_race_id(url)

    # 出馬表取得
    headers = {"User-Agent": "Mozilla/5.0"}
    html = requests.get(url, headers=headers, timeout=10).content
    table = extract_shutuba_table(html)
    horses = parse_shutuba_table(table)

    result_html = ""

    for h in horses:
        horse_id = h["horse_id"]

        past_html = fetch_past_runs_html(horse_id)
        past_table = extract_past_table(past_html)
        past_runs = parse_past_5runs(past_table)

        features = extract_features(past_runs)
        score = calc_condition_score(features)

        pedigree = fetch_pedigree_text(horse_id)

        context = json.dumps({
            "horse": h,
            "past_runs": past_runs,
            "features": features,
            "pedigree": pedigree
        }, ensure_ascii=False)

        summary = generate_summary(context)

        result_html += render_card(h, score, summary)

    full_html = wrap_html(race_id, result_html)
    return func.HttpResponse(full_html, mimetype="text/html")
