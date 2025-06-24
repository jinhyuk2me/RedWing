#!/usr/bin/env python3
"""
FALCON TCP Mock Server
======================

TCP 클라이언트가 연결할 수 있는 독립적인 모의 서버입니다.
simulator.py와 동일한 로직을 사용하지만 실제 TCP 서버로 동작합니다.

사용법:
    python tcp_mock_server.py

기본 포트: 5300 (FALCON GUI TCP 포트)
"""

import socket
import threading
import json
import time
import random
from typing import Dict, Any, Optional, Tuple, Callable
from datetime import datetime

class TCPMockServer:
    """
    독립적인 TCP 모의 서버 (simulator.py 로직 기반)
    
    별도 터미널에서 실행하여 실제 TCP 서버처럼 동작합니다.
    """
    
    def __init__(self, host: str = "localhost", port: int = 5300):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.clients = []  # 연결된 클라이언트들
        
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
            {"status": "WARNING", "result": "WARNING"},
            {"status": "CLEAR", "result": "CLEAR"},
            {"status": "WARNING", "result": "WARNING"}
        ]
        
        self.runway_bravo_rotation_states = [
            {"status": "WARNING", "result": "WARNING"},
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
                "status": "WARNING",  # 초기 상태
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
        
        # 자동 이벤트 생성 관련
        self.auto_events_enabled = False
        self.event_thread: Optional[threading.Thread] = None
        self.event_intervals = {
            "BR_CHANGED": 60.0,          # 60초마다 조류 위험도 변화
            "RWY_A_STATUS_CHANGED": 75.0, # 75초마다 활주로 A 상태 변화
            "RWY_B_STATUS_CHANGED": 90.0  # 90초마다 활주로 B 상태 변화
        }
        self.last_event_times = {
            "BR_CHANGED": 0.0,
            "RWY_A_STATUS_CHANGED": 0.0,
            "RWY_B_STATUS_CHANGED": 0.0
        }
        
        print(f"[TCPMockServer] 🚀 TCP 모의 서버 초기화 완료")
        print(f"[TCPMockServer] 🦅 조류 시나리오: {self.bird_data['risk_level']} 위험도 → {self.bird_data['result']}")
        print(f"[TCPMockServer] 🛬 활주로 상태: ALPHA({self.runway_data['RWY-ALPHA']['status']}), BRAVO({self.runway_data['RWY-BRAVO']['status']})")
        print(f"[TCPMockServer] 🔄 TCP 프로토콜 명세 준수 모드 (CLEAR/WARNING)")
    
    def start_server(self):
        """TCP 서버 시작"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            
            print(f"[TCPMockServer] 🌐 TCP 서버 시작: {self.host}:{self.port}")
            print(f"[TCPMockServer] 📡 클라이언트 연결 대기 중...")
            
            # 자동 이벤트 시작
            self.start_auto_events()
            
            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    print(f"[TCPMockServer] 🔌 클라이언트 연결: {client_address}")
                    
                    self.clients.append(client_socket)
                    
                    # 클라이언트 처리 스레드 시작
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.error as e:
                    if self.running:
                        print(f"[TCPMockServer] ❌ 소켓 오류: {e}")
                        
        except Exception as e:
            print(f"[TCPMockServer] ❌ 서버 시작 오류: {e}")
        finally:
            self.stop_server()
    
    def stop_server(self):
        """TCP 서버 중지"""
        print(f"[TCPMockServer] 🛑 서버 중지 중...")
        self.running = False
        self.stop_auto_events()
        
        # 클라이언트 연결 종료
        for client in self.clients:
            try:
                client.close()
            except:
                pass
        self.clients.clear()
        
        # 서버 소켓 종료
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        print(f"[TCPMockServer] ✅ 서버 중지 완료")
    
    def handle_client(self, client_socket, address):
        """클라이언트 요청 처리"""
        buffer = ""
        
        print(f"[TCPMockServer] 👥 클라이언트 핸들러 시작: {address}")
        
        try:
            while self.running:
                # 데이터 수신
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
                
                # 🔧 수신된 원시 데이터 로그 추가
                if data.strip():
                    print(f"[TCPMockServer] 📥 원시 데이터 수신 from {address}: {repr(data)}")
                
                buffer += data
                
                # 줄바꿈으로 메시지 분리
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        print(f"[TCPMockServer] 📨 메시지 처리 시작 from {address}: {line.strip()}")
                        self.process_message(client_socket, line.strip(), address)
                        
        except Exception as e:
            print(f"[TCPMockServer] ❌ 클라이언트 처리 오류 {address}: {e}")
        finally:
            client_socket.close()
            if client_socket in self.clients:
                self.clients.remove(client_socket)
            print(f"[TCPMockServer] 👋 클라이언트 연결 종료: {address}")
    
    def process_message(self, client_socket, message_str: str, address):
        """메시지 처리"""
        try:
            message = json.loads(message_str)
            message_type = message.get("type")
            
            print(f"[TCPMockServer] 📋 메시지 파싱 성공 from {address}: type={message_type}, content={message}")
            
            if message_type == "command":
                command = message.get("command")
                print(f"[TCPMockServer] 💻 명령어 처리: {command}")
                response = self.process_command(command)
                self.send_response(client_socket, command, response, address)
            elif message_type == "gui_ready":
                print(f"[TCPMockServer] 🎯 GUI 준비 완료 신호 수신 from {address}")
                # GUI 준비 완료 시 자동 이벤트 시작
                if not hasattr(self, 'auto_events_started') or not self.auto_events_started:
                    self.start_auto_events()
                    self.auto_events_started = True
            else:
                print(f"[TCPMockServer] ❓ 알 수 없는 메시지 타입: {message_type}")
                
        except json.JSONDecodeError as e:
            print(f"[TCPMockServer] ❌ JSON 파싱 오류 from {address}: {e}, 원본: {repr(message_str)}")
        except Exception as e:
            print(f"[TCPMockServer] ❌ 메시지 처리 오류 from {address}: {e}")
    
    def send_response(self, client_socket, command: str, result: str, address):
        """응답 전송"""
        try:
            response = {
                "type": "response",
                "command": command,
                "result": result
            }
            
            response_str = json.dumps(response) + "\n"
            print(f"[TCPMockServer] 📤 응답 전송 to {address} (원시): {repr(response_str)}")
            client_socket.send(response_str.encode('utf-8'))
            print(f"[TCPMockServer] ✅ 응답 전송 완료 to {address}: {command} = {result}")
            
        except Exception as e:
            print(f"[TCPMockServer] ❌ 응답 전송 오류 to {address}: {e}")
    
    def broadcast_event(self, event_type: str, result: str):
        """모든 클라이언트에게 이벤트 브로드캐스트"""
        if not self.clients:
            print(f"[TCPMockServer] ⚠️ 브로드캐스트할 클라이언트가 없음: {event_type}")
            return
        
        event_message = {
            "type": "event",
            "event": event_type,
            "result": result
        }
        
        event_str = json.dumps(event_message) + "\n"
        print(f"[TCPMockServer] 📢 이벤트 브로드캐스트 준비 (클라이언트 {len(self.clients)}개): {event_type} = {result}")
        print(f"[TCPMockServer] 📤 브로드캐스트 메시지 (원시): {repr(event_str)}")
        
        for i, client in enumerate(list(self.clients)):  # 리스트 복사로 안전하게 순회
            try:
                client.send(event_str.encode('utf-8'))
                print(f"[TCPMockServer] ✅ 이벤트 전송 완료 to 클라이언트 #{i+1}: {event_type} = {result}")
            except Exception as e:
                print(f"[TCPMockServer] ❌ 이벤트 전송 실패 to 클라이언트 #{i+1}: {e}")
                # 연결이 끊긴 클라이언트는 제거
                if client in self.clients:
                    self.clients.remove(client)
        
        print(f"[TCPMockServer] 📤 이벤트 브로드캐스트 완료: {event_type} = {result}")
    
    def start_auto_events(self):
        """자동 이벤트 생성 시작"""
        if self.auto_events_enabled:
            return
        
        self.auto_events_enabled = True
        self.event_thread = threading.Thread(target=self._auto_event_loop, daemon=True)
        self.event_thread.start()
        print("[TCPMockServer] 🚀 자동 이벤트 생성 시작")
    
    def stop_auto_events(self):
        """자동 이벤트 생성 중지"""
        self.auto_events_enabled = False
        if self.event_thread and self.event_thread.is_alive():
            self.event_thread.join(timeout=2)
        print("[TCPMockServer] ⏹️ 자동 이벤트 생성 중지")
    
    def _auto_event_loop(self):
        """자동 이벤트 생성 루프"""
        print("[TCPMockServer] 🔄 자동 이벤트 루프 시작")
        
        # 초기 타이밍 설정
        current_time = time.time()
        self.last_event_times = {
            "BR_CHANGED": current_time,
            "RWY_A_STATUS_CHANGED": current_time + 20.0,  # 20초 후
            "RWY_B_STATUS_CHANGED": current_time + 40.0   # 40초 후
        }
        
        while self.auto_events_enabled:
            try:
                current_time = time.time()
                
                # 각 이벤트 타입별로 시간 간격 체크
                for event_type, interval in self.event_intervals.items():
                    last_time = self.last_event_times[event_type]
                    
                    if current_time - last_time >= interval:
                        # 이벤트 생성 및 브로드캐스트
                        event_data = self.generate_event(event_type)
                        if event_data:
                            self.broadcast_event(event_data["event"], event_data["result"])
                        
                        self.last_event_times[event_type] = current_time
                
                # 1초 대기
                time.sleep(1.0)
                
            except Exception as e:
                print(f"[TCPMockServer] ❌ 자동 이벤트 루프 오류: {e}")
                time.sleep(5.0)
        
        print("[TCPMockServer] 🔄 자동 이벤트 루프 종료")
    
    def generate_event(self, event_type: str) -> Optional[Dict[str, Any]]:
        """이벤트 생성 (simulator.py와 동일한 로직)"""
        if event_type == "BR_CHANGED":
            self._rotate_bird_state()
            return {
                "type": "event",
                "event": "BR_CHANGED",
                "result": self.bird_data["result"]
            }
        elif event_type == "RWY_A_STATUS_CHANGED":
            self._rotate_runway_state("RWY-ALPHA")
            return {
                "type": "event",
                "event": "RWY_A_STATUS_CHANGED",
                "result": self.runway_data["RWY-ALPHA"]["status"]
            }
        elif event_type == "RWY_B_STATUS_CHANGED":
            self._rotate_runway_state("RWY-BRAVO")
            return {
                "type": "event",
                "event": "RWY_B_STATUS_CHANGED",
                "result": self.runway_data["RWY-BRAVO"]["status"]
            }
        return None
    
    def _rotate_bird_state(self):
        """조류 위험도 로테이션"""
        self.bird_rotation_index = (self.bird_rotation_index + 1) % len(self.bird_rotation_states)
        new_state = self.bird_rotation_states[self.bird_rotation_index]
        
        old_level = self.bird_data['risk_level']
        
        self.bird_data = self.risk_scenarios[self.bird_rotation_index % len(self.risk_scenarios)].copy()
        self.bird_data['risk_level'] = new_state['risk_level']
        self.bird_data['result'] = new_state['result']
        
        print(f"[TCPMockServer] 🦅 BIRD 로테이션: {old_level} → {self.bird_data['risk_level']} ({self.bird_data['result']})")
    
    def _rotate_runway_state(self, runway_id):
        """활주로 상태 로테이션"""
        if runway_id == "RWY-ALPHA":
            self.runway_alpha_rotation_index = (self.runway_alpha_rotation_index + 1) % len(self.runway_alpha_rotation_states)
            new_state = self.runway_alpha_rotation_states[self.runway_alpha_rotation_index]
            old_status = self.runway_data["RWY-ALPHA"]["status"]
            self.runway_data["RWY-ALPHA"]["status"] = new_state["status"]
            print(f"[TCPMockServer] 🛬 RWY-ALPHA 로테이션: {old_status} → {new_state['status']}")
        elif runway_id == "RWY-BRAVO":
            self.runway_bravo_rotation_index = (self.runway_bravo_rotation_index + 1) % len(self.runway_bravo_rotation_states)
            new_state = self.runway_bravo_rotation_states[self.runway_bravo_rotation_index]
            old_status = self.runway_data["RWY-BRAVO"]["status"]
            self.runway_data["RWY-BRAVO"]["status"] = new_state["status"]
            print(f"[TCPMockServer] 🛬 RWY-BRAVO 로테이션: {old_status} → {new_state['status']}")
    
    def process_command(self, command: str) -> str:
        """명령어 처리 (simulator.py 로직과 동일)"""
        if command == "BR_INQ":
            return self.process_bird_inquiry()
        elif command == "RWY_A_STATUS":
            return self.process_runway_alpha_status()
        elif command == "RWY_B_STATUS":
            return self.process_runway_bravo_status()
        elif command == "RWY_AVAIL_INQ":
            return self.process_runway_availability()
        else:
            print(f"[TCPMockServer] ❓ 알 수 없는 명령어: {command}")
            return "UNRECOGNIZED_COMMAND"
    
    def process_bird_inquiry(self) -> str:
        """조류 위험도 조회"""
        result = self.bird_data["result"]
        print(f"[TCPMockServer] 🦅 BIRD 현재 상태: {self.bird_data['risk_level']} → {result}")
        return result
    
    def process_runway_alpha_status(self) -> str:
        """활주로 알파 상태 조회"""
        runway_info = self.runway_data["RWY-ALPHA"]
        status = runway_info["status"]
        result = "CLEAR" if status == "CLEAR" else "WARNING"
        print(f"[TCPMockServer] 🛬 RWY-ALPHA 현재 상태: {status} → {result}")
        return result
    
    def process_runway_bravo_status(self) -> str:
        """활주로 브라보 상태 조회"""
        runway_info = self.runway_data["RWY-BRAVO"]
        status = runway_info["status"]
        result = "CLEAR" if status == "CLEAR" else "WARNING"
        print(f"[TCPMockServer] 🛬 RWY-BRAVO 현재 상태: {status} → {result}")
        return result
    
    def process_runway_availability(self) -> str:
        """활주로 가용성 조회"""
        available_runways = [rwy for rwy, info in self.runway_data.items() if info["status"] == "CLEAR"]
        
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
                result = "A_ONLY"
        else:
            result = "ALL"
        
        print(f"[TCPMockServer] 🛬 사용 가능한 활주로: {available_runways} → {result}")
        return result


def main():
    """메인 함수"""
    import signal
    import sys
    
    print("="*60)
    print("🚀 FALCON TCP Mock Server")
    print("="*60)
    print("📡 실제 TCP 서버처럼 동작하는 모의 서버입니다.")
    print("🔌 클라이언트 연결을 기다리며 자동으로 이벤트를 생성합니다.")
    print("⚠️  종료하려면 Ctrl+C를 누르세요.")
    print("="*60)
    
    server = TCPMockServer()
    
    def signal_handler(sig, frame):
        print("\n[TCPMockServer] 🛑 종료 신호 수신...")
        server.stop_server()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        server.start_server()
    except KeyboardInterrupt:
        print("\n[TCPMockServer] 🛑 사용자 종료 요청...")
    except Exception as e:
        print(f"[TCPMockServer] ❌ 서버 오류: {e}")
    finally:
        server.stop_server()


if __name__ == "__main__":
    main()
