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
        QProgressBar, QSlider, QMessageBox, QWidget, QGroupBox
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
            
            # 음성 상호작용 처리 (콜사인 없이)
            interaction = self.controller.handle_voice_interaction(
                recording_duration=self.recording_duration
            )
            
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
    
    SERVER_HOST = "192.168.0.2"  
    SERVER_PORT = 5300
    FALLBACK_HOST = "localhost"  # 연결 실패 시 fallback
    
    # 🔧 GUI 업데이트를 위한 시그널 정의 (스레드 안전성)
    bird_risk_changed_signal = pyqtSignal(str)
    runway_alpha_changed_signal = pyqtSignal(str)
    runway_bravo_changed_signal = pyqtSignal(str)
    event_tts_signal = pyqtSignal(str)  # 🔧 이벤트 TTS용 시그널 추가
    
    def __init__(self, stt_manager=None, tts_manager=None, api_client=None, 
                 use_keyboard_shortcuts=True, parent=None):
        """GUI 초기화"""
        super().__init__(parent)
        
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
        
        # UI 로드
        self.load_ui()
        self.init_controller()
        self.init_timers()
        self.connect_signals()
        
        # 🔧 GUI 초기화 완료 후 서버 연결 시도 및 준비 완료 신호 전송
        QTimer.singleShot(1000, self.signal_gui_ready)  # 1초 후 신호 전송
        
        # 서버 연결 재시도 타이머 설정
        self.server_retry_timer = QTimer()
        self.server_retry_timer.timeout.connect(self.retry_server_connection)
        self.server_connection_failed = False
        
        print("🚁 RedWing Interface 초기화 완료")
    
    def load_ui(self):
        """UI 파일 로드"""
        ui_file = os.path.join(os.path.dirname(__file__), "redwing_gui.ui")
        
        if not os.path.exists(ui_file):
            raise FileNotFoundError(f"UI 파일을 찾을 수 없습니다: {ui_file}")
        
        # .ui 파일 로드
        uic.loadUi(ui_file, self)
        
        # 위젯 참조 설정
        self.label_title = self.findChild(QLabel, "title")
        self.label_utc_time = self.findChild(QLabel, "time_utc")
        self.label_local_time = self.findChild(QLabel, "time_local")
        self.label_main_status = self.findChild(QLabel, "main_status")
        
        # 버튼들
        self.btn_voice = self.findChild(QPushButton, "voice_button")
        self.btn_marshall = self.findChild(QPushButton, "marshall_button")  # START MARSHALL 버튼
        
        # 활주로 및 조류 상태 라벨들
        self.status_runway_a = self.findChild(QLabel, "status_runway_a")
        self.status_runway_b = self.findChild(QLabel, "status_runway_b")
        self.status_bird_risk = self.findChild(QLabel, "status_bird_risk")
        
        # 🔧 상태 라벨 디버깅
        print(f"[GUI] 상태 라벨 찾기 결과:")
        print(f"  - status_runway_a: {self.status_runway_a is not None}")
        print(f"  - status_runway_b: {self.status_runway_b is not None}")
        print(f"  - status_bird_risk: {self.status_bird_risk is not None}")
        
        # 라벨을 찾지 못한 경우 전체 QLabel 검색
        if not self.status_bird_risk or not self.status_runway_a or not self.status_runway_b:
            print("[GUI] 일부 상태 라벨을 찾지 못함 - 전체 QLabel 검색 시작")
            all_labels = self.findChildren(QLabel)
            print(f"[GUI] 전체 QLabel 위젯: {len(all_labels)}개")
            for i, widget in enumerate(all_labels):
                object_name = widget.objectName()
                if object_name:  # 이름이 있는 것만 출력
                    print(f"[GUI]   {i}: '{object_name}'")
                    # 상태 관련 라벨 자동 할당
                    if 'bird' in object_name.lower() and not self.status_bird_risk:
                        self.status_bird_risk = widget
                        print(f"[GUI] ✅ 조류 위험도 라벨 자동 할당: {object_name}")
                    elif 'runway_a' in object_name.lower() and not self.status_runway_a:
                        self.status_runway_a = widget
                        print(f"[GUI] ✅ 활주로 A 라벨 자동 할당: {object_name}")
                    elif 'runway_b' in object_name.lower() and not self.status_runway_b:
                        self.status_runway_b = widget
                        print(f"[GUI] ✅ 활주로 B 라벨 자동 할당: {object_name}")
        
        # 진행률 및 슬라이더
        self.progress_voice = self.findChild(QProgressBar, "progressBar_voice")
        self.progress_mic_level = self.findChild(QProgressBar, "progress_mic_level")
        self.slider_tts_volume = self.findChild(QSlider, "slider_tts_volume")
        
        # MIC LEVEL 프로그레스바 디버깅
        print(f"[GUI] 프로그레스바 찾기 결과:")
        print(f"   progress_voice: {self.progress_voice is not None}")
        print(f"   progress_mic_level: {self.progress_mic_level is not None}")
        
        # MIC LEVEL 프로그레스바 강제 찾기
        if not self.progress_mic_level:
            print("[GUI] WARN progress_mic_level 못찾음 - 전체 검색 시작")
            all_progress = self.findChildren(QProgressBar)
            print(f"[GUI] 총 {len(all_progress)}개 프로그레스바 발견:")
            for i, widget in enumerate(all_progress):
                name = widget.objectName() if hasattr(widget, 'objectName') else "이름없음"
                print(f"   [{i}] {name}")
                # mic 관련 이름 찾기
                if 'mic' in name.lower() or 'level' in name.lower():
                    print(f"   → MIC 관련 프로그레스바 발견: {name}")
                    self.progress_mic_level = widget
                    break
            else:
                # 여전히 못찾으면 첫번째 것 사용
                if all_progress:
                    print(f"   → 첫번째 프로그레스바를 MIC LEVEL로 사용: {all_progress[0].objectName()}")
                    self.progress_mic_level = all_progress[0]
                else:
                    print("[GUI] ERROR 프로그레스바를 전혀 찾을 수 없음!")
        else:
            print(f"[GUI] OK progress_mic_level 찾음: {self.progress_mic_level.objectName()}")
        
        # NEW 모든 프로그레스바와 슬라이더를 0으로 초기화 (안전하게)
        if self.progress_voice:
            self.progress_voice.setValue(0)
        if self.progress_mic_level:
            self.progress_mic_level.setValue(0)
        if self.slider_tts_volume:
            # NEW TTS 볼륨은 50%로 초기화 (0이면 소리 안남!)
            self.slider_tts_volume.setValue(50)
            
            # NEW 슬라이더 정밀도 향상
            self.slider_tts_volume.setTickPosition(QSlider.TickPosition.TicksBelow)
            self.slider_tts_volume.setTickInterval(10)  # 10% 단위로 눈금
            self.slider_tts_volume.setSingleStep(1)     # 키보드 화살표로 1% 단위 조절
            self.slider_tts_volume.setPageStep(5)       # 마우스 클릭으로 5% 단위 조절
            
            # OK 슬라이더 스타일링 추가 (채워진 부분과 빈 부분 색상 구분)
            self.slider_tts_volume.setStyleSheet("""
                QSlider::groove:vertical {
                    background: transparent;
                    width: 12px;
                    border-radius: 6px;
                    border: 2px solid #404040;
                }
                QSlider::handle:vertical {
                    background: #00ff00;
                    border: 2px solid #008800;
                    width: 20px;
                    height: 20px;
                    border-radius: 10px;
                    margin: 0 -6px;
                }
                QSlider::add-page:vertical {
                    background: #00ff00;
                    border-radius: 6px;
                }
                QSlider::sub-page:vertical {
                    background: transparent;
                    border-radius: 6px;
                }
                QSlider::tick-marks:vertical {
                    spacing: 10px;
                    width: 2px;
                    color: #808080;
                }
            """)
        # TTS 볼륨 라벨은 UI에서 제거됨
        
        print(f"[GUI] 위젯 할당 결과:")
        print(f"  - UTC 시간 라벨: {self.label_utc_time is not None}")
        print(f"  - LOCAL 시간 라벨: {self.label_local_time is not None}")
        print(f"  - START MARSHALL 버튼: {self.btn_marshall is not None}")
        print(f"  - VOICE INPUT 버튼: {self.btn_voice is not None}")
        
        # NEW 초기 시간 설정 (안전하게)
        try:
            self.update_time()  # 즉시 시간 업데이트
        except Exception as e:
            print(f"[GUI] WARN 시간 업데이트 실패: {e}")
        
        print(f"OK UI 파일 로드 완료: {ui_file}")
        print("OK 모든 프로그레스바/슬라이더를 0으로 초기화")
    
    def connect_signals(self):
        """시그널과 슬롯 연결"""
        # 버튼 연결
        if self.btn_voice:
            self.btn_voice.clicked.connect(self.start_voice_input)
        # 🆕 START MARSHALL 버튼 연결
        if self.btn_marshall:
            self.btn_marshall.clicked.connect(self.toggle_marshaling)
        
        # 슬라이더 연결
        if self.slider_tts_volume:
            self.slider_tts_volume.valueChanged.connect(self.update_tts_volume)
        
        # 🔧 시그널 연결 (스레드 안전성)
        self.bird_risk_changed_signal.connect(self.update_bird_risk_display)
        self.runway_alpha_changed_signal.connect(self.update_runway_alpha_display)
        self.runway_bravo_changed_signal.connect(self.update_runway_bravo_display)
        self.event_tts_signal.connect(self.update_tts_display_with_event)
    
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
            
            # OK TTS 속도를 빠르게 설정
            self.set_tts_speed_fast()
            
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
            # 간단한 연결 테스트
            if hasattr(client, 'tcp_client') and client.tcp_client.connect():
                print(f"[GUI] ✅ 서버 클라이언트 연결 성공: {self.SERVER_HOST}:{self.SERVER_PORT}")
                client.tcp_client.disconnect()  # 테스트 연결 해제
                return client
            else:
                print(f"[GUI] ❌ 서버 클라이언트 연결 실패: {self.SERVER_HOST}:{self.SERVER_PORT}")
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
            # 간단한 연결 테스트
            if hasattr(client, 'tcp_client') and client.tcp_client.connect():
                print(f"[GUI] ✅ 서버 클라이언트 localhost 연결 성공: {self.FALLBACK_HOST}:{self.SERVER_PORT}")
                client.tcp_client.disconnect()  # 테스트 연결 해제
                return client
            else:
                print(f"[GUI] ❌ 서버 클라이언트 localhost 연결 실패: {self.FALLBACK_HOST}:{self.SERVER_PORT}")
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
            
            # 🎤 USB 마이크를 최우선으로 사용 (충돌 방지 기능 적용됨)
            priority_groups = [
                (['usb', 'headset'], "USB 헤드셋"),  # USB 헤드셋 최우선
                (['usb', 'mic'], "USB 마이크"),      # USB 마이크 (ABKO N550)
                (['n550', 'abko'], "ABKO N550 마이크"), # 특정 USB 마이크
                (['usb'], "USB 장치"),               # 일반 USB 장치
                (['pipewire'], "PipeWire 오디오"),   # PipeWire (충돌 시 대안)
                (['headset'], "헤드셋"),             # 헤드셋
                (['alc233'], "내장 마이크"),         # 내장 마이크
                (['hw:'], "ALSA 하드웨어 장치"),     # ALSA 하드웨어 장치
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
            # 🔧 직접 호출 (QTimer 제거)
            self.play_event_tts_notification(result, "bird_risk")
    
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
            # 🔧 직접 호출 (QTimer 제거)
            self.play_event_tts_notification(result, "runway_alpha")
    
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
            # 🔧 직접 호출 (QTimer 제거)
            self.play_event_tts_notification(result, "runway_bravo")
    
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
        
        # 마이크 레벨 업데이트 타이머 - 실제 마이크 입력 반영
        self.mic_timer = QTimer()
        self.mic_timer.timeout.connect(self.update_mic_level)
        self.mic_timer.start(50)  # 50ms마다 (더 빠른 업데이트)
        
        # NEW 실시간 마이크 레벨 모니터링 초기화
        self.init_mic_monitoring()
    
    def init_mic_monitoring(self):
        """실시간 마이크 레벨 모니터링 초기화 - 선택된 마이크 사용"""
        try:
            import pyaudio
            import numpy as np
            import threading
            
            print("[GUI] 마이크 모니터링 초기화 시작...")
            
            # 선택된 마이크 디바이스 사용
            selected_mic_index = getattr(self, 'selected_mic_index', None)
            selected_mic_name = getattr(self, 'selected_mic_name', '기본 마이크')
            
            print(f"[GUI] 🎤 모니터링 마이크: {selected_mic_name} (인덱스: {selected_mic_index})")
            
            # PyAudio 설정 - 선택된 마이크 사용
            self.mic_audio = pyaudio.PyAudio()
            self.mic_chunk_size = 1024
            self.mic_sample_rate = 44100
            self.mic_format = pyaudio.paInt16
            self.mic_channels = 1
            self.mic_device_index = selected_mic_index  # 🔧 선택된 마이크 인덱스 사용
            
            # 실시간 레벨 저장용 변수
            self.current_mic_level = 0
            self.mic_monitoring_active = True
            
            # 마이크 모니터링 스레드 시작
            self.mic_monitor_thread = threading.Thread(target=self._monitor_mic_level_simple, daemon=True)
            self.mic_monitor_thread.start()
            
            print(f"[GUI] ✅ 마이크 레벨 모니터링 시작: {selected_mic_name}")
            
        except Exception as e:
            print(f"[GUI] ❌ 마이크 모니터링 초기화 실패: {e}")
            self.mic_audio = None
            self.current_mic_level = 0
    
    def _monitor_mic_level_simple(self):
        """간단한 마이크 레벨 모니터링 (PyAudio 직접 사용) - 녹음 중 일시 중지 기능 추가"""
        try:
            import numpy as np
            import time
            
            stream = None
            loop_counter = 0
            last_debug_time = time.time()
            
            print("[GUI] DEBUG 마이크 모니터링 스레드 시작됨")
            print(f"[GUI] DEBUG mic_monitoring_active = {self.mic_monitoring_active}")
            print(f"[GUI] DEBUG mic_audio = {self.mic_audio}")
            
            while self.mic_monitoring_active:
                try:
                    loop_counter += 1
                    current_time = time.time()
                    
                    # 30초마다 상태 리포트
                    if current_time - last_debug_time > 30.0:
                        print(f"[GUI] 마이크 모니터링 활성: level={self.current_mic_level}%")
                        last_debug_time = current_time
                    
                    # 🔧 녹음 중에는 마이크 모니터링 일시 중지 (디바이스 충돌 방지)
                    if getattr(self, 'is_recording', False):
                        if stream:
                            try:
                                stream.stop_stream()
                                stream.close()
                                print("[GUI] 🔴 녹음 중 - 마이크 모니터링 일시 중지")
                            except:
                                pass
                            stream = None
                        
                        self.current_mic_level = 0  # 녹음 중에는 레벨 0으로 표시
                        time.sleep(0.1)
                        continue
                    
                    # 스트림이 없으면 새로 생성
                    if not stream:
                        try:
                            print(f"[GUI] DEBUG 마이크 스트림 생성 시도...")
                            print(f"   format={self.mic_format}, channels={self.mic_channels}")
                            print(f"   rate={self.mic_sample_rate}, chunk={self.mic_chunk_size}")
                            
                            stream = self.mic_audio.open(
                                format=self.mic_format,
                                channels=self.mic_channels,
                                rate=self.mic_sample_rate,
                                input=True,
                                input_device_index=self.mic_device_index,  # 🔧 선택된 마이크 사용
                                frames_per_buffer=self.mic_chunk_size
                            )
                            print("[GUI] DEBUG 마이크 스트림 생성 성공!")
                        except Exception as stream_error:
                            print(f"[GUI] FAIL 마이크 스트림 생성 실패: {stream_error}")
                            print(f"   에러 타입: {type(stream_error)}")
                            time.sleep(1.0)
                            continue
                    
                    # 오디오 데이터 읽기
                    data = stream.read(self.mic_chunk_size, exception_on_overflow=False)
                    
                    if loop_counter <= 3:
                        print(f"[GUI] DEBUG 오디오 데이터 읽기 성공: {len(data)} bytes")
                    
                    # numpy 배열로 변환
                    audio_array = np.frombuffer(data, dtype=np.int16)
                    
                    if loop_counter <= 3:
                        print(f"[GUI] DEBUG numpy 변환: shape={audio_array.shape}, max={np.max(np.abs(audio_array))}")
                    
                    # 간단한 RMS 레벨 계산
                    rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                    
                    # 🔧 TTS 재생 중에는 마이크 레벨을 0으로 표시 (피드백 방지)
                    is_tts_playing = False
                    if hasattr(self, 'controller') and self.controller and hasattr(self.controller, 'tts_engine'):
                        if hasattr(self.controller.tts_engine, 'is_speaking'):
                            is_tts_playing = self.controller.tts_engine.is_speaking()
                    
                    if is_tts_playing:
                        normalized_level = 0  # TTS 재생 중에는 마이크 레벨 0으로 표시
                    else:
                        # 🔧 MIC LEVEL 민감도 조정 (더욱 덜 민감하게)
                        NOISE_THRESHOLD = 800  # 노이즈 임계값 더 높임 (300→800)
                        if rms > NOISE_THRESHOLD:
                            # 임계값 이상의 신호만 처리 (더 큰 분모로 덜 민감하게)
                            normalized_level = min(100, int((rms - NOISE_THRESHOLD) / 50))
                            # 증폭 계수 더 감소 (1.5→1.0)
                            normalized_level = min(100, int(normalized_level * 1.0))
                        else:
                            normalized_level = 0  # 노이즈 수준은 완전히 0
                    
                    # 현재 레벨 업데이트
                    old_level = getattr(self, 'current_mic_level', -1)
                    self.current_mic_level = int(normalized_level)
                    
                    # 큰 변화가 있을 때만 로그 출력 (10% 이상)
                    if loop_counter <= 3 or abs(self.current_mic_level - old_level) > 15:
                        print(f"[GUI] 마이크 레벨: {self.current_mic_level}% (RMS: {rms:.0f})")
                    
                    # 처리 속도 조절
                    time.sleep(0.05)  # 50ms 대기
                    
                except Exception as e:
                    print(f"[GUI] FAIL 마이크 데이터 처리 오류: {e}")
                    print(f"   에러 타입: {type(e)}")
                    import traceback
                    traceback.print_exc()
                    
                    if stream:
                        try:
                            stream.stop_stream()
                            stream.close()
                        except:
                            pass
                        stream = None
                    time.sleep(0.5)
                    continue
            
            # 정리
            print("[GUI] DEBUG 마이크 모니터링 루프 종료")
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                    print("[GUI] DEBUG 마이크 스트림 정리 완료")
                except:
                    pass
            
        except Exception as e:
            print(f"[GUI] FAIL 마이크 레벨 모니터링 전체 오류: {e}")
            import traceback
            traceback.print_exc()
            self.current_mic_level = 0
    
    def _monitor_mic_level(self):
        """NEW 실시간 마이크 레벨 모니터링 (백그라운드 스레드)"""
        try:
            import pyaudio
            import numpy as np
            import time
            
            stream = None
            
            while self.mic_monitoring_active:
                try:
                    # 일시정지 기능 제거 - 항상 모니터링 활성화
                    
                    # 스트림이 없으면 새로 생성
                    if not stream:
                        try:
                            stream = self.mic_monitor.audio.open(
                                format=self.mic_monitor.format,
                                channels=self.mic_monitor.channels,
                                rate=self.mic_monitor.sample_rate,
                                input=True,
                                input_device_index=self.mic_monitor.input_device_index,
                                frames_per_buffer=self.mic_monitor.chunk_size
                            )
                        except Exception as stream_error:
                            # 스트림 생성 실패 시 1초 대기 후 재시도 (로그 제거)
                            time.sleep(1.0)
                            continue
                    
                    # 오디오 데이터 읽기
                    data = stream.read(self.mic_monitor.chunk_size, exception_on_overflow=False)
                    
                    # numpy 배열로 변환
                    audio_array = np.frombuffer(data, dtype=np.int16)
                    
                    # 간단하고 직관적인 RMS 레벨 계산
                    rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                    
                    # 간단한 0-100 범위 정규화 (더 민감하게)
                    if rms > 0:
                        # 선형 스케일로 변환 (더 직관적)
                        normalized_level = min(100, int(rms / 327.67))  # 32767 / 100
                        # 추가 증폭 (마이크 입력이 작을 때 더 잘 보이도록)
                        normalized_level = min(100, normalized_level * 3)
                    else:
                        normalized_level = 0
                    
                    # 현재 레벨 업데이트
                    self.current_mic_level = int(normalized_level)
                    
                except Exception as e:
                    # 스트림 오류 시 잠시 대기 (로그 제거)
                    if stream:
                        try:
                            stream.stop_stream()
                            stream.close()
                        except:
                            pass
                        stream = None
                    time.sleep(0.5)
                    continue
            
            # 스트림 정리
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass
            
        except Exception as e:
            # 전체 오류 시에만 로그 출력
            print(f"[GUI] 마이크 레벨 모니터링 전체 오류: {e}")
            self.current_mic_level = 0
    
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
    
    def update_mic_level(self):
        """마이크 레벨 업데이트 - 실시간 마이크 입력 반영 (강화된 디버깅)"""
        if not hasattr(self, '_mic_gui_counter'):
            self._mic_gui_counter = 0
        self._mic_gui_counter += 1
        
        # 디버깅 로그 정리 완료
        
        if self.progress_mic_level:
            if hasattr(self, 'mic_audio') and self.mic_audio:
                # 실시간 마이크 레벨 사용
                if hasattr(self, 'current_mic_level'):
                    display_level = self.current_mic_level
                    
                    # 🔧 녹음 중에도 진짜 입력이 없으면 0으로 표시 (부스트 제거)
                    # if self.is_recording:
                    #     display_level = min(100, display_level + 10)
                    
                    old_value = self.progress_mic_level.value()
                    self.progress_mic_level.setValue(display_level)
                    
                    # 로그 정리 완료
                else:
                    # current_mic_level이 없으면 0
                    self.progress_mic_level.setValue(0)
                    pass
            else:
                # 마이크 모니터링이 없는 경우 fallback
                if self.is_recording:
                    import random
                    level = random.randint(30, 90)
                    self.progress_mic_level.setValue(level)
                    if self._mic_gui_counter <= 10:
                        print(f"[GUI] DEBUG 마이크 없음, 녹음 중 - 랜덤값: {level}")
                else:
                    self.progress_mic_level.setValue(0)
                    if self._mic_gui_counter <= 10:
                        print(f"[GUI] DEBUG 마이크 없음, 대기 중 - 0")
        else:
            if self._mic_gui_counter <= 10:
                print(f"[GUI] FAIL progress_mic_level 위젯이 없음!")
    
    def update_tts_volume(self, value):
        """TTS 볼륨 업데이트 - 정밀도 향상"""
        # NEW 실용적인 음소거 처리 (0-5 범위에서 음소거, 사용자 시스템 테스트 기반)
        is_muted = value <= 5
        
        # NEW 슬라이더 색상 업데이트 (음소거 상태 시각적 표현)
        if self.slider_tts_volume:
            if is_muted:
                # 음소거 상태 - 빨간색
                self.slider_tts_volume.setStyleSheet("""
                    QSlider::groove:vertical {
                        background: transparent;
                        width: 12px;
                        border-radius: 6px;
                        border: 2px solid #404040;
                    }
                    QSlider::handle:vertical {
                        background: #ff4444;
                        border: 2px solid #cc0000;
                        width: 20px;
                        height: 20px;
                        border-radius: 10px;
                        margin: 0 -6px;
                    }
                    QSlider::add-page:vertical {
                        background: #ff4444;
                        border-radius: 6px;
                    }
                    QSlider::sub-page:vertical {
                        background: transparent;
                        border-radius: 6px;
                    }
                """)
            else:
                # 정상 상태 - 녹색
                self.slider_tts_volume.setStyleSheet("""
                    QSlider::groove:vertical {
                        background: transparent;
                        width: 12px;
                        border-radius: 6px;
                        border: 2px solid #404040;
                    }
                    QSlider::handle:vertical {
                        background: #00ff00;
                        border: 2px solid #008800;
                        width: 20px;
                        height: 20px;
                        border-radius: 10px;
                        margin: 0 -6px;
                    }
                    QSlider::add-page:vertical {
                        background: #00ff00;
                        border-radius: 6px;
                    }
                    QSlider::sub-page:vertical {
                        background: transparent;
                        border-radius: 6px;
                    }
                """)
        
        # OK 실제 TTS 엔진 볼륨 조절 - 정밀도 향상
        if self.controller and hasattr(self.controller, 'tts_engine'):
            try:
                # NEW 정밀한 볼륨 계산 (0-2 값은 완전 음소거)
                if is_muted:
                    volume_normalized = 0.0
                    effective_volume = 0
                else:
                    # 6-100 범위를 0.1-1.0으로 매핑 (실제 들리는 범위로 조절)
                    volume_normalized = max(0.1, value / 100.0)
                    effective_volume = value
                
                # UnifiedTTSEngine의 볼륨 설정
                if hasattr(self.controller.tts_engine, 'set_volume'):
                    self.controller.tts_engine.set_volume(volume_normalized)
                    if is_muted:
                        print(f"[GUI] MUTE TTS 음소거 설정 (슬라이더 값: {value})")
                    else:
                        print(f"[GUI] OK TTS 볼륨 설정: {effective_volume}% → {volume_normalized:.3f}")
                
                # pyttsx3 엔진의 볼륨 설정 (fallback 엔진용)
                elif hasattr(self.controller.tts_engine, 'pyttsx3_engine'):
                    if self.controller.tts_engine.pyttsx3_engine:
                        self.controller.tts_engine.pyttsx3_engine.setProperty('volume', volume_normalized)
                        if is_muted:
                            print(f"[GUI] MUTE pyttsx3 TTS 음소거 설정 (슬라이더 값: {value})")
                        else:
                            print(f"[GUI] OK pyttsx3 TTS 볼륨 설정: {effective_volume}% → {volume_normalized:.3f}")
                
                else:
                    print(f"[GUI] WARN TTS 엔진에서 볼륨 조절을 지원하지 않습니다")
                    
            except Exception as e:
                print(f"[GUI] FAIL TTS 볼륨 설정 오류: {e}")
        else:
            print(f"[GUI] WARN TTS 컨트롤러가 없어서 볼륨 조절할 수 없습니다")
    
    def set_tts_speed_fast(self):
        """TTS 속도를 조금 빠르게 설정"""
        if self.controller and hasattr(self.controller, 'tts_engine'):
            try:
                # 기본 속도보다 20% 빠르게 (150 → 180)
                fast_speed = 180
                
                # UnifiedTTSEngine의 속도 설정
                if hasattr(self.controller.tts_engine, 'set_rate'):
                    self.controller.tts_engine.set_rate(fast_speed)
                    print(f"[GUI] OK TTS 속도 설정: {fast_speed} WPM (빠름)")
                
                else:
                    print(f"[GUI] WARN TTS 엔진에서 속도 조절을 지원하지 않습니다")
                    
            except Exception as e:
                print(f"[GUI] FAIL TTS 속도 설정 오류: {e}")
        else:
            print(f"[GUI] WARN TTS 컨트롤러가 없어서 속도 조절할 수 없습니다")
    
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
        if self.btn_voice:
            self.btn_voice.setText("RECORDING...")
            self.btn_voice.setEnabled(False)
        if self.label_main_status:
            self.label_main_status.setText("RECORDING")
            self.label_main_status.setStyleSheet("background-color: #331100; color: #ffaa00;")
        
        # 진행률 표시
        if self.progress_voice:
            self.progress_voice.setVisible(True)
            self.progress_voice.setRange(0, 50)  # 5초 * 10 (100ms 단위)
            self.progress_voice.setValue(0)
        
        # 진행률 업데이트 타이머
        self.recording_timer = QTimer()
        self.recording_timer.timeout.connect(self.update_recording_progress)
        self.recording_timer.start(100)  # 100ms마다
        self.recording_progress = 0
        
        # 워커 스레드 시작
        self.voice_worker = VoiceWorkerThread(self.controller)
        self.voice_worker.voice_completed.connect(self.on_voice_completed)
        self.voice_worker.voice_error.connect(self.on_voice_error)
        self.voice_worker.stt_result.connect(self.on_stt_result)
        self.voice_worker.tts_text_ready.connect(self.on_tts_text_ready)
        self.voice_worker.start()
        
        if hasattr(self, 'statusbar') and self.statusbar:
            self.statusbar.showMessage("Voice input in progress... Please speak for 5 seconds")
    
    def update_recording_progress(self):
        """녹음 진행률 업데이트"""
        self.recording_progress += 1
        if self.progress_voice:
            self.progress_voice.setValue(self.recording_progress)
        
        if self.recording_progress >= 50:  # 5초 완료
            self.recording_timer.stop()
    
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
        
        # 🟢 녹음 완료 - 마이크 모니터링 재개
        print("[GUI] 🟢 녹음 완료 - 마이크 모니터링 재개")
        self.is_recording = False
        if self.btn_voice:
            self.btn_voice.setText("VOICE INPUT")
            self.btn_voice.setEnabled(True)
        if self.progress_voice:
            # NEW 프로그레스바를 숨기지 않고 0으로 리셋
            self.progress_voice.setValue(0)
        
        if hasattr(self, 'recording_timer'):
            self.recording_timer.stop()
        
        # 마이크 모니터링은 이미 항상 활성화되어 있음
        
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
            QTimer.singleShot(3000, self.reset_status)
            
        elif status == "FAILED" or status.value == "FAILED" if hasattr(status, 'value') else False:
            # 실제 실패만 ERROR로 표시
            if self.label_main_status:
                self.label_main_status.setText("ERROR")
                self.label_main_status.setStyleSheet("background-color: #330000; color: #ff4444;")
            if hasattr(self, 'statusbar') and self.statusbar:
                self.statusbar.showMessage(f"Processing failed: {result.get('error_message', 'Unknown error')}")
                
            # 3초 후 READY 상태로 복귀
            QTimer.singleShot(3000, self.reset_status)
            
        elif status == "PROCESSING" or status.value == "PROCESSING" if hasattr(status, 'value') else False:
            # 처리 중 상태는 그냥 무시 (이미 RECORDING 상태이므로)
            print(f"[GUI] PROCESSING STATUS: {status}")
            
        else:
            # PENDING이나 기타 상태는 로그만 출력
            print(f"[GUI] INFO 알 수 없는 상태: {status}")
            # READY 상태로 즉시 복귀
            QTimer.singleShot(1000, self.reset_status)
    
    def on_voice_error(self, error: str):
        """음성 처리 오류"""
        # 🟢 오류 발생 - 마이크 모니터링 재개
        print("[GUI] 🟢 오류 발생 - 마이크 모니터링 재개")
        self.is_recording = False
        if self.btn_voice:
            self.btn_voice.setText("VOICE INPUT")
            self.btn_voice.setEnabled(True)
        if self.progress_voice:
            # NEW 프로그레스바를 숨기지 않고 0으로 리셋
            self.progress_voice.setValue(0)
        
        if hasattr(self, 'recording_timer'):
            self.recording_timer.stop()
        
        # 마이크 모니터링은 이미 항상 활성화되어 있음
        
        if self.label_main_status:
            self.label_main_status.setText("ERROR")
            self.label_main_status.setStyleSheet("background-color: #330000; color: #ff4444;")
        if hasattr(self, 'statusbar') and self.statusbar:
            self.statusbar.showMessage(f"Voice processing error: {error}")
        
        QMessageBox.warning(self, "Voice Processing Error", f"Voice processing encountered an error:\n{error}")
        
        # 3초 후 READY 상태로 복귀
        QTimer.singleShot(3000, self.reset_status)
    
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
            if self.btn_marshall:
                self.btn_marshall.setText("STOP MARSHALL")
                self.btn_marshall.setStyleSheet("""
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
            
            # TTS 알림
            if self.controller and self.controller.tts_engine:
                self.controller.tts_engine.speak("Marshaling recognition activated")
                
        except Exception as e:
            print(f"[GUI] ❌ 마샬링 시작 오류: {e}")
    
    def stop_marshaling(self):
        """마샬링 인식 중지"""
        try:
            print("[GUI] 🛑 마샬링 인식 중지")
            self.marshaling_active = False
            
            # 버튼 상태 변경 
            if self.btn_marshall:
                self.btn_marshall.setText("START MARSHALL")
                self.btn_marshall.setStyleSheet("""
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
            
            # TTS 알림
            if self.controller and self.controller.tts_engine:
                self.controller.tts_engine.speak("Marshaling recognition deactivated")
            
            # 메인 상태를 기본으로 복원
            if self.label_main_status:
                self.label_main_status.setText("SYSTEM READY")
                
        except Exception as e:
            print(f"[GUI] ❌ 마샬링 중지 오류: {e}")
    
    def send_marshaling_command(self, command: str):
        """PDS 서버에 마샬링 명령 전송 (포트 5301)"""
        try:
            import socket
            import json
            
            # PDS 서버 주소 (포트 5301)
            pds_host = self.SERVER_HOST
            pds_port = 5301
            
            # 명령 메시지 생성
            command_message = {
                "type": "command",
                "command": command
            }
            
            # TCP 소켓으로 전송
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3.0)  # 3초 타임아웃
                sock.connect((pds_host, pds_port))
                message = json.dumps(command_message) + "\n"
                sock.send(message.encode('utf-8'))
                print(f"[GUI] 📤 PDS 명령 전송: {command} → {pds_host}:{pds_port}")
                
        except Exception as e:
            print(f"[GUI] ❌ PDS 명령 전송 실패: {e}")
            # 폴백: localhost로 시도
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(3.0)
                    sock.connect(("localhost", 5301))
                    message = json.dumps(command_message) + "\n"
                    sock.send(message.encode('utf-8'))
                    print(f"[GUI] 📤 PDS 명령 전송 (localhost): {command}")
            except Exception as e2:
                print(f"[GUI] ❌ PDS 명령 전송 완전 실패: {e2}")
    
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
                
                # TTS로 제스처 안내
                if self.controller and self.controller.tts_engine:
                    self.controller.tts_engine.speak(message)
                    
                # 메인 상태 표시 업데이트
                if self.label_main_status:
                    self.label_main_status.setText(f"MARSHALING: {result}")
                    
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
            
            # 마이크 모니터링 중지
            if hasattr(self, 'mic_monitoring_active'):
                self.mic_monitoring_active = False
                print("[GUI] 마이크 모니터링 중지 요청")
            
            # 마이크 모니터링 스레드 종료 대기
            if hasattr(self, 'mic_monitor_thread'):
                self.mic_monitor_thread.join(timeout=1.0)
                print("[GUI] 마이크 모니터링 스레드 종료")
            
            # 마이크 오디오 객체 정리
            if hasattr(self, 'mic_audio') and self.mic_audio:
                try:
                    self.mic_audio.terminate()
                    print("[GUI] 마이크 PyAudio 정리")
                except:
                    pass
            
            # 타이머 정리
            if hasattr(self, 'time_timer'):
                self.time_timer.stop()
            if hasattr(self, 'mic_timer'):
                self.mic_timer.stop()
            if hasattr(self, 'recording_timer'):
                self.recording_timer.stop()
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
    
    try:
        # RedWing 인터페이스 생성 및 표시
        redwing = RedWing()
        redwing.show()
        
        print("🎯 FALCON RedWing Interface 시작됨")
        
        # 이벤트 루프 실행
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"FAIL RedWing Interface 시작 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 