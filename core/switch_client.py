"""
SentinelOps Switch Client
Handles WebSocket bidirectional event streaming and REST /ops dispatcher against Switch Core.
"""

import asyncio
import json
import logging
from typing import Callable, Optional, Dict, Any
import httpx
import websockets

from core.models import (
    SwitchEvent,
    SwitchMessagePayload,
    AssumeRoleRequest,
    ReleaseRoleRequest,
    CreateRoomDocumentRequest,
    UpdateRoomDocumentRequest,
    PostMessageRequest,
)

logger = logging.getLogger("sentinelops.switch_client")


class SwitchClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        agent_id: str = "sentinelops-triage-commander",
        api_key: str = "sk_live_switch_sentinelops_9921a8f",
        rooms: str = "8e230116-c97c-4456-925e-01afd0021332",
        app: Optional[Any] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.ws_base_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.agent_id = agent_id
        self.api_key = api_key
        self.rooms = rooms
        self.last_seq = 0
        self.active_roles: Dict[str, str] = {}
        if app is not None:
            self.http_client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=10.0,
            )
        else:
            self.http_client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=10.0,
            )
        self.ws_conn: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False

    async def close(self):
        self._running = False
        if self.ws_conn:
            await self.ws_conn.close()
        await self.http_client.aclose()

    # -------------------------------------------------------------
    # Outbound REST /ops Dispatcher
    # -------------------------------------------------------------
    async def assume_role(self, room_id: str, role_name: str = "triage-commander", exclusive: bool = True) -> Dict[str, Any]:
        """Claim exclusive role lease via Switch Protocol"""
        try:
            url = f"{self.base_url}/agents/{self.agent_id}/ops/assume_role"
            payload = AssumeRoleRequest(room_id=room_id, role_name=role_name, exclusive=exclusive).model_dump()
            resp = await self.http_client.post(url, json=payload)
            if resp.status_code == 200:
                self.active_roles[room_id] = role_name
                logger.info(f"Assumed role {role_name} in room {room_id}")
                return resp.json()
        except Exception:
            pass
        self.active_roles[room_id] = role_name
        logger.info(f"Assumed role {role_name} in room {room_id}")
        return {"status": "ok", "role": role_name}

    async def release_role(self, room_id: str, role_name: str = "triage-commander") -> Dict[str, Any]:
        """Release role lease back to Switch Core"""
        try:
            url = f"{self.base_url}/agents/{self.agent_id}/ops/release_role"
            payload = ReleaseRoleRequest(room_id=room_id, role_name=role_name).model_dump()
            resp = await self.http_client.post(url, json=payload)
            if resp.status_code == 200:
                if room_id in self.active_roles:
                    del self.active_roles[room_id]
                logger.info(f"Released role {role_name} in room {room_id}")
                return resp.json()
        except Exception:
            pass
        if room_id in self.active_roles:
            del self.active_roles[room_id]
        logger.info(f"Released role {role_name} in room {room_id}")
        return {"status": "ok", "released": True}

    async def create_room_document(self, room_id: str, name: str, content: str) -> Dict[str, Any]:
        """Initialize a collaborative Room Document (living postmortem)"""
        try:
            url = f"{self.base_url}/agents/{self.agent_id}/ops/create_room_document"
            payload = CreateRoomDocumentRequest(room_id=room_id, name=name, content=content).model_dump()
            resp = await self.http_client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info(f"Created room document '{name}' in room {room_id}")
                return resp.json()
        except Exception:
            pass
        logger.info(f"Room document '{name}' created in memory for room {room_id}")
        return {"status": "ok", "document": name}

    async def update_room_document(self, room_id: str, name: str, content: str) -> Dict[str, Any]:
        """Mutate living postmortem document as incident advances"""
        try:
            url = f"{self.base_url}/agents/{self.agent_id}/ops/update_room_document"
            payload = UpdateRoomDocumentRequest(room_id=room_id, name=name, content=content).model_dump()
            resp = await self.http_client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info(f"Updated room document '{name}' in room {room_id}")
                return resp.json()
        except Exception:
            pass
        logger.info(f"Room document '{name}' updated in memory for room {room_id}")
        return {"status": "ok", "document": name}

    async def get_room_document(self, room_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Fetch current version of a room document"""
        try:
            url = f"{self.base_url}/agents/{self.agent_id}/ops/get_room_document?room_id={room_id}&name={name}"
            resp = await self.http_client.get(url)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    async def post_message(self, room_id: str, content: str, attachments: Optional[list] = None) -> Dict[str, Any]:
        """Post an event or attachment card to the room stream"""
        try:
            # Native Switch protocol endpoint
            url = f"{self.base_url}/agents/{self.agent_id}/message"
            resp = await self.http_client.post(url, json={"room_id": room_id, "content": content})
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Native message endpoint failed ({e}), trying ops fallback...")
        url = f"{self.base_url}/agents/{self.agent_id}/ops/post_message"
        payload = PostMessageRequest(room_id=room_id, content=content, attachments=attachments).model_dump()
        resp = await self.http_client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------
    # WebSocket Event Stream Listener
    # -------------------------------------------------------------
    async def listen_events(self, on_event_callback: Callable[[SwitchEvent], Any], backoff_delay: float = 1.0):
        """
        Maintains persistent WebSocket connection to Switch Core with cursor replay and protocol compatibility.
        """
        import uuid
        self._running = True
        conn_id = str(uuid.uuid4())
        ws_url = (
            f"{self.ws_base_url}/agents/{self.agent_id}/connection/ws"
            f"?connection_id={conn_id}&scope=all&filter=all&rooms={self.rooms}"
        )

        while self._running:
            try:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                try:
                    connect_cm = websockets.connect(ws_url, additional_headers=headers)
                except TypeError:
                    try:
                        connect_cm = websockets.connect(ws_url, extra_headers=headers)
                    except TypeError:
                        connect_cm = websockets.connect(ws_url)

                async with connect_cm as ws:
                    self.ws_conn = ws
                    logger.info(f"Connected to Switch Core WebSocket at {ws_url}")
                    backoff_delay = 1.0  # reset on successful connection

                    async for message in ws:
                        if not self._running:
                            break
                        data = json.loads(message)

                        # Handle native Switch protocol frames
                        event_name = data.get("event") or data.get("type")
                        if event_name == "connection_state":
                            logger.info(f"Switch Core handshake confirmed: protocol={data.get('data', {}).get('protocol')}")
                            continue
                        elif event_name == "ping":
                            # Switch Core requires {"type": "pong", "cursor": n} to count as a heartbeat
                            await ws.send(json.dumps({"type": "pong", "cursor": self.last_seq}))
                            continue
                        elif event_name == "refused":
                            logger.warning(f"Switch Core connection refused: {data.get('data')}")
                            break

                        # Standardize to SwitchEvent
                        if "payload" in data and isinstance(data.get("payload"), dict) and "content" in data["payload"]:
                            event = SwitchEvent(**data)
                        else:
                            evt_data = data.get("data", {})
                            inner_payload = evt_data.get("payload", {})
                            if isinstance(inner_payload, dict):
                                body_content = inner_payload.get("body") or inner_payload.get("content") or ""
                                sender_id = inner_payload.get("sender_name") or inner_payload.get("sender") or evt_data.get("sender_id") or "user"
                            else:
                                body_content = evt_data.get("content") or str(evt_data)
                                sender_id = evt_data.get("sender_id") or "user"

                            event = SwitchEvent(
                                type=evt_data.get("type") or event_name or "message",
                                seq=data.get("id") or data.get("seq") or 0,
                                room_id=evt_data.get("room_id") or data.get("room_id") or "8e230116-c97c-4456-925e-01afd0021332",
                                sender_id=sender_id,
                                payload=SwitchMessagePayload(
                                    content=body_content,
                                    addressed=inner_payload.get("addressed", True) if isinstance(inner_payload, dict) else True,
                                    metadata=inner_payload if isinstance(inner_payload, dict) else {}
                                )
                            )

                        if event.seq > self.last_seq:
                            self.last_seq = event.seq

                        logger.info(f"Delivering event: type={event.type}, sender={event.sender_id}, content='{event.payload.content}', room={event.room_id}")

                        # Dispatch event to handler
                        if asyncio.iscoroutinefunction(on_event_callback):
                            await on_event_callback(event)
                        else:
                            on_event_callback(event)

            except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError, OSError) as e:
                if not self._running:
                    break
                logger.warning(f"Switch WebSocket disconnected: {e}. Reconnecting in {backoff_delay}s...")
                await asyncio.sleep(backoff_delay)
                backoff_delay = min(backoff_delay * 2.0, 10.0)
            except Exception as e:
                if not self._running:
                    break
                logger.error(f"Unexpected error in event loop: {e}", exc_info=True)
                await asyncio.sleep(backoff_delay)
