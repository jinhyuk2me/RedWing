import random
import time
import threading
from typing import Dict, Any, Optional, Tuple, Callable
from datetime import datetime

class TCPSimulator:
    """
    TCP 서버 시뮬레이터 (TCP 프로토콜 명세 준수 + 자동 이벤트 생성)
    
    실제 TCP 서버의 동작을 시뮬레이션하며, 다음 용도로 사용됩니다:
    1. 서버 연결 실패 시 폴백 메커니즘
    2. 개발 및 테스트 환경
    3. 오프라인 모드 지원
    4. 자동 이벤트 생성 및 브로드캐스트
    """
    
    def __init__(self):
        # TCP 프로토콜 기준 명령어 매핑
        self.command_mapping = {
            "BR_INQ": "BR_INQ",
            "RWY_A_STATUS": "RWY_A_STATUS",
            "RWY_B_STATUS": "RWY_B_STATUS", 
            "RWY_AVAIL_INQ": "RWY_AVAIL_INQ"
        }
        
        # TCP 프로토콜 기준 조류 위험도 로테이션 데이터
        self.bird_rotation_states = [
            {"risk_level": "LOW", "result": "BR_LOW"},
            {"risk_level": "MEDIUM", "result": "BR_MEDIUM"}, 
            {"risk_level": "HIGH", "result": "BR_HIGH"},
            {"risk_level": "LOW", "result": "BR_LOW"}  # 다시 LOW로 순환
        ]
        
        # TCP 프로토콜 기준 활주로 상태 로테이션 (CLEAR/WARNING)
        self.runway_alpha_rotation_states = [
            {"status": "CLEAR", "result": "CLEAR"},
            {"status": "WARNING", "result": "WARNING"},  # BLOCKED → WARNING로 수정
            {"status": "CLEAR", "result": "CLEAR"},
            {"status": "WARNING", "result": "WARNING"}
        ]
        
        self.runway_bravo_rotation_states = [
            {"status": "WARNING", "result": "WARNING"},  # BLOCKED → WARNING로 수정
            {"status": "CLEAR", "result": "CLEAR"},
            {"status": "WARNING", "result": "WARNING"},
            {"status": "CLEAR", "result": "CLEAR"}
        ]
        
        # 로테이션 인덱스 초기화
        self.bird_rotation_index = 0
        self.runway_alpha_rotation_index = 0
        self.runway_bravo_rotation_index = 0
        
        # 활주로 데이터 (TCP 프로토콜 기준)
        self.runway_data = {
            "RWY-ALPHA": {
                "status": "CLEAR",
                "risk_level": "LOW", 
                "condition": "DRY",
                "wind": "270/08KT",
                "visibility": "10KM"
            },
            "RWY-BRAVO": {
                "status": "WARNING",  # 초기 상태 - 주의 (BLOCKED → WARNING)
                "risk_level": "MEDIUM",
                "condition": "WET", 
                "wind": "270/12KT",
                "visibility": "8KM"
            }
        }
        
        # TCP 프로토콜 기준 조류 위험도 시나리오
        self.risk_scenarios = [
            {
                "risk_level": "LOW",
                "result": "BR_LOW",
                "bird_count": random.randint(1, 3),
                "species": ["sparrows"],
                "areas": ["taxiway area"]
            },
            {
                "risk_level": "MEDIUM", 
                "result": "BR_MEDIUM",
                "bird_count": random.randint(4, 8),
                "species": ["seagulls", "pigeons"],
                "areas": ["runway vicinity", "approach path"]
            },
            {
                "risk_level": "HIGH",
                "result": "BR_HIGH",
                "bird_count": random.randint(10, 20),
                "species": ["geese", "eagles", "hawks"],
                "areas": ["runway vicinity", "approach path", "departure corridor"]
            }
        ]
        
        # 초기 조류 위험도 (LOW 레벨로 시작)
        self.bird_data = self.risk_scenarios[0].copy()
        self.bird_last_update = datetime.now()
        
        # 🆕 자동 이벤트 생성 관련
        self.auto_events_enabled = False
        self.gui_ready = False  # GUI 준비 완료 여부
        self.event_handlers: Dict[str, Callable] = {}
        self.event_thread: Optional[threading.Thread] = None
        self.event_intervals = {
            "BR_CHANGED": 90.0,          # 90초마다 조류 위험도 변화 (30초 간격으로 순환)
            "RWY_A_STATUS_CHANGED": 90.0, # 90초마다 활주로 A 상태 변화
            "RWY_B_STATUS_CHANGED": 90.0  # 90초마다 활주로 B 상태 변화
        }
        self.last_event_times = {
            "BR_CHANGED": float('inf'),  # 🔧 무한대로 설정 (GUI 준비 전까지 이벤트 생성 방지)
            "RWY_A_STATUS_CHANGED": float('inf'),
            "RWY_B_STATUS_CHANGED": float('inf')
        }
        
        print(f"[TCPSimulator] 🦅 조류 시나리오: {self.bird_data['risk_level']} 위험도 → {self.bird_data['result']}")
        print(f"[TCPSimulator] 🛬 활주로 상태: ALPHA({self.runway_data['RWY-ALPHA']['status']}), BRAVO({self.runway_data['RWY-BRAVO']['status']})")
        print(f"[TCPSimulator] 🔄 TCP 프로토콜 명세 준수 모드 (CLEAR/WARNING)")
    
    # 🆕 자동 이벤트 생성 기능
    def start_auto_events(self):
        """자동 이벤트 생성 시작"""
        if self.auto_events_enabled:
            print("[TCPSimulator] ⚠️ 자동 이벤트가 이미 실행 중입니다")
            return
        
        self.auto_events_enabled = True
        self.event_thread = threading.Thread(target=self._auto_event_loop, daemon=True)
        self.event_thread.start()
        print("[TCPSimulator] 🚀 자동 이벤트 생성 시작 (GUI 준비 완료 대기 중)")
    
    def stop_auto_events(self):
        """자동 이벤트 생성 중지"""
        self.auto_events_enabled = False
        if self.event_thread and self.event_thread.is_alive():
            self.event_thread.join(timeout=2)
        print("[TCPSimulator] ⏹️ 자동 이벤트 생성 중지")
    
    def register_event_handler(self, event_type: str, handler: Callable):
        """이벤트 핸들러 등록"""
        self.event_handlers[event_type] = handler
        print(f"[TCPSimulator] 📝 이벤트 핸들러 등록: {event_type}")
    
    def set_gui_ready(self):
        """GUI 준비 완료 신호"""
        self.gui_ready = True
        # 🔧 GUI 준비 완료 시점에서 이벤트 타이머 초기화 (30초 간격으로 순차 시작)
        current_time = time.time()
        self.last_event_times = {
            "BR_CHANGED": current_time,                    # 즉시 시작 (90초 후 다음 이벤트)
            "RWY_A_STATUS_CHANGED": current_time - 60.0,   # 60초 앞서 시작 (30초 후 첫 이벤트)
            "RWY_B_STATUS_CHANGED": current_time - 30.0    # 30초 앞서 시작 (60초 후 첫 이벤트)
        }
        print("[TCPSimulator] 📢 GUI 준비 완료 신호 수신 - 이벤트 타이머 순차 초기화 (30초 간격으로 순환)")
    
    def _auto_event_loop(self):
        """자동 이벤트 생성 루프"""
        print("[TCPSimulator] 🔄 자동 이벤트 루프 시작")
        
        # GUI 준비 완료 대기
        while self.auto_events_enabled and not self.gui_ready:
            print("[TCPSimulator] ⏳ GUI 준비 완료 대기 중...")
            time.sleep(2.0)  # 2초마다 체크
        
        if not self.auto_events_enabled:
            print("[TCPSimulator] 🔄 GUI 준비 전에 자동 이벤트 루프 종료")
            return
            
        print("[TCPSimulator] ✅ GUI 준비 완료 - 자동 이벤트 생성 시작")
        
        while self.auto_events_enabled:
            try:
                current_time = time.time()
                
                # 각 이벤트 타입별로 시간 간격 체크
                for event_type, interval in self.event_intervals.items():
                    last_time = self.last_event_times[event_type]
                    
                    if current_time - last_time >= interval:
                        # 이벤트 생성 및 전송
                        event_data = self.generate_event(event_type)
                        if event_data and event_type in self.event_handlers:
                            try:
                                self.event_handlers[event_type](event_data)
                                print(f"[TCPSimulator] 📤 자동 이벤트 전송: {event_type} = {event_data.get('result')}")
                            except Exception as e:
                                print(f"[TCPSimulator] ❌ 이벤트 핸들러 오류: {e}")
                        
                        self.last_event_times[event_type] = current_time
                
                # 1초 대기
                time.sleep(1.0)
                
            except Exception as e:
                print(f"[TCPSimulator] ❌ 자동 이벤트 루프 오류: {e}")
                time.sleep(5.0)
        
        print("[TCPSimulator] 🔄 자동 이벤트 루프 종료")
    
    def _rotate_bird_state(self):
        """조류 위험도 로테이션 (TCP 프로토콜 기준)"""
        self.bird_rotation_index = (self.bird_rotation_index + 1) % len(self.bird_rotation_states)
        new_state = self.bird_rotation_states[self.bird_rotation_index]
        
        old_level = self.bird_data['risk_level']
        
        # 새로운 상태로 업데이트
        self.bird_data = self.risk_scenarios[self.bird_rotation_index % len(self.risk_scenarios)].copy()
        self.bird_data['risk_level'] = new_state['risk_level']
        self.bird_data['result'] = new_state['result']
        
        print(f"[TCPSimulator] 🦅 BIRD 로테이션: {old_level} → {self.bird_data['risk_level']} ({self.bird_data['result']})")
    
    def _rotate_runway_state(self, runway_id):
        """활주로 상태 로테이션 (TCP 프로토콜 기준: CLEAR/WARNING)"""
        if runway_id == "RWY-ALPHA":
            self.runway_alpha_rotation_index = (self.runway_alpha_rotation_index + 1) % len(self.runway_alpha_rotation_states)
            new_state = self.runway_alpha_rotation_states[self.runway_alpha_rotation_index]
            old_status = self.runway_data["RWY-ALPHA"]["status"]
            self.runway_data["RWY-ALPHA"]["status"] = new_state["status"]
            print(f"[TCPSimulator] 🛬 RWY-ALPHA 로테이션: {old_status} → {new_state['status']} ({new_state['result']})")
        elif runway_id == "RWY-BRAVO":
            self.runway_bravo_rotation_index = (self.runway_bravo_rotation_index + 1) % len(self.runway_bravo_rotation_states)
            new_state = self.runway_bravo_rotation_states[self.runway_bravo_rotation_index]
            old_status = self.runway_data["RWY-BRAVO"]["status"]
            self.runway_data["RWY-BRAVO"]["status"] = new_state["status"]
            print(f"[TCPSimulator] 🛬 RWY-BRAVO 로테이션: {old_status} → {new_state['status']} ({new_state['result']})")
    
    def process_query(self, intent: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        TCP 프로토콜 기준 시뮬레이션 질의 처리
        
        Args:
            intent: 질의 인텐트 (bird_risk_inquiry, runway_alpha_status 등)
            parameters: 질의 파라미터
            
        Returns:
            TCP 프로토콜 형식의 시뮬레이션 응답 데이터
        """
        if intent == "bird_risk_inquiry":
            # 🔧 중복 로테이션 방지: 현재 상태만 반환
            print(f"[TCPSimulator] 🦅 BIRD 현재 상태: {self.bird_data['risk_level']} → {self.bird_data['result']}")
            
            # TCP 프로토콜 기준 조류 위험도 응답
            return {
                "type": "response",
                "command": "BR_INQ",
                "result": self.bird_data["result"],  # BR_HIGH, BR_MEDIUM, BR_LOW
                "source": "simulator"
            }
            
        elif intent == "runway_alpha_status":
            # 🔧 중복 로테이션 방지: 현재 상태만 반환
            runway_info = self.runway_data["RWY-ALPHA"]
            status = runway_info["status"]
            result = "CLEAR" if status == "CLEAR" else "WARNING"
            
            print(f"[TCPSimulator] 🛬 RWY-ALPHA 현재 상태: {status} → {result}")
            
            return {
                "type": "response",
                "command": "RWY_A_STATUS",
                "result": result,  # CLEAR 또는 WARNING
                "source": "simulator"
            }
            
        elif intent == "runway_bravo_status":
            # 🔧 중복 로테이션 방지: 현재 상태만 반환
            runway_info = self.runway_data["RWY-BRAVO"]
            status = runway_info["status"]
            result = "CLEAR" if status == "CLEAR" else "WARNING"
            
            print(f"[TCPSimulator] 🛬 RWY-BRAVO 현재 상태: {status} → {result}")
            
            return {
                "type": "response",
                "command": "RWY_B_STATUS",
                "result": result,  # CLEAR 또는 WARNING
                "source": "simulator"
            }
            
        elif intent == "available_runway_inquiry":
            available_runways = [rwy for rwy, info in self.runway_data.items() if info["status"] == "CLEAR"]
            
            # TCP 프로토콜 기준 사용 가능한 활주로 응답 (ALL/A_ONLY/B_ONLY/NONE)
            if len(available_runways) == 0:
                result = "NONE"
            elif len(available_runways) >= 2:
                result = "ALL"
            elif len(available_runways) == 1:
                if "RWY-ALPHA" in available_runways:
                    result = "A_ONLY"
                elif "RWY-BRAVO" in available_runways:
                    result = "B_ONLY"
                else:
                    result = "A_ONLY"  # 기본값
            else:
                result = "ALL"
            
            print(f"[TCPSimulator] 🛬 사용 가능한 활주로: {available_runways} → {result}")
            
            return {
                "type": "response",
                "command": "RWY_AVAIL_INQ",
                "result": result,  # TCP 프로토콜 기준 응답 (ALL/A_ONLY/B_ONLY/NONE)
                "source": "simulator"
            }
        
        else:
            return {
                "type": "response",
                "command": "UNKNOWN",
                "result": "UNRECOGNIZED_COMMAND",
                "source": "simulator"
            }
    
    def send_command(self, command: str) -> Tuple[bool, Dict[str, Any]]:
        """
        TCP 클라이언트 호환성을 위한 명령어 처리 메서드
        
        Args:
            command: TCP 명령어 (BIRD_RISK_INQUIRY, RUNWAY_ALPHA_STATUS 등)
            
        Returns:
            (성공 여부, 응답 데이터) 튜플
        """
        # 명령어를 인텐트로 변환
        intent_mapping = {
            "BR_INQ": "bird_risk_inquiry",
            "RWY_A_STATUS": "runway_alpha_status",
            "RWY_B_STATUS": "runway_bravo_status",
            "RWY_AVAIL_INQ": "available_runway_inquiry"
        }
        
        intent = intent_mapping.get(command, "unknown")
        
        try:
            response = self.process_query(intent, {})
            return True, response
        except Exception as e:
            print(f"[TCPSimulator] ❌ 명령어 처리 오류: {e}")
            return False, {
                "type": "response",
                "command": command,
                "result": "ERROR",
                "source": "simulator",
                "error": str(e)
            }
    
    def force_rotate_state(self, state_type: str):
        """
        강제로 상태 로테이션 (테스트 또는 수동 변경용)
        
        Args:
            state_type: "bird", "runway_alpha", "runway_bravo"
        """
        if state_type == "bird":
            self._rotate_bird_state()
        elif state_type == "runway_alpha":
            self._rotate_runway_state("RWY-ALPHA")
        elif state_type == "runway_bravo":
            self._rotate_runway_state("RWY-BRAVO")
        else:
            print(f"[TCPSimulator] ❌ 알 수 없는 상태 타입: {state_type}")
    
    def generate_event(self, event_type: str) -> Optional[Dict[str, Any]]:
        """
        이벤트 생성 (TCP 프로토콜 명세 준수)
        
        Args:
            event_type: 이벤트 타입 (BR_CHANGED, RWY_A_STATUS_CHANGED 등)
            
        Returns:
            이벤트 데이터 또는 None
        """
        if event_type == "BR_CHANGED":
            self._rotate_bird_state()
            return {
                "type": "event",
                "event": "BR_CHANGED",
                "result": self.bird_data["result"]  # BR_LOW, BR_MEDIUM, BR_HIGH
            }
        elif event_type == "RWY_A_STATUS_CHANGED":  # TCP 명세 준수
            self._rotate_runway_state("RWY-ALPHA")
            return {
                "type": "event",
                "event": "RWY_A_STATUS_CHANGED",
                "result": self.runway_data["RWY-ALPHA"]["status"]  # CLEAR, WARNING
            }
        elif event_type == "RWY_B_STATUS_CHANGED":  # TCP 명세 준수
            self._rotate_runway_state("RWY-BRAVO")
            return {
                "type": "event",
                "event": "RWY_B_STATUS_CHANGED",
                "result": self.runway_data["RWY-BRAVO"]["status"]  # CLEAR, WARNING
            }
        return None 