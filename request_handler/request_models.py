from dataclasses import dataclass, field
from typing import Dict, Any
from datetime import datetime
from enum import Enum

class RequestStatus(Enum):
    """요청 처리 상태"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class RequestPriority(Enum):
    """요청 우선순위"""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EMERGENCY = "EMERGENCY"

@dataclass
class PilotRequest:
    """조종사 요청 모델"""
    session_id: str
    callsign: str
    original_text: str
    request_code: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    priority: RequestPriority = RequestPriority.NORMAL
    status: RequestStatus = RequestStatus.PENDING
    confidence_score: float = 0.0
    processing_time: float = 0.0
    
    def __post_init__(self):
        """초기화 후 처리"""
        # 우선순위 자동 설정
        if "emergency" in self.original_text.lower() or "비상" in self.original_text:
            self.priority = RequestPriority.EMERGENCY
        elif "urgent" in self.original_text.lower() or "긴급" in self.original_text:
            self.priority = RequestPriority.HIGH
    
    def set_status(self, status: RequestStatus):
        """상태 변경"""
        self.status = status
    
    def add_parameter(self, key: str, value: Any):
        """파라미터 추가"""
        self.parameters[key] = value
    
    def get_parameter(self, key: str, default: Any = None) -> Any:
        """파라미터 조회"""
        return self.parameters.get(key, default)

@dataclass
class PilotResponse:
    """조종사 응답 모델"""
    session_id: str
    request_code: str
    response_text: str
    response_code: str = "SUCCESS"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    processing_time: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)
    
    def is_success(self) -> bool:
        """성공 응답인지 확인"""
        return self.response_code == "SUCCESS"
    
    def add_data(self, key: str, value: Any):
        """응답 데이터 추가"""
        self.data[key] = value

# 편의 함수들
def create_pilot_request(session_id: str, callsign: str, text: str, 
                        request_code: str, parameters: Dict[str, Any] = None) -> PilotRequest:
    """PilotRequest 생성 편의 함수"""
    return PilotRequest(
        session_id=session_id,
        callsign=callsign,
        original_text=text,
        request_code=request_code,
        parameters=parameters or {}
    )

def create_pilot_response(session_id: str, request_code: str, 
                         response_text: str, processing_time: float = 0.0) -> PilotResponse:
    """PilotResponse 생성 편의 함수"""
    return PilotResponse(
        session_id=session_id,
        request_code=request_code,
        response_text=response_text,
        processing_time=processing_time
    ) 