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
        app: Optional[Any] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.ws_base_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.agent_id = agent_id
        self.api_key = api_key
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
        url = f"{self.base_url}/agents/{self.agent_id}/ops/assume_role"
        payload = AssumeRoleRequest(room_id=room_id, role_name=role_name, exclusive=exclusive).model_dump()
        resp = await self.http_client.post(url, json=payload)
        resp.raise_for_status()
        self.active_roles[room_id] = role_name
        logger.info(f"Assumed role {role_name} in room {room_id}")
        return resp.json()

    async def release_role(self, room_id: str, role_name: str = "triage-commander") -> Dict[str, Any]:
        """Release role lease back to Switch Core"""
        url = f"{self.base_url}/agents/{self.agent_id}/ops/release_role"
        payload = ReleaseRoleRequest(room_id=room_id, role_name=role_name).model_dump()
        resp = await self.http_client.post(url, json=payload)
        resp.raise_for_status()
        if room_id in self.active_roles:
            del self.active_roles[room_id]
        logger.info(f"Released role {role_name} in room {room_id}")
        return resp.json()

    async def create_room_document(self, room_id: str, name: str, content: str) -> Dict[str, Any]:
        """Initialize a collaborative Room Document (living postmortem)"""
        url = f"{self.base_url}/agents/{self.agent_id}/ops/create_room_document"
        payload = CreateRoomDocumentRequest(room_id=room_id, name=name, content=content).model_dump()
        resp = await self.http_client.post(url, json=payload)
        resp.raise_for_status()
        logger.info(f"Created room document '{name}' in room {room_id}")
        return resp.json()

    async def update_room_document(self, room_id: str, name: str, content: str) -> Dict[str, Any]:
        """Mutate living postmortem document as incident advances"""
        url = f"{self.base_url}/agents/{self.agent_id}/ops/update_room_document"
        payload = UpdateRoomDocumentRequest(room_id=room_id, name=name, content=content).model_dump()
        resp = await self.http_client.post(url, json=payload)
        resp.raise_for_status()
        logger.info(f"Updated room document '{name}' in room {room_id}")
        return resp.json()

    async def get_room_document(self, room_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Fetch current version of a room document"""
        url = f"{self.base_url}/agents/{self.agent_id}/ops/get_room_document?room_id={room_id}&name={name}"
        resp = await self.http_client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def post_message(self, room_id: str, content: str, attachments: Optional[list] = None) -> Dict[str, Any]:
        """Post an event or attachment card to the room stream"""
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
        Maintains persistent WebSocket connection to Switch Core with cursor replay.
        """
        self._running = True
        ws_url = f"{self.ws_base_url}/agents/{self.agent_id}/connection/ws?cursor={self.last_seq}"

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
                        event = SwitchEvent(**data)
                        if event.seq > self.last_seq:
                            self.last_seq = event.seq

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
