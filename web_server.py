from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from aiohttp import WSMsgType, web

from game import is_local_host, release_worldwide_host, start_embedded_server
from server import GameServer
from shared import SERVER_PORT


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"


def public_room_config() -> dict[str, object]:
    host = os.environ.get("PUBLIC_SERVER_HOST", "shortline.proxy.rlwy.net").strip() or "shortline.proxy.rlwy.net"
    try:
        port = int(os.environ.get("PUBLIC_SERVER_PORT", "55839"))
    except ValueError:
        port = 55839
    room_name = os.environ.get("PUBLIC_ROOM_NAME", "Dungeon Drift Public").strip()[:32]
    room_code = os.environ.get("PUBLIC_ROOM_CODE", "").strip()[:6]
    auto_connect = os.environ.get("PUBLIC_AUTO_CONNECT", "0").strip().lower() in {"1", "true", "yes", "on"}
    lock_settings = os.environ.get("PUBLIC_LOCK_SETTINGS", "0").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "host": host,
        "port": port,
        "room_name": room_name,
        "room_code": room_code,
        "auto_connect": auto_connect,
        "lock_settings": lock_settings,
    }


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_ROOT / "index.html")


async def config_handler(request: web.Request) -> web.Response:
    return web.json_response(request.app["public_room_config"])


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    tcp_reader = None
    tcp_writer = None
    pump_task: asyncio.Task | None = None
    app = request.app

    async def close_remote() -> None:
        nonlocal tcp_writer, pump_task
        if pump_task is not None:
            pump_task.cancel()
            try:
                await pump_task
            except asyncio.CancelledError:
                pass
            pump_task = None
        if tcp_writer is not None:
            tcp_writer.close()
            try:
                await tcp_writer.wait_closed()
            except OSError:
                pass
            tcp_writer = None

    async def pump_remote() -> None:
        nonlocal tcp_reader
        try:
            while tcp_reader is not None:
                line = await tcp_reader.readline()
                if not line:
                    await ws.send_json({"type": "disconnected", "message": "Game server disconnected."})
                    break
                await ws.send_str(line.decode("utf-8").strip())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not ws.closed:
                await ws.send_json({"type": "error", "message": f"Proxy error: {exc}"})

    async for message in ws:
        if message.type == WSMsgType.TEXT:
            try:
                payload = json.loads(message.data)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON payload."})
                continue

            msg_type = payload.get("type")
            if msg_type == "connect":
                await close_remote()
                host = str(payload.get("host", "127.0.0.1")).strip() or "127.0.0.1"
                port = int(payload.get("port", SERVER_PORT))
                name = str(payload.get("name", "Adventurer")).strip()[:18] or "Adventurer"
                color_index = int(payload.get("color_index", 0))
                server_name = str(payload.get("server_name", "")).strip()[:32]
                room_code = str(payload.get("password", "")).strip()[:32]

                if is_local_host(host) and app["embedded_server"] is None:
                    app["embedded_server"] = start_embedded_server(host, port, server_name=server_name, join_password=room_code)
                    if app["embedded_server"] is not None:
                        await asyncio.sleep(0.2)

                try:
                    tcp_reader, tcp_writer = await asyncio.open_connection(host, port)
                    tcp_writer.write(
                        (
                            json.dumps(
                                {
                                    "type": "join",
                                    "name": name,
                                    "color_index": color_index,
                                    "password": room_code,
                                },
                                separators=(",", ":"),
                            )
                            + "\n"
                        ).encode("utf-8")
                    )
                    await tcp_writer.drain()
                    welcome_line = await tcp_reader.readline()
                    if not welcome_line:
                        raise RuntimeError("No response from game server.")
                    welcome = json.loads(welcome_line.decode("utf-8"))
                    await ws.send_json(welcome)
                    if welcome.get("type") == "error":
                        await close_remote()
                    else:
                        pump_task = asyncio.create_task(pump_remote())
                except Exception as exc:
                    await ws.send_json({"type": "error", "message": f"Could not connect to {host}:{port} ({exc})"})
                    await close_remote()
            elif msg_type in {"input", "action"}:
                if tcp_writer is None:
                    await ws.send_json({"type": "error", "message": "Join a server first."})
                    continue
                tcp_writer.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
                await tcp_writer.drain()
            else:
                await ws.send_json({"type": "error", "message": f"Unsupported message type: {msg_type}"})
        elif message.type == WSMsgType.ERROR:
            break

    await close_remote()
    return ws


async def on_cleanup(app: web.Application) -> None:
    embedded_server: GameServer | None = app.get("embedded_server")
    if embedded_server is not None:
        release_worldwide_host(getattr(embedded_server, "worldwide_host_info", None))
        embedded_server.running = False
        try:
            if getattr(embedded_server, "discovery_socket", None) is not None:
                embedded_server.discovery_socket.close()
        except OSError:
            pass
        try:
            if embedded_server.server_socket is not None:
                embedded_server.server_socket.close()
        except OSError:
            pass


def build_app() -> web.Application:
    app = web.Application()
    app["embedded_server"] = None
    app["public_room_config"] = public_room_config()
    app.router.add_get("/", index)
    app.router.add_get("/config", config_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_static("/assets/", WEB_ROOT, show_index=False)
    app.on_cleanup.append(on_cleanup)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the web client and proxy websocket traffic to the TCP game server.")
    parser.add_argument("--host", default="0.0.0.0", help="Web server bind host.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")), help="Web server port.")
    args = parser.parse_args()
    web.run_app(build_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
