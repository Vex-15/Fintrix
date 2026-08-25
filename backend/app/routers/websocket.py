"""
WebSocket API — real-time updates for the Fintrix dashboard.
Replaces SSE for bidirectional communication.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.services.auth import decode_token

router = APIRouter()


# ---------------------------------------------------------------------------
# Connection Manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manages WebSocket connections with merchant-scoped rooms."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}  # room -> [websockets]
        self.all_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket, room: str = "global"):
        await websocket.accept()
        self.all_connections.append(websocket)
        if room not in self.active_connections:
            self.active_connections[room] = []
        self.active_connections[room].append(websocket)

    def disconnect(self, websocket: WebSocket, room: str = "global"):
        if websocket in self.all_connections:
            self.all_connections.remove(websocket)
        if room in self.active_connections and websocket in self.active_connections[room]:
            self.active_connections[room].remove(websocket)

    async def send_to_room(self, room: str, event_type: str, data: dict):
        """Send a message to all connections in a room."""
        message = json.dumps({"event": event_type, "data": data}, default=str)
        connections = self.active_connections.get(room, [])
        disconnected = []
        for connection in connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn, room)

    async def broadcast(self, event_type: str, data: dict):
        """Send a message to ALL connections."""
        message = json.dumps({"event": event_type, "data": data}, default=str)
        disconnected = []
        for connection in self.all_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            if conn in self.all_connections:
                self.all_connections.remove(conn)

    @property
    def connection_count(self) -> int:
        return len(self.all_connections)


# Global manager instance
manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Public broadcast function (used by other modules)
# ---------------------------------------------------------------------------

async def broadcast_ws(event_type: str, data: dict, room: str | None = None):
    """Broadcast a WebSocket event. Can be called from anywhere in the app."""
    if room:
        await manager.send_to_room(room, event_type, data)
    else:
        await manager.broadcast(event_type, data)


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket connection endpoint.
    
    Supports:
    - Authentication via query param: ?token=<jwt_token>
    - Room subscription based on merchant_id
    - Bidirectional messaging
    
    Client messages:
    - {"type": "subscribe", "room": "merchant_xxx"}
    - {"type": "ping"}
    
    Server messages:
    - {"event": "connected", "data": {...}}
    - {"event": "pipeline.step", "data": {...}}
    - {"event": "exception.detected", "data": {...}}
    - etc.
    """
    # Authenticate (optional — token in query params)
    token = websocket.query_params.get("token")
    merchant_id = "global"
    user_info = None

    if token:
        try:
            payload = decode_token(token)
            merchant_id = payload.get("merchant_id", "global")
            user_info = {"email": payload.get("email"), "role": payload.get("role")}
        except Exception:
            pass  # Allow unauthenticated connections in dev

    await manager.connect(websocket, room=merchant_id)

    try:
        # Send welcome message
        await websocket.send_text(json.dumps({
            "event": "connected",
            "data": {
                "status": "connected",
                "room": merchant_id,
                "user": user_info,
                "connections": manager.connection_count,
                "timestamp": datetime.utcnow().isoformat(),
            },
        }))

        # Keep connection alive and handle client messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(data)

                msg_type = message.get("type", "")

                if msg_type == "ping":
                    await websocket.send_text(json.dumps({
                        "event": "pong",
                        "data": {"ts": datetime.utcnow().isoformat()},
                    }))

                elif msg_type == "subscribe":
                    new_room = message.get("room", "global")
                    manager.disconnect(websocket, merchant_id)
                    merchant_id = new_room
                    manager.active_connections.setdefault(new_room, []).append(websocket)
                    await websocket.send_text(json.dumps({
                        "event": "subscribed",
                        "data": {"room": new_room},
                    }))

            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_text(json.dumps({
                        "event": "ping",
                        "data": {"ts": datetime.utcnow().isoformat()},
                    }))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(websocket, merchant_id)


@router.get("/ws/status")
async def websocket_status():
    """Get WebSocket connection status."""
    return {
        "active_connections": manager.connection_count,
        "rooms": {room: len(conns) for room, conns in manager.active_connections.items()},
    }
