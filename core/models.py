"""
SentinelOps Core Models
Pydantic schemas conforming strictly to the Switch Agent Protocol & Room Document specs.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid


class SwitchMessagePayload(BaseModel):
    content: str
    addressed: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    attachments: Optional[List[Dict[str, Any]]] = None


class SwitchEvent(BaseModel):
    type: str  # e.g., 'connection_state', 'message', 'role_assigned', 'decision_callback'
    seq: int
    room_id: str
    sender_id: str
    role: Optional[str] = None
    payload: SwitchMessagePayload
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssumeRoleRequest(BaseModel):
    room_id: str
    role_name: str
    exclusive: bool = True


class ReleaseRoleRequest(BaseModel):
    room_id: str
    role_name: str


class CreateRoomDocumentRequest(BaseModel):
    room_id: str
    name: str
    content: str


class UpdateRoomDocumentRequest(BaseModel):
    room_id: str
    document_id: Optional[str] = None
    name: Optional[str] = None
    content: str


class PostMessageRequest(BaseModel):
    room_id: str
    content: str
    attachments: Optional[List[Dict[str, Any]]] = None


class RoomDocument(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    room_id: str
    name: str
    content: str
    created_by_agent_id: str
    version: int = 1
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DecisionContext(BaseModel):
    action: str  # e.g., "revert", "abort", "escalate"
    commit_sha: str
    room_id: str
    service_name: Optional[str] = "checkout-service-api"


class DecisionCallbackPayload(BaseModel):
    user_id: str
    user_name: str
    channel_id: str
    context: DecisionContext


class DiagnosticReport(BaseModel):
    incident_id: str
    service_impacted: str
    error_rate: str
    root_cause_file: str
    root_cause_line: int
    offending_commit: str
    author: str
    commit_message: str
    suggested_action: str
    pii_redacted_count: int
    sarif_status: str
