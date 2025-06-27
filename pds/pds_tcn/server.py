# -*- coding: utf-8 -*-
"""
Improved TCP Server with Advanced Gesture Detection
오동작 방지를 위한 개선된 PDS TCP 서버
"""

import socket
import threading
import json
import time
import logging
from typing import Dict, Optional, Callable
from datetime import datetime

from config import SERVER_CONFIG, GESTURE_CLASSES, TTS_MESSAGES, TCP_GESTURE_NAMES, IMPROVED_GESTURE_CONFIG
from detector import ImprovedAdaptiveWindowPoseDetector

class ImprovedPDSTCPServer:
    """오동작 방지를 위한 개선된 PDS TCP 서버"""
    
    def __init__(self, gesture_callback: Optional[Callable] = None):
        self.logger = logging.getLogger(__name__)
        
        # 서버 설정
        self.host = SERVER_CONFIG['redwing_host']
        self.command_port = SERVER_CONFIG['command_port']  # RedWing → PDS
        self.event_port = SERVER_CONFIG['event_port']      # PDS → RedWing
        
        # 소켓
        self.command_socket = None
        self.event_socket = None
        
        # 상태
        self.is_running = False
        self.marshaling_active = False
        
        # 클라이언트 연결
        self.redwing_connection = None
        
        # 개선된 제스처 검출기
        self.pose_detector = ImprovedAdaptiveWindowPoseDetector()
        self.gesture_callback = gesture_callback
        
        # 제스처 이벤트 관리
        self.last_gesture = None
        self.last_gesture_time = 0
        self.gesture_cooldown = 2.0  # 쿨다운을 2초로 증가 (안정성 우선)
        
        # 개선된 제스처 확신도 관리
        self.improved_config = IMPROVED_GESTURE_CONFIG
        self.gesture_confirmation = {
            'current_gesture': None,
            'confirmation_count': 0,
            'required_confirmations': 5,  # 5회 연속으로 증가
            'confidence_threshold': 0.85,  # 더 높은 신뢰도 임계값
            'completion_required': True    # 동작 완료 필수
        }
        
        # 확신도 이력 추적
        self.confirmation_history = []
        
    def start_server(self):
        """서버 시작"""
        try:
            self.is_running = True
            
            # 명령 수신 서버 시작
            self._start_command_server()
            
            # 이벤트 송신 클라이언트 시작  
            self._start_event_client()
            
            self.logger.info("🎯 개선된 PDS TCP 서버 시작 완료 (고급 오동작 방지)")
            
        except Exception as e:
            self.logger.error(f"서버 시작 실패: {e}")
            self.stop_server()
    
    def _start_command_server(self):
        """명령 수신 서버 시작"""
        self.command_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.command_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.command_socket.bind(('0.0.0.0', self.command_port))
        self.command_socket.listen(SERVER_CONFIG['max_clients'])
        
        self.logger.info(f"명령 수신 서버 시작: 포트 {self.command_port}")
        
        # 명령 수신 스레드
        command_thread = threading.Thread(target=self._handle_commands, daemon=True)
        command_thread.start()
    
    def _start_event_client(self):
        """이벤트 송신 클라이언트 시작"""
        # RedWing 서버에 연결 시도
        event_thread = threading.Thread(target=self._connect_to_redwing, daemon=True)
        event_thread.start()
    
    def _connect_to_redwing(self):
        """RedWing 서버에 연결"""
        max_retries = 10
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                self.event_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.event_socket.connect((self.host, self.event_port))
                self.logger.info(f"RedWing 서버 연결 성공: {self.host}:{self.event_port}")
                break
                
            except Exception as e:
                self.logger.warning(f"RedWing 연결 실패 ({attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    self.logger.error("RedWing 서버 연결 포기")
                    self.event_socket = None
    
    def _handle_commands(self):
        """명령 처리 스레드"""
        while self.is_running:
            try:
                client_socket, address = self.command_socket.accept()
                self.logger.info(f"클라이언트 연결: {address}")
                
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
                elif command == 'MARSHALING_STOP':
                    self._stop_marshaling()
                else:
                    self.logger.warning(f"알 수 없는 명령: {command}")
                    
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 파싱 오류: {e}")
        except Exception as e:
            self.logger.error(f"명령 처리 오류: {e}")
    
    def _start_marshaling(self):
        """개선된 마샬링 시작"""
        self.marshaling_active = True
        self.logger.info("🎯 개선된 마샬링 인식 활성화")
        
        # 상태 초기화
        self.gesture_confirmation = {
            'current_gesture': None,
            'confirmation_count': 0,
            'required_confirmations': 5,
            'confidence_threshold': 0.85,
            'completion_required': True
        }
        self.confirmation_history = []
        
        # 응답 송신
        response = {
            "type": "response",
            "response": "MARSHALING_RECOGNITION_ACTIVATED",
            "mode": "improved_adaptive_window",
            "features": {
                "motion_completion_detection": True,
                "prediction_consistency_check": True,
                "dynamic_thresholds": True,
                "gesture_transition_detection": True,
                "confidence_trend_analysis": True
            }
        }
        self._send_to_redwing(response)
        
        # 개선된 제스처 인식 시작
        self._start_improved_gesture_recognition()
    
    def _stop_marshaling(self):
        """마샬링 중지"""
        self.marshaling_active = False
        self.logger.info("개선된 마샬링 인식 비활성화")
        
        # 응답 송신
        response = {
            "type": "response", 
            "response": "MARSHALING_RECOGNITION_DEACTIVATED"
        }
        self._send_to_redwing(response)
    
    def _start_improved_gesture_recognition(self):
        """개선된 제스처 인식 시작"""
        if hasattr(self, 'gesture_thread') and self.gesture_thread.is_alive():
            return
            
        self.gesture_thread = threading.Thread(target=self._improved_gesture_recognition_loop, daemon=True)
        self.gesture_thread.start()
    
    def _improved_gesture_recognition_loop(self):
        """개선된 제스처 인식 루프"""
        import cv2
        
        cap = cv2.VideoCapture(0)  # 웹캠 사용
        
        if not cap.isOpened():
            self.logger.error("카메라를 열 수 없습니다")
            return
        
        self.logger.info("🎯 개선된 제스처 인식 루프 시작")
        
        while self.marshaling_active and self.is_running:
            ret, frame = cap.read()
            if not ret:
                continue
            
            # 개선된 프레임 처리
            processed_frame, gesture, confidence, debug_info = self.pose_detector.process_frame(frame)
            
            # 개선된 제스처 확신도 검증
            if gesture and confidence > self.gesture_confirmation['confidence_threshold']:
                self._process_improved_gesture_confirmation(gesture, confidence, debug_info)
            
            # 프레임 표시 (디버그용)
            if processed_frame is not None:
                final_frame = self.pose_detector.draw_adaptive_info(
                    processed_frame, gesture, confidence, debug_info)
                
                # 개선된 확신도 정보 추가
                self._draw_improved_confirmation_info(final_frame, debug_info)
                
                cv2.imshow('Improved PDS - Advanced Marshaling Recognition', final_frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        
        cap.release()
        cv2.destroyAllWindows()
        self.logger.info("개선된 제스처 인식 루프 종료")
    
    def _process_improved_gesture_confirmation(self, gesture: str, confidence: float, debug_info: Dict):
        """개선된 제스처 확신도 처리"""
        current_time = time.time()
        
        # 동작 완료 여부 확인 (필수 조건)
        gesture_completed = debug_info.get('gesture_completed', False)
        if self.gesture_confirmation['completion_required'] and not gesture_completed:
            return  # 완료되지 않은 동작은 무시
        
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
            # 새로운 제스처 - 카운트 리셋하되, 더 엄격하게
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
        if same_gesture_count < 4:  # 5개 중 최소 4개는 같아야 함
            return False
        
        # 평균 신뢰도가 충분한지 확인
        avg_confidence = sum(h['confidence'] for h in recent_history) / len(recent_history)
        if avg_confidence < 0.85:
            return False
        
        # 모두 완료된 동작인지 확인
        completed_count = sum(1 for h in recent_history if h['gesture_completed'])
        if completed_count < 3:  # 5개 중 최소 3개는 완료되어야 함
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
            f"Gesture Completed: {debug_info.get('gesture_completed', False)}"
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
        y_start = height - 200
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
            }
        }
        
        self._send_to_redwing(event)
        self.logger.info(f"🎯 개선된 제스처 이벤트 송신: {tcp_gesture} (신뢰도: {confidence:.2f})")
    
    def _send_to_redwing(self, data: Dict):
        """RedWing에 데이터 송신"""
        if not self.event_socket:
            self.logger.warning("RedWing 연결이 없습니다")
            return False
        
        try:
            message = json.dumps(data, ensure_ascii=False) + '\n'
            self.event_socket.send(message.encode('utf-8'))
            return True
            
        except Exception as e:
            self.logger.error(f"RedWing 송신 오류: {e}")
            self.event_socket = None
            # 재연결 시도
            self._connect_to_redwing()
            return False
    
    def stop_server(self):
        """서버 중지"""
        self.is_running = False
        self.marshaling_active = False
        
        if self.command_socket:
            self.command_socket.close()
        if self.event_socket:
            self.event_socket.close()
        
        self.logger.info("개선된 PDS TCP 서버 중지")

if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.INFO)
    
    # 개선된 서버 시작
    server = ImprovedPDSTCPServer()
    
    try:
        server.start_server()
        
        print("🎯 개선된 PDS 서버 실행 중...")
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