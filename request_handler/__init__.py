"""
요청 처리 패키지

이 패키지는 사용자 요청의 전체 라이프사이클을 관리합니다:
1. 요청 분류 (request_classifier.py) - 사용자 요청을 분류하고 구조화
2. 요청 연결 (request_connector.py) - TCP 서버와의 통신 담당
3. 응답 처리 (request_processor.py) - 서버 응답 처리 및 변환
"""

from .request_analyzer import RequestClassifier
from .request_connector import TCPServerClient
from .request_processor import ResponseProcessor
from .request_models import (
    PilotRequest, PilotResponse, RequestStatus, RequestPriority,
    create_pilot_request, create_pilot_response
)

# 편의를 위한 별칭
RequestParser = RequestClassifier
ServerClient = TCPServerClient
ResponseHandler = ResponseProcessor

__all__ = [
    'RequestClassifier',
    'TCPServerClient', 
    'ResponseProcessor',
    'PilotRequest',
    'PilotResponse',
    'RequestStatus',
    'RequestPriority',
    'create_pilot_request',
    'create_pilot_response',
    'RequestParser',
    'ServerClient',
    'ResponseHandler'
] 