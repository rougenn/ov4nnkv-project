"""A2A Demo Inspector — мини-приложение для отправки запросов в A2A-агента."""
import asyncio
import os
from datetime import datetime
from uuid import uuid4

import httpx
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BASE_URL = os.getenv("AGENT_BASE_URL", "http://localhost:10000")

# Опциональная Bearer-авторизация. Если AGENT_AUTH_TOKEN задан — будет
# добавляться в Authorization-заголовок. Если IAM_URL+IAM_KEY_ID+IAM_SECRET
# заданы — токен запрашивается через указанный IAM-эндпоинт. Если ничего
# не задано, запросы идут без авторизации (локальный режим).
AGENT_AUTH_TOKEN = os.getenv("AGENT_AUTH_TOKEN")
IAM_URL = os.getenv("IAM_URL")
IAM_KEY_ID = os.getenv("IAM_KEY_ID")
IAM_SECRET = os.getenv("IAM_SECRET")


async def get_access_token() -> str | None:
    """Получить access_token, если настроена IAM-авторизация."""
    if AGENT_AUTH_TOKEN:
        return AGENT_AUTH_TOKEN
    if not (IAM_URL and IAM_KEY_ID and IAM_SECRET):
        return None
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(IAM_URL, json={"keyId": IAM_KEY_ID, "secret": IAM_SECRET})
        response.raise_for_status()
        return response.json()["access_token"]


def _auth_headers(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


async def get_agent_card(token: str | None) -> dict:
    """Получить agent card по A2A discovery эндпоинту."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            f"{BASE_URL}/.well-known/agent.json", headers=_auth_headers(token)
        )
        response.raise_for_status()
        return response.json()


async def send_a2a_message(token: str | None, message: str) -> dict:
    """Отправить сообщение A2A-агенту и получить ответ."""
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
                "messageId": uuid4().hex,
            }
        },
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(5 * 60.0)) as client:
        headers = {"Content-Type": "application/json", **_auth_headers(token)}
        response = await client.post(BASE_URL, json=payload, headers=headers)
        response.raise_for_status()
        return {
            "request": payload,
            "response": response.json(),
            "timestamp": datetime.now().isoformat(),
        }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/agent-card", methods=["GET"])
def api_agent_card():
    try:
        token = asyncio.run(get_access_token())
        card = asyncio.run(get_agent_card(token))
        return jsonify({"success": True, "data": card})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/send", methods=["POST"])
def api_send():
    try:
        data = request.json or {}
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"success": False, "error": "Message is required"}), 400

        token = asyncio.run(get_access_token())
        result = asyncio.run(send_a2a_message(token, message))
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_RUN_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 5000)),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
