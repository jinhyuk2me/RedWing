from typing import Dict, Any, Optional

class EventProcessor:
    """
    이벤트 메시지 처리 및 변환
    
    수신된 이벤트 메시지를 분석하고 적절한 형태로 변환합니다.
    """
    
    def __init__(self):
        """이벤트 프로세서 초기화"""
        # 이벤트 타입별 처리 규칙
        self.event_type_mapping = {
            "BR_CHANGED": "bird_risk",
            "RWY_A_STATUS_CHANGED": "runway_alpha",
            "RWY_B_STATUS_CHANGED": "runway_bravo",
            "RUNWAY_ALPHA_STATUS_CHANGED": "runway_alpha",
            "RUNWAY_BRAVO_STATUS_CHANGED": "runway_bravo"
        }
        
        # 결과 코드 매핑
        self.result_mapping = {
            # 조류 위험도
            "BR_LOW": "NORMAL",
            "BR_MEDIUM": "CAUTION",
            "BR_HIGH": "WARNING",
            
            # 활주로 상태
            "CLEAR": "CLEAR",
            "BLOCKED": "BLOCKED",
            "WARNING": "WARNING"
        }
        
        print("[EventProcessor] 초기화 완료")
    
    def process_event_message(self, event_message: dict) -> Dict[str, Any]:
        """
        이벤트 메시지 처리
        
        Args:
            event_message: 원본 이벤트 메시지
            
        Returns:
            처리된 이벤트 데이터
        """
        try:
            event_name = event_message.get("event", "UNKNOWN")
            result = event_message.get("result", "UNKNOWN")
            timestamp = event_message.get("timestamp")
            
            # 이벤트 타입 결정
            event_type = self.event_type_mapping.get(event_name, "unknown")
            
            # 결과 값 변환
            processed_result = self.result_mapping.get(result, result)
            
            processed_event = {
                "event_name": event_name,
                "event_type": event_type,
                "result": processed_result,
                "original_result": result,
                "timestamp": timestamp,
                "raw_message": event_message
            }
            
            print(f"[EventProcessor] 이벤트 처리: {event_name} → {event_type} ({processed_result})")
            return processed_event
            
        except Exception as e:
            print(f"[EventProcessor] 이벤트 처리 오류: {e}")
            return {
                "event_name": "ERROR",
                "event_type": "error",
                "result": "PROCESSING_ERROR",
                "error": str(e),
                "raw_message": event_message
            }
    
    def get_event_description(self, event_type: str, result: str) -> str:
        """
        이벤트 설명 생성
        
        Args:
            event_type: 이벤트 타입
            result: 결과 값
            
        Returns:
            이벤트 설명 문자열
        """
        descriptions = {
            "bird_risk": {
                "NORMAL": "조류 위험도가 낮음으로 변경되었습니다",
                "CAUTION": "조류 위험도가 보통으로 변경되었습니다",
                "WARNING": "조류 위험도가 높음으로 변경되었습니다"
            },
            "runway_alpha": {
                "CLEAR": "활주로 알파가 사용 가능 상태로 변경되었습니다",
                "BLOCKED": "활주로 알파가 차단되었습니다",
                "WARNING": "활주로 알파에 경고가 발생했습니다"
            },
            "runway_bravo": {
                "CLEAR": "활주로 브라보가 사용 가능 상태로 변경되었습니다",
                "BLOCKED": "활주로 브라보가 차단되었습니다",
                "WARNING": "활주로 브라보에 경고가 발생했습니다"
            }
        }
        
        return descriptions.get(event_type, {}).get(result, f"{event_type} 이벤트: {result}")
    
    def get_priority_level(self, event_type: str, result: str) -> int:
        """
        이벤트 우선순위 결정
        
        Args:
            event_type: 이벤트 타입
            result: 결과 값
            
        Returns:
            우선순위 (1: 높음, 2: 보통, 3: 낮음)
        """
        priority_rules = {
            "bird_risk": {
                "WARNING": 1,   # 높은 조류 위험도 - 최우선
                "CAUTION": 2,   # 보통 조류 위험도 - 보통
                "NORMAL": 3     # 낮은 조류 위험도 - 낮음
            },
            "runway_alpha": {
                "WARNING": 1,   # 활주로 경고 - 최우선
                "BLOCKED": 1,   # 활주로 차단 - 최우선
                "CLEAR": 3      # 활주로 정상 - 낮음
            },
            "runway_bravo": {
                "WARNING": 1,   # 활주로 경고 - 최우선
                "BLOCKED": 1,   # 활주로 차단 - 최우선
                "CLEAR": 3      # 활주로 정상 - 낮음
            }
        }
        
        return priority_rules.get(event_type, {}).get(result, 2)
    
    def should_trigger_tts(self, event_type: str, result: str) -> bool:
        """
        TTS 알림 필요 여부 결정
        
        Args:
            event_type: 이벤트 타입
            result: 결과 값
            
        Returns:
            TTS 알림 필요 여부
        """
        # 모든 이벤트에 대해 TTS 알림 (필요시 조건 추가)
        tts_rules = {
            "bird_risk": ["WARNING", "CAUTION", "NORMAL"],
            "runway_alpha": ["WARNING", "BLOCKED", "CLEAR"],
            "runway_bravo": ["WARNING", "BLOCKED", "CLEAR"]
        }
        
        return result in tts_rules.get(event_type, [])
    
    def format_for_display(self, processed_event: Dict[str, Any]) -> str:
        """
        UI 표시용 이벤트 포맷팅
        
        Args:
            processed_event: 처리된 이벤트 데이터
            
        Returns:
            표시용 문자열
        """
        event_type = processed_event.get("event_type", "unknown")
        result = processed_event.get("result", "UNKNOWN")
        timestamp = processed_event.get("timestamp", "")
        
        # 이벤트 아이콘
        icons = {
            "bird_risk": "🦅",
            "runway_alpha": "🛬",
            "runway_bravo": "🛬",
            "unknown": "📢"
        }
        
        icon = icons.get(event_type, "📢")
        description = self.get_event_description(event_type, result)
        
        if timestamp:
            return f"{icon} [{timestamp}] {description}"
        else:
            return f"{icon} {description}"
    
    def get_supported_events(self) -> list:
        """
        지원하는 이벤트 목록 반환
        
        Returns:
            지원하는 이벤트 이름 리스트
        """
        return list(self.event_type_mapping.keys()) 