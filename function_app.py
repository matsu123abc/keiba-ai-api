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

@app.route(route="process_past")
def process_past(req: func.HttpRequest) -> func.HttpResponse:
    # URL パラメータ取得
    url = req.params.get("url")

    # race_id 抽出（URL がある場合のみ）
    race_id = extract_race_id(url) if url else None

    # HTML 取得テスト（URL がある場合のみ）
    html_status = "未実行"
    if url:
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            html_status = f"成功（{len(res.content)} bytes）"
        except Exception as e:
            html_status = f"エラー: {e}"

    # 結果を返す
    body = f"""
    <html>
    <head><meta charset="UTF-8"></head>
    <body>
        <h2>process_past デバッグ版（ステップ1＋2）</h2>
        <p><b>URL:</b> {url}</p>
        <p><b>race_id:</b> {race_id}</p>
        <p><b>HTML取得:</b> {html_status}</p>
    </body>
    </html>
    """

    return func.HttpResponse(body, mimetype="text/html")
