"""
세션 처리 패키지

이 패키지는 음성 상호작용 세션의 라이프사이클을 관리합니다:
- 세션 생성 및 관리
- 상호작용 로그 기록
- 세션 통계 및 분석
- 로그 검색 및 정리
"""

from .session_manager import SessionManager, InteractionLog

# 편의를 위한 별칭
SessionHandler = SessionManager

__all__ = [
    'SessionManager',
    'InteractionLog',
    'SessionHandler'
] 