# -*- coding: utf-8 -*-
"""
RedWing GUI Server
GUI를 서버로 전환하여 여러 클라이언트들이 연결할 수 있도록 함
"""

import socket
import threading
import json
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from queue import Queue

class RedWingGUIServer:
    """RedWing GUI 서버 - 클라이언트들이 연결할 수 있는 중앙 서버"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.logger = logging.getLogger(__name__)
        
        # 서버 설정
        self.host = host
        self.port = port
        self.server_socket = None
        self.is_running = False
        
        # 클라이언트 관리
        self.clients: List[Dict] = []  # 연결된 클라이언트들
        self.client_lock = threading.Lock()
        
        # PDS 서버 연결
        self.pds_connected = False
        self.pds_socket = None
        self.pds_client_info = None  # PDS 클라이언트 정보 (인바운드 연결용)
        self.pds_host = "localhost"
        self.pds_port = 8001
        
        # Main Server 연결
        self.main_server_connected = False
        self.main_server_socket = None
        self.main_server_host = "localhost"
        self.main_server_port = 5300
        
        # 이벤트 큐
        self.event_queue = Queue()
        
        # 메시지 로그
        self.message_history = []
        
        self.logger.info(f"🖥️ RedWing GUI Server 초기화: {host}:{port}")
    
    def start_server(self):
        """GUI 서버 시작"""
        try:
            self.is_running = True
            
            # 메인 서버 소켓 시작
            self._start_main_server()
            
            # PDS 서버는 인바운드 클라이언트로 연결하므로 아웃바운드 연결 불필요
            # self._connect_to_pds()  # 제거: PDS가 클라이언트로 연결함
            
            # Main Server 연결
            self._connect_to_main_server()
            
            # 이벤트 처리 스레드 시작
            self._start_event_processor()
            
            self.logger.info("🖥️ RedWing GUI Server 시작 완료")
            
        except Exception as e:
            self.logger.error(f"GUI 서버 시작 실패: {e}")
            self.stop_server()
    
    def _start_main_server(self):
        """메인 GUI 서버 시작"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(10)
        
        self.logger.info(f"GUI 서버 시작: {self.host}:{self.port}")
        
        # 클라이언트 연결 처리 스레드
        accept_thread = threading.Thread(target=self._handle_client_connections, daemon=True)
        accept_thread.start()
    
    def _handle_client_connections(self):
        """클라이언트 연결 처리"""
        while self.is_running:
            try:
                client_socket, address = self.server_socket.accept()
                
                client_info = {
                    'socket': client_socket,
                    'address': address,
                    'connected_time': datetime.now(),
                    'client_type': 'unknown',
                    'id': len(self.clients) + 1
                }
                
                with self.client_lock:
                    self.clients.append(client_info)
                
                self.logger.info(f"🔌 클라이언트 연결: {address} (총 {len(self.clients)}개)")
                
                # 클라이언트 처리 스레드
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_info,),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                if self.is_running:
                    self.logger.error(f"클라이언트 연결 처리 오류: {e}")
    
    def _handle_client(self, client_info: Dict):
        """개별 클라이언트 처리"""
        client_socket = client_info['socket']
        address = client_info['address']
        buffer = ""
        
        try:
            # PDS 서버가 아닌 경우에만 환영 메시지 전송
            # (PDS는 시스템 메시지로 등록하므로 welcome 불필요)
            
            while self.is_running:
                data = client_socket.recv(4096).decode('utf-8')
                if not data:
                    break
                
                buffer += data
                
                # 메시지 분할 처리
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    if message.strip():
                        self._process_client_message(client_info, message.strip())
                        
        except Exception as e:
            self.logger.error(f"클라이언트 처리 오류 {address}: {e}")
        finally:
            self._disconnect_client(client_info)
    
    def _process_client_message(self, client_info: Dict, message: str):
        """클라이언트 메시지 처리"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            self.logger.info(f"📨 클라이언트 메시지: {client_info['address']} - {msg_type}")
            
            # 메시지 이력에 추가
            self.message_history.append({
                'timestamp': datetime.now().isoformat(),
                'client': client_info['address'],
                'type': msg_type,
                'data': data
            })
            
            # 메시지 타입별 처리
            if msg_type == 'register':
                self._handle_client_registration(client_info, data)
            elif msg_type == 'command':
                self._handle_client_command(client_info, data)
            elif msg_type == 'query':
                self._handle_client_query(client_info, data)
            elif msg_type == 'voice_request':
                self._handle_voice_request(client_info, data)
            elif msg_type == 'system':
                self._handle_system_message(client_info, data)
            elif msg_type == 'heartbeat':
                self._handle_heartbeat(client_info, data)
            elif msg_type == 'response':
                self._handle_response_message(client_info, data)
            elif msg_type == 'event':
                self._handle_event_message(client_info, data)
            elif msg_type == 'gui_ready':
                self._handle_gui_ready(client_info, data)
            else:
                self.logger.warning(f"알 수 없는 메시지 타입: {msg_type}")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 파싱 오류: {e}")
        except Exception as e:
            self.logger.error(f"메시지 처리 오류: {e}")
    
    def _handle_client_registration(self, client_info: Dict, data: Dict):
        """클라이언트 등록 처리"""
        client_type = data.get('client_type', 'unknown')
        client_info['client_type'] = client_type
        
        response = {
            "type": "registration_response",
            "status": "success",
            "assigned_id": client_info['id'],
            "client_type": client_type
        }
        
        self._send_to_client(client_info['socket'], response)
        self.logger.info(f"클라이언트 등록: {client_info['address']} - {client_type}")
    
    def _handle_client_command(self, client_info: Dict, data: Dict):
        """클라이언트 명령 처리"""
        command = data.get('command')
        
        if command in ['MARSHALING_START', 'MARSHALING_STOP']:
            # GUI에서 온 메시지를 그대로 PDS에 전달
            self._forward_to_pds(data)
        elif command == 'GET_STATUS':
            self._send_server_status(client_info)
        elif command in ['BR_INQ', 'RWY_A_STATUS', 'RWY_B_STATUS', 'RWY_AVAIL_INQ']:
            # 🔧 명령어 형태로 온 쿼리도 Main Server로 전달
            self.logger.info(f"📤 클라이언트 명령어를 Main Server로 전달: {command}")
            self._forward_to_main_server(client_info, data)
        else:
            self.logger.warning(f"알 수 없는 명령: {command}")
    
    def _handle_client_query(self, client_info: Dict, data: Dict):
        """클라이언트 쿼리 처리"""
        query_type = data.get('query_type')
        
        if query_type in ['BR_INQ', 'RWY_A_STATUS', 'RWY_B_STATUS', 'RWY_AVAIL_INQ']:
            # 🔧 Main Server가 기대하는 명령어 형식으로 변환
            command_data = {
                "type": "command",
                "command": query_type
            }
            self.logger.info(f"📤 클라이언트 쿼리를 Main Server 명령어로 변환: {query_type}")
            # Main Server로 명령어 전달
            self._forward_to_main_server(client_info, command_data)
        else:
            self.logger.warning(f"알 수 없는 쿼리: {query_type}")
    
    def _handle_voice_request(self, client_info: Dict, data: Dict):
        """음성 요청 처리"""
        # TODO: 음성 처리 로직 구현
        response = {
            "type": "voice_response",
            "status": "not_implemented",
            "message": "음성 처리 기능은 향후 구현 예정입니다"
        }
        self._send_to_client(client_info['socket'], response)
    
    def _handle_system_message(self, client_info: Dict, data: Dict):
        """시스템 메시지 처리"""
        message = data.get('message', '')
        self.logger.info(f"📡 시스템 메시지: {client_info['address']} - {message}")
        
        if message == 'PDS_SERVER_CONNECTED':
            client_info['client_type'] = 'pds_server'
            self.pds_connected = True  # PDS 연결 상태 업데이트
            self.pds_client_info = client_info  # PDS 클라이언트 정보 저장
            self.logger.info(f"✅ PDS 서버 등록 및 연결 상태 업데이트: {client_info['address']}")
    
    def _handle_heartbeat(self, client_info: Dict, data: Dict):
        """하트비트 처리"""
        # 조용히 처리 (로그 스팸 방지)
        timestamp = data.get('timestamp', '')
        status = data.get('status', 'unknown')
        
        # 필요시 클라이언트 상태 업데이트
        if 'last_heartbeat' not in client_info:
            client_info['last_heartbeat'] = timestamp
            client_info['status'] = status
    
    def _handle_response_message(self, client_info: Dict, data: Dict):
        """응답 메시지 처리 (PDS로부터의 응답)"""
        response = data.get('response', '')
        
        # 마샬링 관련 응답은 GUI에 전달하지 않음 (Qt 타이머 충돌 방지)
        if response in ['MARSHALING_RECOGNITION_ACTIVATED', 'MARSHALING_RECOGNITION_DEACTIVATED']:
            self.logger.info(f"🔧 마샬링 응답 수신 (GUI 전달 안함): {response}")
            return
        
        # 기타 응답은 GUI에 전달
        self._broadcast_to_non_pds_clients(data)
    
    def _handle_event_message(self, client_info: Dict, data: Dict):
        """이벤트 메시지 처리 (PDS로부터의 제스처 이벤트)"""
        # 그냥 GUI에 전달만 함
        self._broadcast_to_non_pds_clients(data)
    
    def _handle_gui_ready(self, client_info: Dict, data: Dict):
        """GUI 준비 완료 메시지 처리"""
        self.logger.info(f"🎯 GUI 준비 완료 신호 수신: {client_info['address']}")
        client_info['client_type'] = 'gui_client'
        
        # GUI 준비 완료 응답
        response = {
            "type": "gui_ready_response",
            "status": "acknowledged",
            "message": "GUI 준비 완료 확인됨"
        }
        self._send_to_client(client_info['socket'], response)
    
    def _connect_to_pds(self):
        """PDS 서버 연결"""
        try:
            self.pds_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.pds_socket.settimeout(5.0)
            self.pds_socket.connect((self.pds_host, self.pds_port))
            
            self.pds_connected = True
            self.logger.info(f"✅ PDS 서버 연결: {self.pds_host}:{self.pds_port}")
            
            # PDS 메시지 수신 스레드
            pds_thread = threading.Thread(target=self._handle_pds_messages, daemon=True)
            pds_thread.start()
            
        except Exception as e:
            self.logger.warning(f"PDS 서버 연결 실패: {e}")
            self.pds_connected = False
    
    def _connect_to_main_server(self):
        """Main Server 연결"""
        try:
            self.main_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Main Server는 요청-응답 방식이므로 연결 시에만 timeout 적용
            self.main_server_socket.settimeout(5.0)
            self.main_server_socket.connect((self.main_server_host, self.main_server_port))
            
            # 연결 후에는 timeout 제거 (blocking 모드로 변경)
            self.main_server_socket.settimeout(None)
            
            self.main_server_connected = True
            self.logger.info(f"✅ Main Server 연결: {self.main_server_host}:{self.main_server_port}")
            
            # Main Server 메시지 수신 스레드 시작 (이벤트 수신을 위해)
            main_thread = threading.Thread(target=self._handle_main_server_messages, daemon=True)
            main_thread.start()
            
        except Exception as e:
            self.logger.warning(f"Main Server 연결 실패: {e}")
            self.main_server_connected = False
    
    def _handle_pds_messages(self):
        """PDS 메시지 수신 처리"""
        buffer = ""
        
        while self.is_running and self.pds_connected:
            try:
                data = self.pds_socket.recv(4096).decode('utf-8')
                if not data:
                    break
                
                buffer += data
                
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    if message.strip():
                        self._process_pds_message(message.strip())
                        
            except Exception as e:
                self.logger.error(f"PDS 메시지 수신 오류: {e}")
                self.pds_connected = False
                break
    
    def _handle_main_server_messages(self):
        """Main Server 메시지 수신 처리"""
        buffer = ""
        
        while self.is_running and self.main_server_connected:
            try:
                data = self.main_server_socket.recv(4096).decode('utf-8')
                if not data:
                    break
                
                buffer += data
                
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    if message.strip():
                        self._process_main_server_message(message.strip())
                        
            except Exception as e:
                self.logger.error(f"Main Server 메시지 수신 오류: {e}")
                self.main_server_connected = False
                break
    
    def _process_pds_message(self, message: str):
        """PDS 메시지 처리"""
        try:
            data = json.loads(message)
            
            # PDS 이벤트를 모든 클라이언트에게 브로드캐스트
            if data.get('type') == 'event':
                self._broadcast_to_clients(data)
                
        except Exception as e:
            self.logger.error(f"PDS 메시지 처리 오류: {e}")
    
    def _process_main_server_message(self, message: str):
        """Main Server 메시지 처리"""
        try:
            data = json.loads(message)
            self.logger.info(f"📨 Main Server 메시지 수신: {data}")
            
            # Main Server 메시지는 PDS가 아닌 클라이언트들에게만 브로드캐스트
            self._broadcast_to_non_pds_clients(data)
            
            # 로그 메시지 개선 - 타입에 따라 다른 정보 출력
            if data.get('type') == 'event':
                self.logger.info(f"📡 Main Server 이벤트 브로드캐스트 완료: {data.get('event', 'unknown')}")
            elif data.get('type') == 'response':
                self.logger.info(f"📡 Main Server 응답 브로드캐스트 완료: {data.get('command', 'unknown')}")
            else:
                self.logger.info(f"📡 Main Server 메시지 브로드캐스트 완료: {data.get('type', 'unknown')}")
            
        except Exception as e:
            self.logger.error(f"Main Server 메시지 처리 오류: {e}")
    
    def _forward_to_pds(self, data: Dict):
        """PDS 서버로 메시지 전달 (인바운드 클라이언트에게)"""
        if not self.pds_connected or not self.pds_client_info:
            self.logger.warning("PDS 서버가 연결되지 않음")
            return False
        
        try:
            # PDS 클라이언트에게 메시지 전송
            success = self._send_to_client(self.pds_client_info['socket'], data)
            if success:
                self.logger.info(f"✅ PDS로 메시지 전달 완료: {data.get('command', 'unknown')}")
            else:
                self.logger.error("PDS로 메시지 전달 실패")
                self.pds_connected = False
                self.pds_client_info = None
            return success
        except Exception as e:
            self.logger.error(f"PDS 전달 오류: {e}")
            self.pds_connected = False
            self.pds_client_info = None
            return False
    
    def _forward_to_main_server(self, client_info: Dict, data: Dict):
        """Main Server로 쿼리 전달"""
        if not self.main_server_connected:
            self.logger.warning("Main Server가 연결되지 않음")
            return False
        
        try:
            message = json.dumps(data) + '\n'
            self.main_server_socket.send(message.encode('utf-8'))
            return True
        except Exception as e:
            self.logger.error(f"Main Server 전달 오류: {e}")
            self.main_server_connected = False
            return False
    
    def _send_to_client(self, client_socket, data: Dict):
        """특정 클라이언트에게 메시지 전송"""
        try:
            message = json.dumps(data, ensure_ascii=False) + '\n'
            client_socket.send(message.encode('utf-8'))
            return True
        except Exception as e:
            self.logger.error(f"클라이언트 전송 오류: {e}")
            return False
    
    def _broadcast_to_clients(self, data: Dict):
        """모든 클라이언트에게 브로드캐스트"""
        with self.client_lock:
            for client_info in list(self.clients):
                if not self._send_to_client(client_info['socket'], data):
                    # 전송 실패한 클라이언트 제거
                    self._disconnect_client(client_info)
    
    def _broadcast_to_non_pds_clients(self, data: Dict):
        """PDS가 아닌 클라이언트들에게만 브로드캐스트"""
        with self.client_lock:
            for client_info in list(self.clients):
                # PDS 서버가 아닌 클라이언트에게만 전송
                if client_info.get('client_type') != 'pds_server':
                    if not self._send_to_client(client_info['socket'], data):
                        # 전송 실패한 클라이언트 제거
                        self._disconnect_client(client_info)
    
    def _disconnect_client(self, client_info: Dict):
        """클라이언트 연결 해제"""
        try:
            client_info['socket'].close()
        except:
            pass
        
        # PDS 클라이언트인 경우 연결 상태 업데이트
        if client_info.get('client_type') == 'pds_server':
            self.pds_connected = False
            self.pds_client_info = None
            self.logger.info(f"🤚 PDS 서버 연결 해제됨: {client_info['address']}")
        
        with self.client_lock:
            if client_info in self.clients:
                self.clients.remove(client_info)
        
        self.logger.info(f"👋 클라이언트 연결 해제: {client_info['address']} (남은 클라이언트: {len(self.clients)}개)")
    
    def _send_server_status(self, client_info: Dict):
        """서버 상태 정보 전송"""
        status = {
            "type": "server_status",
            "timestamp": datetime.now().isoformat(),
            "server_info": {
                "host": self.host,
                "port": self.port,
                "running": self.is_running,
                "connected_clients": len(self.clients)
            },
            "connections": {
                "pds_connected": self.pds_connected,
                "main_server_connected": self.main_server_connected
            },
            "clients": [
                {
                    "id": c['id'],
                    "address": str(c['address']),
                    "type": c['client_type'],
                    "connected_time": c['connected_time'].isoformat()
                } for c in self.clients
            ]
        }
        
        self._send_to_client(client_info['socket'], status)
    
    def _start_event_processor(self):
        """이벤트 처리 스레드 시작"""
        event_thread = threading.Thread(target=self._event_processor_loop, daemon=True)
        event_thread.start()
    
    def _event_processor_loop(self):
        """이벤트 처리 루프"""
        while self.is_running:
            try:
                # 큐에서 이벤트 처리
                if not self.event_queue.empty():
                    event = self.event_queue.get_nowait()
                    self._broadcast_to_clients(event)
                
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"이벤트 처리 오류: {e}")
    
    def add_event(self, event: Dict):
        """이벤트 큐에 추가"""
        self.event_queue.put(event)
    
    def stop_server(self):
        """GUI 서버 중지"""
        self.is_running = False
        
        # 모든 클라이언트 연결 해제
        with self.client_lock:
            for client_info in list(self.clients):
                self._disconnect_client(client_info)
        
        # 서버 소켓들 정리
        if self.server_socket:
            self.server_socket.close()
        if self.pds_socket:
            try:
                self.pds_socket.close()
            except:
                pass
        if self.main_server_socket:
            try:
                self.main_server_socket.close()
            except:
                pass
        
        self.logger.info("🖥️ RedWing GUI Server 중지 완료")
    
    def get_server_info(self) -> Dict:
        """서버 정보 반환"""
        return {
            "host": self.host,
            "port": self.port,
            "running": self.is_running,
            "connected_clients": len(self.clients),
            "pds_connected": self.pds_connected,
            "main_server_connected": self.main_server_connected,
            "message_history_count": len(self.message_history)
        }

def main():
    """RedWing GUI Server 단독 실행"""
    import signal
    import sys
    import os
    
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 포트 정보 출력
    try:
        from ..config.ports import get_port_info
        get_port_info()
    except ImportError:
        # 직접 실행 시 절대 경로 사용
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
        from config.ports import get_port_info
        get_port_info()
    
    # GUI 서버 시작
    server = RedWingGUIServer()
    
    def signal_handler(sig, frame):
        print("\n🛑 GUI 서버 종료 중...")
        try:
            server.is_running = False
            if hasattr(server, 'server_socket') and server.server_socket:
                server.server_socket.close()
        except:
            pass
        print("✅ GUI 서버 종료 완료")
        os._exit(0)  # 강제 종료
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        server.start_server()
        
        print("\n🖥️ RedWing GUI Server 실행 중...")
        print(f"📡 GUI Server: {server.host}:{server.port}")
        print(f"🤚 PDS 연결: {server.pds_host}:{server.pds_port}")
        print(f"✈️  Main Server 연결: {server.main_server_host}:{server.main_server_port}")
        print("🔌 클라이언트 연결 대기 중...")
        print("\nCtrl+C로 종료")
        
        # 서버 유지
        while True:
            time.sleep(1)
            
    except Exception as e:
        print(f"❌ GUI 서버 오류: {e}")
        server.stop_server()

if __name__ == "__main__":
    main() 