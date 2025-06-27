from dataclasses import dataclass
from enum import Enum
from typing import Optional

class BirdRiskLevel(Enum):
    """조류 위험도 레벨"""
    HIGH = "BR_HIGH"
    MEDIUM = "BR_MEDIUM"
    LOW = "BR_LOW"

class RunwayStatus(Enum):
    """활주로 상태"""
    CLEAR = "CLEAR"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"

class RunwayAvailability(Enum):
    """활주로 가용성"""
    ALL = "ALL"
    A_ONLY = "A_ONLY"
    B_ONLY = "B_ONLY"
    NONE = "NONE"

class EventType(Enum):
    """이벤트 타입"""
    BR_CHANGED = "BR_CHANGED"
    RWY_A_STATUS_CHANGED = "RWY_A_STATUS_CHANGED"
    RWY_B_STATUS_CHANGED = "RWY_B_STATUS_CHANGED"
    MARSHALING_GESTURE_DETECTED = "MARSHALING_GESTURE_DETECTED"

class CommandType(Enum):
    """명령 타입"""
    BR_INQ = "BR_INQ"
    RWY_A_STATUS = "RWY_A_STATUS"
    RWY_B_STATUS = "RWY_B_STATUS"
    RWY_AVAIL_INQ = "RWY_AVAIL_INQ"

@dataclass
class BaseMessage:
    """기본 메시지 클래스"""
    type: str  # "event", "command", "response"

@dataclass
class EventMessage(BaseMessage):
    """이벤트 메시지"""
    event: EventType
    result: str

@dataclass
class CommandMessage(BaseMessage):
    """명령 메시지"""
    command: CommandType

@dataclass
class ResponseMessage(BaseMessage):
    """응답 메시지"""
    command: CommandType
    result: str

# 이벤트 생성 편의 함수들
def create_bird_risk_event(risk_level: BirdRiskLevel) -> EventMessage:
    return EventMessage(
        type="event",
        event=EventType.BR_CHANGED,
        result=risk_level.value
    )

def create_runway_a_status_event(status: RunwayStatus) -> EventMessage:
    return EventMessage(
        type="event",
        event=EventType.RWY_A_STATUS_CHANGED,
        result=status.value
    )

def create_runway_b_status_event(status: RunwayStatus) -> EventMessage:
    return EventMessage(
        type="event",
        event=EventType.RWY_B_STATUS_CHANGED,
        result=status.value
    )

# 명령 생성 편의 함수들
def create_bird_risk_inquiry() -> CommandMessage:
    return CommandMessage(
        type="command",
        command=CommandType.BR_INQ
    )

def create_runway_a_status_inquiry() -> CommandMessage:
    return CommandMessage(
        type="command",
        command=CommandType.RWY_A_STATUS
    )

def create_runway_b_status_inquiry() -> CommandMessage:
    return CommandMessage(
        type="command",
        command=CommandType.RWY_B_STATUS
    )

def create_runway_availability_inquiry() -> CommandMessage:
    return CommandMessage(
        type="command",
        command=CommandType.RWY_AVAIL_INQ
    )

# 응답 생성 편의 함수들
def create_bird_risk_response(risk_level: BirdRiskLevel) -> ResponseMessage:
    return ResponseMessage(
        type="response",
        command=CommandType.BR_INQ,
        result=risk_level.value
    )

def create_runway_a_status_response(status: RunwayStatus) -> ResponseMessage:
    return ResponseMessage(
        type="response",
        command=CommandType.RWY_A_STATUS,
        result=status.value
    )

def create_runway_b_status_response(status: RunwayStatus) -> ResponseMessage:
    return ResponseMessage(
        type="response",
        command=CommandType.RWY_B_STATUS,
        result=status.value
    )

def create_runway_availability_response(availability: RunwayAvailability) -> ResponseMessage:
    return ResponseMessage(
        type="response",
        command=CommandType.RWY_AVAIL_INQ,
        result=availability.value
    ) 