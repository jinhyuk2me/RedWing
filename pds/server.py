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
import cv2
import numpy as np
import torch
import mediapipe as mp
from collections import deque
from pathlib import Path

from config import SERVER_CONFIG, GESTURE_CLASSES, TTS_MESSAGES, TCP_GESTURE_NAMES, IMPROVED_GESTURE_CONFIG, NETWORK_CONFIG, DEMO_VIDEO_CONFIG, MEDIAPIPE_CONFIG
from model import GestureModelManager
from utils import setup_logging

class SimpleGestureDetector:
    """create_visual_demo.py와 동일한 간단하고 정확한 제스처 검출기"""
    
    def __init__(self):
        self.logger = setup_logging()
        
        # MediaPipe 초기화
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # 모델 로드
        self.model_manager = GestureModelManager()
        self.model = self.model_manager.load_model()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)
        self.model.eval()
        
        # 자세 버퍼 (30프레임)
        self.pose_buffer = deque(maxlen=30)
        self.key_landmarks = MEDIAPIPE_CONFIG['key_landmarks']
        
        self.logger.info("✅ 간단한 제스처 검출기 초기화 완료")
    
    def extract_pose_landmarks(self, frame):
        """자세 추출 (create_visual_demo.py와 동일)"""
        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False
        
        results = self.pose.process(rgb_frame)
        
        if results.pose_landmarks:
            pose_data = []
            for idx in self.key_landmarks:
                landmark = results.pose_landmarks.landmark[idx]
                pose_data.append([landmark.x, landmark.y, landmark.visibility])
            
            return np.array(pose_data, dtype=np.float32), results
        
        return None, results
    
    def normalize_pose_data(self, pose_data):
        """정규화 (create_visual_demo.py와 동일)"""
        if pose_data.shape[0] == 0:
            return pose_data
            
        normalized_pose = pose_data.copy()
        
        # Hip 중심점 계산
        left_hip = pose_data[9]
        right_hip = pose_data[10]
        
        if left_hip[2] > 0.5 and right_hip[2] > 0.5:
            center = (left_hip[:2] + right_hip[:2]) / 2
            
            # 상대 좌표로 변환
            for joint_idx in range(len(self.key_landmarks)):
                if pose_data[joint_idx][2] > 0.5:
                    normalized_pose[joint_idx][:2] -= center
            
            # 스케일 정규화
            left_shoulder = pose_data[3]
            right_shoulder = pose_data[4]
            
            if left_shoulder[2] > 0.5 and right_shoulder[2] > 0.5:
                shoulder_width = np.linalg.norm(left_shoulder[:2] - right_shoulder[:2])
                if shoulder_width > 0:
                    normalized_pose[:, :2] /= shoulder_width
        
        return normalized_pose
    
    def predict_gesture(self, pose_sequence):
        """제스처 예측 (create_visual_demo.py와 동일)"""
        if len(pose_sequence) < 30:
            return None, 0.0
        
        # 최근 30프레임 사용
        input_sequence = np.array(pose_sequence[-30:])  # (30, 17, 3)
        input_sequence = input_sequence[:, :, :2]  # (30, 17, 2) - x,y만
        input_sequence = input_sequence.reshape(input_sequence.shape[0], -1)  # (30, 34)
        
        # 예측
        input_tensor = torch.FloatTensor(input_sequence).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            output = self.model(input_tensor)
            probabilities = torch.softmax(output, dim=1)
            confidence, predicted_class = torch.max(probabilities, 1)
            
            predicted_gesture = GESTURE_CLASSES[predicted_class.item()]
            confidence_score = confidence.item()
        
        return predicted_gesture, confidence_score
    
    def process_frame(self, frame):
        """프레임 처리 (create_visual_demo.py 방식)"""
        # 자세 추정
        pose_data, pose_results = self.extract_pose_landmarks(frame)
        
        prediction = None
        confidence = 0.0
        
        if pose_data is not None:
            normalized_pose = self.normalize_pose_data(pose_data)
            self.pose_buffer.append(normalized_pose)
            
            if len(self.pose_buffer) == 30:
                prediction, confidence = self.predict_gesture(list(self.pose_buffer))
        
        debug_info = {
            'gesture_completed': True,  # 간단화
            'motion_duration': 2.0,
            'consistency_info': {
                'consistent_gesture': prediction,
                'consistency_score': confidence if prediction else 0
            },
            'confidence_trend': {
                'is_stable_increasing': True
            },
            'pose_results': pose_results
        }
        
        return frame, prediction, confidence, debug_info

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
        
        # 🎯 간단하고 정확한 제스처 검출기 사용
        self.pose_detector = SimpleGestureDetector()
        self.gesture_callback = gesture_callback
        
        # 제스처 이벤트 관리
        self.last_gesture = None
        self.last_gesture_time = 0
        self.gesture_cooldown = 3.0
        
        # 간단한 제스처 확신도 관리
        self.gesture_confirmation = {
            'current_gesture': None,
            'confirmation_count': 0,
            'required_confirmations': 30,  # 30프레임 연속 (약 1초, 30fps 기준)
            'confidence_threshold': 0.9,   # 임계값: 90%
        }
        
        # 확신도 이력 추적
        self.confirmation_history = []
        
        # 카메라 객체 재사용을 위한 멤버 변수
        self.camera_cap = None
        self.camera_index = None
        
        # 🎬 데모 영상 관련 변수
        self.demo_mode = DEMO_VIDEO_CONFIG['enabled']
        self.demo_videos = []
        self.current_demo_video_index = 0
        self.demo_gesture_index = 0
        self.demo_video_in_gesture = 0
        
        # 🎬 데모 영상 세그먼트 정보
        self.demo_segments = []
        self.current_frame_idx = 0
        
        # 색상 정의 (create_visual_demo.py와 동일)
        self.colors = {
            'stop': (0, 0, 255),      # Red
            'forward': (0, 255, 0),   # Green  
            'left': (255, 0, 0),      # Blue
            'right': (0, 255, 255),   # Yellow
            'background': (0, 0, 0),   # Black
            'text': (255, 255, 255),   # White
            'skeleton': (255, 128, 0)  # Orange
        }
        
        self.logger.info(f"🎯 독립적 PDS 서버 초기화: {self.host}:{self.port}")

    def _initialize_camera(self):
        """카메라 또는 데모 영상 초기화"""
        if self.demo_mode:
            return self._initialize_demo_video()
        else:
            # 실제 카메라 초기화 (필요시)
            import cv2
            for camera_index in [0, 1, 2]:
                try:
                    cap = cv2.VideoCapture(camera_index)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            self.logger.info(f"✅ 카메라 {camera_index} 초기화 성공")
                            return cap
                    cap.release()
                except Exception as e:
                    self.logger.warning(f"카메라 {camera_index} 초기화 실패: {e}")
            return None

    def _auto_rotate_frame(self, frame):
        """GUI에서 올바른 방향으로 보이도록 회전 조정"""
        if frame is None:
            return frame
        
        # pose_data_rotated로 만든 데모는 이미 올바른 방향이므로 추가 회전 불필요
        return frame

    def _send_improved_gesture_event(self, gesture: str, confidence: float, debug_info: Dict):
        """제스처 이벤트 송신"""
        # 내부 제스처명을 TCP 통신용 대문자로 변환
        tcp_gesture = TCP_GESTURE_NAMES.get(gesture, gesture.upper())
        
        event = {
            "type": "event",
            "event": "MARSHALING_GESTURE_DETECTED",
            "result": tcp_gesture,
            "confidence": confidence
        }
        
        # RedWing GUI Server로 전송
        if self.redwing_connected:
            self._send_to_redwing(event)
        
        # 연결된 클라이언트들에게도 전송
        self._broadcast_to_clients(event)
        
        self.logger.info(f"🎯 제스처 이벤트 송신: {tcp_gesture} (신뢰도: {confidence:.2f})")

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

    def stop_server(self):
        """서버 중지"""
        self.is_running = False
        self.marshaling_active = False
        
        # 카메라 해제
        if self.camera_cap:
            self.camera_cap.release()
            self.camera_cap = None
        
        # OpenCV 윈도우 해제
        try:
            cv2.destroyAllWindows()
        except:
            pass
        
        self.logger.info("독립적 PDS TCP 서버 중지")

    def _start_marshaling(self):
        """마샬링 시작"""
        if self.marshaling_active:
            self.logger.warning("⚠️ 마샬링이 이미 활성화되어 있습니다")
            return
        
        self.marshaling_active = True
        self.logger.info("🎯 마샬링 시작")
        
        # 제스처 확신도 상태 리셋
        self.gesture_confirmation = {
            'current_gesture': None,
            'confirmation_count': 0,
            'required_confirmations': 30,
            'confidence_threshold': 0.9,
        }
        
        return True

    def _stop_marshaling(self):
        """마샬링 중지"""
        if not self.marshaling_active:
            self.logger.warning("⚠️ 마샬링이 이미 비활성화되어 있습니다")
            return
        
        self.marshaling_active = False
        self.logger.info("🛑 마샬링 중지")
        return True

    def _show_initial_gui(self):
        """통합 GUI 스레드 시작"""
        import threading
        
        # 통합 GUI 관리 스레드 시작
        gui_thread = threading.Thread(target=self._unified_gui_loop, daemon=True)
        gui_thread.start()
        self.logger.info("✅ 통합 GUI 스레드 시작")

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

    def _prepare_demo_videos(self):
        """데모 영상 준비 - concatenated_demo 파일 사용"""
        demo_dir = Path('demo_videos')
        if not demo_dir.exists():
            self.logger.warning("⚠️ demo_videos 폴더가 없습니다")
            return
        
        # 원본 concatenated_demo 파일 찾기 (_predictions 제외)
        demo_files = []
        for file in demo_dir.glob('concatenated_demo_*.mp4'):
            # _predictions.mp4 파일은 제외 (이미 예측이 포함된 최종 영상)
            if not file.name.endswith('_predictions.mp4'):
                demo_files.append(file)
        
        if not demo_files:
            self.logger.warning("⚠️ 원본 concatenated_demo 파일이 없습니다")
            return
        
        # 가장 최근 원본 파일
        latest_demo = sorted(demo_files)[-1]
        segments_file = str(latest_demo).replace('.mp4', '_segments.json')
        
        if not Path(segments_file).exists():
            self.logger.warning(f"⚠️ 세그먼트 파일이 없습니다: {segments_file}")
            return
        
        # 세그먼트 정보 로드
        with open(segments_file, 'r', encoding='utf-8') as f:
            self.demo_segments = json.load(f)
        
        self.demo_videos = [{'path': str(latest_demo), 'segments': self.demo_segments}]
        self.logger.info(f"🎬 데모 영상 준비 완료: {latest_demo.name}")
        self.logger.info(f"📊 세그먼트 수: {len(self.demo_segments)}개")

    def _initialize_demo_video(self):
        """데모 영상 초기화"""
        import cv2
        
        # 데모 영상 준비
        if not self.demo_videos:
            self._prepare_demo_videos()
        
        if not self.demo_videos:
            self.logger.error("❌ 데모 영상 파일이 없습니다")
            return None
        
        # 데모 영상 파일 열기
        demo_video = self.demo_videos[0]
        cap = cv2.VideoCapture(demo_video['path'])
        
        if not cap.isOpened():
            self.logger.error(f"❌ 데모 영상 열기 실패: {demo_video['path']}")
            return None
        
        self.current_frame_idx = 0
        self.logger.info(f"🎬 데모 영상 시작: {demo_video['path']}")
        return cap

    def _get_current_ground_truth(self):
        """현재 프레임의 ground truth 제스처 반환"""
        if not self.demo_segments:
            return None
        
        for segment in self.demo_segments:
            if segment['start_frame'] <= self.current_frame_idx <= segment['end_frame']:
                return segment['gesture']
        
        return None

    def _draw_enhanced_gui_overlay_rotated(self, frame, gesture, confidence, debug_info, frame_count):
        """회전된 프레임에 맞는 오버레이 (create_visual_demo.py 스타일)"""
        if frame is None:
            return frame
        
        height, width = frame.shape[:2]  # 이미 회전된 프레임의 크기
        
        # 현재 ground truth 가져오기
        gt_gesture = self._get_current_ground_truth() if self.demo_mode else None
        
        # 반투명 오버레이 패널 생성
        overlay = frame.copy()
        
        # 상단 정보 패널 (반투명 검은 배경)
        cv2.rectangle(overlay, (0, 0), (width, 120), self.colors['background'], -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # 하단 정보 패널
        cv2.rectangle(overlay, (0, height-80), (width, height), self.colors['background'], -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # 자세 스켈레톤 그리기 (회전된 좌표계에서)
        pose_results = debug_info.get('pose_results')
        if pose_results and pose_results.pose_landmarks:
            # 스켈레톤을 더 굵고 눈에 띄게
            self.pose_detector.mp_drawing.draw_landmarks(
                frame, 
                pose_results.pose_landmarks, 
                self.pose_detector.mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=self.pose_detector.mp_drawing.DrawingSpec(
                    color=self.colors['skeleton'], thickness=4, circle_radius=6),
                connection_drawing_spec=self.pose_detector.mp_drawing.DrawingSpec(
                    color=self.colors['skeleton'], thickness=3)
            )
        
        # Ground Truth (왼쪽 상단)
        if gt_gesture:
            gt_color = self.colors.get(gt_gesture, self.colors['text'])
            cv2.rectangle(frame, (10, 10), (300, 50), gt_color, 3)
            cv2.putText(frame, f'GROUND TRUTH: {gt_gesture.upper()}', (20, 35), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, gt_color, 2)
        else:
            # 실시간 카메라 모드
            cv2.rectangle(frame, (10, 10), (300, 50), (0, 255, 0), 3)
            cv2.putText(frame, 'LIVE CAMERA MODE', (20, 35), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        
        # AI 예측 (오른쪽 상단)
        if gesture and confidence > 0:
            pred_color = self.colors.get(gesture, self.colors['text'])
            cv2.rectangle(frame, (width-350, 10), (width-10, 50), pred_color, 3)
            cv2.putText(frame, f'AI PREDICTION: {gesture.upper()}', (width-340, 35), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, pred_color, 2)
            
            # 신뢰도 바 (오른쪽 상단 아래)
            bar_width = int(300 * confidence)
            cv2.rectangle(frame, (width-350, 60), (width-50, 85), (64, 64, 64), -1)
            cv2.rectangle(frame, (width-350, 60), (width-350+bar_width, 85), pred_color, -1)
            cv2.putText(frame, f'Confidence: {confidence:.1%}', (width-340, 100), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['text'], 2)
        
        # 정확성 표시 (중앙 상단) - 데모 모드에서만
        if self.demo_mode and gesture and gt_gesture:
            is_correct = gesture == gt_gesture
            status_color = (0, 255, 0) if is_correct else (0, 0, 255)
            status_text = "CORRECT" if is_correct else "WRONG"
            
            cv2.rectangle(frame, (width//2-100, 10), (width//2+100, 50), status_color, 3)
            cv2.putText(frame, status_text, (width//2-80, 35), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
        
        # 시스템 상태 (하단 왼쪽)
        if self.demo_mode:
            total_frames = int(self.camera_cap.get(cv2.CAP_PROP_FRAME_COUNT)) if self.camera_cap else 1
            progress = (self.current_frame_idx / total_frames) * 100 if total_frames > 0 else 0
            status_text = f"Frame: {self.current_frame_idx}/{total_frames} ({progress:.1f}%)"
        else:
            status_text = f"Frame: {frame_count} | PDS Server Active"
        
        if self.redwing_connected:
            status_text += " | RedWing Connected"
        
        cv2.putText(frame, status_text, (10, height-50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['text'], 2)
        
        # 제스처 확신도 정보 (하단 중앙)
        conf_text = f"Confirmations: {self.gesture_confirmation['confirmation_count']}/{self.gesture_confirmation['required_confirmations']}"
        cv2.putText(frame, conf_text, (width//2-100, height-50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['text'], 2)
        
        # 모델 정보 (하단 오른쪽)
        cv2.putText(frame, "TCN Gesture Model", (width-200, height-50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['text'], 2)
        cv2.putText(frame, "Real-time Recognition", (width-200, height-25), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['text'], 1)
        
        return frame

    def _process_improved_gesture_confirmation(self, gesture: str, confidence: float, debug_info: Dict):
        """간단한 제스처 확신도 처리"""
        current_time = time.time()
        
        # 제스처 확신도 카운팅
        if self.gesture_confirmation['current_gesture'] == gesture:
            self.gesture_confirmation['confirmation_count'] += 1
        else:
            # 새로운 제스처 - 카운트 리셋
            self.gesture_confirmation['current_gesture'] = gesture
            self.gesture_confirmation['confirmation_count'] = 1
        
        # 필요한 확신 횟수에 도달했는지 확인
        if self.gesture_confirmation['confirmation_count'] >= self.gesture_confirmation['required_confirmations']:
            
            # 쿨다운 체크
            if (self.last_gesture != gesture or 
                current_time - self.last_gesture_time > self.gesture_cooldown):
                
                self._send_improved_gesture_event(gesture, confidence, debug_info)
                self.last_gesture = gesture
                self.last_gesture_time = current_time
                
                # 확신도 카운트 리셋
                self.gesture_confirmation['confirmation_count'] = 0
                
                self.logger.info(f"✅ 확인된 제스처 이벤트: {gesture} (신뢰도: {confidence:.2f})")

    def _unified_gui_loop(self):
        """단일 스레드에서 모든 GUI 관리 (create_visual_demo.py 방식)"""
        import time
        
        window_name = 'PDS Marshaling System'
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
        cv2.moveWindow(window_name, 100, 100)
        
        # 카메라는 필요할 때만 초기화
        camera_cap = None
        frame_count = 0
        
        self.logger.info("🎯 통합 GUI 루프 시작 (create_visual_demo.py 방식)")
        
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
                    # === 카메라/데모 영상 피드 모드 ===
                    if not camera_cap:
                        # 카메라 또는 데모 영상 초기화
                        camera_cap = self._initialize_camera()
                        if not camera_cap:
                            self.logger.error("❌ 카메라/데모 영상 초기화 실패")
                            # 에러 화면 표시
                            frame = np.zeros((480, 640, 3), dtype=np.uint8)
                            cv2.putText(frame, "CAMERA ERROR", (200, 240), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                            cv2.imshow(window_name, frame)
                            time.sleep(1.0)
                            continue
                        else:
                            self.logger.info("📹 카메라/데모 영상 초기화 성공")
                            frame_count = 0
                            self.camera_cap = camera_cap  # 클래스 변수에도 저장
                    
                    # 프레임 읽기
                    ret, frame = camera_cap.read()
                    if not ret or frame is None:
                        if self.demo_mode:
                            # 🎬 데모 영상이 끝나면 처음부터 다시 시작
                            self.logger.info("🎬 데모 영상 끝 - 처음부터 다시 시작")
                            camera_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            self.current_frame_idx = 0
                            continue
                        else:
                            self.logger.warning("⚠️ 카메라 프레임 읽기 실패")
                            camera_cap = None
                            continue
                    
                    frame_count += 1
                    if self.demo_mode:
                        self.current_frame_idx += 1
                    
                    # 🎯 create_visual_demo.py와 동일한 제스처 인식 처리
                    try:
                        processed_frame, gesture, confidence, debug_info = self.pose_detector.process_frame(frame)
                        display_frame = processed_frame if processed_frame is not None else frame
                        
                        # 제스처 확신도 검증
                        if gesture and confidence > self.gesture_confirmation['confidence_threshold']:
                            self._process_improved_gesture_confirmation(gesture, confidence, debug_info)
                        
                        # 🔄 GUI 표시용 회전 (90도 시계방향)
                        display_frame = self._auto_rotate_frame(display_frame)
                        
                        # 🎨 회전된 프레임에 맞는 오버레이 적용
                        display_frame = self._draw_enhanced_gui_overlay_rotated(
                            display_frame, gesture, confidence, debug_info, frame_count)
                        
                        # 화면에 맞게 크기 조정 (최대 1280x720)
                        h, w = display_frame.shape[:2]
                        if w > 1280 or h > 720:
                            scale = min(1280/w, 720/h)
                            new_w, new_h = int(w * scale), int(h * scale)
                            display_frame = cv2.resize(display_frame, (new_w, new_h))
                        
                        cv2.imshow(window_name, display_frame)
                        
                        # 데모 모드에서 정확도 로깅
                        if self.demo_mode and gesture:
                            gt_gesture = self._get_current_ground_truth()
                            if gt_gesture:
                                if gesture == gt_gesture:
                                    self.logger.info(f"✅ 제스처 일치: {gesture} (신뢰도: {confidence:.2f})")
                                else:
                                    self.logger.warning(f"🚨 제스처 불일치: 예상({gt_gesture}) vs 인식({gesture}) (신뢰도: {confidence:.2f})")
                        
                    except Exception as e:
                        self.logger.error(f"제스처 처리 오류: {e}")
                        # 오류 시 원본 프레임 표시 (회전 및 크기 조정)
                        cv2.putText(frame, "PROCESSING ERROR", (10, 60), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        
                        # GUI 표시용 회전 및 크기 조정
                        error_frame = self._auto_rotate_frame(frame)
                        h, w = error_frame.shape[:2]
                        if w > 1280 or h > 720:
                            scale = min(1280/w, 720/h)
                            new_w, new_h = int(w * scale), int(h * scale)
                            error_frame = cv2.resize(error_frame, (new_w, new_h))
                        
                        cv2.imshow(window_name, error_frame)
                
                # 키 입력 처리
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    self.logger.info("사용자가 'q' 키로 종료 요청")
                    self.stop_server()
                    break
                elif key == ord(' '):  # 스페이스바로 마샬링 토글
                    if self.marshaling_active:
                        self.logger.info("사용자가 스페이스바로 마샬링 중지 요청")
                        self._stop_marshaling()
                    else:
                        self.logger.info("사용자가 스페이스바로 마샬링 시작 요청")
                        self._start_marshaling()
                    
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
        print("🎨 create_visual_demo.py와 동일한 정확한 처리 방식 사용")
        print("🎯 간단한 제스처 확신도: 30프레임 연속 감지 (약 1초, 임계값: 0.9)")
        print("⏰ 쿨다운: 3.0초")
        print("\n🎮 키 조작:")
        print("  - 스페이스바: 마샬링 시작/중지")
        print("  - Q: 서버 종료")
        
        # 🎬 데모 모드 정보 출력
        if DEMO_VIDEO_CONFIG['enabled']:
            print("\n🎬 데모 영상 모드 활성화")
            print("📁 concatenated_demo 파일 자동 검색")
            print("🔁 무한 반복 재생")
            print("📊 ground truth와 실시간 비교")
        else:
            print("\n📹 실시간 카메라 모드")
        
        print("\n💡 스페이스바를 눌러 마샬링을 시작하세요!")
        print("Ctrl+C로 종료")
        
        # 서버 유지
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n서버 종료 중...")
        server.stop_server() 