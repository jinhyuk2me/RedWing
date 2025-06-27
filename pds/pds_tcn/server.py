# -*- coding: utf-8 -*-
"""
Independent PDS TCP Server with Advanced Gesture Detection
Main Server와 완전 독립적인 PDS TCP 서버
"""

import socket
import threading
import json
import time
import logging
from typing import Dict, Optional, Callable
from datetime import datetime

from config import SERVER_CONFIG, GESTURE_CLASSES, TTS_MESSAGES, TCP_GESTURE_NAMES, IMPROVED_GESTURE_CONFIG, NETWORK_CONFIG
from detector import ImprovedAdaptiveWindowPoseDetector

class IndependentPDSServer:
    """Main Server와 완전 독립적인 PDS TCP 서버"""
    
    def __init__(self, gesture_callback: Optional[Callable] = None):
        self.logger = logging.getLogger(__name__)
        
        # 🎯 독립적 서버 설정
        self.host = SERVER_CONFIG['host']
        self.port = SERVER_CONFIG['port']
        self.redwing_host = SERVER_CONFIG['redwing_host']
        self.redwing_port = SERVER_CONFIG['redwing_port']
        
        # 소켓들
        self.server_socket = None
        self.redwing_socket = None
        
        # 상태
        self.is_running = False
        self.marshaling_active = False
        self.redwing_connected = False
        
        # 클라이언트 연결 관리
        self.clients = []
        
        # 개선된 제스처 검출기
        self.pose_detector = ImprovedAdaptiveWindowPoseDetector()
        self.gesture_callback = gesture_callback
        
        # 제스처 이벤트 관리
        self.last_gesture = None
        self.last_gesture_time = 0
        self.gesture_cooldown = 2.0
        
        # 개선된 제스처 확신도 관리
        self.improved_config = IMPROVED_GESTURE_CONFIG
        self.gesture_confirmation = {
            'current_gesture': None,
            'confirmation_count': 0,
            'required_confirmations': 5,
            'confidence_threshold': 0.85,
            'completion_required': True
        }
        
        # 확신도 이력 추적
        self.confirmation_history = []
        
        # 카메라 객체 재사용을 위한 멤버 변수
        self.camera_cap = None
        self.camera_index = None
        
        self.logger.info(f"🎯 독립적 PDS 서버 초기화: {self.host}:{self.port}")
        
    def start_server(self):
        """독립적 서버 시작"""
        try:
            self.is_running = True
            
            # PDS 명령 수신 서버 시작
            self._start_command_server()
            
            # RedWing GUI Server 연결 시작
            self._start_redwing_connection()
            
            # RedWing GUI에서 마샬링 제어하도록 대기 상태로 시작
            self._show_initial_gui()
            
            self.logger.info("🎯 독립적 PDS TCP 서버 시작 완료 (Main Server와 무관)")
            
        except Exception as e:
            self.logger.error(f"서버 시작 실패: {e}")
            self.stop_server()
    
    def _start_command_server(self):
        """PDS 명령 수신 서버 시작"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(SERVER_CONFIG['max_clients'])
        
        self.logger.info(f"PDS 명령 수신 서버 시작: {self.host}:{self.port}")
        
        # 명령 수신 스레드
        command_thread = threading.Thread(target=self._handle_commands, daemon=True)
        command_thread.start()
    
    def _start_redwing_connection(self):
        """RedWing GUI Server 연결 시작"""
        if SERVER_CONFIG.get('auto_connect_redwing', True):
            redwing_thread = threading.Thread(target=self._connect_to_redwing, daemon=True)
            redwing_thread.start()
    
    def _connect_to_redwing(self):
        """RedWing GUI Server에 연결"""
        max_retries = NETWORK_CONFIG['redwing_connect_retries']
        retry_delay = NETWORK_CONFIG['redwing_connect_delay']
        
        for attempt in range(max_retries):
            try:
                self.redwing_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.redwing_socket.settimeout(NETWORK_CONFIG['connection_timeout'])
                self.redwing_socket.connect((self.redwing_host, self.redwing_port))
                
                # 연결 후 timeout 제거 (blocking 모드로 변경)
                self.redwing_socket.settimeout(None)
                
                self.redwing_connected = True
                self.logger.info(f"✅ RedWing GUI Server 연결 성공: {self.redwing_host}:{self.redwing_port}")
                
                # 연결 확인 메시지 전송
                self._send_to_redwing({
                    "type": "system",
                    "message": "PDS_SERVER_CONNECTED",
                    "server_info": {
                        "host": self.host,
                        "port": self.port,
                        "capabilities": ["gesture_recognition", "marshaling_detection"]
                    }
                })
                
                # 연결 유지 스레드 시작
                heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
                heartbeat_thread.start()
                
                # RedWing 메시지 수신 스레드 시작
                redwing_message_thread = threading.Thread(target=self._handle_redwing_messages, daemon=True)
                redwing_message_thread.start()
                
                break
                
            except Exception as e:
                self.logger.warning(f"RedWing 연결 실패 ({attempt+1}/{max_retries}): {e}")
                if self.redwing_socket:
                    try:
                        self.redwing_socket.close()
                    except:
                        pass
                    self.redwing_socket = None
                
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    self.logger.error("RedWing GUI Server 연결 포기 - 독립적 모드로 계속 실행")
                    self.redwing_connected = False
    
    def _heartbeat_loop(self):
        """RedWing 연결 유지"""
        while self.is_running and self.redwing_connected:
            try:
                time.sleep(NETWORK_CONFIG['heartbeat_interval'])
                
                if self.redwing_socket and self.redwing_connected:
                    heartbeat = {
                        "type": "heartbeat",
                        "timestamp": datetime.now().isoformat(),
                        "status": "active" if self.marshaling_active else "standby"
                    }
                    self._send_to_redwing(heartbeat)
                
            except Exception as e:
                self.logger.warning(f"하트비트 전송 실패: {e}")
                self.redwing_connected = False
                # 재연결 시도
                if NETWORK_CONFIG.get('reconnect_on_failure', True):
                    self._connect_to_redwing()
                break
    
    def _handle_redwing_messages(self):
        """RedWing GUI Server로부터 메시지 수신 처리"""
        buffer = ""
        
        self.logger.info("🔄 RedWing 메시지 수신 스레드 시작")
        
        while self.is_running and self.redwing_connected:
            try:
                if not self.redwing_socket:
                    break
                
                # RedWing으로부터 메시지 수신
                data = self.redwing_socket.recv(SERVER_CONFIG['buffer_size']).decode('utf-8')
                if not data:
                    self.logger.warning("RedWing 연결이 종료됨")
                    break
                
                buffer += data
                
                # 개행 문자로 메시지 분할
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    if message.strip():
                        self.logger.info(f"📨 RedWing 메시지 수신: {message.strip()}")
                        self._process_redwing_message(message.strip())
                        
            except Exception as e:
                if self.is_running and self.redwing_connected:
                    self.logger.error(f"RedWing 메시지 수신 오류: {e}")
                break
        
        self.redwing_connected = False
        self.logger.info("RedWing 메시지 수신 스레드 종료")
    
    def _process_redwing_message(self, message: str):
        """RedWing으로부터 받은 메시지 처리"""
        try:
            message_data = json.loads(message)
            message_type = message_data.get('type')
            
            self.logger.info(f"📡 RedWing 메시지 처리: {message_data}")
            
            if message_type == 'command':
                command = message_data.get('command')
                
                if command == 'MARSHALING_START':
                    self.logger.info("🎯 RedWing으로부터 마샬링 시작 명령 수신")
                    self._start_marshaling()
                elif command == 'MARSHALING_STOP':
                    self.logger.info("🛑 RedWing으로부터 마샬링 중지 명령 수신")
                    self._stop_marshaling()
                elif command == 'STATUS':
                    self.logger.info("📊 RedWing으로부터 상태 조회 명령 수신")
                    # 상태 정보를 RedWing에 응답
                    self._send_status_to_redwing()
                else:
                    self.logger.warning(f"알 수 없는 RedWing 명령: {command}")
            else:
                self.logger.info(f"기타 RedWing 메시지 타입: {message_type}")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"RedWing 메시지 JSON 파싱 오류: {e}")
        except Exception as e:
            self.logger.error(f"RedWing 메시지 처리 오류: {e}")
    
    def _send_status_to_redwing(self):
        """RedWing에 상태 정보 전송"""
        status = {
            "type": "status_response",
            "server_info": {
                "host": self.host,
                "port": self.port,
                "running": self.is_running,
                "marshaling_active": self.marshaling_active,
                "redwing_connected": self.redwing_connected,
                "connected_clients": len(self.clients)
            },
            "gesture_info": {
                "last_gesture": self.last_gesture,
                "confirmation_count": self.gesture_confirmation['confirmation_count'],
                "confidence_threshold": self.gesture_confirmation['confidence_threshold']
            },
            "timestamp": datetime.now().isoformat()
        }
        
        self._send_to_redwing(status)
    
    def _handle_commands(self):
        """명령 처리 스레드"""
        while self.is_running:
            try:
                client_socket, address = self.server_socket.accept()
                self.logger.info(f"클라이언트 연결: {address}")
                
                self.clients.append(client_socket)
                
                # 클라이언트 처리 스레드
                client_thread = threading.Thread(
                    target=self._handle_client, 
                    args=(client_socket, address),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                if self.is_running:
                    self.logger.error(f"클라이언트 연결 처리 오류: {e}")
    
    def _handle_client(self, client_socket, address):
        """개별 클라이언트 처리"""
        buffer = ""
        
        try:
            while self.is_running:
                data = client_socket.recv(SERVER_CONFIG['buffer_size']).decode('utf-8')
                if not data:
                    break
                
                buffer += data
                
                # 개행 문자로 메시지 분할
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    if message.strip():
                        self._process_command(message.strip(), client_socket)
                        
        except Exception as e:
            self.logger.error(f"클라이언트 처리 오류 {address}: {e}")
        finally:
            client_socket.close()
            if client_socket in self.clients:
                self.clients.remove(client_socket)
            self.logger.info(f"클라이언트 연결 종료: {address}")
    
    def _process_command(self, message: str, client_socket):
        """명령 처리"""
        try:
            command_data = json.loads(message)
            command_type = command_data.get('type')
            command = command_data.get('command')
            
            self.logger.info(f"명령 수신: {command_data}")
            
            if command_type == 'command':
                if command == 'MARSHALING_START':
                    self._start_marshaling()
                    self._send_response(client_socket, "MARSHALING_RECOGNITION_ACTIVATED")
                elif command == 'MARSHALING_STOP':
                    self._stop_marshaling()
                    self._send_response(client_socket, "MARSHALING_RECOGNITION_DEACTIVATED")
                elif command == 'STATUS':
                    self._send_status(client_socket)
                else:
                    self.logger.warning(f"알 수 없는 명령: {command}")
                    self._send_response(client_socket, "UNKNOWN_COMMAND")
                    
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 파싱 오류: {e}")
            self._send_response(client_socket, "INVALID_JSON")
        except Exception as e:
            self.logger.error(f"명령 처리 오류: {e}")
            self._send_response(client_socket, "PROCESSING_ERROR")
    
    def _send_response(self, client_socket, response_text: str):
        """클라이언트에게 응답 전송"""
        try:
            response = {
                "type": "response",
                "response": response_text,
                "timestamp": datetime.now().isoformat()
            }
            message = json.dumps(response) + '\n'
            client_socket.send(message.encode('utf-8'))
        except Exception as e:
            self.logger.error(f"응답 전송 오류: {e}")
    
    def _send_status(self, client_socket):
        """상태 정보 전송"""
        status = {
            "type": "status",
            "server_info": {
                "host": self.host,
                "port": self.port,
                "running": self.is_running,
                "marshaling_active": self.marshaling_active,
                "redwing_connected": self.redwing_connected,
                "connected_clients": len(self.clients)
            },
            "gesture_info": {
                "last_gesture": self.last_gesture,
                "confirmation_count": self.gesture_confirmation['confirmation_count'],
                "confidence_threshold": self.gesture_confirmation['confidence_threshold']
            },
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            message = json.dumps(status) + '\n'
            client_socket.send(message.encode('utf-8'))
        except Exception as e:
            self.logger.error(f"상태 전송 오류: {e}")
    
    def _start_marshaling(self):
        """독립적 마샬링 시작 - GUI에서 이벤트 처리만"""
        if self.marshaling_active:
            self.logger.warning("⚠️ 마샬링이 이미 활성화되어 있습니다")
            return
        
        self.marshaling_active = True
        self.logger.info("🎯 독립적 마샬링 시작 - GUI에서 카메라 피드 활성화")
        
        # 제스처 확신도 상태 리셋
        self.gesture_confirmation = {
            'current_gesture': None,
            'confirmation_count': 0,
            'required_confirmations': 5,
            'confidence_threshold': 0.85,
            'completion_required': True
        }
        self.confirmation_history = []
        self._debug_count = 0  # 디버그 카운터 리셋
        
        # RedWing에 알림
        if self.redwing_connected:
            self._send_to_redwing({
                "type": "response",
                "response": "MARSHALING_RECOGNITION_ACTIVATED"
            })
        
        # 개선된 제스처 인식 시작 (원래 방식으로)
        self._start_improved_gesture_recognition()
        self.logger.info("🎯 독립적 마샬링 시작 완료")
        return True
    
    def _stop_marshaling(self):
        """독립적 마샬링 중지 - 통합 GUI에서 처리"""
        if not self.marshaling_active:
            self.logger.warning("⚠️ 마샬링이 이미 비활성화되어 있습니다")
            return
        
        self.marshaling_active = False
        self.logger.info("🛑 독립적 마샬링 중지 - 통합 GUI에서 대기 화면으로 전환")
        
        # RedWing에 알림
        if self.redwing_connected:
            self._send_to_redwing({
                "type": "response",
                "response": "MARSHALING_RECOGNITION_DEACTIVATED"
            })
        
        return True
    
    def _start_improved_gesture_recognition(self):
        """개선된 제스처 인식 시작 - 통합 GUI에서 처리"""
        # 마샬링 활성화 (통합 GUI 루프에서 자동으로 카메라 모드로 전환)
        self.marshaling_active = True
        self.logger.info("🎯 마샬링 활성화 - 통합 GUI에서 카메라 모드로 전환")
    
    def _initialize_camera(self):
        """카메라 초기화 (재사용 가능)"""
        import cv2
        import gc
        
        # 기존 카메라가 있으면 재사용 시도
        if self.camera_cap is not None and self.camera_index is not None:
            try:
                if self.camera_cap.isOpened():
                    # 카메라 동작 테스트
                    ret, frame = self.camera_cap.read()
                    if ret and frame is not None and frame.size > 0:
                        self.logger.info(f"✅ 기존 카메라 {self.camera_index} 재사용")
                        return self.camera_cap
                    else:
                        self.logger.warning("⚠️ 기존 카메라 프레임 읽기 실패 - 재초기화")
                        self.camera_cap.release()
                        self.camera_cap = None
                        self.camera_index = None
                else:
                    self.logger.warning("⚠️ 기존 카메라가 닫혀있음 - 재초기화")
                    self.camera_cap = None
                    self.camera_index = None
            except Exception as e:
                self.logger.warning(f"⚠️ 기존 카메라 테스트 실패: {e} - 재초기화")
                if self.camera_cap:
                    try:
                        self.camera_cap.release()
                    except:
                        pass
                self.camera_cap = None
                self.camera_index = None
        
        # 새 카메라 초기화
        for camera_index in [0, 1, 2]:
            try:
                self.logger.info(f"🔍 카메라 {camera_index} 시도 중...")
                
                # 리소스 정리 및 대기
                gc.collect()
                time.sleep(0.5)
                
                cap = cv2.VideoCapture(camera_index)
                
                # 카메라 설정 최적화
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 버퍼 크기 최소화
                    cap.set(cv2.CAP_PROP_FPS, 30)        # FPS 설정
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)   # 해상도 설정
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))  # 코덱 설정
                    
                    # 카메라 동작 테스트
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        self.logger.info(f"✅ 카메라 {camera_index} 사용 가능 (해상도: {frame.shape})")
                        self.camera_cap = cap
                        self.camera_index = camera_index
                        return cap
                    else:
                        self.logger.warning(f"⚠️ 카메라 {camera_index} 프레임 읽기 실패")
                        cap.release()
                else:
                    self.logger.warning(f"⚠️ 카메라 {camera_index} 열기 실패")
                    if cap:
                        cap.release()
                    
            except Exception as e:
                self.logger.warning(f"❌ 카메라 {camera_index} 시도 실패: {e}")
                if 'cap' in locals():
                    try:
                        cap.release()
                    except:
                        pass
                
            # 다음 카메라 시도 전 대기
            time.sleep(0.2)
        
        # 모든 카메라 초기화 실패
        return None
    

    
    def _demo_mode_loop(self):
        """카메라 없이 데모 모드 실행"""
        import time
        
        self.logger.info("🎮 데모 모드 시작 - 5초마다 STOP 제스처 시뮬레이션")
        
        demo_gestures = ['stop', 'forward', 'left', 'right']
        gesture_index = 0
        
        while self.marshaling_active and self.is_running:
            time.sleep(5.0)  # 5초 대기
            
            if not self.marshaling_active:
                break
                
            # 데모 제스처 시뮬레이션
            gesture = demo_gestures[gesture_index % len(demo_gestures)]
            confidence = 0.95
            
            debug_info = {
                'gesture_completed': True,
                'motion_duration': 2.0,
                'consistency_info': {
                    'consistent_gesture': gesture,
                    'consistency_score': 0.90
                },
                'confidence_trend': {
                    'is_stable_increasing': True
                }
            }
            
            self.logger.info(f"🎮 데모 제스처: {gesture.upper()} (신뢰도: {confidence:.2f})")
            
            # 제스처 확신도 처리
            self._process_improved_gesture_confirmation(gesture, confidence, debug_info)
            
            gesture_index += 1
        
        self.logger.info("🎮 데모 모드 종료")
    
    def _process_improved_gesture_confirmation(self, gesture: str, confidence: float, debug_info: Dict):
        """개선된 제스처 확신도 처리"""
        current_time = time.time()
        
        # 동작 완료 여부 확인 (필수 조건)
        gesture_completed = debug_info.get('gesture_completed', False)
        if self.gesture_confirmation['completion_required'] and not gesture_completed:
            return
        
        # 일관성 검사
        consistency_info = debug_info.get('consistency_info', {})
        consistent_gesture = consistency_info.get('consistent_gesture')
        consistency_score = consistency_info.get('consistency_score', 0)
        
        # 일관성이 좋지 않으면 무시
        if (consistent_gesture and 
            consistency_score < self.improved_config['consistency_threshold']):
            self.logger.debug(f"일관성 부족으로 무시: {gesture} (점수: {consistency_score:.2f})")
            return
        
        # 신뢰도 추세 검사
        trend_info = debug_info.get('confidence_trend', {})
        is_stable_increasing = trend_info.get('is_stable_increasing', False)
        
        # 신뢰도 추세가 좋지 않으면 무시
        if not is_stable_increasing and len(self.pose_detector.confidence_history) >= 10:
            self.logger.debug(f"신뢰도 추세 불안정으로 무시: {gesture}")
            return
        
        # 제스처 확신도 카운팅
        if self.gesture_confirmation['current_gesture'] == gesture:
            self.gesture_confirmation['confirmation_count'] += 1
        else:
            # 새로운 제스처 - 카운트 리셋
            self.gesture_confirmation['current_gesture'] = gesture
            self.gesture_confirmation['confirmation_count'] = 1
        
        # 확신도 이력 추가
        self.confirmation_history.append({
            'gesture': gesture,
            'confidence': confidence,
            'time': current_time,
            'consistency_score': consistency_score,
            'is_stable_increasing': is_stable_increasing,
            'gesture_completed': gesture_completed
        })
        
        # 이력 관리 (최근 20개만 유지)
        if len(self.confirmation_history) > 20:
            self.confirmation_history = self.confirmation_history[-20:]
        
        # 필요한 확신 횟수에 도달했는지 확인
        if self.gesture_confirmation['confirmation_count'] >= self.gesture_confirmation['required_confirmations']:
            
            # 쿨다운 체크
            if (self.last_gesture != gesture or 
                current_time - self.last_gesture_time > self.gesture_cooldown):
                
                # 추가 검증: 최근 확신도 이력 분석
                if self._validate_gesture_history(gesture):
                    
                    self._send_improved_gesture_event(gesture, confidence, debug_info)
                    self.last_gesture = gesture
                    self.last_gesture_time = current_time
                    
                    # 확신도 카운트 리셋
                    self.gesture_confirmation['confirmation_count'] = 0
                    
                    self.logger.info(f"✅ 확인된 제스처 이벤트: {gesture} (신뢰도: {confidence:.2f}, 일관성: {consistency_score:.2f})")
                else:
                    self.logger.debug(f"이력 검증 실패로 무시: {gesture}")
    
    def _validate_gesture_history(self, gesture: str) -> bool:
        """제스처 이력 검증"""
        if len(self.confirmation_history) < 5:
            return False
        
        # 최근 5개 이력 검사
        recent_history = self.confirmation_history[-5:]
        
        # 모두 같은 제스처인지 확인
        same_gesture_count = sum(1 for h in recent_history if h['gesture'] == gesture)
        if same_gesture_count < 4:
            return False
        
        # 평균 신뢰도가 충분한지 확인
        avg_confidence = sum(h['confidence'] for h in recent_history) / len(recent_history)
        if avg_confidence < 0.85:
            return False
        
        # 모두 완료된 동작인지 확인
        completed_count = sum(1 for h in recent_history if h['gesture_completed'])
        if completed_count < 3:
            return False
        
        return True
    
    def _draw_improved_confirmation_info(self, frame, debug_info):
        """개선된 확신도 정보 화면에 표시"""
        import cv2
        height, width = frame.shape[:2]
        
        # 확신도 정보
        conf_info = [
            f"Gesture: {self.gesture_confirmation['current_gesture'] or 'None'}",
            f"Confirmations: {self.gesture_confirmation['confirmation_count']}/{self.gesture_confirmation['required_confirmations']}",
            f"Completion Required: {self.gesture_confirmation['completion_required']}",
            f"Motion Duration: {debug_info.get('motion_duration', 0):.1f}s",
            f"Gesture Completed: {debug_info.get('gesture_completed', False)}",
            f"RedWing Connected: {self.redwing_connected}"
        ]
        
        # 일관성 정보
        consistency_info = debug_info.get('consistency_info', {})
        if consistency_info:
            conf_info.append(f"Consistency: {consistency_info.get('consistency_score', 0):.2f}")
        
        # 신뢰도 추세 정보
        trend_info = debug_info.get('confidence_trend', {})
        if trend_info:
            conf_info.append(f"Trend OK: {trend_info.get('is_stable_increasing', False)}")
        
        # 최근 이력 개수
        conf_info.append(f"History: {len(self.confirmation_history)}")
        
        # 하단에 표시
        y_start = height - 220
        for i, text in enumerate(conf_info):
            cv2.putText(frame, text, (10, y_start + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.5, (255, 255, 255), 1)
    
    def _send_improved_gesture_event(self, gesture: str, confidence: float, debug_info: Dict):
        """개선된 제스처 이벤트 송신"""
        # 내부 제스처명을 TCP 통신용 대문자로 변환
        tcp_gesture = TCP_GESTURE_NAMES.get(gesture, gesture.upper())
        
        event = {
            "type": "event",
            "event": "MARSHALING_GESTURE_DETECTED",
            "result": tcp_gesture,
            "confidence": confidence,
            "source": "PDS_SERVER",
            "detection_method": "improved_adaptive_window",
            "motion_duration": debug_info.get('motion_duration', 0),
            "confirmation_count": self.gesture_confirmation['confirmation_count'],
            "gesture_completed": debug_info.get('gesture_completed', False),
            "consistency_score": debug_info.get('consistency_info', {}).get('consistency_score', 0),
            "trend_stable": debug_info.get('confidence_trend', {}).get('is_stable_increasing', False),
            "validation_checks": {
                "motion_completion": True,
                "prediction_consistency": True,
                "confidence_trend": True,
                "history_validation": True
            },
            "timestamp": datetime.now().isoformat()
        }
        
        # RedWing GUI Server로 전송
        if self.redwing_connected:
            self._send_to_redwing(event)
        
        # 연결된 클라이언트들에게도 전송
        self._broadcast_to_clients(event)
        
        self.logger.info(f"🎯 독립적 제스처 이벤트 송신: {tcp_gesture} (신뢰도: {confidence:.2f})")
    
    def _send_to_redwing(self, data: Dict):
        """RedWing GUI Server에 데이터 송신"""
        if not self.redwing_socket or not self.redwing_connected:
            return False
        
        try:
            message = json.dumps(data, ensure_ascii=False) + '\n'
            self.redwing_socket.send(message.encode('utf-8'))
            return True
            
        except Exception as e:
            self.logger.error(f"RedWing 송신 오류: {e}")
            self.redwing_connected = False
            self.redwing_socket = None
            # 재연결 시도
            if NETWORK_CONFIG.get('reconnect_on_failure', True):
                self._connect_to_redwing()
            return False
    
    def _broadcast_to_clients(self, data: Dict):
        """연결된 모든 클라이언트에게 브로드캐스트"""
        if not self.clients:
            return
        
        message = json.dumps(data, ensure_ascii=False) + '\n'
        
        for client in list(self.clients):  # 리스트 복사로 안전하게 순회
            try:
                client.send(message.encode('utf-8'))
            except Exception as e:
                self.logger.warning(f"클라이언트 브로드캐스트 실패: {e}")
                if client in self.clients:
                    self.clients.remove(client)
                try:
                    client.close()
                except:
                    pass
    
    def stop_server(self):
        """서버 중지"""
        self.is_running = False
        self.marshaling_active = False
        
        # 카메라 완전 해제 (서버 종료 시에만)
        if self.camera_cap:
            try:
                self.camera_cap.release()
                self.camera_cap = None
                self.camera_index = None
                self.logger.info("📹 카메라 완전 해제 (서버 종료)")
            except Exception as e:
                self.logger.warning(f"카메라 완전 해제 중 오류: {e}")
        
        # OpenCV 윈도우 완전 해제 (서버 종료 시에만)
        try:
            import cv2
            cv2.destroyAllWindows()
            self.logger.info("🖼️ OpenCV 윈도우 완전 해제 (서버 종료)")
        except Exception as e:
            self.logger.warning(f"OpenCV 윈도우 완전 해제 중 오류: {e}")
        
        # 소켓들 정리
        if self.server_socket:
            self.server_socket.close()
        if self.redwing_socket:
            try:
                self.redwing_socket.close()
            except:
                pass
        
        # 클라이언트들 정리
        for client in self.clients:
            try:
                client.close()
            except:
                pass
        self.clients.clear()
        
        self.logger.info("독립적 PDS TCP 서버 중지")
    
    def _show_initial_gui(self):
        """통합 GUI 스레드 시작"""
        import threading
        
        # 통합 GUI 관리 스레드 시작
        gui_thread = threading.Thread(target=self._unified_gui_loop, daemon=True)
        gui_thread.start()
        self.logger.info("✅ 통합 GUI 스레드 시작")
    
    def _unified_gui_loop(self):
        """단일 스레드에서 모든 GUI 관리"""
        import cv2
        import numpy as np
        import time
        
        window_name = 'PDS Marshaling System'
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
        cv2.moveWindow(window_name, 100, 100)
        
        # 카메라는 필요할 때만 초기화
        camera_cap = None
        frame_count = 0
        
        self.logger.info("🎯 통합 GUI 루프 시작")
        
        while self.is_running:
            try:
                if not self.marshaling_active:
                    # === 대기 화면 모드 ===
                    if camera_cap:
                        # 카메라 해제
                        camera_cap.release()
                        camera_cap = None
                        self.logger.info("📹 카메라 해제 (대기 모드)")
                    
                    # 대기 화면 표시
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(frame, "PDS MARSHALING SYSTEM", (120, 150), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                    cv2.putText(frame, "STATUS: STANDBY", (200, 220), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
                    cv2.putText(frame, "Waiting for MARSHALING_START", (130, 300), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 1)
                    
                    cv2.imshow(window_name, frame)
                    time.sleep(0.5)  # 대기 모드에서는 느리게 업데이트
                    
                else:
                    # === 카메라 피드 모드 ===
                    if not camera_cap:
                        # 카메라 초기화
                        camera_cap = self._initialize_camera()
                        if not camera_cap:
                            self.logger.error("❌ 카메라 초기화 실패")
                            # 에러 화면 표시
                            frame = np.zeros((480, 640, 3), dtype=np.uint8)
                            cv2.putText(frame, "CAMERA ERROR", (200, 240), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                            cv2.imshow(window_name, frame)
                            time.sleep(1.0)
                            continue
                        else:
                            self.logger.info("📹 카메라 초기화 성공")
                            frame_count = 0
                    
                    # 카메라 프레임 읽기
                    ret, frame = camera_cap.read()
                    if not ret or frame is None:
                        self.logger.warning("⚠️ 카메라 프레임 읽기 실패")
                        continue
                    
                    frame_count += 1
                    
                    # 제스처 인식 처리
                    try:
                        processed_frame, gesture, confidence, debug_info = self.pose_detector.process_frame(frame)
                        display_frame = processed_frame if processed_frame is not None else frame
                        
                        # 정보 표시
                        cv2.putText(display_frame, f"Frame: {frame_count}", (10, 30), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.putText(display_frame, "GESTURE RECOGNITION ACTIVE", (10, 60), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        
                        if gesture:
                            cv2.putText(display_frame, f"Gesture: {gesture}", (10, 90), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                            cv2.putText(display_frame, f"Confidence: {confidence:.2f}", (10, 120), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                        
                        # 제스처 확신도 검증
                        if gesture and confidence > 0.7:
                            self._process_improved_gesture_confirmation(gesture, confidence, debug_info)
                        
                        cv2.imshow(window_name, display_frame)
                        
                    except Exception as e:
                        self.logger.error(f"제스처 처리 오류: {e}")
                        # 오류 시 원본 프레임 표시
                        cv2.putText(frame, "PROCESSING ERROR", (10, 60), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        cv2.imshow(window_name, frame)
                
                # 키 입력 처리
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    self.logger.info("사용자가 'q' 키로 종료 요청")
                    self.stop_server()
                    break
                    
            except Exception as e:
                self.logger.error(f"GUI 루프 오류: {e}")
                time.sleep(0.1)
        
        # 정리
        if camera_cap:
            camera_cap.release()
        cv2.destroyAllWindows()
        self.logger.info("통합 GUI 루프 종료")

if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.INFO)
    
    # 포트 정보 출력
    from config import get_port_info
    get_port_info()
    
    # 독립적 서버 시작
    server = IndependentPDSServer()
    
    try:
        server.start_server()
        
        print("\n🎯 독립적 PDS 서버 실행 중...")
        print(f"📡 PDS 서버 포트: {SERVER_CONFIG['port']}")
        print(f"🖥️  RedWing 연결: {SERVER_CONFIG['redwing_host']}:{SERVER_CONFIG['redwing_port']}")
        print("🚀 Main Server와 완전 독립적으로 실행")
        print("📊 다중 윈도우: 30f(1s), 45f(1.5s), 60f(2s), 90f(3s)")
        print("🧠 스마트 윈도우 선택: 활성화")
        print("🔍 동적 신뢰도 임계값: 0.95 → 0.85 → 0.75")
        print("✅ 동작 완료 감지: 필수")
        print("🎯 제스처 확신도: 5회 연속 감지 + 동작 완료")
        print("📈 일관성 분석: 70% 이상")
        print("📊 신뢰도 추세: 안정적 증가")
        print("🔄 전환 패턴 감지: 활성화")
        print("⏰ 쿨다운: 2.0초")
        print("🔍 이력 검증: 5개 중 4개 일치")
        print("\nCtrl+C로 종료")
        
        # 서버 유지
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n서버 종료 중...")
        server.stop_server() 