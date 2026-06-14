import asyncio
import json
import os
import time

import httpx
import websockets
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
KICK_CHANNEL = os.getenv("KICK_CHANNEL", "tutomanx")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "cambiar123")
APP_URL = os.getenv("APP_URL", "")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

obs_connections: set[WebSocket] = set()
cooldowns: dict[str, float] = {}


async def get_chatroom_id(channel: str) -> int:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://kick.com/api/v2/channels/{channel}", headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()["chatroom"]["id"]


async def broadcast_obs(payload: dict):
    dead = set()
    for ws in obs_connections:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    obs_connections.difference_update(dead)


async def handle_command(content: str):
    content = content.strip().lower()
    if not content.startswith("!"):
        return

    # Special command: show sounds list
    if content == "!sonidos":
        result = supabase.table("sounds").select("command").eq("active", True).order("command").execute()
        commands = [s["command"] for s in result.data]
        await broadcast_obs({"type": "sonidos", "commands": commands})
        return

    result = supabase.table("sounds").select("*").eq("active", True).execute()
    for sound in result.data:
        if content == sound["command"].lower():
            last = cooldowns.get(sound["command"], 0)
            if time.time() - last >= sound["cooldown"]:
                cooldowns[sound["command"]] = time.time()
                await broadcast_obs({"type": "play", "url": sound["audio_url"], "command": sound["command"]})
            break


async def kick_bot():
    pusher_url = "wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c?protocol=7&client=js&version=7.6.0&flash=false"
    while True:
        try:
            print(f"[Bot] Conectando al chat de {KICK_CHANNEL}...")
            chatroom_id = await get_chatroom_id(KICK_CHANNEL)
            print(f"[Bot] Chatroom ID: {chatroom_id}")

            async with websockets.connect(pusher_url) as ws:
                await ws.send(json.dumps({
                    "event": "pusher:subscribe",
                    "data": {"auth": "", "channel": f"chatrooms.{chatroom_id}.v2"}
                }))
                print(f"[Bot] Escuchando chat...")

                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("event") == "pusher:ping":
                        await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                    elif msg.get("event") == "App\\Events\\ChatMessageEvent":
                        data = json.loads(msg["data"])
                        content = data.get("content", "")
                        asyncio.create_task(handle_command(content))

        except Exception as e:
            print(f"[Bot] Error: {e} — reconectando en 5s...")
            await asyncio.sleep(5)


async def keep_alive():
    await asyncio.sleep(120)
    while APP_URL:
        try:
            async with httpx.AsyncClient() as client:
                await client.get(f"{APP_URL}/health", timeout=5)
        except Exception:
            pass
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(kick_bot())
    asyncio.create_task(keep_alive())
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def admin_page():
    with open("static/admin.html", encoding="utf-8") as f:
        return f.read()


@app.get("/obs", response_class=HTMLResponse)
async def obs_page():
    with open("static/obs.html", encoding="utf-8") as f:
        return f.read()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    obs_connections.add(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, Exception):
        obs_connections.discard(websocket)


# ── API ──────────────────────────────────────────────────────────────────────

def auth(password: str):
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")


@app.get("/api/sounds")
async def list_sounds():
    result = supabase.table("sounds").select("*").order("command").execute()
    return result.data


@app.post("/api/sounds")
async def create_sound(
    command: str = Form(...),
    cooldown: int = Form(10),
    password: str = Form(...),
    file: UploadFile = File(...),
):
    auth(password)
    command = command.strip().lower()
    if not command.startswith("!"):
        command = "!" + command

    file_bytes = await file.read()
    ext = file.filename.rsplit(".", 1)[-1]
    filename = f"{command[1:]}_{int(time.time())}.{ext}"

    supabase.storage.from_("audios").upload(
        filename, file_bytes, {"content-type": file.content_type or "audio/mpeg"}
    )
    audio_url = supabase.storage.from_("audios").get_public_url(filename)

    existing = supabase.table("sounds").select("id").eq("command", command).execute()
    if existing.data:
        result = supabase.table("sounds").update({
            "filename": file.filename, "audio_url": audio_url, "cooldown": cooldown, "active": True
        }).eq("command", command).execute()
    else:
        result = supabase.table("sounds").insert({
            "command": command, "filename": file.filename,
            "audio_url": audio_url, "cooldown": cooldown, "active": True
        }).execute()

    return result.data[0]


@app.put("/api/sounds/{sound_id}")
async def update_sound(sound_id: int, request: Request):
    body = await request.json()
    auth(body.pop("password", ""))
    result = supabase.table("sounds").update(body).eq("id", sound_id).execute()
    return result.data[0]


@app.delete("/api/sounds/{sound_id}")
async def delete_sound(sound_id: int, password: str):
    auth(password)
    # Get filename to delete from storage
    row = supabase.table("sounds").select("audio_url").eq("id", sound_id).execute()
    if row.data:
        url = row.data[0]["audio_url"]
        filename = url.split("/")[-1]
        try:
            supabase.storage.from_("audios").remove([filename])
        except Exception:
            pass
    supabase.table("sounds").delete().eq("id", sound_id).execute()
    return {"ok": True}


@app.post("/api/test/{sound_id}")
async def test_sound(sound_id: int, request: Request):
    body = await request.json()
    auth(body.get("password", ""))
    row = supabase.table("sounds").select("*").eq("id", sound_id).execute()
    if not row.data:
        raise HTTPException(status_code=404)
    sound = row.data[0]
    await broadcast_obs({"type": "play", "url": sound["audio_url"], "command": sound["command"]})
    return {"ok": True}
