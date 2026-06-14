import asyncio
import json
import os
import time

import httpx
import websockets
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
KICK_CHANNEL = os.getenv("KICK_CHANNEL", "tutomanx")
KICK_CHATROOM_ID = os.getenv("KICK_CHATROOM_ID", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "cambiar123")
MOD_PASSWORD = os.getenv("MOD_PASSWORD", "mod123")
APP_URL = os.getenv("APP_URL", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Faltan variables de entorno: SUPABASE_URL y SUPABASE_SERVICE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

obs_connections: set[WebSocket] = set()
cooldowns: dict[str, float] = {}
user_cooldowns: dict[str, float] = {}
USER_COOLDOWN = 60


def get_role(password: str) -> str | None:
    if password == ADMIN_PASSWORD:
        return "admin"
    if password == MOD_PASSWORD:
        return "mod"
    return None


def require_role(password: str, min_role: str = "mod") -> str:
    role = get_role(password)
    if role is None:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    if min_role == "admin" and role != "admin":
        raise HTTPException(status_code=403, detail="Solo el admin puede hacer esto")
    return role


async def get_chatroom_id(channel: str) -> int:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://kick.com/",
        "Origin": "https://kick.com",
    }
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for url in [
            f"https://kick.com/api/v2/channels/{channel}",
            f"https://kick.com/api/v1/channels/{channel}",
        ]:
            try:
                r = await client.get(url, headers=headers, timeout=15)
                if r.status_code == 200:
                    return r.json()["chatroom"]["id"]
            except Exception:
                continue
    raise RuntimeError(f"No se pudo obtener chatroom ID para {channel}")


async def broadcast_obs(payload: dict):
    dead = set()
    for ws in obs_connections:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    obs_connections.difference_update(dead)


async def handle_command(content: str, sender: dict):
    content = content.strip().lower()
    if not content.startswith("!"):
        return

    username = sender.get("slug") or sender.get("username") or "anon"
    badges = {b.get("type", "").lower() for b in (sender.get("identity") or {}).get("badges", [])}
    is_broadcaster = "broadcaster" in badges
    is_mod = "moderator" in badges
    is_vip = "vip" in badges
    is_sub = (sender.get("subscribed_for") or 0) > 0 or "subscriber" in badges
    is_privileged = is_broadcaster or is_mod

    if content == "!sonidos":
        last = cooldowns.get("!sonidos", 0)
        if time.time() - last < 20:
            return
        cooldowns["!sonidos"] = time.time()
        result = supabase.table("sounds").select("command").eq("active", True).order("command").execute()
        commands = [s["command"] for s in result.data]
        await broadcast_obs({"type": "sonidos", "commands": commands})
        return

    # Cooldown global por usuario (60 segundos entre cualquier sonido)
    last_user = user_cooldowns.get(username, 0)
    if time.time() - last_user < USER_COOLDOWN:
        return

    result = supabase.table("sounds").select("*").eq("active", True).execute()
    for sound in result.data:
        if content == sound["command"].lower():
            # Broadcaster y mods pasan siempre
            if not is_privileged:
                if sound.get("vips_only") and not is_vip:
                    return
                if sound.get("subs_only") and not is_sub and not is_vip:
                    return
            last = cooldowns.get(sound["command"], 0)
            if time.time() - last >= sound["cooldown"]:
                cooldowns[sound["command"]] = time.time()
                user_cooldowns[username] = time.time()
                filename = sound["audio_url"].split("/")[-1]
                proxy_url = f"{APP_URL}/audio/{filename}" if APP_URL else sound["audio_url"]
                await broadcast_obs({
                    "type": "play",
                    "url": proxy_url,
                    "command": sound["command"],
                    "volume": sound.get("volume", 80)
                })
            break


async def kick_bot():
    pusher_url = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=7.6.0&flash=false"
    while True:
        try:
            print(f"[Bot] Conectando al chat de {KICK_CHANNEL}...")
            chatroom_id = int(KICK_CHATROOM_ID) if KICK_CHATROOM_ID else await get_chatroom_id(KICK_CHANNEL)
            print(f"[Bot] Chatroom ID: {chatroom_id}")

            async with websockets.connect(pusher_url) as ws:
                await ws.send(json.dumps({
                    "event": "pusher:subscribe",
                    "data": {"auth": "", "channel": f"chatrooms.{chatroom_id}.v2"}
                }))
                print("[Bot] Escuchando chat...")

                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("event") == "pusher:ping":
                        await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                    elif msg.get("event") == "App\\Events\\ChatMessageEvent":
                        data = json.loads(msg["data"])
                        asyncio.create_task(handle_command(data.get("content", ""), data.get("sender", {})))

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

@app.post("/api/auth")
async def auth_endpoint(request: Request):
    body = await request.json()
    role = get_role(body.get("password", ""))
    if not role:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    return {"role": role}


@app.get("/api/sounds")
async def list_sounds():
    result = supabase.table("sounds").select("*").order("command").execute()
    return result.data


@app.post("/api/sounds")
async def create_sound(
    command: str = Form(...),
    cooldown: int = Form(10),
    volume: int = Form(80),
    subs_only: int = Form(0),
    vips_only: int = Form(0),
    password: str = Form(...),
    file: UploadFile = File(...),
):
    require_role(password, "mod")

    command = command.strip().lower()
    if not command.startswith("!"):
        command = "!" + command

    if len(command) < 2:
        raise HTTPException(status_code=400, detail="El comando es demasiado corto")

    allowed_ext = {"mp3", "wav", "ogg", "m4a"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail="Formato no permitido. Usa mp3, wav u ogg")

    volume = max(0, min(100, volume))
    cooldown = max(0, min(300, cooldown))

    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo no puede superar 20 MB")

    filename = f"{command[1:]}_{int(time.time())}.{ext}"
    supabase.storage.from_("audios").upload(
        filename, file_bytes, {"content-type": file.content_type or "audio/mpeg"}
    )
    audio_url = supabase.storage.from_("audios").get_public_url(filename)

    existing = supabase.table("sounds").select("id").eq("command", command).execute()
    if existing.data:
        result = supabase.table("sounds").update({
            "filename": file.filename, "audio_url": audio_url,
            "cooldown": cooldown, "volume": volume, "active": True,
            "subs_only": bool(subs_only), "vips_only": bool(vips_only)
        }).eq("command", command).execute()
    else:
        result = supabase.table("sounds").insert({
            "command": command, "filename": file.filename,
            "audio_url": audio_url, "cooldown": cooldown,
            "volume": volume, "active": True,
            "subs_only": bool(subs_only), "vips_only": bool(vips_only)
        }).execute()

    return result.data[0]


@app.put("/api/sounds/{sound_id}")
async def update_sound(sound_id: int, request: Request):
    body = await request.json()
    require_role(body.pop("password", ""), "mod")
    result = supabase.table("sounds").update(body).eq("id", sound_id).execute()
    return result.data[0]


@app.delete("/api/sounds/{sound_id}")
async def delete_sound(sound_id: int, password: str):
    require_role(password, "admin")
    row = supabase.table("sounds").select("audio_url").eq("id", sound_id).execute()
    if row.data:
        filename = row.data[0]["audio_url"].split("/")[-1]
        try:
            supabase.storage.from_("audios").remove([filename])
        except Exception:
            pass
    supabase.table("sounds").delete().eq("id", sound_id).execute()
    return {"ok": True}


@app.post("/api/test/{sound_id}")
async def test_sound(sound_id: int, request: Request):
    body = await request.json()
    require_role(body.get("password", ""), "mod")
    row = supabase.table("sounds").select("*").eq("id", sound_id).execute()
    if not row.data:
        raise HTTPException(status_code=404)
    sound = row.data[0]
    filename = sound["audio_url"].split("/")[-1]
    proxy_url = f"{APP_URL}/audio/{filename}" if APP_URL else sound["audio_url"]
    await broadcast_obs({
        "type": "play",
        "url": proxy_url,
        "command": sound["command"],
        "volume": sound.get("volume", 80)
    })
    return {"ok": True}


@app.get("/audio/{filename}")
async def proxy_audio(filename: str):
    url = supabase.storage.from_("audios").get_public_url(filename)
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        if r.status_code != 200:
            raise HTTPException(status_code=404)
    content_type = r.headers.get("content-type", "audio/mpeg")
    return StreamingResponse(
        iter([r.content]),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600", "Access-Control-Allow-Origin": "*"}
    )
