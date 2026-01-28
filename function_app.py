import azure.functions as func
import logging
import json

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="keiba_scraper")
def keiba_scraper(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )
    
@app.route(route="shutuba", auth_level=func.AuthLevel.ANONYMOUS)
def shutuba(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("shutuba function triggered")

    try:
        race_id = req.params.get("raceId")
        if not race_id:
            try:
                body = req.get_json()
                race_id = body.get("raceId") if body else None
            except:
                race_id = None

        if not race_id:
            return func.HttpResponse(
                json.dumps({"error": "raceId is required"}, ensure_ascii=False),
                mimetype="application/json",
                status_code=400
            )

        dummy_data = {
            "202606010701": ["ミライスター", "サクラブレイブ", "ゴールドフラッシュ"],
            "2026010101": ["アカネノヒカリ", "シンカイリュウ"]
        }

        horses = dummy_data.get(race_id, [])

        return func.HttpResponse(
            json.dumps(horses, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"shutuba error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500
        )

@app.route(route="past_runs", auth_level=func.AuthLevel.ANONYMOUS)
def past_runs(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("past_runs function triggered")

    try:
        horse_name = req.params.get("horseName")
        if not horse_name:
            try:
                body = req.get_json()
                horse_name = body.get("horseName") if body else None
            except:
                horse_name = None

        if not horse_name:
            return func.HttpResponse(
                json.dumps({"error": "horseName is required"}, ensure_ascii=False),
                mimetype="application/json",
                status_code=400
            )

        # 仮の過去走データ（後でスクレイピングやDBに置き換え可能）
        dummy_data = {
            "ミライスター": [
                {"date": "2025-12-01", "rank": 1, "distance": 1800},
                {"date": "2025-11-10", "rank": 3, "distance": 1600}
            ],
            "サクラブレイブ": [
                {"date": "2025-12-05", "rank": 5, "distance": 2000}
            ]
        }

        runs = dummy_data.get(horse_name, [])

        return func.HttpResponse(
            json.dumps(runs, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"past_runs error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500
        )

@app.route(route="training", auth_level=func.AuthLevel.ANONYMOUS)
def training(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("training function triggered")

    try:
        horse_name = req.params.get("horseName")
        if not horse_name:
            try:
                body = req.get_json()
                horse_name = body.get("horseName") if body else None
            except:
                horse_name = None

        if not horse_name:
            return func.HttpResponse(
                json.dumps({"error": "horseName is required"}, ensure_ascii=False),
                mimetype="application/json",
                status_code=400
            )

        # 仮の調教データ（後でスクレイピングやDBに置き換え可能）
        dummy_data = {
            "ミライスター": {"date": "2026-01-20", "time": "65.2", "comment": "良好な動き"},
            "サクラブレイブ": {"date": "2026-01-18", "time": "66.8", "comment": "やや重い"}
        }

        training_info = dummy_data.get(horse_name, {})

        return func.HttpResponse(
            json.dumps(training_info, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"training error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500
        )

@app.route(route="scoring", auth_level=func.AuthLevel.ANONYMOUS)
def scoring(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("scoring function triggered")

    try:
        horse_name = req.params.get("horseName")
        if not horse_name:
            try:
                body = req.get_json()
                horse_name = body.get("horseName") if body else None
            except:
                horse_name = None

        if not horse_name:
            return func.HttpResponse(
                json.dumps({"error": "horseName is required"}, ensure_ascii=False),
                mimetype="application/json",
                status_code=400
            )

        # 仮の過去走データ（順位リスト）
        past_runs_data = {
            "ミライスター": [1, 3],
            "サクラブレイブ": [5],
            "ゴールドフラッシュ": [2, 4, 6]
        }

        # 仮の調教データ（タイム）
        training_data = {
            "ミライスター": 65.2,
            "サクラブレイブ": 66.8,
            "ゴールドフラッシュ": 64.5
        }

        runs = past_runs_data.get(horse_name, [])
        training_time = training_data.get(horse_name, 70.0)

        # スコア計算（例：平均順位 × 調教タイム ÷ 100）
        avg_rank = sum(runs) / len(runs) if runs else 5
        score = round((avg_rank * training_time) / 100, 2)

        return func.HttpResponse(
            json.dumps({"horseName": horse_name, "score": score}, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"scoring error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500
        )

@app.route(route="ranking", auth_level=func.AuthLevel.ANONYMOUS)
def ranking(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("ranking function triggered")

    try:
        race_id = req.params.get("raceId")
        if not race_id:
            try:
                body = req.get_json()
                race_id = body.get("raceId") if body else None
            except:
                race_id = None

        if not race_id:
            return func.HttpResponse(
                json.dumps({"error": "raceId is required"}, ensure_ascii=False),
                mimetype="application/json",
                status_code=400
            )

        # shutuba と同じ仮データ
        shutuba_data = {
            "202606010701": ["ミライスター", "サクラブレイブ", "ゴールドフラッシュ"],
            "2026010101": ["アカネノヒカリ", "シンカイリュウ"]
        }

        horses = shutuba_data.get(race_id, [])

        # scoring API と同じ仮データ
        past_runs_data = {
            "ミライスター": [1, 3],
            "サクラブレイブ": [5],
            "ゴールドフラッシュ": [2, 4, 6],
            "アカネノヒカリ": [3, 2],
            "シンカイリュウ": [7]
        }

        training_data = {
            "ミライスター": 65.2,
            "サクラブレイブ": 66.8,
            "ゴールドフラッシュ": 64.5,
            "アカネノヒカリ": 67.1,
            "シンカイリュウ": 70.5
        }

        ranking_list = []

        for horse in horses:
            runs = past_runs_data.get(horse, [])
            training_time = training_data.get(horse, 70.0)

            avg_rank = sum(runs) / len(runs) if runs else 5
            score = round((avg_rank * training_time) / 100, 2)

            ranking_list.append({
                "horseName": horse,
                "score": score
            })

        # スコアの低い順に並べる（好調順）
        ranking_list.sort(key=lambda x: x["score"])

        return func.HttpResponse(
            json.dumps(ranking_list, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"ranking error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500
        )
