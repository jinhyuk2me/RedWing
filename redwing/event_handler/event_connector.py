from typing import Dict, Callable, Optional, Any
import json
import time

# 통합된 TCP 클라이언트 사용
from network import TCPClient
from simulator import TCPSimulator

class EventManager:
    """
    이벤트 관리 및 핸들러 등록
    
    TCP 서버로부터 이벤트를 수신하고, 등록된 핸들러에게 전달합니다.
    시뮬레이터 모드에서는 자동 이벤트 생성 기능을 제공합니다.
    """
    
    def __init__(self, server_host: str = "localhost", server_port: int = 5300, use_simulator: bool = True):
        """
        이벤트 매니저 초기화
        
        Args:
            server_host: TCP 서버 호스트
            server_port: TCP 서버 포트
            use_simulator: 연결 실패 시 시뮬레이터 사용 여부
        """
        # 통합된 TCP 클라이언트 사용
        self.tcp_client = TCPClient(server_host, server_port)
        self.use_simulator = use_simulator
        
        # 시뮬레이터 초기화
        if use_simulator:
            self.simulator = TCPSimulator()
        else:
            self.simulator = None
        
        print(f"[EventManager] 초기화 완료: {server_host}:{server_port}")
    
    def connect(self) -> bool:
        """
        TCP 서버에 연결하고 이벤트 수신 시작
        
        Returns:
            연결 성공 여부
        """
        success = self.tcp_client.connect()
        if success:
            print(f"[EventManager] ✅ 서버 연결 성공")
        else:
            print(f"[EventManager] ❌ 서버 연결 실패")
            if self.use_simulator:
                print(f"[EventManager] 🔄 시뮬레이터로 폴백")
                # 🆕 시뮬레이터 자동 이벤트 설정
                self._setup_simulator_events()
        return success
    
    def disconnect(self):
        """서버 연결 해제"""
        self.tcp_client.disconnect()
        
        # 🆕 시뮬레이터 자동 이벤트 중지
        if hasattr(self, 'simulator') and self.simulator:
            self.simulator.stop_auto_events()
        
        print(f"[EventManager] 연결 해제 완료")
    
    def register_handler(self, event_name: str, handler: Callable):
        """
        이벤트 핸들러 등록
        
        Args:
            event_name: 이벤트 이름 (BR_CHANGED, RWY_A_STATUS_CHANGED 등)
            handler: 이벤트 처리 함수 (event_data: dict를 인자로 받음)
        """
        self.tcp_client.register_event_handler(event_name, handler)
        print(f"[EventManager] 이벤트 핸들러 등록: {event_name}")
        
        # 🆕 시뮬레이터에도 핸들러 등록
        if self.use_simulator and self.simulator:
            self.simulator.register_event_handler(event_name, self._handle_simulator_event)
    
    def unregister_handler(self, event_name: str):
        """
        이벤트 핸들러 해제
        
        Args:
            event_name: 이벤트 이름
        """
        self.tcp_client.unregister_event_handler(event_name)
        print(f"[EventManager] 이벤트 핸들러 해제: {event_name}")
    
    def get_registered_events(self) -> list:
        """
        등록된 이벤트 목록 반환
        
        Returns:
            등록된 이벤트 이름 리스트
        """
        return self.tcp_client.get_registered_events()
    
    def is_connected(self) -> bool:
        """
        연결 상태 확인
        
        Returns:
            연결 상태
        """
        return self.tcp_client.is_connected()
    
    def get_status(self) -> Dict[str, Any]:
        """
        이벤트 매니저 상태 정보 반환
        
        Returns:
            상태 정보 딕셔너리
        """
        status = self.tcp_client.get_server_status()
        status["registered_events"] = self.get_registered_events()
        
        # 🆕 시뮬레이터 상태 추가
        if self.use_simulator and self.simulator:
            status["simulator_auto_events"] = getattr(self.simulator, 'auto_events_enabled', False)
            status["simulator_event_intervals"] = getattr(self.simulator, 'event_intervals', {})
        
        return status
    
    def handle_event(self, event_message: dict):
        """
        이벤트 처리
        
        Args:
            event_message: 이벤트 메시지
        """
        try:
            # TCP 서버에서 이벤트 수신
            if self.is_connected():
                self._notify_handlers(event_message)
            elif self.use_simulator and self.simulator:
                # 시뮬레이터에서 이벤트 생성
                event_type = event_message.get("event")
                simulator_event = self.simulator.generate_event(event_type)
                if simulator_event:
                    self._notify_handlers(simulator_event)
        except Exception as e:
            print(f"[EventManager] ❌ 이벤트 처리 오류: {e}")
    
    def _notify_handlers(self, event_message: dict):
        """
        등록된 핸들러에게 이벤트 전달
        
        Args:
            event_message: 이벤트 메시지
        """
        event_name = event_message.get("event")
        if event_name in self.tcp_client.event_handlers:
            handler = self.tcp_client.event_handlers[event_name]
            try:
                handler(event_message)
            except Exception as e:
                print(f"[EventManager] ❌ 핸들러 실행 오류: {e}")
    
    # 🆕 시뮬레이터 자동 이벤트 설정
    def _setup_simulator_events(self):
        """시뮬레이터 자동 이벤트 설정"""
        if not self.use_simulator or not self.simulator:
            return
        
        # 시뮬레이터에 이벤트 핸들러 등록
        self.simulator.register_event_handler("BR_CHANGED", self._handle_simulator_event)
        self.simulator.register_event_handler("RWY_A_STATUS_CHANGED", self._handle_simulator_event)
        self.simulator.register_event_handler("RWY_B_STATUS_CHANGED", self._handle_simulator_event)
        
        # 자동 이벤트 시작
        self.simulator.start_auto_events()
        print("[EventManager] 🚀 시뮬레이터 자동 이벤트 시작")
    
    def _handle_simulator_event(self, event_data: dict):
        """시뮬레이터 이벤트를 GUI로 전달"""
        print(f"[EventManager] 📤 시뮬레이터 이벤트 전달: {event_data.get('event')} = {event_data.get('result')}")
        self._notify_handlers(event_data)
    
    # 🆕 수동 이벤트 트리거 기능
    def trigger_event(self, event_type: str) -> bool:
        """
        수동으로 이벤트 트리거
        
        Args:
            event_type: 이벤트 타입 (BR_CHANGED, RWY_A_STATUS_CHANGED, RWY_B_STATUS_CHANGED)
            
        Returns:
            성공 여부
        """
        if self.use_simulator and self.simulator:
            event_data = self.simulator.generate_event(event_type)
            if event_data:
                self._handle_simulator_event(event_data)
                return True
        
        return False
    
    # 🆕 자동 이벤트 제어 기능
    def start_auto_events(self):
        """자동 이벤트 시작"""
        if self.use_simulator and self.simulator:
            self.simulator.start_auto_events()
            print("[EventManager] 🚀 자동 이벤트 시작")
    
    def stop_auto_events(self):
        """자동 이벤트 중지"""
        if self.use_simulator and self.simulator:
            self.simulator.stop_auto_events()
            print("[EventManager] ⏹️ 자동 이벤트 중지")
    
    def set_event_intervals(self, intervals: Dict[str, float]):
        """
        이벤트 간격 설정
        
        Args:
            intervals: 이벤트 타입별 간격 (초)
        """
        if self.use_simulator and self.simulator:
            self.simulator.event_intervals.update(intervals)
            print(f"[EventManager] ⏱️ 이벤트 간격 설정: {intervals}")
    
    def signal_gui_ready(self):
        """GUI 준비 완료 신호를 TCP 서버에 전달"""
        if self.use_simulator and self.simulator:
            # 시뮬레이터 사용 시에는 시뮬레이터에 신호 전송
            self.simulator.set_gui_ready()
            print("[EventManager] 📢 GUI 준비 완료 신호를 시뮬레이터에 전달")
        else:
            # 실제 TCP 서버 사용 시에는 서버에 신호 전송
            if self.tcp_client and self.tcp_client.is_connected():
                try:
                    # GUI_READY 메시지를 서버에 전송
                    message = {
                        "type": "gui_ready",
                        "timestamp": time.time()
                    }
                    message_str = json.dumps(message) + "\n"
                    self.tcp_client.socket.send(message_str.encode('utf-8'))
                    print("[EventManager] 📢 GUI 준비 완료 신호를 TCP 서버에 전달")
                except Exception as e:
                    print(f"[EventManager] ❌ GUI 준비 완료 신호를 서버에 전송 실패: {e}")
            else:
                print("[EventManager] ⚠️ TCP 서버에 연결되지 않아 GUI 준비 완료 신호를 전송할 수 없음")