#!/usr/bin/env python3
"""
dl-falcon RedWing Interface
항공전자장비 스타일 파일럿 인터페이스 - .ui 파일 기반
음성 인터페이스, 활주로 상태, 조류 위험도 모니터링 통합
"""

import sys
import os
import time
import threading
from datetime import datetime, timezone
from typing import Optional

# Qt imports
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
        QProgressBar, QMessageBox, QWidget, QGroupBox
    )
    from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt, QMutex, QEventLoop
    from PyQt6 import uic
except ImportError:
    print("FAIL PyQt6가 설치되지 않았습니다. 설치하려면:")
    print("pip install PyQt6")
    sys.exit(1)

# 프로젝트 모듈 imports
sys.path.insert(0, os.path.dirname(__file__))

from main_controller import get_voice_controller

# 타입 힌트용 import (TYPE_CHECKING 블록에서만 사용)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main_controller.main_controller import VoiceInteractionController

class VoiceWorkerThread(QThread):
    """음성 처리를 위한 워커 스레드"""
    
    # 시그널 정의
    voice_started = pyqtSignal()
    voice_completed = pyqtSignal(dict)  # interaction 결과
    voice_error = pyqtSignal(str)
    stt_result = pyqtSignal(str, float)  # text, confidence
    tts_text_ready = pyqtSignal(str)  # TTS 텍스트 생성 완료
    recording_progress = pyqtSignal(int)  # 실제 녹음 진행률
    
    def __init__(self, controller: "VoiceInteractionController"):
        super().__init__()
        self.controller = controller
        self.recording_duration = 5.0
    
    def run(self):
        """음성 처리 실행"""
        try:
            print(f"[VoiceWorkerThread] 🎤 음성 처리 시작")
            self.voice_started.emit()
            
            # OK STT 완료 콜백 설정 (컨트롤러의 STT 처리 완료 즉시 호출됨)
            def on_stt_completed(stt_result):
                """STT 완료 즉시 GUI에 전달"""
                if stt_result:
                    stt_text = stt_result.text
                    stt_confidence = stt_result.confidence_score
                    print(f"[VoiceWorkerThread] 🚀 STT 완료 콜백 → GUI 시그널 전송: '{stt_text}' ({stt_confidence:.2f})")
                    self.stt_result.emit(stt_text, stt_confidence)
                else:
                    print(f"[VoiceWorkerThread] WARN STT 결과가 없습니다")
            
            # OK TTS 텍스트 생성 완료 콜백 설정
            def on_tts_text_ready(tts_text):
                """TTS 텍스트 생성 완료 즉시 GUI에 전달"""
                if tts_text:
                    print(f"[VoiceWorkerThread] TTS TEXT READY 콜백 → GUI 시그널 전송: '{tts_text[:50]}...'")
                    self.tts_text_ready.emit(tts_text)
                else:
                    print(f"[VoiceWorkerThread] WARN TTS 텍스트가 없습니다")
            
            # 컨트롤러에 콜백들 설정
            self.controller.set_stt_callback(on_stt_completed)
            self.controller.set_tts_callback(on_tts_text_ready)
            
            # 🎯 실제 녹음 진행률 추적 스레드 시작
            import threading
            import time
            
            def recording_progress_tracker():
                """실제 녹음 진행률 추적 - 실시간 타이밍 기반"""
                import time
                duration = self.recording_duration
                steps = 50  # 50단계
                
                # 초기화 시간 고려하여 약간 지연 후 시작
                time.sleep(0.3)  # AudioIO 초기화 시간 고려
                
                start_time = time.time()
                self.recording_progress.emit(0)
                
                while hasattr(self, '_recording_active') and self._recording_active:
                    current_time = time.time()
                    elapsed_time = current_time - start_time
                    
                    # 실제 경과 시간 기준으로 진행률 계산
                    progress = min(steps, int((elapsed_time / duration) * steps))
                    self.recording_progress.emit(progress)
                    
                    # 완료되면 종료
                    if elapsed_time >= duration:
                        self.recording_progress.emit(steps)  # 100% 완료
                        break
                    
                    # 더 정밀한 업데이트 (50ms마다)
                    time.sleep(0.05)
            
            # 녹음 시작 시그널
            self._recording_active = True
            progress_thread = threading.Thread(target=recording_progress_tracker, daemon=True)
            progress_thread.start()
            
            # 🎯 실제 녹음 시간 측정
            actual_start_time = time.time()
            print(f"[VoiceWorkerThread] ⏱️ 실제 녹음 시작: {self.recording_duration}초 예정")
            
            # 음성 상호작용 처리 (콜사인 없이)
            interaction = self.controller.handle_voice_interaction(
                recording_duration=self.recording_duration
            )
            
            # 실제 녹음 시간 계산
            actual_end_time = time.time()
            actual_duration = actual_end_time - actual_start_time
            print(f"[VoiceWorkerThread] ⏱️ 실제 녹음 완료: {actual_duration:.2f}초 (예정: {self.recording_duration}초)")
            
            # 녹음 완료 시그널
            self._recording_active = False
            
            # OK 간단한 요약만 출력 (전체 객체 출력 금지)
            print(f"[VoiceWorkerThread] 🔄 상호작용 완료:")
            print(f"  - 세션: {interaction.session_id}")
            print(f"  - 상태: {interaction.status}")
            print(f"  - STT: '{interaction.stt_result.text if interaction.stt_result else 'None'}'")
            print(f"  - 요청: {interaction.pilot_request.request_code if interaction.pilot_request else 'None'}")
            print(f"  - TTS: '{interaction.pilot_response.response_text if interaction.pilot_response else 'None'}'")
            
            # TTS 응답 텍스트 확인
            response_text = interaction.pilot_response.response_text if interaction.pilot_response else ""
            print(f"[VoiceWorkerThread] SPK TTS 응답: '{response_text}'")
            
            # OK TTS 응답 상세 디버깅
            print(f"[VoiceWorkerThread] SEARCH TTS 응답 상세:")
            print(f"  - interaction.pilot_response: {interaction.pilot_response is not None}")
            if interaction.pilot_response:
                print(f"  - response_text: '{interaction.pilot_response.response_text}'")
                print(f"  - response_text 길이: {len(interaction.pilot_response.response_text) if interaction.pilot_response.response_text else 0}")
            print(f"  - interaction.tts_text: '{interaction.tts_text}'")
            
            # 완료 시그널 (TTS 응답 포함)
            result = {
                'session_id': interaction.session_id,
                'status': interaction.status,
                'stt_text': interaction.stt_result.text if interaction.stt_result else "",
                'request_code': interaction.pilot_request.request_code if interaction.pilot_request else "",
                'response_text': response_text,
                'error_message': getattr(interaction, 'error_message', None)
            }
            
            print(f"[VoiceWorkerThread] 📤 완료 시그널 전송: {result}")
            print(f"[VoiceWorkerThread] 📤 최종 response_text: '{result['response_text']}'")
            self.voice_completed.emit(result)
            
        except Exception as e:
            print(f"[VoiceWorkerThread] FAIL 음성 처리 오류: {e}")
            self.voice_error.emit(str(e))

class RedWing(QMainWindow):
    
    SERVER_HOST = "localhost"  # 새로운 RedWing GUI Server로 연결
    SERVER_PORT = 8000         # RedWing GUI Server 포트
    FALLBACK_HOST = "127.0.0.1"  # 연결 실패 시 fallback
    
    # 🔧 GUI 업데이트를 위한 시그널 정의 (스레드 안전성)
    bird_risk_changed_signal = pyqtSignal(str)
    runway_alpha_changed_signal = pyqtSignal(str)
    runway_bravo_changed_signal = pyqtSignal(str)
    event_tts_signal = pyqtSignal(str)  # 🔧 이벤트 TTS용 시그널 추가
    reset_status_signal = pyqtSignal()  # 🔧 상태 리셋용 시그널 추가
    
    def __init__(self, stt_manager=None, tts_manager=None, api_client=None, 
                 use_keyboard_shortcuts=True, parent=None):
        """GUI 초기화"""
        super().__init__(parent)
        
        # 초기화 상태 변수
        self.initialization_success = False
        
        try:
            # Core managers 설정
            self.stt_manager = stt_manager
            self.tts_manager = tts_manager
            self.api_client = api_client
            
            # 컨트롤러 초기화
            self.controller: Optional["VoiceInteractionController"] = None
            self.voice_worker: Optional[VoiceWorkerThread] = None
            self.is_recording = False
            # 🆕 마샬링 상태 변수
            self.marshaling_active = False
            
            # 서버 연결 재시도 관리 (스레드 안전)
            self.server_retry_active = False
            self.server_connection_failed = False
            
            print("🔧 UI 로드 중...")
            # UI 로드
            self.load_ui()
            
            print("🔧 컨트롤러 초기화 중...")
            # 컨트롤러 초기화 (선택적으로 실행)
            try:
                self.init_controller()
            except Exception as controller_error:
                print(f"⚠️ 컨트롤러 초기화 실패 (계속 진행): {controller_error}")
                self.controller = None
            
            print("🔧 타이머 초기화 중...")
            # 타이머 초기화
            self.init_timers()
            
            print("🔧 시그널 연결 중...")
            # 시그널 연결
            self.connect_signals()
            
            # 🔧 GUI 초기화 완료 후 서버 연결 시도 및 준비 완료 신호 전송 (스레드 안전)
            threading.Timer(1.0, lambda: self.signal_gui_ready()).start()  # 1초 후 신호 전송
            
            self.initialization_success = True
            print("🚁 RedWing Interface 초기화 완료")
            
        except Exception as e:
            print(f"❌ RedWing Interface 초기화 실패: {e}")
            import traceback
            traceback.print_exc()
            self.initialization_success = False
            # 초기화 실패해도 GUI는 표시되도록 함
            self.setWindowTitle("RedWing Interface (초기화 실패)")
            if hasattr(self, 'label_main_status'):
                self.label_main_status.setText("INIT FAILED")
                self.label_main_status.setStyleSheet("background-color: #330000; color: #ff4444;")
    
    def load_ui(self):
        """UI 파일 로드"""
        try:
            # 현재 디렉토리에서 .ui 파일 로드
            ui_file = os.path.join(os.path.dirname(__file__), "redwing_gui.ui")
            if not os.path.exists(ui_file):
                raise FileNotFoundError(f"UI 파일을 찾을 수 없습니다: {ui_file}")
            
            # .ui 파일 로드
            uic.loadUi(ui_file, self)
            print(f"✅ UI 파일 로드 완료: {ui_file}")
            
            # UI 요소들 찾기
            self.voice_button = self.findChild(QPushButton, "voice_button")
            self.marshall_button = self.findChild(QPushButton, "marshall_button")
            self.label_main_status = self.findChild(QLabel, "main_status")
            self.label_utc_time = self.findChild(QLabel, "time_utc")
            self.label_local_time = self.findChild(QLabel, "time_local")
            self.label_runway_alpha = self.findChild(QLabel, "status_runway_a")
            self.label_runway_bravo = self.findChild(QLabel, "status_runway_b")
            self.label_bird_risk = self.findChild(QLabel, "status_bird_risk")
            self.progress_voice = self.findChild(QProgressBar, "progressBar_voice")
            
            # UI 요소 확인
            print(f"[GUI] UI 요소 확인:")
            print(f"   voice_button: {self.voice_button is not None}")
            print(f"   marshall_button: {self.marshall_button is not None}")
            print(f"   label_main_status: {self.label_main_status is not None}")
            print(f"   progress_voice: {self.progress_voice is not None}")
            
            # 기본 상태 설정
            if self.progress_voice:
                self.progress_voice.setValue(0)
            
        except Exception as e:
            print(f"❌ UI 로드 실패: {e}")
            raise
    
    def connect_signals(self):
        """시그널과 슬롯 연결"""
        # 버튼 연결
        if self.voice_button:
            self.voice_button.clicked.connect(self.start_voice_input)
        # 🆕 START MARSHAL 버튼 연결
        if self.marshall_button:
            self.marshall_button.clicked.connect(self.toggle_marshaling)
        
        # 시그널 연결 완료
        
        # 🔧 시그널 연결 (스레드 안전성)
        self.bird_risk_changed_signal.connect(self.update_bird_risk_display)
        self.runway_alpha_changed_signal.connect(self.update_runway_alpha_display)
        self.runway_bravo_changed_signal.connect(self.update_runway_bravo_display)
        self.event_tts_signal.connect(self.update_tts_display_with_event)
        self.reset_status_signal.connect(self.reset_status)
    
    def init_controller(self):
        """컨트롤러 초기화"""
        try:
            print(f"[GUI] 🔧 컨트롤러 초기화 중... (서버: {self.SERVER_HOST}:{self.SERVER_PORT})")
            
            # 🔧 마이크 디바이스 확인 및 선택
            self.check_and_setup_microphone()
            
            # 런타임에 지연 로딩된 함수 가져오기
            if not hasattr(self, '_voice_controller_func'):
                _, self._voice_controller_func = get_voice_controller()
            
            # 🔧 선택된 마이크로 AudioIO 인스턴스 직접 생성
            from audio_io.mic_speaker_io import AudioIO
            selected_mic_index = getattr(self, 'selected_mic_index', None)
            
            print(f"[GUI] 🎤 AudioIO 생성 - 마이크 인덱스: {selected_mic_index}")
            audio_io = AudioIO(input_device_index=selected_mic_index)
            
            # 컨트롤러 생성 - 커스텀 AudioIO 사용
            print(f"[GUI] 🔧 컨트롤러 생성 중 (마이크: {getattr(self, 'selected_mic_name', '기본 마이크')})")
            
            # VoiceInteractionController를 직접 생성
            from main_controller.main_controller import VoiceInteractionController
            from engine import WhisperSTTEngine, UnifiedTTSEngine
            from request_handler import RequestClassifier, TCPServerClient, ResponseProcessor
            from session_handler import SessionManager
            
            # 각 모듈 직접 초기화
            stt_engine = WhisperSTTEngine(model_name="small", language="en", device="auto")
            query_parser = RequestClassifier()
            
            # TCP 기반 서버 클라이언트 - fallback 로직 포함
            main_server_client = self._create_server_client_with_fallback()
            
            response_processor = ResponseProcessor()
            tts_engine = UnifiedTTSEngine(
                use_coqui=True,
                coqui_model="tts_models/en/ljspeech/tacotron2-DDC",
                fallback_to_pyttsx3=True,
                device="cuda"
            )
            session_manager = SessionManager()
            
            # VoiceInteractionController 생성 (선택된 마이크 사용)
            self.controller = VoiceInteractionController(
                audio_io=audio_io,  # 🔧 선택된 마이크가 포함된 AudioIO 사용
                stt_engine=stt_engine,
                query_parser=query_parser,
                main_server_client=main_server_client,
                response_processor=response_processor,
                tts_engine=tts_engine,
                session_manager=session_manager
            )
            
            # 이벤트 핸들러 초기화
            self.setup_event_handlers()
            
            self.update_system_status_display()
            if hasattr(self, 'statusbar') and self.statusbar:
                self.statusbar.showMessage("System ready")
            
        except Exception as e:
            if hasattr(self, 'statusbar') and self.statusbar:
                self.statusbar.showMessage(f"Initialization error: {e}")
            QMessageBox.critical(self, "Initialization Error", f"System initialization failed:\n{e}")
    
    def setup_event_handlers(self):
        """이벤트 핸들러 설정 - localhost fallback 포함"""
        # 먼저 기본 서버로 시도
        if self._try_connect_event_manager(self.SERVER_HOST):
            return
        
        # 기본 서버 실패 시 localhost로 fallback 시도
        print(f"[GUI] 🔄 기본 서버({self.SERVER_HOST}) 연결 실패 - localhost로 fallback 시도")
        if self._try_connect_event_manager(self.FALLBACK_HOST):
            return
        
        # 모든 연결 실패
        print(f"[GUI] ❌ 모든 서버 연결 실패 - 재시도 모드로 전환")
        self.event_manager = None
        self.event_processor = None
        self.event_tts = None
        self.server_connection_failed = True
        # 10초 후부터 5초마다 서버 연결 재시도
        self.server_retry_timer.start(10000)  # 10초 후 시작
    
    def _try_connect_event_manager(self, host: str) -> bool:
        """특정 호스트로 이벤트 매니저 연결 시도"""
        try:
            print(f"[GUI] 🔌 이벤트 매니저 연결 시도: {host}:{self.SERVER_PORT}")
            
            from event_handler import EventManager, EventProcessor, EventTTS
            
            # 이벤트 매니저 초기화
            self.event_manager = EventManager(
                server_host=host, 
                server_port=self.SERVER_PORT, 
                use_simulator=False  # 시뮬레이터 fallback 비활성화
            )
            self.event_processor = EventProcessor()
            self.event_tts = EventTTS(self.controller.tts_engine if self.controller else None)
            
            # 🔧 EventTTS에 스레드 안전한 GUI 콜백 설정
            if self.event_tts:
                self.event_tts.set_gui_callback(self.thread_safe_event_tts_update)
                # 🔧 녹음 상태 체크 콜백 설정
                self.event_tts.set_recording_checker(self.is_recording_or_processing)
                print("[GUI] EventTTS 스레드 안전 GUI 콜백 및 녹음 체크 설정 완료")
            
            # 🔧 TCP 프로토콜 명세에 맞는 이벤트 핸들러 등록
            self.event_manager.register_handler("BR_CHANGED", self.on_bird_risk_changed)
            self.event_manager.register_handler("RWY_A_STATUS_CHANGED", self.on_runway_alpha_changed)
            self.event_manager.register_handler("RWY_B_STATUS_CHANGED", self.on_runway_bravo_changed)
            # 🆕 마샬링 제스처 이벤트 핸들러 등록
            self.event_manager.register_handler("MARSHALING_GESTURE_DETECTED", self.on_marshaling_gesture)
            
            # 이벤트 매니저 연결 시도
            success = self.event_manager.connect()
            
            if success:
                print(f"[GUI] ✅ 이벤트 핸들러 설정 완료: {host}:{self.SERVER_PORT}")
                return True
            else:
                print(f"[GUI] ❌ 이벤트 매니저 연결 실패: {host}:{self.SERVER_PORT}")
                # 실패한 매니저 정리
                if hasattr(self, 'event_manager') and self.event_manager:
                    try:
                        self.event_manager.disconnect()
                    except:
                        pass
                self.event_manager = None
                self.event_processor = None
                self.event_tts = None
                return False
            
        except Exception as e:
            print(f"[GUI] ❌ 이벤트 핸들러 설정 오류 ({host}): {e}")
            # 실패한 매니저 정리
            if hasattr(self, 'event_manager') and self.event_manager:
                try:
                    self.event_manager.disconnect()
                except:
                    pass
            self.event_manager = None
            self.event_processor = None
            self.event_tts = None
            return False
    
    def _create_server_client_with_fallback(self):
        """서버 클라이언트 생성 - localhost fallback 포함"""
        from request_handler import TCPServerClient
        
        # 먼저 기본 서버로 시도
        try:
            print(f"[GUI] 🔌 서버 클라이언트 연결 시도: {self.SERVER_HOST}:{self.SERVER_PORT}")
            client = TCPServerClient(
                server_host=self.SERVER_HOST,
                server_port=self.SERVER_PORT,
                use_simulator=False
            )
            # 연결 테스트 제거 - 실제 사용시에 연결하도록 변경
            print(f"[GUI] ✅ 서버 클라이언트 생성 완료: {self.SERVER_HOST}:{self.SERVER_PORT}")
            return client
        except Exception as e:
            print(f"[GUI] ❌ 서버 클라이언트 생성 오류 ({self.SERVER_HOST}): {e}")
        
        # 기본 서버 실패 시 localhost로 fallback
        try:
            print(f"[GUI] 🔄 서버 클라이언트 localhost fallback 시도: {self.FALLBACK_HOST}:{self.SERVER_PORT}")
            client = TCPServerClient(
                server_host=self.FALLBACK_HOST,
                server_port=self.SERVER_PORT,
                use_simulator=False
            )
            # 연결 테스트 제거 - 실제 사용시에 연결하도록 변경
            print(f"[GUI] ✅ 서버 클라이언트 localhost 생성 완료: {self.FALLBACK_HOST}:{self.SERVER_PORT}")
            return client
        except Exception as e:
            print(f"[GUI] ❌ 서버 클라이언트 localhost 생성 오류: {e}")
        
        # 모든 연결 실패 - 기본 클라이언트 반환 (시뮬레이터 없이)
        print(f"[GUI] ⚠️ 모든 서버 연결 실패 - 기본 클라이언트 반환")
        return TCPServerClient(
            server_host=self.SERVER_HOST,  # 기본 호스트로 설정 (나중에 재시도용)
            server_port=self.SERVER_PORT,
            use_simulator=False
        )
    
    def thread_safe_event_tts_update(self, tts_message: str):
        """스레드 안전한 이벤트 TTS 업데이트 - 녹음 중 차단"""
        # 🔧 녹음 중이면 이벤트 TTS 완전 차단
        if hasattr(self, 'is_recording') and self.is_recording:
            print(f"[GUI] 🚫 녹음 중이므로 이벤트 TTS 차단: '{tts_message[:50]}...'")
            return
        
        # 🔧 음성 워커 스레드가 실행 중이면 차단
        if hasattr(self, 'voice_worker') and self.voice_worker and self.voice_worker.isRunning():
            print(f"[GUI] 🚫 음성 처리 중이므로 이벤트 TTS 차단: '{tts_message[:50]}...'")
            return
        
        print(f"[GUI] 🔔 스레드 안전 이벤트 TTS 시그널 전송: '{tts_message[:50]}...'")
        self.event_tts_signal.emit(tts_message)
    
    def signal_gui_ready(self):
        """GUI 준비 완료 신호를 이벤트 매니저에 전송"""
        try:
            if hasattr(self, 'event_manager') and self.event_manager:
                self.event_manager.signal_gui_ready()
                print("[GUI] ✅ GUI 준비 완료 신호를 이벤트 매니저에 전송")
            else:
                if hasattr(self, 'server_connection_failed') and self.server_connection_failed:
                    print("[GUI] ⚠️ 서버 연결 실패 상태 - 재시도 중...")
                else:
                    print("[GUI] ⚠️ 이벤트 매니저가 없어 GUI 준비 완료 신호를 전송할 수 없음")
        except Exception as e:
            print(f"[GUI] ❌ GUI 준비 완료 신호 전송 오류: {e}")
    
    def retry_server_connection(self):
        """서버 연결 재시도 - localhost fallback 포함"""
        print(f"[GUI] 🔄 서버 연결 재시도 중...")
        
        # 기존 이벤트 매니저가 있으면 정리
        if hasattr(self, 'event_manager') and self.event_manager:
            try:
                self.event_manager.disconnect()
            except:
                pass
        
        # 먼저 기본 서버로 재시도
        if self._try_connect_event_manager(self.SERVER_HOST):
            self.server_connection_failed = False
            self.server_retry_timer.stop()  # 재시도 타이머 중지
            self.signal_gui_ready()
            return
        
        # 기본 서버 실패 시 localhost로 재시도
        print(f"[GUI] 🔄 기본 서버 재시도 실패 - localhost로 재시도")
        if self._try_connect_event_manager(self.FALLBACK_HOST):
            self.server_connection_failed = False
            self.server_retry_timer.stop()  # 재시도 타이머 중지
            self.signal_gui_ready()
            return
        
        # 모든 재시도 실패
        print(f"[GUI] ❌ 모든 서버 재시도 실패 - 5초 후 다시 시도")
        # 이벤트 처리 다시 비활성화
        self.event_manager = None
        self.event_processor = None
        self.event_tts = None
        
        # 타이머 간격을 5초로 변경하여 계속 재시도
        self.server_retry_timer.stop()
        self.server_retry_timer.start(5000)  # 5초마다 재시도
    
    def check_and_setup_microphone(self):
        """마이크 디바이스 확인 및 설정"""
        try:
            print("[GUI] 🎤 마이크 디바이스 검색 중...")
            
            # AudioIO의 마이크 디바이스 리스트 기능 사용
            from audio_io.mic_speaker_io import AudioIO
            
            # 사용 가능한 마이크 디바이스 리스트 출력
            devices = AudioIO.list_input_devices()
            
            # 헤드셋/USB 마이크 우선 선택
            selected_device_index = None
            selected_device_name = ""
            
            print("[GUI] 🔍 헤드셋/USB 마이크 검색 중...")
            
            # 🎤 pipewire 우선 사용 (ABKO 헤드셋이 기본 마이크로 설정됨)
            priority_groups = [
                (['pipewire'], "PipeWire 오디오 (ABKO N550 헤드셋 사용)"), # pipewire 최우선 (ABKO 헤드셋 포함)
                (['n550', 'abko'], "ABKO N550 헤드셋 마이크"), # ABKO 헤드셋 직접 접근
                (['usb', 'headset'], "USB 헤드셋"),     # USB 헤드셋
                (['usb', 'mic'], "USB 마이크"),         # USB 마이크
                (['usb'], "USB 장치"),                  # 일반 USB 장치
                (['headset'], "헤드셋"),                # 헤드셋
                (['alc233'], "내장 마이크"),            # 내장 마이크
                (['hw:'], "ALSA 하드웨어 장치"),        # ALSA 하드웨어 장치
            ]
            
            for keywords, description in priority_groups:
                for device in devices:
                    name_lower = device['name'].lower()
                    if any(keyword in name_lower for keyword in keywords):
                        # 완전히 제외할 키워드 (실제로 사용할 수 없는 것들만)
                        exclude_keywords = ['built-in monitor', 'loopback', 'null']
                        if not any(exclude in name_lower for exclude in exclude_keywords):
                            selected_device_index = device['index']
                            selected_device_name = device['name']
                            
                            # pipewire 선택 시 실제 기본 마이크 확인
                            if 'pipewire' in keywords:
                                try:
                                    import subprocess
                                    result = subprocess.run(['wpctl', 'inspect', '@DEFAULT_SOURCE@'], 
                                                          capture_output=True, text=True, timeout=2)
                                    if result.returncode == 0 and 'ABKO N550' in result.stdout:
                                        description = "PipeWire 오디오 → ABKO N550 헤드셋 확인됨 ✅"
                                    elif result.returncode == 0:
                                        # 다른 마이크가 기본값인 경우 표시
                                        for line in result.stdout.split('\n'):
                                            if 'node.nick' in line:
                                                mic_name = line.split('"')[1] if '"' in line else "Unknown"
                                                description = f"PipeWire 오디오 → {mic_name} 사용 중"
                                                break
                                except Exception:
                                    pass  # wpctl 실패해도 계속 진행
                            
                            print(f"[GUI] ✅ 마이크 선택: {selected_device_name} (인덱스: {selected_device_index}) - {description}")
                            break
                
                if selected_device_index is not None:
                    break
            
            # 우선 마이크를 찾지 못한 경우 기본 마이크 선택
            if selected_device_index is None:
                # 마지막으로 기본 마이크 선택
                for device in devices:
                    if 'default' in device['name'].lower():
                        selected_device_index = device['index']
                        selected_device_name = device['name']
                        print(f"[GUI] 📢 기본 마이크 선택: {selected_device_name} (인덱스: {selected_device_index})")
                        break
                
                if selected_device_index is None:
                    print("[GUI] ⚠️ 사용 가능한 마이크를 찾지 못했습니다")
                    selected_device_index = None  # 시스템 기본값
                    selected_device_name = "시스템 기본 마이크"
            
            # 선택된 마이크 정보 저장
            self.selected_mic_index = selected_device_index
            self.selected_mic_name = selected_device_name
            
            print(f"[GUI] 🎤 최종 선택된 마이크: {selected_device_name}")
            print(f"[GUI] 📋 마이크 인덱스: {selected_device_index}")
            
        except Exception as e:
            print(f"[GUI] ❌ 마이크 설정 오류: {e}")
            self.selected_mic_index = None
            self.selected_mic_name = "기본 마이크"
    
    def is_recording_or_processing(self) -> bool:
        """녹음 또는 음성 처리 중인지 확인"""
        # 녹음 중인지 확인
        if hasattr(self, 'is_recording') and self.is_recording:
            return True
        
        # 음성 워커 스레드가 실행 중인지 확인
        if hasattr(self, 'voice_worker') and self.voice_worker and self.voice_worker.isRunning():
            return True
        
        return False
    
    def on_bird_risk_changed(self, event_data: dict):
        """조류 위험도 변화 이벤트 처리"""
        if self.event_processor:
            processed_event = self.event_processor.process_event_message(event_data)
            result = processed_event.get("original_result", "UNKNOWN")
            event_type = processed_event.get("event_type", "bird_risk")
            
            print(f"[GUI] 📢 조류 위험도 변화: {result}")
            
            # 🔧 스레드 안전한 GUI 업데이트 (시그널 사용)
            self.bird_risk_changed_signal.emit(result)
            
            # 새로운 EventTTS 사용
            if self.event_tts:
                # 🔧 원본 값 사용 (BR_HIGH, BR_MEDIUM 등)
                self.event_tts.play_event_notification(event_type, processed_event.get("original_result", "UNKNOWN"))
        else:
            # 폴백: 기존 방식
            result = event_data.get("result", "UNKNOWN")
            # 🔧 스레드 안전한 GUI 업데이트 (시그널 사용)
            self.bird_risk_changed_signal.emit(result)
            # 🔧 스레드 안전한 이벤트 TTS 호출
            self.thread_safe_event_tts_update(self.get_standard_event_message(result, "bird_risk"))
    
    def on_runway_alpha_changed(self, event_data: dict):
        """활주로 알파 상태 변화 이벤트 처리"""
        if self.event_processor:
            processed_event = self.event_processor.process_event_message(event_data)
            result = processed_event.get("original_result", "UNKNOWN")
            event_type = processed_event.get("event_type", "runway_alpha")
            
            print(f"[GUI] 📢 활주로 알파 상태 변화: {result}")
            
            # 🔧 스레드 안전한 GUI 업데이트 (시그널 사용)
            self.runway_alpha_changed_signal.emit(result)
            
            # 새로운 EventTTS 사용
            if self.event_tts:
                # 🔧 원본 값 사용 (BR_HIGH, BR_MEDIUM 등)
                self.event_tts.play_event_notification(event_type, processed_event.get("original_result", "UNKNOWN"))
        else:
            # 폴백: 기존 방식
            result = event_data.get("result", "UNKNOWN")
            # 🔧 스레드 안전한 GUI 업데이트 (시그널 사용)
            self.runway_alpha_changed_signal.emit(result)
            # 🔧 스레드 안전한 이벤트 TTS 호출
            self.thread_safe_event_tts_update(self.get_standard_event_message(result, "runway_alpha"))
    
    def on_runway_bravo_changed(self, event_data: dict):
        """활주로 브라보 상태 변화 이벤트 처리"""
        if self.event_processor:
            processed_event = self.event_processor.process_event_message(event_data)
            result = processed_event.get("original_result", "UNKNOWN")
            event_type = processed_event.get("event_type", "runway_bravo")
            
            print(f"[GUI] 📢 활주로 브라보 상태 변화: {result}")
            
            # 🔧 스레드 안전한 GUI 업데이트 (시그널 사용)
            self.runway_bravo_changed_signal.emit(result)
            
            # 새로운 EventTTS 사용
            if self.event_tts:
                # 🔧 원본 값 사용 (BR_HIGH, BR_MEDIUM 등)
                self.event_tts.play_event_notification(event_type, processed_event.get("original_result", "UNKNOWN"))
        else:
            # 폴백: 기존 방식
            result = event_data.get("result", "UNKNOWN")
            # 🔧 스레드 안전한 GUI 업데이트 (시그널 사용)
            self.runway_bravo_changed_signal.emit(result)
            # 🔧 스레드 안전한 이벤트 TTS 호출
            self.thread_safe_event_tts_update(self.get_standard_event_message(result, "runway_bravo"))
    
    def play_event_tts_notification(self, result: str, event_type: str):
        """
        이벤트 TTS 음성 알림 재생 (기존 표준 응답 메시지 사용)
        
        Args:
            result: 이벤트 결과 (BR_HIGH, RWY_A_BLOCKED 등)
            event_type: 이벤트 유형 (bird_risk, runway_alpha, runway_bravo)
        """
        try:
            # 현재 음성 입력 중이면 알림 스킵
            if hasattr(self, 'voice_worker') and self.voice_worker and self.voice_worker.isRunning():
                print(f"[GUI] ⏸️ 음성 입력 중이므로 이벤트 TTS 스킵: {result}")
                return
            
            # 기존 표준 응답 메시지 사용
            tts_message = self.get_standard_event_message(result, event_type)
            
            if tts_message and self.controller and hasattr(self.controller, 'tts_engine'):
                print(f"[GUI] 🔊 이벤트 TTS 재생: '{tts_message}'")
                
                # 개선된 TTS 엔진의 speak_event 메서드 사용 (충돌 방지)
                if hasattr(self.controller.tts_engine, 'speak_event'):
                    self.controller.tts_engine.speak_event(tts_message)
                else:
                    # 폴백: 기존 방식 (TTS 재생 상태 확인)
                    if hasattr(self.controller.tts_engine, 'is_speaking') and self.controller.tts_engine.is_speaking():
                        print(f"[GUI] ⏸️ TTS 재생 중이므로 이벤트 TTS 스킵: {result}")
                        return
                    self.controller.tts_engine.speak(tts_message)
                
                # GUI 텍스트 업데이트
                self.update_tts_display_with_event(tts_message)
            
        except Exception as e:
            print(f"[GUI] ❌ 이벤트 TTS 재생 오류: {e}")
    
    def get_standard_event_message(self, result: str, event_type: str) -> str:
        """
        기존 표준 응답 메시지를 사용하여 이벤트 메시지 생성
        
        Args:
            result: 이벤트 결과
            event_type: 이벤트 유형
            
        Returns:
            표준 TTS 메시지 텍스트
        """
        # TCP 결과를 표준 응답 코드로 변환 (BLOCKED/WARNING 통일 처리)
        result_to_response_code = {
            # 조류 위험도
            "BR_HIGH": "BIRD_RISK_HIGH",
            "BR_MEDIUM": "BIRD_RISK_MEDIUM", 
            "BR_LOW": "BIRD_RISK_LOW",
            
            # 활주로 알파 상태 (BLOCKED/WARNING 모두 WARNING으로 처리)
            "RWY_A_CLEAR": "RWY_A_CLEAR",
            "RWY_A_BLOCKED": "RWY_A_WARNING",  # BLOCKED → WARNING으로 처리
            "RWY_A_WARNING": "RWY_A_WARNING",  # WARNING 그대로
            "CLEAR": "RWY_A_CLEAR",            # TCP 명세 직접 매핑
            "BLOCKED": "RWY_A_WARNING",        # BLOCKED → WARNING으로 처리
            "WARNING": "RWY_A_WARNING",        # WARNING 그대로
            
            # 활주로 브라보 상태 (BLOCKED/WARNING 모두 WARNING으로 처리)
            "RWY_B_CLEAR": "RWY_B_CLEAR",
            "RWY_B_BLOCKED": "RWY_B_WARNING",  # BLOCKED → WARNING으로 처리
            "RWY_B_WARNING": "RWY_B_WARNING"   # WARNING 그대로
        }
        
        # 기존 표준 응답 메시지 (response_processor.py와 동일) - BLOCKED/WARNING 통일
        standard_responses = {
            # 조류 위험도 응답
            "BIRD_RISK_HIGH": "WARNING. Bird risk high. Advise extreme vigilance.",
            "BIRD_RISK_MEDIUM": "CAUTION. Bird activity reported near runway threshold.",
            "BIRD_RISK_LOW": "Runway CLEAR of bird activity currently.",
            
            # 활주로 상태 응답 (BLOCKED/WARNING 통일 처리)
            "RWY_A_CLEAR": "Runway Alpha is clear. Cleared for operations.",
            "RWY_A_BLOCKED": "WARNING. Runway Alpha advisory. Proceed with vigilance.",  # BLOCKED → WARNING 메시지
            "RWY_A_WARNING": "WARNING. Runway Alpha advisory. Proceed with vigilance.",  # WARNING 메시지
            "RWY_B_CLEAR": "Runway Bravo is clear. Cleared for operations.",
            "RWY_B_BLOCKED": "WARNING. Runway Bravo advisory. Proceed with vigilance.",  # BLOCKED → WARNING 메시지
            "RWY_B_WARNING": "WARNING. Runway Bravo advisory. Proceed with vigilance."   # WARNING 메시지
        }
        
        response_code = result_to_response_code.get(result)
        if response_code and response_code in standard_responses:
            return standard_responses[response_code]
        
        # 기본 메시지
        return f"Status update: {result}"
    
    def update_tts_display_with_event(self, tts_message: str):
        """이벤트 TTS 메시지 처리 (콘솔 로그만)"""
        print(f"[GUI] 🔔 이벤트 TTS 메시지: '{tts_message}'")
        
        # TTS 응답 텍스트 위젯이 UI에서 제거되어 콘솔 로그로만 처리
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[GUI] [{timestamp}] EVENT TTS: {tts_message}")
    
    def update_bird_risk_display(self, risk_level: str):
        """조류 위험도 디스플레이 업데이트"""
        print(f"[GUI] 🔄 조류 위험도 업데이트 시도: {risk_level}")
        if hasattr(self, 'status_bird_risk') and self.status_bird_risk:
            # TCP 결과를 GUI 표시용으로 변환
            display_mapping = {
                "BR_HIGH": "WARNING",   # 변경됨
                "BR_MEDIUM": "CAUTION", # 변경됨
                "BR_LOW": "NORMAL"      # 변경됨
            }
            display_text = display_mapping.get(risk_level, risk_level)
            
            self.status_bird_risk.setText(f"BIRD RISK: {display_text}")
            
            # 색상 설정 (WARNING=빨강, CAUTION=노랑, NORMAL=초록)
            if risk_level == "BR_HIGH":  # WARNING
                style = """QLabel {
                font-weight: bold;
                background-color: #000800;
                border: 2px solid #cc0000;
                border-radius: 6px;
                padding: 8px;
                font-family: "Courier New", monospace;
                color: #ff4444;
            }"""
            elif risk_level == "BR_MEDIUM":
                style = """QLabel {
                font-weight: bold;
                background-color: #000800;
                border: 2px solid #cc8800;
                border-radius: 6px;
                padding: 8px;
                font-family: "Courier New", monospace;
                color: #ffaa00;
            }"""
            else:
                style = """QLabel {
                font-weight: bold;
                background-color: #000800;
                border: 2px solid #006600;
                border-radius: 6px;
                padding: 8px;
                font-family: "Courier New", monospace;
                color: #00ff00;
            }"""
            
            self.status_bird_risk.setStyleSheet(style)
            
            print(f"[GUI] ✅ 조류 위험도 라벨 업데이트: {display_text} ({risk_level})")
        else:
            print(f"[GUI] ❌ 조류 위험도 라벨을 찾을 수 없음: status_bird_risk = {getattr(self, 'status_bird_risk', None)}")
    
    def update_runway_alpha_display(self, status: str):
        """활주로 알파 상태 디스플레이 업데이트 (BLOCKED/WARNING 통일 처리)"""
        print(f"[GUI] 🔄 활주로 알파 업데이트 시도: {status}")
        if hasattr(self, 'status_runway_a') and self.status_runway_a:
            # TCP 결과를 GUI 표시용으로 변환 (BLOCKED/WARNING 모두 WARNING으로 표시)
            display_mapping = {
                "RWY_A_CLEAR": "CLEAR",
                "RWY_A_BLOCKED": "WARNING",    # BLOCKED → WARNING으로 표시
                "RWY_A_WARNING": "WARNING",    # WARNING 그대로
                "CLEAR": "CLEAR",              # TCP 명세 직접 매핑
                "BLOCKED": "WARNING",          # BLOCKED → WARNING으로 표시
                "WARNING": "WARNING"           # WARNING 그대로
            }
            display_text = display_mapping.get(status, status)
            
            self.status_runway_a.setText(f"RWY ALPHA: {display_text}")
            
            # 색상 설정 (CLEAR는 녹색, 나머지는 모두 황색 WARNING)
            if status in ["RWY_A_CLEAR", "CLEAR"]:
                style = """QLabel {
                font-weight: bold;
                background-color: #000800;
                border: 2px solid #006600;
                border-radius: 6px;
                padding: 8px;
                font-family: "Courier New", monospace;
                color: #00ff00;
            }"""
            else:
                # BLOCKED/WARNING 모두 황색 WARNING으로 표시
                style = """QLabel {
                font-weight: bold;
                background-color: #1a1a00;
                border: 2px solid #cccc00;
                border-radius: 6px;
                padding: 8px;
                font-family: "Courier New", monospace;
                color: #ffff00;
            }"""
            
            self.status_runway_a.setStyleSheet(style)
            
            print(f"[GUI] ✅ 활주로 알파 라벨 업데이트: {display_text} ({status})")
        else:
            print(f"[GUI] ❌ 활주로 알파 라벨을 찾을 수 없음: status_runway_a = {getattr(self, 'status_runway_a', None)}")
    
    def update_runway_bravo_display(self, status: str):
        """활주로 브라보 상태 디스플레이 업데이트 (BLOCKED/WARNING 통일 처리)"""
        print(f"[GUI] 🔄 활주로 브라보 업데이트 시도: {status}")
        if hasattr(self, 'status_runway_b') and self.status_runway_b:
            # TCP 결과를 GUI 표시용으로 변환 (BLOCKED/WARNING 모두 WARNING으로 표시)
            display_mapping = {
                "RWY_B_CLEAR": "CLEAR",
                "RWY_B_BLOCKED": "WARNING",    # BLOCKED → WARNING으로 표시
                "RWY_B_WARNING": "WARNING",    # WARNING 그대로
                "CLEAR": "CLEAR",              # TCP 명세 직접 매핑
                "BLOCKED": "WARNING",          # BLOCKED → WARNING으로 표시
                "WARNING": "WARNING"           # WARNING 그대로
            }
            display_text = display_mapping.get(status, status)
            
            self.status_runway_b.setText(f"RWY BRAVO: {display_text}")
            
            # 색상 설정 (CLEAR는 녹색, 나머지는 모두 황색 WARNING)
            if status in ["RWY_B_CLEAR", "CLEAR"]:
                style = """QLabel {
                font-weight: bold;
                background-color: #000800;
                border: 2px solid #006600;
                border-radius: 6px;
                padding: 8px;
                font-family: "Courier New", monospace;
                color: #00ff00;
            }"""
            else:
                # BLOCKED/WARNING 모두 황색 WARNING으로 표시
                style = """QLabel {
                font-weight: bold;
                background-color: #1a1a00;
                border: 2px solid #cccc00;
                border-radius: 6px;
                padding: 8px;
                font-family: "Courier New", monospace;
                color: #ffff00;
            }"""
            
            self.status_runway_b.setStyleSheet(style)
            
            print(f"[GUI] ✅ 활주로 브라보 라벨 업데이트: {display_text} ({status})")
        else:
            print(f"[GUI] ❌ 활주로 브라보 라벨을 찾을 수 없음: status_runway_b = {getattr(self, 'status_runway_b', None)}")
    
    def init_timers(self):
        """타이머 초기화"""
        # 시간 업데이트 타이머
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(1000)  # 1초마다
    
    def update_time(self):
        """시간 업데이트"""
        now = datetime.now()
        utc_now = datetime.now(timezone.utc)
        
        # 각각 고유한 라벨에 시간 설정
        if self.label_utc_time:
            utc_time_str = f"UTC: {utc_now.strftime('%H:%M:%S')}"
            self.label_utc_time.setText(utc_time_str)
            
        if self.label_local_time:
            local_time_str = f"LOCAL: {now.strftime('%H:%M:%S')}"
            self.label_local_time.setText(local_time_str)
    

    

    
    def update_system_status_display(self):
        """시스템 상태 디스플레이 업데이트 - 메인 상태는 녹음 중일 때 건드리지 않음"""
        if not self.controller:
            return
        
        # 🔧 녹음 중일 때는 메인 상태 라벨 업데이트 방지
        if hasattr(self, 'is_recording') and self.is_recording:
            print(f"[GUI] 시스템 상태 업데이트 스킵: 녹음 중")
            return
        
        # 시스템 상태 라벨들이 UI에서 제거되어 콘솔 로그로만 확인
        status = self.controller.get_system_status()
        print(f"[GUI] 시스템 상태: {status}")
    
    def start_voice_input(self):
        """음성 입력 시작"""
        if self.is_recording or not self.controller:
            return
        
        # 🔴 녹음 시작 - 마이크 모니터링이 일시 중지됩니다
        print("[GUI] 🔴 녹음 시작 - 마이크 모니터링 일시 중지")
        self.is_recording = True
        if self.voice_button:
            self.voice_button.setText("RECORDING...")
            self.voice_button.setEnabled(False)
        if self.label_main_status:
            self.label_main_status.setText("RECORDING")
            self.label_main_status.setStyleSheet("background-color: #331100; color: #ffaa00;")
        
        # 진행률 표시
        if self.progress_voice:
            self.progress_voice.setRange(0, 50)  # 5초 * 10 (100ms 단위)
            self.progress_voice.setValue(0)
        
        # 워커 스레드 시작
        self.voice_worker = VoiceWorkerThread(self.controller)
        self.voice_worker.voice_completed.connect(self.on_voice_completed)
        self.voice_worker.voice_error.connect(self.on_voice_error)
        self.voice_worker.stt_result.connect(self.on_stt_result)
        self.voice_worker.tts_text_ready.connect(self.on_tts_text_ready)
        self.voice_worker.recording_progress.connect(self.on_recording_progress)
        self.voice_worker.start()
        
        if hasattr(self, 'statusbar') and self.statusbar:
            self.statusbar.showMessage("Voice input in progress... Please speak for 5 seconds")
    
    def on_recording_progress(self, progress: int):
        """실제 녹음 진행률 업데이트 (VoiceWorkerThread에서 전달)"""
        if self.progress_voice:
            self.progress_voice.setValue(progress)
    
    def on_stt_result(self, text: str, confidence: float):
        """STT 결과 처리"""
        print(f"[GUI] STT RESULT: '{text}' (confidence: {confidence:.2f})")
        
        # STT 결과 텍스트 위젯이 UI에서 제거되어 콘솔 로그로만 처리
        if hasattr(self, 'statusbar') and self.statusbar:
            self.statusbar.showMessage(f"Voice recognition completed: {text}")
    
    def on_tts_text_ready(self, tts_text):
        """TTS 텍스트 생성 완료 즉시 GUI에 전달"""
        print(f"[GUI] 🔧 on_tts_text_ready 시작 - TTS 텍스트: '{tts_text[:50] if tts_text else 'None'}...'")
        
        if tts_text:
            print(f"[GUI] TTS TEXT READY 즉시 GUI에 전달: '{tts_text[:50]}...'")
            
            # TTS 응답 텍스트 위젯이 UI에서 제거되어 콘솔 로그로만 처리
            print(f"[GUI] TTS 응답: {tts_text}")
            
            # 🔧 서버 응답이 확정되자마자 상태 즉시 업데이트 (TTS 완료 기다리지 않음)
            self.update_status_from_response(tts_text)
        else:
            print(f"[GUI] WARN TTS 텍스트가 없습니다")
        
        print(f"[GUI] 🔧 on_tts_text_ready 종료")
    
    def on_voice_completed(self, result):
        print(f"[GUI] on_voice_completed 시작")
        print(f"[GUI] result 타입: {type(result)}")
        
        # OK result는 딕셔너리이므로 키 확인
        if 'stt_text' in result and result['stt_text']:
            print(f"[GUI] STT 결과: {result['stt_text'][:50]}...")
        
        # 🔧 TTS 응답 처리는 on_tts_text_ready에서 이미 완료되었으므로 여기서는 하지 않음
        # 음성 재생 완료 후에는 단순히 상태만 확인
        if 'response_text' in result and result['response_text']:
            tts_text = result['response_text']
            print(f"[GUI] TTS 응답 확인 - 길이: {len(tts_text)} (이미 on_tts_text_ready에서 처리됨)")
        else:
            print(f"[GUI] FAIL TTS 응답이 없음 - result 키들: {list(result.keys())}")
        
        print(f"[GUI] on_voice_completed 종료")
        
        # 🟢 녹음 완료 - 간단한 상태 변경만
        print("[GUI] 🟢 녹음 완료")
        self.is_recording = False
        if self.voice_button:
            self.voice_button.setText("VOICE INPUT")
            self.voice_button.setEnabled(True)
        if self.progress_voice:
            # NEW 프로그레스바를 숨기지 않고 0으로 리셋
            self.progress_voice.setValue(0)
        
        # 진행률은 VoiceWorkerThread에서 실시간으로 관리됨
        
        # NEW 상태에 따른 적절한 처리
        status = result.get('status', 'UNKNOWN')
        
        if status == "COMPLETED" or status.value == "COMPLETED" if hasattr(status, 'value') else False:
            if self.label_main_status:
                self.label_main_status.setText("COMPLETED")
                self.label_main_status.setStyleSheet("background-color: #001a00; color: #00ff00;")
            
            # 🔧 상태 업데이트는 이미 on_tts_text_ready에서 완료됨 (중복 제거)
            # self.update_runway_status(result['request_code'])
            # self.update_status_from_response(result['response_text'])
            
            if hasattr(self, 'statusbar') and self.statusbar:
                self.statusbar.showMessage(f"Processing completed: {result['request_code']}")
                
            # 3초 후 READY 상태로 복귀
            threading.Timer(3.0, lambda: self.reset_status_signal.emit()).start()
            
        elif status == "FAILED" or status.value == "FAILED" if hasattr(status, 'value') else False:
            # 실제 실패만 ERROR로 표시
            if self.label_main_status:
                self.label_main_status.setText("ERROR")
                self.label_main_status.setStyleSheet("background-color: #330000; color: #ff4444;")
            if hasattr(self, 'statusbar') and self.statusbar:
                self.statusbar.showMessage(f"Processing failed: {result.get('error_message', 'Unknown error')}")
                
            # 3초 후 READY 상태로 복귀
            threading.Timer(3.0, lambda: self.reset_status_signal.emit()).start()
            
        elif status == "PROCESSING" or status.value == "PROCESSING" if hasattr(status, 'value') else False:
            # 처리 중 상태는 그냥 무시 (이미 RECORDING 상태이므로)
            print(f"[GUI] PROCESSING STATUS: {status}")
            
        else:
            # PENDING이나 기타 상태는 로그만 출력
            print(f"[GUI] INFO 알 수 없는 상태: {status}")
            # READY 상태로 즉시 복귀
            threading.Timer(1.0, lambda: self.reset_status_signal.emit()).start()
    
    def on_voice_error(self, error: str):
        """음성 처리 오류"""
        # 🟢 오류 발생 - 간단한 상태 변경만
        print("[GUI] 🟢 오류 발생")
        self.is_recording = False
        if self.voice_button:
            self.voice_button.setText("VOICE INPUT")
            self.voice_button.setEnabled(True)
        if self.progress_voice:
            # NEW 프로그레스바를 숨기지 않고 0으로 리셋
            self.progress_voice.setValue(0)
        
        # 진행률은 VoiceWorkerThread에서 실시간으로 관리됨
        
        if self.label_main_status:
            self.label_main_status.setText("ERROR")
            self.label_main_status.setStyleSheet("background-color: #330000; color: #ff4444;")
        if hasattr(self, 'statusbar') and self.statusbar:
            self.statusbar.showMessage(f"Voice processing error: {error}")
        
        QMessageBox.warning(self, "Voice Processing Error", f"Voice processing encountered an error:\n{error}")
        
        # 3초 후 READY 상태로 복귀
        threading.Timer(3.0, lambda: self.reset_status_signal.emit()).start()
    
    def reset_status(self):
        """상태를 READY로 리셋"""
        if self.label_main_status:
            self.label_main_status.setText("READY")
            self.label_main_status.setStyleSheet("background-color: #001a00; color: #00ff00;")
        if hasattr(self, 'statusbar') and self.statusbar:
            self.statusbar.showMessage("System ready")
    
    def update_runway_status(self, request_code: str):
        """활주로 상태 업데이트 - 항공 표준 색상 적용"""
        if "RUNWAY_ALPHA" in request_code and self.status_runway_a:
            self.status_runway_a.setText("RWY ALPHA: STANDBY")
            # 🟢 어두운 녹색 - 스탠바이/대기 (CLEAR와 구분)
            self.status_runway_a.setStyleSheet("background-color: #000800; color: #009900; border: 2px solid #006600; padding: 8px; border-radius: 6px; font-weight: bold;")
        elif "RUNWAY_BRAVO" in request_code and self.status_runway_b:
            self.status_runway_b.setText("RWY BRAVO: STANDBY")
            # 🟢 어두운 녹색 - 스탠바이/대기 (CLEAR와 구분)
            self.status_runway_b.setStyleSheet("background-color: #000800; color: #009900; border: 2px solid #006600; padding: 8px; border-radius: 6px; font-weight: bold;")
        elif "BIRD_RISK" in request_code and self.status_bird_risk:
            self.status_bird_risk.setText("BIRD LEVEL: PROCESSING")
            # 🔵 파란색 - 처리 중
            self.status_bird_risk.setStyleSheet("background-color: #001a1a; color: #00ffff; border: 2px solid #0099aa; padding: 8px; border-radius: 6px; font-weight: bold;")
    
    def update_status_from_response(self, response_text: str):
        """응답 텍스트에서 상태 정보 추출하여 라벨 업데이트 - 기존 UI 스타일 유지"""
        if not response_text:
            return
        
        # 활주로 상태 업데이트 (항공 표준 색상 적용)
        response_upper = response_text.upper()
        print(f"[GUI] 🛬 활주로 파싱 - 응답: '{response_text[:100]}'")
        
        # 🆕 "Available runways" 응답 파싱 - 여러 활주로를 한 번에 업데이트
        if "AVAILABLE RUNWAYS" in response_upper:
            print(f"[GUI] 🛬 사용가능 활주로 목록 응답 감지")
        elif "NO RUNWAYS AVAILABLE" in response_upper:
            print(f"[GUI] 🛬 사용가능 활주로 없음 응답 감지 - 모든 활주로 BLOCKED 처리")
        
        if "AVAILABLE RUNWAYS" in response_upper or "NO RUNWAYS AVAILABLE" in response_upper:
            
            # ALPHA/ALFA 활주로 상태 판단
            if ("ALFA" in response_upper or "ALPHA" in response_upper) and self.status_runway_a:
                old_text = self.status_runway_a.text()
                new_text = "RWY ALPHA: CLEAR"
                if old_text != new_text:
                    self.status_runway_a.setText(new_text)
                    self.status_runway_a.setStyleSheet("background-color: #001a00; color: #00ff00; border: 2px solid #00aa00; padding: 8px; border-radius: 6px; font-weight: bold;")
                    print(f"[GUI] 🛬 RWY ALPHA 업데이트 (Available): {old_text} → CLEAR")
                else:
                    print(f"[GUI] 🛬 RWY ALPHA 변경 없음 (Available): {old_text}")
            elif self.status_runway_a:
                # ALPHA가 Available runways 목록에 없으면 BLOCKED으로 간주
                old_text = self.status_runway_a.text()
                new_text = "RWY ALPHA: BLOCKED"
                if old_text != new_text:
                    self.status_runway_a.setText(new_text)
                    self.status_runway_a.setStyleSheet("background-color: #1a0000; color: #ff0000; border: 2px solid #aa0000; padding: 8px; border-radius: 6px; font-weight: bold;")
                    print(f"[GUI] 🛬 RWY ALPHA 업데이트 (Not Available): {old_text} → BLOCKED")
                else:
                    print(f"[GUI] 🛬 RWY ALPHA 변경 없음 (Not Available): {old_text}")
            
            # BRAVO 활주로 상태 판단
            if "BRAVO" in response_upper and self.status_runway_b:
                old_text = self.status_runway_b.text()
                new_text = "RWY BRAVO: CLEAR"
                if old_text != new_text:
                    self.status_runway_b.setText(new_text)
                    self.status_runway_b.setStyleSheet("background-color: #001a00; color: #00ff00; border: 2px solid #00aa00; padding: 8px; border-radius: 6px; font-weight: bold;")
                    print(f"[GUI] 🛬 RWY BRAVO 업데이트 (Available): {old_text} → CLEAR")
                else:
                    print(f"[GUI] 🛬 RWY BRAVO 변경 없음 (Available): {old_text}")
            elif self.status_runway_b:
                # BRAVO가 Available runways 목록에 없으면 BLOCKED으로 간주
                old_text = self.status_runway_b.text()
                new_text = "RWY BRAVO: BLOCKED"
                if old_text != new_text:
                    self.status_runway_b.setText(new_text)
                    self.status_runway_b.setStyleSheet("background-color: #1a0000; color: #ff0000; border: 2px solid #aa0000; padding: 8px; border-radius: 6px; font-weight: bold;")
                    print(f"[GUI] 🛬 RWY BRAVO 업데이트 (Not Available): {old_text} → BLOCKED")
                else:
                    print(f"[GUI] 🛬 RWY BRAVO 변경 없음 (Not Available): {old_text}")
            
            # "No runways available" 처리
            if "NO RUNWAYS AVAILABLE" in response_upper:
                print(f"[GUI] 🛬 모든 활주로 사용 불가 상태")
                if self.status_runway_a:
                    old_text = self.status_runway_a.text()
                    new_text = "RWY ALPHA: BLOCKED"
                    if old_text != new_text:
                        self.status_runway_a.setText(new_text)
                        self.status_runway_a.setStyleSheet("background-color: #1a0000; color: #ff0000; border: 2px solid #aa0000; padding: 8px; border-radius: 6px; font-weight: bold;")
                        print(f"[GUI] 🛬 RWY ALPHA 업데이트 (No Runways): {old_text} → BLOCKED")
                if self.status_runway_b:
                    old_text = self.status_runway_b.text()
                    new_text = "RWY BRAVO: BLOCKED"
                    if old_text != new_text:
                        self.status_runway_b.setText(new_text)
                        self.status_runway_b.setStyleSheet("background-color: #1a0000; color: #ff0000; border: 2px solid #aa0000; padding: 8px; border-radius: 6px; font-weight: bold;")
                        print(f"[GUI] 🛬 RWY BRAVO 업데이트 (No Runways): {old_text} → BLOCKED")
        
        # RWY ALPHA 상태 체크 (개별 응답 형식: "RWY-ALPHA is clear, condition good, wind 5kt.")
        elif ("ALPHA" in response_upper or "ALFA" in response_upper or "RWY-ALPHA" in response_upper) and self.status_runway_a:
            print(f"[GUI] 🛬 ALPHA 키워드 감지됨")
            old_text = self.status_runway_a.text()
            
            # 🆕 "Runway Alfa available for landing" 패턴 인식 개선
            if ("IS CLEAR" in response_upper or "CLEAR" in response_upper or 
                "AVAILABLE" in response_upper or "OPERATIONAL" in response_upper or
                "GOOD" in response_upper or "FOR LANDING" in response_upper):
                new_text = "RWY ALPHA: CLEAR"
                if old_text != new_text:  # 중복 업데이트 방지
                    self.status_runway_a.setText(new_text)
                    # 🟢 녹색 - 정상/안전/사용가능
                    self.status_runway_a.setStyleSheet("background-color: #001a00; color: #00ff00; border: 2px solid #00aa00; padding: 8px; border-radius: 6px; font-weight: bold;")
                    print(f"[GUI] 🛬 RWY ALPHA 업데이트: {old_text} → CLEAR")
                else:
                    print(f"[GUI] 🛬 RWY ALPHA 변경 없음: {old_text} (이미 CLEAR)")
            elif ("IS CAUTION" in response_upper or "CAUTION" in response_upper or 
                  "WARNING" in response_upper or "WET" in response_upper):
                # 🔧 CAUTION과 WARNING 모두 WARNING으로 통일 표시
                new_text = "RWY ALPHA: WARNING"
                if old_text != new_text:  # 중복 업데이트 방지
                    self.status_runway_a.setText(new_text)
                    # 🟡 황색 - 주의/경고
                    self.status_runway_a.setStyleSheet("background-color: #1a1a00; color: #ffff00; border: 2px solid #aaaa00; padding: 8px; border-radius: 6px; font-weight: bold;")
                    print(f"[GUI] 🛬 RWY ALPHA 업데이트: {old_text} → WARNING (CAUTION/WARNING 통일)")
                else:
                    print(f"[GUI] 🛬 RWY ALPHA 변경 없음: {old_text} (이미 WARNING)")
            elif ("IS BLOCKED" in response_upper or "BLOCKED" in response_upper or 
                  "CLOSED" in response_upper or "POOR" in response_upper):
                new_text = "RWY ALPHA: BLOCKED"
                if old_text != new_text:  # 중복 업데이트 방지
                    self.status_runway_a.setText(new_text)
                    # 🔴 빨간색 - 위험/차단
                    self.status_runway_a.setStyleSheet("background-color: #1a0000; color: #ff0000; border: 2px solid #aa0000; padding: 8px; border-radius: 6px; font-weight: bold;")
                    print(f"[GUI] 🛬 RWY ALPHA 업데이트: {old_text} → BLOCKED")
                else:
                    print(f"[GUI] 🛬 RWY ALPHA 변경 없음: {old_text} (이미 BLOCKED)")
            else:
                print(f"[GUI] 🛬 RWY ALPHA 상태 키워드 매칭 실패 - 응답: '{response_upper}'")
        
        # RWY BRAVO 상태 체크 (개별 응답 형식: "RWY-BRAVO is clear, condition good, wind 5kt.")
        elif ("BRAVO" in response_upper or "BRAVO" in response_upper or "RWY-BRAVO" in response_upper) and self.status_runway_b:
            print(f"[GUI] 🛬 BRAVO 키워드 감지됨")
            old_text = self.status_runway_b.text()
            
            # 🆕 "Runway Bravo available for landing" 패턴 인식 개선
            if ("IS CLEAR" in response_upper or "CLEAR" in response_upper or 
                "AVAILABLE" in response_upper or "OPERATIONAL" in response_upper or
                "GOOD" in response_upper or "FOR LANDING" in response_upper):
                new_text = "RWY BRAVO: CLEAR"
                if old_text != new_text:  # 중복 업데이트 방지
                    self.status_runway_b.setText(new_text)
                    # 🟢 녹색 - 정상/안전/사용가능
                    self.status_runway_b.setStyleSheet("background-color: #001a00; color: #00ff00; border: 2px solid #00aa00; padding: 8px; border-radius: 6px; font-weight: bold;")
                    print(f"[GUI] 🛬 RWY BRAVO 업데이트: {old_text} → CLEAR")
                else:
                    print(f"[GUI] 🛬 RWY BRAVO 변경 없음: {old_text} (이미 CLEAR)")
            elif ("IS CAUTION" in response_upper or "CAUTION" in response_upper or 
                  "WARNING" in response_upper or "WET" in response_upper):
                # 🔧 CAUTION과 WARNING 모두 WARNING으로 통일 표시
                new_text = "RWY BRAVO: WARNING"
                if old_text != new_text:  # 중복 업데이트 방지
                    self.status_runway_b.setText(new_text)
                    # 🟡 황색 - 주의/경고
                    self.status_runway_b.setStyleSheet("background-color: #1a1a00; color: #ffff00; border: 2px solid #aaaa00; padding: 8px; border-radius: 6px; font-weight: bold;")
                    print(f"[GUI] 🛬 RWY BRAVO 업데이트: {old_text} → WARNING (CAUTION/WARNING 통일)")
                else:
                    print(f"[GUI] 🛬 RWY BRAVO 변경 없음: {old_text} (이미 WARNING)")
            elif ("IS BLOCKED" in response_upper or "BLOCKED" in response_upper or 
                  "CLOSED" in response_upper or "POOR" in response_upper):
                new_text = "RWY BRAVO: BLOCKED"
                if old_text != new_text:  # 중복 업데이트 방지
                    self.status_runway_b.setText(new_text)
                    # 🔴 빨간색 - 위험/차단
                    self.status_runway_b.setStyleSheet("background-color: #1a0000; color: #ff0000; border: 2px solid #aa0000; padding: 8px; border-radius: 6px; font-weight: bold;")
                    print(f"[GUI] 🛬 RWY BRAVO 업데이트: {old_text} → BLOCKED")
                else:
                    print(f"[GUI] 🛬 RWY BRAVO 변경 없음: {old_text} (이미 BLOCKED)")
            else:
                print(f"[GUI] 🛬 RWY BRAVO 상태 키워드 매칭 실패 - 응답: '{response_upper}'")
        
        # 조류 위험도 업데이트 (BIRD LEVEL로 되돌리고 단계적 표시)
        if self.status_bird_risk:
            # 더 정확한 BIRD 레벨 탐지
            response_upper = response_text.upper()
            print(f"[GUI] 🦅 BIRD 파싱 시작 - 응답 텍스트: '{response_text[:100]}'")
            print(f"[GUI] 🦅 대문자 변환: '{response_upper[:100]}'")
            
            if "BIRD" in response_upper or "AVIAN" in response_upper:
                print(f"[GUI] 🦅 BIRD 키워드 감지됨")
                old_text = self.status_bird_risk.text()
                
                # 구체적인 레벨 키워드 먼저 체크
                if "LOW" in response_upper or "MINIMAL" in response_upper or "LEVEL 1" in response_upper:
                    new_text = "BIRD LEVEL: LOW"
                    if old_text != new_text:  # 중복 업데이트 방지
                        self.status_bird_risk.setText(new_text)
                        # 🟢 녹색 - 낮은 위험
                        self.status_bird_risk.setStyleSheet("background-color: #001a00; color: #00ff00; border: 2px solid #00aa00; padding: 8px; border-radius: 6px; font-weight: bold;")
                        print(f"[GUI] 🦅 BIRD LEVEL 업데이트: {old_text} → LOW")
                    else:
                        print(f"[GUI] 🦅 BIRD LEVEL 변경 없음: {old_text} (이미 LOW)")
                elif "MEDIUM" in response_upper or "MODERATE" in response_upper or "LEVEL 2" in response_upper:
                    new_text = "BIRD LEVEL: MEDIUM"
                    if old_text != new_text:  # 중복 업데이트 방지
                        self.status_bird_risk.setText(new_text)
                        # 🟡 황색 - 중간 위험
                        self.status_bird_risk.setStyleSheet("background-color: #1a1a00; color: #ffff00; border: 2px solid #aaaa00; padding: 8px; border-radius: 6px; font-weight: bold;")
                        print(f"[GUI] 🦅 BIRD LEVEL 업데이트: {old_text} → MEDIUM")
                    else:
                        print(f"[GUI] 🦅 BIRD LEVEL 변경 없음: {old_text} (이미 MEDIUM)")
                elif "HIGH" in response_upper or "LEVEL 3" in response_upper or "SEVERE" in response_upper:
                    new_text = "BIRD LEVEL: HIGH"
                    if old_text != new_text:  # 중복 업데이트 방지
                        self.status_bird_risk.setText(new_text)
                        # 🔴 빨간색 - 높은 위험
                        self.status_bird_risk.setStyleSheet("background-color: #1a0000; color: #ff0000; border: 2px solid #aa0000; padding: 8px; border-radius: 6px; font-weight: bold;")
                        print(f"[GUI] 🦅 BIRD LEVEL 업데이트: {old_text} → HIGH")
                    else:
                        print(f"[GUI] 🦅 BIRD LEVEL 변경 없음: {old_text} (이미 HIGH)")
                elif "NONE" in response_upper or "CLEAR" in response_upper or "NO BIRD" in response_upper or "CLEAR TO PROCEED" in response_upper:
                    new_text = "BIRD LEVEL: CLEAR"
                    if old_text != new_text:  # 중복 업데이트 방지
                        self.status_bird_risk.setText(new_text)
                        # 🟢 녹색 - 안전/클리어
                        self.status_bird_risk.setStyleSheet("background-color: #001a00; color: #00ff00; border: 2px solid #00aa00; padding: 8px; border-radius: 6px; font-weight: bold;")
                        print(f"[GUI] 🦅 BIRD LEVEL 업데이트: {old_text} → CLEAR")
                    else:
                        print(f"[GUI] 🦅 BIRD LEVEL 변경 없음: {old_text} (이미 CLEAR)")
                else:
                    # 🆕 레벨 키워드가 없는 일반적인 BIRD ACTIVITY는 MEDIUM으로 처리
                    if "ACTIVITY" in response_upper or "REPORTED" in response_upper or "BE ADVISED" in response_upper:
                        self.status_bird_risk.setText("BIRD LEVEL: MEDIUM")
                        # 🟡 황색 - 일반적인 조류 활동 보고
                        self.status_bird_risk.setStyleSheet("background-color: #1a1a00; color: #ffff00; border: 2px solid #aaaa00; padding: 8px; border-radius: 6px; font-weight: bold;")
                        print(f"[GUI] 🦅 BIRD LEVEL 업데이트: {old_text} → MEDIUM (일반 활동 보고)")
                    else:
                        print(f"[GUI] 🦅 BIRD 레벨 키워드 매칭 실패 - 응답: '{response_upper}'")
            else:
                print(f"[GUI] 🦅 BIRD 관련 키워드 없음 - 스킵")
            # 만약 응답에 활주로만 있고 BIRD 정보가 없으면 BIRD LEVEL 업데이트하지 않음
    
    # show_system_status 메서드는 UI에서 해당 버튼이 제거되어 삭제됨
    
    # 🆕 마샬링 관련 함수들
    def toggle_marshaling(self):
        """마샬링 인식 시작/중지"""
        if not self.marshaling_active:
            # 마샬링 시작
            self.start_marshaling()
        else:
            # 마샬링 중지
            self.stop_marshaling()
    
    def start_marshaling(self):
        """마샬링 인식 시작"""
        try:
            print("[GUI] 🤚 마샬링 인식 시작")
            self.marshaling_active = True
            
            # 버튼 상태 변경
            if self.marshall_button:
                self.marshall_button.setText("STOP MARSHAL")
                self.marshall_button.setStyleSheet("""
                    QPushButton {
                        background-color: #1a0000;
                        border: 3px solid #ff0000;
                        color: #ff0000;
                        font-size: 16px;
                        font-weight: bold;
                        font-family: "Courier New", monospace;
                        border-radius: 6px;
                        padding: 8px;
                    }
                    QPushButton:hover {
                        background-color: #2d0000;
                        border-color: #ff3333;
                    }
                """)
                
            # PDS 서버에 마샬링 시작 명령 전송
            self.send_marshaling_command("MARSHALING_START")
            
            # TTS 알림 (스레드 안전)
            if self.controller and self.controller.tts_engine:
                threading.Thread(target=lambda: self.controller.tts_engine.speak("Marshaling recognition activated"), daemon=True).start()
                
        except Exception as e:
            print(f"[GUI] ❌ 마샬링 시작 오류: {e}")
    
    def stop_marshaling(self):
        """마샬링 인식 중지"""
        try:
            print("[GUI] 🛑 마샬링 인식 중지")
            self.marshaling_active = False
            
            # 버튼 상태 변경 
            if self.marshall_button:
                self.marshall_button.setText("START MARSHAL")
                self.marshall_button.setStyleSheet("""
                    QPushButton {
                        background-color: #001a00;
                        border: 3px solid #00ff00;
                        color: #00ff00;
                        font-size: 16px;
                        font-weight: bold;
                        font-family: "Courier New", monospace;
                        border-radius: 6px;
                        padding: 8px;
                    }
                    QPushButton:hover {
                        background-color: #002d00;
                        border-color: #33ff33;
                    }
                """)
                
            # PDS 서버에 마샬링 중지 명령 전송
            self.send_marshaling_command("MARSHALING_STOP")
            
            # TTS 알림 (스레드 안전)  
            if self.controller and self.controller.tts_engine:
                threading.Thread(target=lambda: self.controller.tts_engine.speak("Marshaling recognition deactivated"), daemon=True).start()
            
            # 메인 상태를 기본으로 복원
            if self.label_main_status:
                self.label_main_status.setText("SYSTEM READY")
                
        except Exception as e:
            print(f"[GUI] ❌ 마샬링 중지 오류: {e}")
    
    def send_marshaling_command(self, command: str):
        """GUI Server를 통해 PDS 서버에 마샬링 명령 전송"""
        try:
            import socket
            import json
            
            # GUI Server 주소 (포트 8000)
            gui_server_host = self.SERVER_HOST
            gui_server_port = self.SERVER_PORT
            
            # 명령 메시지 생성 (GUI Server 프로토콜에 맞게)
            command_message = {
                "type": "command",
                "command": command
            }
            
            # TCP 소켓으로 GUI Server에 전송
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3.0)  # 3초 타임아웃
                sock.connect((gui_server_host, gui_server_port))
                message = json.dumps(command_message) + "\n"
                sock.send(message.encode('utf-8'))
                print(f"[GUI] 📤 GUI Server를 통해 마샬링 명령 전송: {command} → {gui_server_host}:{gui_server_port}")
                
        except Exception as e:
            print(f"[GUI] ❌ GUI Server 마샬링 명령 전송 실패: {e}")
            # 폴백: 127.0.0.1로 시도
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(3.0)
                    sock.connect((self.FALLBACK_HOST, self.SERVER_PORT))
                    message = json.dumps(command_message) + "\n"
                    sock.send(message.encode('utf-8'))
                    print(f"[GUI] 📤 GUI Server 마샬링 명령 전송 (fallback): {command}")
            except Exception as e2:
                print(f"[GUI] ❌ GUI Server 마샬링 명령 전송 완전 실패: {e2}")
    
    def on_marshaling_gesture(self, event_data: dict):
        """마샬링 제스처 이벤트 처리"""
        try:
            result = event_data.get('result', 'UNKNOWN')
            confidence = event_data.get('confidence', 0.0)
            
            print(f"[GUI] 🤚 마샬링 제스처 감지: {result} (신뢰도: {confidence:.2f})")
            
            # 신뢰도가 70% 이상일 때만 처리
            if confidence >= 0.7:
                # 제스처별 TTS 메시지
                gesture_messages = {
                    "STOP": "Stop",
                    "MOVE_FORWARD": "Move forward",
                    "TURN_LEFT": "Turn left",
                    "TURN_RIGHT": "Turn right"
                }
                
                message = gesture_messages.get(result, f"Unknown gesture: {result}")
                
                # TTS로 제스처 안내 (스레드 안전)
                if self.controller and self.controller.tts_engine:
                    # 백그라운드 스레드에서 안전하게 TTS 호출
                    threading.Thread(target=lambda: self.controller.tts_engine.speak(message), daemon=True).start()
                    
                # 메인 상태 표시 업데이트
                if self.label_main_status:
                    self.label_main_status.setText(result)
                    
            else:
                print(f"[GUI] 🤚 신뢰도 부족으로 무시: {confidence:.2f} < 0.70")
                
        except Exception as e:
            print(f"[GUI] ❌ 마샬링 제스처 처리 오류: {e}")

    
    def closeEvent(self, event):
        """NEW GUI 종료 시 리소스 정리"""
        try:
            # 이벤트 매니저 종료 (시뮬레이터 자동 이벤트 포함)
            if hasattr(self, 'event_manager') and self.event_manager:
                self.event_manager.disconnect()
                print("[GUI] 이벤트 매니저 종료 완료")
            
            # 컨트롤러 종료 (TTS 엔진 포함)
            if hasattr(self, 'controller') and self.controller:
                self.controller.shutdown()
                print("[GUI] 컨트롤러 종료 완료")
            
            # 🔧 마이크 모니터링 정리 (비활성화된 상태이므로 간단히 처리)
            if hasattr(self, 'mic_monitoring_active'):
                self.mic_monitoring_active = False
                print("[GUI] 마이크 모니터링 정리 완료 (이미 비활성화됨)")
            
            # 타이머 정리
            if hasattr(self, 'time_timer'):
                self.time_timer.stop()
            if hasattr(self, 'server_retry_timer'):
                self.server_retry_timer.stop()
            
            print("[GUI] 리소스 정리 완료")
            
        except Exception as e:
            print(f"[GUI] 리소스 정리 중 오류: {e}")
        
        # 기본 종료 처리
        event.accept()

def main():
    """메인 실행 함수"""
    app = QApplication(sys.argv)
    
    # 애플리케이션 정보 설정
    app.setApplicationName("FALCON RedWing")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("dl-falcon")
    
    # 애플리케이션 종료 시 Qt 객체들이 자동으로 정리되도록 설정
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_DisableWindowContextHelpButton)
    except AttributeError:
        # PyQt6에서는 다른 속성 이름을 사용
        pass
    
    redwing = None
    
    try:
        # RedWing 인터페이스 생성 및 표시
        print("🎯 FALCON RedWing Interface 초기화 중...")
        redwing = RedWing()
        redwing.show()
        
        print("🎯 FALCON RedWing Interface 시작됨")
        print("GUI가 표시되었습니다. 창을 닫으려면 X 버튼을 클릭하세요.")
        
        # 이벤트 루프 실행
        exit_code = app.exec()
        print(f"🎯 애플리케이션 정상 종료: exit_code={exit_code}")
        return exit_code
        
    except KeyboardInterrupt:
        print("\n🛑 사용자가 Ctrl+C로 종료 요청")
        if redwing:
            redwing.close()
        return 0
        
    except Exception as e:
        print(f"❌ RedWing Interface 시작 오류: {e}")
        import traceback
        traceback.print_exc()
        
        # 에러 메시지 박스 표시
        try:
            from PyQt6.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("RedWing 시작 오류")
            msg.setText(f"RedWing Interface를 시작할 수 없습니다:\n\n{str(e)}")
            msg.setDetailedText(traceback.format_exc())
            msg.exec()
        except:
            pass
        
        return 1
    
    finally:
        # 정리 작업
        try:
            if redwing:
                print("🧹 RedWing 인스턴스 정리 중...")
                redwing.close()
            print("🧹 Qt 애플리케이션 정리 중...")
            app.quit()
        except Exception as cleanup_error:
            print(f"⚠️ 정리 중 오류: {cleanup_error}")
        
        print("✅ 애플리케이션 완전 종료")

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 