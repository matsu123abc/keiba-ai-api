import azure.functions as func
import logging
import json
import requests
from bs4 import BeautifulSoup
import re
import os
from typing import List, Dict

# =========================================================
# Azure Functions v2 FunctionApp（1つだけ）
# =========================================================
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# =========================================================
# 共通：race_id 抽出
# =========================================================
def extract_race_id(url: str):
    m = re.search(r"race_id=(\d{12,13})", url)
    if m:
        return m.group(1)

    m = re.search(r"(\d{12})", url)
    if m:
        return m.group(1)

    return None

# =========================================================
# 共通：出馬表（shutuba_past.html）
# =========================================================
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

# =========================================================
# shutuba 関数
# =========================================================
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

# =========================================================
# scoring 関数
# =========================================================
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

        # 枠順
        try:
            waku = int(h.get("waku", 0))
            score += max(5, 25 - waku * 3)
        except:
            pass

        # 騎手
        jockey = h.get("jockey", "")
        jockey_score_map = {
            "川田": 25, "ルメール": 25, "戸崎": 20, "横山武": 20,
            "松山": 18, "坂井": 18, "武豊": 18,
        }
        for key, val in jockey_score_map.items():
            if key in jockey:
                score += val
                break

        # 斤量
        try:
            weight = float(h.get("weight", "0").replace("kg", "").strip())
            score += max(0, 20 - (weight - 55) * 1.5)
        except:
            pass

        # オッズ
        odds = h.get("odds")
        if odds:
            try:
                odds_val = float(odds)
                score += max(0, 30 - odds_val * 2)
            except:
                pass

        # 馬番
        try:
            umaban = int(h.get("umaban", 0))
            score += max(0, 15 - umaban * 0.5)
        except:
            pass

        score = max(0, min(100, round(score, 2)))

        scored.append({**h, "score": score})

    return func.HttpResponse(
        json.dumps({"horses": scored}, ensure_ascii=False),
        mimetype="application/json"
    )

# =========================================================
# ranking 関数
# =========================================================
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
        total = h.get("score", 0)

        # 枠順補正
        try:
            waku = int(h.get("waku", 0))
            total += max(0, 10 - (waku - 1) * 1.2)
        except:
            pass

        # 騎手補正
        jockey = h.get("jockey", "")
        jockey_score_map = {
            "川田": 8, "ルメール": 8, "戸崎": 6, "横山武": 6,
            "松山": 5, "坂井": 5, "武豊": 5,
        }
        for key, val in jockey_score_map.items():
            if key in jockey:
                total += val
                break

        # オッズ補正
        odds = h.get("odds")
        if odds:
            try:
                odds_val = float(odds)
                total += max(0, 15 - odds_val * 1.5)
            except:
                pass

        # 馬番補正
        try:
            umaban = int(h.get("umaban", 0))
            total += max(0, 8 - umaban * 0.3)
        except:
            pass

        ranked.append({**h, "ranking_score": round(total, 2)})

    ranked_sorted = sorted(ranked, key=lambda x: x["ranking_score"], reverse=True)

    return func.HttpResponse(
        json.dumps({"horses": ranked_sorted}, ensure_ascii=False),
        mimetype="application/json"
    )

# =========================================================
# process_past（調子分析 + AI要約）
# =========================================================

# OpenAI import
try:
    from openai import AzureOpenAI
    openai_import_error = None
except Exception as e:
    AzureOpenAI = None
    openai_import_error = str(e)


def get_openai_client():
    if AzureOpenAI is None:
        return None, f"OpenAI import エラー: {openai_import_error}"

    try:
        client = AzureOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            api_version="2024-02-01",
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT")
        )
        return client, None
    except Exception as e:
        return None, f"OpenAI クライアント初期化エラー: {e}"


# 出馬表（process_past 用）
def extract_shutuba_table_with_links(html_bytes):
    soup = BeautifulSoup(html_bytes, "lxml")

    table = soup.find("table", class_="RaceTable01 RaceTable01-HorseList")
    if table:
        return table

    table = soup.find("table", class_="Shutuba_Table")
    if table:
        return table

    table = soup.find("table", class_="RaceTable01 RaceTable01-Shutuba")
    if table:
        return table

    return None


def parse_shutuba_table_with_links(table):
    rows = table.find_all("tr")[1:]
    horses = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        waku = cols[0].text.strip()
        umaban = cols[1].text.strip()

        if not waku or not waku[0].isdigit():
            continue

        horse_name = ""
        horse_id = None

        for c in cols:
            a = c.find("a")
            if a and "horse" in (a.get("href") or ""):
                horse_name = a.text.strip()
                horse_url = a.get("href", "")
                horse_id = horse_url.rstrip("/").split("/")[-1]
                break

        if not horse_name or not horse_id:
            continue

        horses.append({
            "waku": waku,
            "umaban": umaban,
            "horse_name": horse_name,
            "horse_id": horse_id,
        })

    return horses


# Ajax 過去走
def fetch_past_runs_html(horse_id: str):
    url = f"https://db.netkeiba.com/horse/ajax_horse_results.html?id={horse_id}"
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Referer": "https://db.netkeiba.com/",
            "Cookie": "device=pc"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()

        res.encoding = "euc-jp"

        return res.text, None
    except Exception as e:
        return None, f"過去走HTML取得エラー: {e}"


def extract_past_table_from_ajax(html_text: str):
    soup = BeautifulSoup(html_text, "lxml")
    return soup.find("table")

# =========================================================
# ① AI要約用（LLM に渡す軽量データ）
# =========================================================
def parse_past_5runs(table):
    rows = table.find_all("tr")[1:]
    past_runs = []

    for row in rows[:5]:
        cols = row.find_all("td")

        def safe(idx):
            if idx < len(cols):
                return cols[idx].get_text(strip=True)
            return ""

        past_runs.append({
            "date": safe(0),
            "race": safe(1),
            "class": safe(2),
            "distance": safe(3),
            "condition": safe(4),
            "finish": safe(5),
            "time": safe(7),
            "agari": safe(10),
            "passing": safe(11),
            "jockey": safe(12),
            "weight": safe(13),
            "body_weight": safe(14),
        })

    return past_runs


# =========================================================
# ② 調子スコア計算用（特徴量抽出のための数値データ）
# =========================================================
def parse_past_5runs_for_condition(table):
    rows = table.find_all("tr")
    if len(rows) <= 1:
        return []

    past_runs = []

    for row in rows[1:6]:
        cols = row.find_all("td")

        def safe(idx):
            if idx < len(cols):
                return cols[idx].get_text(strip=True)
            return ""

        past_runs.append({
            "date": safe(0),
            "race_name": safe(1),
            "class": safe(2),
            "distance": safe(3),
            "baba": safe(4),
            "rank": safe(5),
            "time": safe(7),
            "margin": safe(8),
            "pop": safe(9),
            "agari": safe(10),
            "passing": safe(11),
            "jockey": safe(12),
            "weight": safe(13),
            "body_weight": safe(14),
        })

    return past_runs

# 特徴量抽出
def extract_features(past_runs):
    try:
        ranks, pops, margins = [], [], []
        agari_list = []
        race_levels = []
        distance_fit_list = []
        baba_fit_list = []

        def get_race_level(name):
            if "G1" in name: return 6
            if "G2" in name: return 5
            if "G3" in name: return 4
            if "OP" in name: return 3
            if "3勝" in name: return 2
            if "2勝" in name: return 1
            return 0

        def parse_distance(s):
            try: return int(s.replace("m", "").strip())
            except: return None

        def parse_baba(s):
            if "良" in s: return "良"
            if "稍" in s: return "稍重"
            if "重" in s: return "重"
            if "不" in s: return "不良"
            return None

        last_distance = None
        last_baba = None

        if past_runs:
            last_distance = parse_distance(past_runs[0].get("distance", ""))
            last_baba = parse_baba(past_runs[0].get("baba", ""))

        for r in past_runs:
            try: ranks.append(int(r.get("rank", "")))
            except: pass
            try: pops.append(int(r.get("pop", "")))
            except: pass
            try: margins.append(float(r.get("margin", "")))
            except: pass

            try:
                agari = int(r.get("agari", ""))
                agari_list.append(agari)
            except:
                pass

            race_levels.append(get_race_level(r.get("race_name", "")))

            dist = parse_distance(r.get("distance", ""))
            if dist and last_distance:
                if dist > last_distance: distance_fit_list.append(1)
                elif dist < last_distance: distance_fit_list.append(-1)
                else: distance_fit_list.append(0)

            baba = parse_baba(r.get("baba", ""))
            if baba and last_baba:
                baba_fit_list.append(1 if baba == last_baba else 0)

        return {
            "avg_rank": sum(ranks)/len(ranks) if ranks else 99,
            "avg_pop": sum(pops)/len(pops) if pops else 99,
            "avg_margin": sum(margins)/len(margins) if margins else 9.9,
            "avg_agari": sum(agari_list)/len(agari_list) if agari_list else 99,
            "avg_race_level": sum(race_levels)/len(race_levels) if race_levels else 0,
            "distance_fit": sum(distance_fit_list) if distance_fit_list else 0,
            "baba_fit": sum(baba_fit_list) if baba_fit_list else 0
        }, None

    except Exception as e:
        return None, f"特徴量抽出エラー: {e}"


def calc_condition_score(f):
    score = 100
    score -= f["avg_rank"] * 2
    score -= f["avg_pop"] * 1.5
    score -= f["avg_margin"] * 5
    score -= f["avg_agari"] * 1.2
    score += f["avg_race_level"] * 3
    score += f["distance_fit"] * 5
    score += f["baba_fit"] * 4
    return max(0, min(100, round(score, 2)))


def fetch_pedigree_text(horse_id: str):
    try:
        url = f"https://db.netkeiba.com/horse/ped/{horse_id}/"
        html = requests.get(url, timeout=10).content
        soup = BeautifulSoup(html, "lxml")
        return soup.get_text(" ", strip=True), None
    except Exception as e:
        return None, f"血統取得エラー: {e}"


def generate_summary(client, context: str):
    try:
        prompt = f"""
あなたは競馬の専門アナリストです。
以下のデータ（過去走・特徴量・血統）を基に、
競走馬の「強み」「弱み」「適性」を200字以内で要約してください。

【出力フォーマット】
{{
  "strong": "...",
  "weak": "...",
  "suitability": "..."
}}

【解析対象データ】
{context}
"""

        res = client.chat.completions.create(
            model="keiba-gpt4omini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.4
        )

        return res.choices[0].message.content, None

    except Exception as e:
        return None, f"OpenAI 要約エラー: {e}"


def render_card(h, score, summary):
    return f"""
<div style="border:1px solid #ccc; padding:10px; margin:10px; border-radius:8px;">
  <h3>{h["horse_name"]}（{h.get("jockey", "")}）</h3>
  <p><b>枠番:</b> {h.get("waku", "")} / <b>馬番:</b> {h.get("umaban", "")}</p>
  <p><b>調子スコア:</b> {score}</p>
  <p>{summary}</p>
</div>
"""


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

@app.route(route="process_past")
def process_past(req: func.HttpRequest) -> func.HttpResponse:

    url = req.params.get("url")
    if not url:
        return func.HttpResponse("url パラメータが必要です", status_code=400)

    race_id = extract_race_id(url)

    # 出馬表取得
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        html = requests.get(url, headers=headers, timeout=10).content
        table = extract_shutuba_table_with_links(html)
        if table is None:
            return func.HttpResponse("出馬表テーブルが見つかりませんでした", status_code=500)
        horses = parse_shutuba_table_with_links(table)
    except Exception as e:
        return func.HttpResponse(f"出馬表取得エラー: {e}", status_code=500)

    # OpenAI クライアント
    client, err = get_openai_client()
    if err:
        return func.HttpResponse(err, status_code=500)

    result_html = ""

    # 各馬処理
    for h in horses:
        horse_id = h["horse_id"]

        # Ajax 過去走取得
        past_html, err = fetch_past_runs_html(horse_id)
        if err:
            result_html += render_card(h, 0, err)
            continue

        past_table = extract_past_table_from_ajax(past_html)
        if past_table is None:
            result_html += render_card(h, 0, "過去走テーブルなし")
            continue

        # ---------------------------------------------------------
        # ① 調子スコア用（詳細データ）
        # ---------------------------------------------------------
        past_runs_condition = parse_past_5runs_for_condition(past_table)
        if not past_runs_condition:
            result_html += render_card(h, 0, "過去走データなし")
            continue

        features, err = extract_features(past_runs_condition)
        if err:
            result_html += render_card(h, 0, err)
            continue

        score = calc_condition_score(features)

        # ---------------------------------------------------------
        # ② AI要約用（軽量データ）
        # ---------------------------------------------------------
        past_runs_summary = parse_past_5runs(past_table)

        pedigree, err = fetch_pedigree_text(horse_id)
        if err:
            result_html += render_card(h, score, err)
            continue

        # LLM に渡すコンテキスト
        context = json.dumps(
            {
                "horse": h,
                "past_runs": past_runs_summary,   # ← 軽量版を渡す
                "features": features,
                "pedigree": pedigree,
            },
            ensure_ascii=False,
        )

        summary, err = generate_summary(client, context)
        if err:
            result_html += render_card(h, score, err)
            continue

        result_html += render_card(h, score, summary)

    full_html = wrap_html(race_id, result_html)
    return func.HttpResponse(full_html, mimetype="text/html")

