import json
import logging
import os
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
FALLBACK_TEXT = os.getenv(
    "ALICE_FALLBACK_TEXT",
    "Извините, произошла ошибка. Повторите запрос, пожалуйста.",
)

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("alice-skill")

app = FastAPI(title="alice-skill", version="1.0.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("incoming request method=%s path=%s", request.method, request.url.path)
    response = await call_next(request)
    logger.info(
        "completed request method=%s path=%s status=%s",
        request.method,
        request.url.path,
        response.status_code,
    )
    return response


def alice_response(text: str, end_session: bool = False) -> Dict[str, Any]:
    return {
        "response": {
            "text": text,
            "end_session": end_session,
        },
        "version": "1.0",
    }


def extract_user_text(payload: Dict[str, Any]) -> str:
    request_data = payload.get("request")
    if not isinstance(request_data, dict):
        return ""

    original = request_data.get("original_utterance")
    command = request_data.get("command")

    text = original if isinstance(original, str) and original.strip() else command
    if not isinstance(text, str):
        return ""
    return text.strip()


def is_new_session(payload: Dict[str, Any]) -> bool:
    session_data = payload.get("session")
    if not isinstance(session_data, dict):
        return False
    return bool(session_data.get("new", False))


def build_skill_text(user_text: str, new_session: bool) -> str:
    if new_session:
        return (
            "Привет. Я backend навыка Алисы. "
            "Скажите команду, и я обработаю ее через webhook."
        )

    if not user_text:
        return "Я не расслышала команду. Повторите, пожалуйста."

    normalized = user_text.lower()
    if "помощ" in normalized or "help" in normalized:
        return "Скажите любую команду. Я верну подтверждение и текст запроса."

    return f"Принято: {user_text}"


@app.post("/alice")
async def alice_webhook(request: Request) -> JSONResponse:
    try:
        raw_body = await request.body()
        body_preview = raw_body.decode("utf-8", errors="replace")
        if len(body_preview) > 3000:
            body_preview = f"{body_preview[:3000]}...<truncated>"
        logger.info("incoming /alice request body=%s", body_preview)

        try:
            payload: Any = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError:
            logger.warning("invalid JSON body on /alice")
            return JSONResponse(alice_response("Некорректный JSON в запросе."))

        if not isinstance(payload, dict):
            logger.warning("payload is not an object: %s", type(payload).__name__)
            return JSONResponse(alice_response("Некорректный формат запроса."))

        user_text = extract_user_text(payload)
        new_session = is_new_session(payload)
        session_id = ""
        session_data = payload.get("session")
        if isinstance(session_data, dict):
            raw_session_id = session_data.get("session_id")
            if isinstance(raw_session_id, str):
                session_id = raw_session_id

        logger.info(
            "parsed alice request session_id=%s new_session=%s user_text=%r",
            session_id or "<empty>",
            new_session,
            user_text,
        )

        reply_text = build_skill_text(user_text, new_session)
        return JSONResponse(alice_response(reply_text))
    except Exception:
        logger.exception("unhandled error in /alice")
        return JSONResponse(alice_response(FALLBACK_TEXT))


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "service": "alice-skill"}
