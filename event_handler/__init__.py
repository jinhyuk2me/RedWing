"""
이벤트 처리 패키지

이 패키지는 시스템 이벤트의 전체 라이프사이클을 관리합니다:
- 이벤트 연결 및 수신 (event_connector.py)
- 이벤트 메시지 변환 (event_processor.py)
- 이벤트 음성 합성 (event_synthesizer.py)
"""

from .event_connector import EventManager
from .event_processor import EventProcessor
from .event_synthesizer import EventTTS
from .event_models import (
    BirdRiskLevel, RunwayStatus, RunwayAvailability, EventType, CommandType,
    EventMessage, CommandMessage, ResponseMessage,
    create_bird_risk_event, create_runway_a_status_event, create_runway_b_status_event
)

# 편의를 위한 별칭
EventHandler = EventManager

__all__ = [
    'EventManager',
    'EventProcessor',
    'EventTTS',
    'BirdRiskLevel',
    'RunwayStatus',
    'RunwayAvailability',
    'EventType',
    'CommandType',
    'EventMessage',
    'CommandMessage',
    'ResponseMessage',
    'create_bird_risk_event',
    'create_runway_a_status_event',
    'create_runway_b_status_event',
    'EventHandler'
] 