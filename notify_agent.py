from __future__ import annotations

import logging
import os
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()

APP_NAME = "office-notify-agent"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(APP_NAME)

app = FastAPI(title=APP_NAME)


@app.post("/speak")
async def speak(request: Request):
    data: Dict[str, Any] = await request.json()
    logger.info("Notify payload: %s", data)

    payload = data.get("payload", {}) or {}
    message = payload.get("message") or data.get("message") or ""

    print("\n=== OFFICE NOTIFY ===")
    print(f"target: {data.get('target')}")
    print(f"message: {message}")
    print("=====================\n")

    return JSONResponse(
        {
            "ok": True,
            "received": True,
            "message": message,
            "target": data.get("target"),
        }
    )


@app.get("/health")
async def health():
    return {"ok": True, "service": APP_NAME}