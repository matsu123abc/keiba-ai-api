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
