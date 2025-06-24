import socket
import json
import threading
import time
from typing import Dict, Any, Optional, Tuple, Callable
from queue import Queue, Empty

class TCPClient:
    """
    통합 TCP 클라이언트
    
    서버와의 TCP 통신을 담당하며, 명령어 전송/응답 처리와 이벤트 수신을 모두 처리합니다.
    """
    
    def __init__(self, server_host: str = "localhost", server_port: int = 5300):
        """
        TCP 클라이언트 초기화
        
        Args:
            server_host: 서버 호스트
            server_port: 서버 포트 (기본값: 5300)
        """
        self.server_host = server_host
        self.server_port = server_port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        
        # 응답 대기 큐 (명령어 응답용)
        self.response_queue = Queue()
        
        # 이벤트 핸들러 관리
        self.event_handlers: Dict[str, Callable] = {}
        
        # 메시지 수신 스레드
        self.listener_thread: Optional[threading.Thread] = None
        
        # 명령어 매핑 (TCP 프로토콜 스펙 기준)
        self.command_mapping = {
            "BIRD_RISK_INQUIRY": "BR_INQ",
            "RUNWAY_ALPHA_STATUS": "RWY_A_STATUS", 
            "RUNWAY_BRAVO_STATUS": "RWY_B_STATUS",
            "AVAILABLE_RUNWAY_INQUIRY": "RWY_AVAIL_INQ"
        }
        
        print(f"[TCPClient] 초기화: {server_host}:{server_port}")
    
    def connect(self) -> bool:
        """
        서버에 연결
        
        Returns:
            연결 성공 여부
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)  # 10초 타임아웃
            self.socket.connect((self.server_host, self.server_port))
            
            self.connected = True
            self.running = True
            
            # 메시지 수신 스레드 시작
            self.listener_thread = threading.Thread(target=self._message_listener, daemon=True)
            self.listener_thread.start()
            
            print(f"[TCPClient] ✅ 서버 연결 성공: {self.server_host}:{self.server_port}")
            return True
            
        except Exception as e:
            print(f"[TCPClient] ❌ 서버 연결 실패: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """서버 연결 해제"""
        self.running = False
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join(timeout=2)
        
        print(f"[TCPClient] 연결 해제 완료")
    
    def send_command(self, command: str, timeout: float = 30.0) -> Tuple[bool, Dict[str, Any]]:
        """
        명령어 전송 및 응답 대기
        
        Args:
            command: 명령어 (BIRD_RISK_INQUIRY, RUNWAY_ALPHA_STATUS 등)
            timeout: 응답 대기 시간 (초)
            
        Returns:
            (성공 여부, 응답 데이터) 튜플
        """
        if not self.connected:
            return False, {"error": "not_connected", "message": "서버에 연결되지 않음"}
        
        try:
            # TCP 메시지 형태로 변환
            tcp_command = self.command_mapping.get(command, command)
            message = {
                "type": "command",
                "command": tcp_command
            }
            
            # JSON 메시지 전송
            message_str = json.dumps(message) + "\n"
            print(f"[TCPClient] 📤 명령어 전송 (원시): {repr(message_str)}")
            self.socket.send(message_str.encode('utf-8'))
            
            print(f"[TCPClient] ✅ 명령어 전송 완료: {tcp_command}")
            
            # 응답 대기
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = self.response_queue.get(timeout=1.0)
                    if response.get("command") == tcp_command:
                        print(f"[TCPClient] ✅ 응답 수신: {response.get('result', 'OK')}")
                        return True, response
                except Empty:
                    continue
            
            print(f"[TCPClient] ⏰ 응답 타임아웃: {tcp_command}")
            return False, {"error": "timeout", "message": "응답 시간 초과"}
            
        except Exception as e:
            print(f"[TCPClient] ❌ 명령어 전송 오류: {e}")
            return False, {"error": "send_failed", "message": str(e)}
    
    def register_event_handler(self, event_name: str, handler: Callable):
        """
        이벤트 핸들러 등록
        
        Args:
            event_name: 이벤트 이름 (BR_CHANGED, RUNWAY_ALPHA_STATUS_CHANGED 등)
            handler: 이벤트 처리 함수 (event_data: dict를 인자로 받음)
        """
        self.event_handlers[event_name] = handler
        print(f"[TCPClient] 이벤트 핸들러 등록: {event_name}")
    
    def unregister_event_handler(self, event_name: str):
        """
        이벤트 핸들러 해제
        
        Args:
            event_name: 이벤트 이름
        """
        if event_name in self.event_handlers:
            del self.event_handlers[event_name]
            print(f"[TCPClient] 이벤트 핸들러 해제: {event_name}")
    
    def get_registered_events(self) -> list:
        """
        등록된 이벤트 목록 반환
        
        Returns:
            등록된 이벤트 이름 리스트
        """
        return list(self.event_handlers.keys())
    
    def _message_listener(self):
        """메시지 수신 스레드 (명령어 응답과 이벤트 모두 처리)"""
        buffer = ""
        
        print("[TCPClient] 메시지 수신 스레드 시작")
        
        while self.running and self.connected:
            try:
                if not self.socket:
                    break
                
                # 데이터 수신
                data = self.socket.recv(1024).decode('utf-8')
                if not data:
                    print("[TCPClient] 서버 연결 종료됨")
                    break
                
                # 🔧 수신된 원시 데이터 로그 추가
                if data.strip():
                    print(f"[TCPClient] 📥 원시 데이터 수신: {repr(data)}")
                
                buffer += data
                
                # 줄바꿈으로 메시지 분리
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        print(f"[TCPClient] 📨 메시지 처리 시작: {line.strip()}")
                        self._process_message(line.strip())
                        
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[TCPClient] 메시지 수신 오류: {e}")
                break
        
        self.connected = False
        print("[TCPClient] 메시지 수신 스레드 종료")
    
    def _process_message(self, message_str: str):
        """
        수신된 메시지 처리 (응답과 이벤트 모두 처리)
        
        Args:
            message_str: JSON 형태의 메시지 문자열
        """
        try:
            message = json.loads(message_str)
            message_type = message.get("type")
            
            print(f"[TCPClient] 📋 메시지 파싱 성공: type={message_type}, content={message}")
            
            if message_type == "response":
                # 명령어 응답 처리
                print(f"[TCPClient] 💬 응답 메시지를 큐에 추가: {message}")
                self.response_queue.put(message)
            elif message_type == "event":
                # 이벤트 처리
                print(f"[TCPClient] 🔔 이벤트 메시지 처리: {message}")
                self._handle_event(message)
            else:
                print(f"[TCPClient] ❓ 알 수 없는 메시지 타입: {message_type}")
                
        except json.JSONDecodeError as e:
            print(f"[TCPClient] ❌ JSON 파싱 오류: {e}, 원본: {repr(message_str)}")
        except Exception as e:
            print(f"[TCPClient] ❌ 메시지 처리 오류: {e}")
    
    def _handle_event(self, event_message: dict):
        """
        이벤트 메시지 처리
        
        Args:
            event_message: 이벤트 메시지 딕셔너리
        """
        event_name = event_message.get("event")
        event_result = event_message.get("result", "UNKNOWN")
        
        print(f"[TCPClient] 🎯 이벤트 처리 시작: {event_name} = {event_result}")
        
        if not event_name:
            print("[TCPClient] ⚠️ 이벤트 이름이 없는 메시지")
            return
        
        if event_name in self.event_handlers:
            try:
                print(f"[TCPClient] ✅ 등록된 핸들러 호출: {event_name}")
                # 등록된 핸들러 호출
                self.event_handlers[event_name](event_message)
                print(f"[TCPClient] ✅ 이벤트 처리 완료: {event_name} = {event_result}")
            except Exception as e:
                print(f"[TCPClient] ❌ 이벤트 핸들러 오류 ({event_name}): {e}")
        else:
            # 핸들러가 등록되지 않은 이벤트
            print(f"[TCPClient] 📢 미등록 이벤트 수신 (등록된 핸들러: {list(self.event_handlers.keys())}): {event_name} = {event_result}")
    
    def is_connected(self) -> bool:
        """
        연결 상태 확인
        
        Returns:
            연결 상태
        """
        return self.connected
    
    def get_server_status(self) -> Dict[str, Any]:
        """
        서버 상태 정보 조회
        
        Returns:
            서버 상태 정보
        """
        return {
            "connected": self.connected,
            "host": self.server_host,
            "port": self.server_port,
            "registered_events": list(self.event_handlers.keys())
        }