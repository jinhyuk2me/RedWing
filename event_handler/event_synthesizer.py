from typing import Dict, Any, Optional, List
from datetime import datetime

class EventTTS:
    """
    이벤트 TTS 처리
    
    이벤트 발생 시 적절한 TTS 메시지를 생성하고 재생합니다.
    """
    
    def __init__(self, tts_engine=None):
        """
        이벤트 TTS 초기화
        
        Args:
            tts_engine: TTS 엔진 인스턴스
        """
        self.tts_engine = tts_engine
        self.gui_callback = None  # GUI 업데이트 콜백 함수
        self.recording_checker = None  # 녹음 상태 체크 콜백 함수
        
        # 🇺🇸 영어 이벤트 TTS 메시지 템플릿 (TCP 프로토콜 기준)
        self.event_tts_templates = {
            "en": {
                "bird_risk": {
                    "HIGH": "WARNING. Bird risk high. Advise extreme vigilance.",
                    "MEDIUM": "CAUTION. Bird activity reported. Maintain vigilance on approach.",
                    "LOW": "CLEAR. Minimal bird activity. Normal operations approved.",
                    "CAUTION": "CAUTION. Bird activity reported. Maintain vigilance on approach.",
                    "CLEAR": "CLEAR. Minimal bird activity. Normal operations approved.",
                    "WARNING": "WARNING. Bird risk high. Advise extreme vigilance.",
                    "NORMAL": "CLEAR. Minimal bird activity. Normal operations approved.",
                    "BR_HIGH": "WARNING. Bird risk high. Advise extreme vigilance.",
                    "BR_MEDIUM": "CAUTION. Bird activity reported. Maintain vigilance on approach.",
                    "BR_LOW": "CLEAR. Minimal bird activity. Normal operations approved."
                },
                "runway_alpha": {
                    "CLEAR": "CLEAR. Runway Alpha operational. Normal landing and takeoff procedures approved.",
                    "WARNING": "WARNING. Runway Alpha advisory. Proceed with vigilance.",
                    "BLOCKED": "WARNING. Runway Alpha advisory. Proceed with vigilance."  # 호환성을 위해 유지
                },
                "runway_bravo": {
                    "CLEAR": "CLEAR. Runway Bravo operational. Normal landing and takeoff procedures approved.",
                    "WARNING": "WARNING. Runway Bravo advisory. Proceed with vigilance.",
                    "BLOCKED": "WARNING. Runway Bravo advisory. Proceed with vigilance."  # 호환성을 위해 유지
                }
            },
            "ko": {
                "bird_risk": {
                    "HIGH": "경고. 조류 위험도 높음. 극도로 주의하시기 바랍니다.",
                    "MEDIUM": "주의. 조류 활동이 보고되었습니다. 접근 시 주의를 유지하십시오.",
                    "LOW": "정상. 조류 활동이 최소한입니다. 정상 운항이 승인되었습니다.",
                    "CAUTION": "주의. 조류 활동이 보고되었습니다. 접근 시 주의를 유지하십시오.",
                    "CLEAR": "정상. 조류 활동이 최소한입니다. 정상 운항이 승인되었습니다.",
                    "WARNING": "경고. 조류 위험도 높음. 극도로 주의하시기 바랍니다.",
                    "NORMAL": "정상. 조류 활동이 최소한입니다. 정상 운항이 승인되었습니다.",
                    "BR_HIGH": "경고. 조류 위험도 높음. 극도로 주의하시기 바랍니다.",
                    "BR_MEDIUM": "주의. 조류 활동이 보고되었습니다. 접근 시 주의를 유지하십시오.",
                    "BR_LOW": "정상. 조류 활동이 최소한입니다. 정상 운항이 승인되었습니다."
                },
                "runway_alpha": {
                    "CLEAR": "정상. 알파 활주로 운영 중입니다. 정상 착륙 및 이륙 절차가 승인되었습니다.",
                    "WARNING": "경고. 알파 활주로 주의 요망. 주의하여 진행 바랍니다.",
                    "BLOCKED": "경고. 알파 활주로 주의 요망. 주의하여 진행 바랍니다."  # 호환성을 위해 유지
                },
                "runway_bravo": {
                    "CLEAR": "정상. 브라보 활주로 운영 중입니다. 정상 착륙 및 이륙 절차가 승인되었습니다.",
                    "WARNING": "경고. 브라보 활주로 주의 요망. 주의하여 진행 바랍니다.",
                    "BLOCKED": "경고. 브라보 활주로 주의 요망. 주의하여 진행 바랍니다."  # 호환성을 위해 유지
                }
            }
        }
        
        # 한국어 TTS 메시지 템플릿 (필요시 사용)
        self.tts_templates_ko = {
            "bird_risk": {
                "WARNING": "경고. 조류 위험도 높음. 주의 바람.",
                "CAUTION": "주의. 활주로 근처에서 조류 활동 보고됨.",
                "NORMAL": "현재 활주로에 조류 활동 없음. 정상.",
                "UNKNOWN": "조류 활동 상황 불명. 관제탑에 연락 바람.",
                "ERROR": "조류 감시 시스템 고장. 관제탑에 연락 바람."
            },
            "runway_alpha": {
                "WARNING": "경고. 활주로 알파 주의 요망. 주의하여 진행 바람.",
                "CLEAR": "활주로 알파 정상. 운항 허가.",
                "BLOCKED": "경고. 활주로 알파 주의 요망. 주의하여 진행 바람.",
                "UNKNOWN": "활주로 알파 상태 불명. 관제탑에 연락 바람.",
                "ERROR": "활주로 알파 감시 시스템 고장."
            },
            "runway_bravo": {
                "WARNING": "경고. 활주로 브라보 주의 요망. 주의하여 진행 바람.",
                "CLEAR": "활주로 브라보 정상. 운항 허가.",
                "BLOCKED": "경고. 활주로 브라보 주의 요망. 주의하여 진행 바람.",
                "UNKNOWN": "활주로 브라보 상태 불명. 관제탑에 연락 바람.",
                "ERROR": "활주로 브라보 감시 시스템 고장."
            },
            "unknown": {
                "UNKNOWN": "시스템 상태 불명. 관제탑에 연락 바람.",
                "ERROR": "시스템 고장 감지됨. 즉시 관제탑에 연락 바람."
            }
        }
        
        print("[EventTTS] 초기화 완료")
    
    def set_tts_engine(self, tts_engine):
        """
        TTS 엔진 설정
        
        Args:
            tts_engine: TTS 엔진 인스턴스
        """
        self.tts_engine = tts_engine
        print("[EventTTS] TTS 엔진 설정 완료")
    
    def set_gui_callback(self, callback):
        """
        GUI 업데이트 콜백 설정
        
        Args:
            callback: GUI 업데이트 함수 (message: str) -> None
        """
        self.gui_callback = callback
        print("[EventTTS] GUI 콜백 설정 완료")
    
    def set_recording_checker(self, checker):
        """
        녹음 상태 체크 콜백 설정
        
        Args:
            checker: 녹음 상태 체크 함수 () -> bool (True면 녹음 중)
        """
        self.recording_checker = checker
        print("[EventTTS] 녹음 상태 체크 콜백 설정 완료")
    
    def play_event_notification(self, event_type: str, result: str, language: str = "en"):
        """
        이벤트 TTS 알림 재생
        
        Args:
            event_type: 이벤트 타입 (bird_risk, runway_alpha, runway_bravo)
            result: 결과 값 (HIGH, MEDIUM, LOW, WARNING, CLEAR)
            language: 언어 ("en" 또는 "ko")
        """
        if not self.tts_engine:
            print("[EventTTS] ⚠️ TTS 엔진이 설정되지 않음")
            return
        
        # 🔧 녹음 중이면 이벤트 TTS 완전 차단
        if self.recording_checker and self.recording_checker():
            print(f"[EventTTS] 🚫 녹음 중이므로 이벤트 TTS 완전 차단: {event_type} - {result}")
            return
        
        try:
            # TTS 메시지 생성
            tts_message = self.get_tts_message(event_type, result, language)
            
            if not tts_message:
                print(f"[EventTTS] ⚠️ TTS 메시지를 찾을 수 없음: {event_type} - {result}")
                return
            
            # GUI 콜백 호출 (TTS 재생 전에 먼저 GUI 업데이트)
            if self.gui_callback:
                print(f"[EventTTS] 🔔 GUI 콜백 호출: '{tts_message[:50]}...'")
                self.gui_callback(tts_message)
            
            # TTS 엔진의 speak_event 메서드 사용 (충돌 방지)
            if hasattr(self.tts_engine, 'speak_event'):
                self.tts_engine.speak_event(tts_message, language=language)
                print(f"[EventTTS] ✅ 이벤트 TTS 재생: {event_type} - {result}")
            else:
                # 일반 speak 메서드 사용 (폴백)
                self.tts_engine.speak(tts_message, tts_type="event", language=language)
                print(f"[EventTTS] ✅ 이벤트 TTS 재생 (폴백): {event_type} - {result}")
                
        except Exception as e:
            print(f"[EventTTS] ❌ TTS 재생 오류: {e}")
    
    def get_tts_message(self, event_type: str, result: str, language: str = "en") -> str:
        """
        이벤트 타입과 결과에 따른 TTS 메시지 생성 (TCP 프로토콜 기준)
        
        Args:
            event_type: 이벤트 타입 (bird_risk, runway_alpha, runway_bravo)
            result: 결과 값 (HIGH/MEDIUM/LOW, CLEAR/WARNING)
            language: 언어 ("en" 또는 "ko")
            
        Returns:
            TTS 메시지 문자열
        """
        templates = self.event_tts_templates.get(language, self.event_tts_templates.get("en", {}))
        
        # 직접 매칭 시도
        if event_type in templates and result in templates[event_type]:
            return templates[event_type][result]
        
        # 기본 메시지 (항공 관제 형식으로 수정)
        if language == "ko":
            return f"알림: {event_type} 상태 변경. 주의 바랍니다."
        else:
            # 이벤트 타입별 기본 메시지
            if event_type == "bird_risk":
                return f"ADVISORY. Bird activity level {result}. Maintain awareness."
            elif event_type == "runway_alpha":
                return f"ADVISORY. Runway Alpha status {result}. Proceed with caution."
            elif event_type == "runway_bravo":
                return f"ADVISORY. Runway Bravo status {result}. Proceed with caution."
            else:
                return f"ADVISORY. {event_type} status {result}. Maintain awareness."
    
    def get_priority_delay(self, event_type: str, result: str) -> float:
        """
        이벤트 우선순위에 따른 지연 시간 계산
        
        Args:
            event_type: 이벤트 타입
            result: 결과 값
            
        Returns:
            지연 시간 (초)
        """
        # 높은 우선순위 이벤트는 즉시 재생
        high_priority = {
            "bird_risk": ["WARNING"],  # WARNING만 최우선으로 변경
            "runway_alpha": ["WARNING", "BLOCKED"],
            "runway_bravo": ["WARNING", "BLOCKED"]
        }
        
        if result in high_priority.get(event_type, []):
            return 0.0  # 즉시 재생
        else:
            return 0.5  # 0.5초 지연
    
    def format_event_for_log(self, event_type: str, result: str, language: str = "en") -> str:
        """
        로그용 이벤트 포맷팅
        
        Args:
            event_type: 이벤트 타입
            result: 결과 값
            language: 언어
            
        Returns:
            로그용 문자열
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        tts_message = self.get_tts_message(event_type, result, language)
        
        return f"[{timestamp}] 🔔 EVENT: {tts_message}"
    
    def should_interrupt_current_tts(self, event_type: str, result: str) -> bool:
        """
        현재 TTS를 중단하고 이벤트 TTS를 재생할지 결정
        
        Args:
            event_type: 이벤트 타입
            result: 결과 값
            
        Returns:
            중단 여부
        """
        # 높은 우선순위 이벤트는 현재 TTS를 중단
        interrupt_events = {
            "bird_risk": ["WARNING"],  # WARNING만 중단으로 변경
            "runway_alpha": ["WARNING", "BLOCKED"],
            "runway_bravo": ["WARNING", "BLOCKED"]
        }
        
        return result in interrupt_events.get(event_type, [])
    
    def get_available_languages(self) -> list:
        """
        지원하는 언어 목록 반환
        
        Returns:
            지원하는 언어 코드 리스트
        """
        return ["en", "ko"]
    
    def get_supported_event_types(self, language: str = "en") -> List[str]:
        """
        지원하는 이벤트 타입 목록 반환 (TCP 프로토콜 기준)
        
        Args:
            language: 언어
            
        Returns:
            지원하는 이벤트 타입 리스트
        """
        templates = self.event_tts_templates.get(language, self.event_tts_templates.get("en", {}))
        return list(templates.keys())
    
    def add_custom_template(self, event_type: str, result: str, message: str, language: str = "en"):
        """
        사용자 정의 TTS 템플릿 추가 (TCP 프로토콜 기준)
        
        Args:
            event_type: 이벤트 타입
            result: 결과 값
            message: TTS 메시지
            language: 언어
        """
        if language not in self.event_tts_templates:
            self.event_tts_templates[language] = {}
        
        templates = self.event_tts_templates[language]
        
        if event_type not in templates:
            templates[event_type] = {}
        
        templates[event_type][result] = message
        print(f"[EventTTS] 사용자 정의 템플릿 추가: {language}.{event_type}.{result} = '{message}'") 