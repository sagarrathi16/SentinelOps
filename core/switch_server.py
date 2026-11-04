"""
SentinelOps Switch Core Server Emulator
Implements the Switch Protocol specification for local zero-tunneling operation:
- Port 8000: Core REST & WebSocket Agent Gateway + Room Documents
- Port 8081: Mattermost Interactive Decision Callback Listener
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.models import (
    SwitchEvent,
    SwitchMessagePayload,
    AssumeRoleRequest,
    ReleaseRoleRequest,
    CreateRoomDocumentRequest,
    UpdateRoomDocumentRequest,
    PostMessageRequest,
    RoomDocument,
    DecisionCallbackPayload,
)

logger = logging.getLogger("sentinelops.switch_server")

# -------------------------------------------------------------
# In-Memory State Store (backed by JSON / Postgres in Prod)
# -------------------------------------------------------------
class SwitchRoomStore:
    def __init__(self):
        self.events: Dict[str, List[SwitchEvent]] = {}  # room_id -> list of events
        self.roles: Dict[str, Dict[str, str]] = {}     # room_id -> {role_name: agent_id}
        self.documents: Dict[str, Dict[str, RoomDocument]] = {} # room_id -> {doc_name: RoomDocument}
        self.connected_sockets: List[WebSocket] = []
        self.global_seq = 0

    def append_event(self, room_id: str, sender_id: str, event_type: str, payload: Dict, role: Optional[str] = None) -> SwitchEvent:
        self.global_seq += 1
        event = SwitchEvent(
            type=event_type,
            seq=self.global_seq,
            room_id=room_id,
            sender_id=sender_id,
            role=role,
            payload=SwitchMessagePayload(**payload) if isinstance(payload, dict) else payload,
            timestamp=datetime.now(timezone.utc)
        )
        if room_id not in self.events:
            self.events[room_id] = []
        self.events[room_id].append(event)
        return event

store = SwitchRoomStore()

# -------------------------------------------------------------
# FastAPI Core Application (:8000)
# -------------------------------------------------------------
app = FastAPI(title="Switch Core Protocol Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Switch Core Server",
        "total_events": store.global_seq,
        "active_sockets": len(store.connected_sockets)
    }


# WebSocket Gateway
@app.websocket("/agents/{agent_id}/connection/ws")
async def agent_ws_endpoint(websocket: WebSocket, agent_id: str, cursor: int = Query(0)):
    await websocket.accept()
    store.connected_sockets.append(websocket)
    logger.info(f"Agent {agent_id} connected via WebSocket (cursor={cursor})")

    # Send initial connection state
    await websocket.send_text(json.dumps({
        "type": "connection_state",
        "seq": store.global_seq,
        "room_id": "system",
        "sender_id": "switch-core",
        "payload": {"content": f"Connected as {agent_id}", "addressed": True}
    }))

    try:
        while True:
            # Keep alive and receive agent acknowledgments or pings
            data = await websocket.receive_text()
            # Agent can echo or ping
    except WebSocketDisconnect:
        logger.info(f"Agent {agent_id} disconnected")
    finally:
        if websocket in store.connected_sockets:
            store.connected_sockets.remove(websocket)


async def broadcast_event(event: SwitchEvent):
    """Broadcasts event frame to all active WebSockets"""
    raw_json = event.model_dump_json()
    disconnected = []
    for ws in store.connected_sockets:
        try:
            await ws.send_text(raw_json)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in store.connected_sockets:
            store.connected_sockets.remove(ws)


# REST /ops Endpoints
@app.post("/agents/{agent_id}/ops/assume_role")
async def assume_role(agent_id: str, req: AssumeRoleRequest):
    if req.room_id not in store.roles:
        store.roles[req.room_id] = {}

    current_holder = store.roles[req.room_id].get(req.role_name)
    if current_holder and current_holder != agent_id and req.exclusive:
        raise HTTPException(
            status_code=409,
            detail=f"Role '{req.role_name}' in room '{req.room_id}' is already held by agent '{current_holder}'"
        )

    store.roles[req.room_id][req.role_name] = agent_id
    event = store.append_event(
        room_id=req.room_id,
        sender_id="switch-core",
        event_type="role_assigned",
        payload={"content": f"Agent {agent_id} assumed role {req.role_name}"},
        role="system"
    )
    await broadcast_event(event)
    return {"status": "ok", "role": req.role_name, "holder": agent_id}


@app.post("/agents/{agent_id}/ops/release_role")
async def release_role(agent_id: str, req: ReleaseRoleRequest):
    if req.room_id in store.roles and store.roles[req.room_id].get(req.role_name) == agent_id:
        del store.roles[req.room_id][req.role_name]
        event = store.append_event(
            room_id=req.room_id,
            sender_id="switch-core",
            event_type="role_released",
            payload={"content": f"Agent {agent_id} released role {req.role_name}"},
            role="system"
        )
        await broadcast_event(event)
        return {"status": "ok", "role": req.role_name, "released": True}
    return {"status": "ok", "released": False}


@app.post("/agents/{agent_id}/ops/create_room_document")
async def create_room_document(agent_id: str, req: CreateRoomDocumentRequest):
    if req.room_id not in store.documents:
        store.documents[req.room_id] = {}

    doc = RoomDocument(
        room_id=req.room_id,
        name=req.name,
        content=req.content,
        created_by_agent_id=agent_id,
        version=1
    )
    store.documents[req.room_id][req.name] = doc
    event = store.append_event(
        room_id=req.room_id,
        sender_id=agent_id,
        event_type="document_created",
        payload={"content": f"Created room document '{req.name}'", "metadata": {"name": req.name, "doc_id": doc.id}},
        role=store.roles.get(req.room_id, {}).get("triage-commander", "agent")
    )
    await broadcast_event(event)
    return doc.model_dump()


@app.post("/agents/{agent_id}/ops/update_room_document")
async def update_room_document(agent_id: str, req: UpdateRoomDocumentRequest):
    if req.room_id not in store.documents or req.name not in store.documents[req.room_id]:
        # Upsert if not present
        return await create_room_document(agent_id, CreateRoomDocumentRequest(room_id=req.room_id, name=req.name or "incident-postmortem.md", content=req.content))

    doc = store.documents[req.room_id][req.name]
    doc.content = req.content
    doc.version += 1
    doc.updated_at = datetime.now(timezone.utc)

    event = store.append_event(
        room_id=req.room_id,
        sender_id=agent_id,
        event_type="document_updated",
        payload={"content": f"Updated room document '{req.name}' (v{doc.version})", "metadata": {"name": req.name, "version": doc.version}},
        role=store.roles.get(req.room_id, {}).get("triage-commander", "agent")
    )
    await broadcast_event(event)
    return doc.model_dump()


@app.get("/agents/{agent_id}/ops/get_room_document")
async def get_room_document(agent_id: str, room_id: str, name: str):
    if room_id in store.documents and name in store.documents[room_id]:
        return store.documents[room_id][name].model_dump()
    raise HTTPException(status_code=404, detail=f"Document '{name}' not found in room '{room_id}'")


@app.post("/agents/{agent_id}/ops/post_message")
async def post_message(agent_id: str, req: PostMessageRequest):
    role = store.roles.get(req.room_id, {}).get("triage-commander", "agent")
    event = store.append_event(
        room_id=req.room_id,
        sender_id=agent_id,
        event_type="message",
        payload={"content": req.content, "attachments": req.attachments or []},
        role=role
    )
    await broadcast_event(event)

    # Forward to Mattermost incoming webhook if available
    import os
    import httpx
    mm_webhook = os.getenv("MATTERMOST_WEBHOOK_URL", "http://mattermost:8065/hooks/rmh6yh47zty7ukxzm3xy9kw9ka")
    if mm_webhook:
        try:
            mm_payload = {
                "username": "triage-commander",
                "icon_emoji": ":robot_face:",
                "text": req.content,
                "props": {
                    "attachments": req.attachments or []
                }
            }
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(mm_webhook, json=mm_payload)
        except Exception as e:
            logger.warning(f"Could not forward message to Mattermost: {e}")

    return {"status": "ok", "seq": event.seq}


@app.get("/gateway/rooms/{room_id}/events")
async def get_room_events(room_id: str, since_seq: int = 0):
    events = store.events.get(room_id, [])
    return [e.model_dump() for e in events if e.seq > since_seq]


@app.post("/inject/alert")
async def inject_alert(request: Request):
    """Injects an incident alert into the room event log"""
    room_id = "inc-checkout-482"
    content = "CRITICAL: HTTP 500 error rate spiked to 14.8% on /checkout"
    try:
        body = await request.body()
        if body:
            import json
            from urllib.parse import parse_qs
            body_str = body.decode("utf-8", errors="replace")
            if body_str.strip().startswith("{"):
                data = json.loads(body_str)
            else:
                parsed = parse_qs(body_str)
                data = {k: v[0] for k, v in parsed.items()}
            if "content" in data and data["content"]:
                content = data["content"]
            if "room_id" in data and data["room_id"]:
                room_id = data["room_id"]
    except Exception as e:
        logger.warning(f"Error parsing inject alert request: {e}")

    # Also check query params if not provided in body
    qp_content = request.query_params.get("content")
    if qp_content:
        content = qp_content
    qp_room = request.query_params.get("room_id")
    if qp_room:
        room_id = qp_room

    event = store.append_event(
        room_id=room_id,
        sender_id="usr-mattermost-webhook",
        event_type="message",
        payload={"content": content, "addressed": True},
        role="monitoring-alert"
    )
    await broadcast_event(event)

    # Forward alert to Mattermost
    import os
    import httpx
    mm_webhook = os.getenv("MATTERMOST_WEBHOOK_URL", "http://mattermost:8065/hooks/rmh6yh47zty7ukxzm3xy9kw9ka")
    if mm_webhook:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(mm_webhook, json={
                    "username": "Alertmanager (Datadog)",
                    "icon_emoji": ":rotating_light:",
                    "text": f":rotating_light: **{content}**"
                })
        except Exception:
            pass

    return {"status": "injected", "seq": event.seq, "room_id": room_id}


@app.post("/gateway/mattermost/outgoing")
async def mattermost_outgoing_webhook(request: Request):
    """
    Receives messages typed in Mattermost channel and forwards them into Switch room event log.
    Supports both JSON and x-www-form-urlencoded payloads natively.
    """
    data = {}
    try:
        body = await request.body()
        if body:
            body_str = body.decode("utf-8", errors="replace")
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type or body_str.strip().startswith("{"):
                import json
                data = json.loads(body_str)
            else:
                from urllib.parse import parse_qs
                parsed = parse_qs(body_str)
                data = {k: v[0] for k, v in parsed.items()}
    except Exception as e:
        logger.warning(f"Error parsing Mattermost outgoing payload: {e}")
        data = {}

    text = data.get("text", "").strip()
    user_name = data.get("user_name", "user")
    room_id = "inc-checkout-482"
    logger.info(f"Mattermost outgoing message from @{user_name}: '{text}'")

    if not text:
        return JSONResponse({"status": "empty_text_ignored"})

    # Broadcast event into Switch room
    event = store.append_event(
        room_id=room_id,
        sender_id=user_name,
        event_type="message",
        payload={"content": text, "addressed": True},
        role="user"
    )
    await broadcast_event(event)

    # If user typed status or general question without approve
    if any(k in text.lower() for k in ["status", "help", "@triage-commander", "@trigger-commander"]):
        if not any(k in text.lower() for k in ["approve", "rollback", "revert"]):
            return JSONResponse({
                "response_type": "in_channel",
                "text": f":satellite: **@triage-commander Active in #{room_id}**\n- **Role:** Autonomous SRE Incident Commander\n- **Status:** Monitoring `checkout-service-api`\n- **Commands:** Type `@triage-commander approve rollback` to authorize remediation."
            })

    return JSONResponse({"status": "received"})


# -------------------------------------------------------------
# Mattermost Interactive Decision Callback Endpoint (:8081 / :8000)
# -------------------------------------------------------------
@app.post("/actions/approve_rollback")
async def approve_rollback_action(payload: DecisionCallbackPayload):
    """
    Handles interactive button callback from Mattermost card.
    Broadcasts decision event to unblock autonomous remediation.
    """
    logger.info(f"Received interactive decision callback from user @{payload.user_name} (Action: {payload.context.action})")

    event = store.append_event(
        room_id=payload.context.room_id,
        sender_id=payload.user_name,
        event_type="decision_callback",
        payload={
            "content": f"Decision: Approved {payload.context.action} for commit #{payload.context.commit_sha} by @{payload.user_name}",
            "metadata": {
                "action": payload.context.action,
                "commit_sha": payload.context.commit_sha,
                "approved_by": payload.user_name,
                "user_id": payload.user_id,
            }
        },
        role="incident-lead"
    )
    await broadcast_event(event)

    # Mattermost expects updated post attachment
    return JSONResponse(
        status_code=200,
        content={
            "update": {
                "message": f"Incident Remediation Authorized by @{payload.user_name}",
                "props": {
                    "attachments": [
                        {
                            "color": "#28a745",
                            "title": "Remediation Approved",
                            "text": f":white_check_mark: **Action Authorized:** `git revert {payload.context.commit_sha}`\n**Authorized by:** @{payload.user_name}\n**Status:** Executing automated staging rollback and regression suite...",
                        }
                    ]
                }
            }
        }
    )


# Helper function to run server programmatically
def start_server(host: str = "127.0.0.1", port: int = 8000):
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    uvicorn.run("core.switch_server:app", host="0.0.0.0", port=8000, reload=True)
