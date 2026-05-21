from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()

APP_NAME = "alice-office-skill"
DB_PATH = os.getenv("DB_PATH", "office_calls.db")
OFFICE_NOTIFY_API_URL = os.getenv("OFFICE_NOTIFY_API_URL", "").strip()
OFFICE_NOTIFY_API_KEY = os.getenv("OFFICE_NOTIFY_API_KEY", "").strip()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(APP_NAME)

app = FastAPI(title=APP_NAME)


# -----------------------------
# Database
# -----------------------------
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                aliases TEXT NOT NULL,
                notify_target TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                aliases TEXT NOT NULL,
                room_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                caller_text TEXT NOT NULL,
                employee_id INTEGER,
                room_id INTEGER,
                status TEXT NOT NULL,
                dispatch_result TEXT,
                FOREIGN KEY(employee_id) REFERENCES employees(id),
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            )
            """
        )

        rooms_count = cur.execute("SELECT COUNT(*) AS c FROM rooms").fetchone()["c"]
        if rooms_count == 0:
            rooms = [
                ("Бухгалтерия", "бухгалтерия,бухгалтерии,в бухгалтерию"),
                ("Продажи", "продажи,отдел продаж,в продажи"),
                ("Директор", "директор,кабинет директора,у директора"),
                ("Ресепшен", "ресепшен,приемная,на ресепшен"),
            ]
            cur.executemany(
                "INSERT INTO rooms(name, aliases, notify_target) VALUES(?,?,?)",
                [(name, aliases, f"room:{name.lower()}") for name, aliases in rooms],
            )

        employees_count = cur.execute("SELECT COUNT(*) AS c FROM employees").fetchone()["c"]
        if employees_count == 0:
            rooms_map = {
                row["name"]: row["id"]
                for row in cur.execute("SELECT id, name FROM rooms").fetchall()
            }
            employees = [
                ("Иван", "иван,ивана", rooms_map["Бухгалтерия"]),
                ("Анна", "анна,анну,анне", rooms_map["Продажи"]),
                ("Сергей", "сергей,сергея", rooms_map["Директор"]),
                ("Мария", "мария,марию", rooms_map["Ресепшен"]),
            ]
            cur.executemany(
                "INSERT INTO employees(name, aliases, room_id) VALUES(?,?,?)",
                employees,
            )

        conn.commit()


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("Database initialized")


# -----------------------------
# Helpers
# -----------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s\-]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_aliases(raw: str) -> List[str]:
    return [a.strip() for a in raw.split(",") if a.strip()]


def matches_alias(text: str, alias: str) -> bool:
    text_n = normalize(text)
    alias_n = normalize(alias)
    if not text_n or not alias_n:
        return False
    pattern = rf"(?<!\w){re.escape(alias_n)}(?!\w)"
    return re.search(pattern, text_n) is not None


def find_by_alias(text: str, table: str) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()

    for row in rows:
        for alias in split_aliases(row["aliases"]):
            if matches_alias(text, alias):
                return row
    return None


def detect_action(text: str) -> str:
    t = normalize(text)
    if any(word in t for word in ["позови", "вызови", "пригласи", "попроси подойти", "сообщи", "передай"]):
        return "call"
    if any(word in t for word in ["где", "кто", "в каком кабинете", "кто сейчас", "найди"]):
        return "find"
    if any(word in t for word in ["помощь", "что ты умеешь", "команды", "help"]):
        return "help"
    return "unknown"


def save_call(
    caller_text: str,
    employee_id: Optional[int],
    room_id: Optional[int],
    status: str,
    dispatch_result: str,
) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO calls(created_at, caller_text, employee_id, room_id, status, dispatch_result)
            VALUES(?,?,?,?,?,?)
            """,
            (now_iso(), caller_text, employee_id, room_id, status, dispatch_result),
        )
        conn.commit()
        return cur.lastrowid


def serialize_session(session: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("session_id", "message_id", "user_id")
    return {k: session[k] for k in keys if k in session}


def build_response(
    text: str,
    tts: Optional[str] = None,
    buttons: Optional[List[Dict[str, Any]]] = None,
    end_session: bool = False,
    session: Optional[Dict[str, Any]] = None,
    application_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "response": {
            "text": text[:1024],
            "tts": (tts or text)[:1024],
            "end_session": end_session,
        },
        "version": "1.0",
    }

    if buttons:
        response["response"]["buttons"] = buttons

    if session:
        response["session"] = serialize_session(session)

    if application_state is not None:
        response["application_state"] = application_state

    return response


def notify_office(room_notify_target: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Локально/в проде сюда подставляется ваш агент уведомлений.
    Для проверки в docker-compose это будет notify_agent.py.
    """
    if not OFFICE_NOTIFY_API_URL:
        logger.info("Dry-run notify: %s", payload)
        return {"ok": False, "mode": "dry_run", "message": "OFFICE_NOTIFY_API_URL not set"}

    headers = {"Content-Type": "application/json"}
    if OFFICE_NOTIFY_API_KEY:
        headers["Authorization"] = f"Bearer {OFFICE_NOTIFY_API_KEY}"

    body = {
        "target": room_notify_target,
        "payload": payload,
    }

    logger.info("Sending notify request to %s", OFFICE_NOTIFY_API_URL)
    resp = requests.post(OFFICE_NOTIFY_API_URL, json=body, headers=headers, timeout=10)
    resp.raise_for_status()

    try:
        return resp.json()
    except Exception:
        return {"ok": True, "raw": resp.text}


# -----------------------------
# Core logic
# -----------------------------
def handle_alice_request(data: Dict[str, Any]) -> Dict[str, Any]:
    session = data.get("session", {}) or {}
    request_data = data.get("request", {}) or {}

    user_text = (
        request_data.get("original_utterance")
        or request_data.get("command")
        or ""
    ).strip()

    if not user_text and session.get("new"):
        return build_response(
            text="Здравствуйте. Скажите, кого и куда нужно позвать.",
            buttons=[
                {"title": "Позвать сотрудника", "hide": True},
                {"title": "Помощь", "hide": True},
            ],
            session=session,
        )

    if session.get("new"):
        return build_response(
            text="Здравствуйте. Скажите, кого и куда нужно позвать.",
            tts="Здравствуйте. Скажите, кого и куда нужно позвать.",
            buttons=[
                {"title": "Позвать сотрудника", "hide": True},
                {"title": "Помощь", "hide": True},
            ],
            session=session,
        )

    action = detect_action(user_text)

    if action == "help":
        return build_response(
            text=(
                "Скажите, например: позови Ивана в бухгалтерию. "
                "Или: где сейчас Анна."
            ),
            tts=(
                "Скажите, например: позови Ивана в бухгалтерию. "
                "Или: где сейчас Анна."
            ),
            buttons=[
                {"title": "Позвать сотрудника", "hide": True},
                {"title": "Показать команды", "hide": True},
            ],
            session=session,
        )

    with get_db() as conn:
        employee = find_by_alias(user_text, "employees")
        room = find_by_alias(user_text, "rooms")

        if action == "find":
            if employee is None:
                return build_response(
                    text="Не нашел сотрудника. Назовите имя еще раз.",
                    tts="Не нашёл сотрудника. Назовите имя ещё раз.",
                    buttons=[{"title": "Помощь", "hide": True}],
                    session=session,
                )

            room_name = "не привязан к кабинету"
            if employee["room_id"]:
                row = conn.execute("SELECT name FROM rooms WHERE id = ?", (employee["room_id"],)).fetchone()
                if row:
                    room_name = row["name"]

            msg = f"{employee['name']} сейчас: {room_name}."
            return build_response(
                text=msg,
                tts=msg,
                buttons=[
                    {"title": "Позвать этого сотрудника", "hide": True},
                    {"title": "Помощь", "hide": True},
                ],
                session=session,
            )

        if action == "call":
            if employee is None:
                return build_response(
                    text="Кого позвать? Назовите имя сотрудника.",
                    tts="Кого позвать? Назовите имя сотрудника.",
                    buttons=[{"title": "Помощь", "hide": True}],
                    session=session,
                )

            target_room = room
            if target_room is None and employee["room_id"]:
                target_room = conn.execute(
                    "SELECT * FROM rooms WHERE id = ?",
                    (employee["room_id"],),
                ).fetchone()

            if target_room is None:
                return build_response(
                    text=f"У сотрудника {employee['name']} не указан кабинет. Сначала привяжите его к кабинету.",
                    tts=f"У сотрудника {employee['name']} не указан кабинет. Сначала привяжите его к кабинету.",
                    buttons=[{"title": "Помощь", "hide": True}],
                    session=session,
                )

            notify_text = f"{employee['name']}, вас зовет босс. Подойдите, пожалуйста."
            payload = {
                "employee": employee["name"],
                "room": target_room["name"],
                "message": notify_text,
                "source": "alice_skill",
                "caller_text": user_text,
                "ts": now_iso(),
            }

            try:
                dispatch_result = notify_office(target_room["notify_target"], payload)
                save_call(
                    caller_text=user_text,
                    employee_id=employee["id"],
                    room_id=target_room["id"],
                    status="sent",
                    dispatch_result=json.dumps(dispatch_result, ensure_ascii=False),
                )
                reply = f"Запрос принят. Я позову {employee['name']} в {target_room['name']}."
                return build_response(
                    text=reply,
                    tts=reply,
                    buttons=[
                        {"title": "Позвать еще", "hide": True},
                        {"title": "Статус", "hide": True},
                    ],
                    session=session,
                    application_state={
                        "last_action": "call",
                        "employee": employee["name"],
                        "room": target_room["name"],
                    },
                )
            except Exception as exc:
                logger.exception("Notify failed: %s", exc)
                save_call(
                    caller_text=user_text,
                    employee_id=employee["id"],
                    room_id=target_room["id"],
                    status="error",
                    dispatch_result=str(exc),
                )
                return build_response(
                    text="Не смог отправить уведомление. Проверьте notify API.",
                    tts="Не смог отправить уведомление. Проверьте notify API.",
                    buttons=[{"title": "Помощь", "hide": True}],
                    session=session,
                )

    return build_response(
        text="Я не понял команду. Скажите, например: позови Ивана в бухгалтерию.",
        tts="Я не понял команду. Скажите, например: позови Ивана в бухгалтерию.",
        buttons=[
            {"title": "Помощь", "hide": True},
            {"title": "Позвать сотрудника", "hide": True},
        ],
        session=session,
    )


# -----------------------------
# Routes
# -----------------------------
@app.post("/alice")
async def alice_webhook(request: Request):
    try:
        data = await request.json()
        logger.info("Incoming Alice request: %s", json.dumps(data, ensure_ascii=False))
    except Exception:
        logger.exception("Bad JSON in request")
        return JSONResponse(
            build_response(
                text="Ошибка запроса. Попробуйте еще раз.",
                tts="Ошибка запроса. Попробуйте ещё раз.",
            ),
            status_code=400,
        )

    try:
        result = handle_alice_request(data)
        return JSONResponse(result)
    except Exception:
        logger.exception("Unhandled skill error")
        return JSONResponse(
            build_response(
                text="Внутренняя ошибка навыка. Попробуйте еще раз.",
                tts="Внутренняя ошибка навыка. Попробуйте ещё раз.",
            ),
            status_code=200,
        )


@app.get("/health")
async def health():
    return {"ok": True, "service": APP_NAME}