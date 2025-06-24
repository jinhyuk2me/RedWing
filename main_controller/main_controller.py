import time
from typing import Optional, Tuple
from datetime import datetime

# 각 모듈 import - 절대 import로 변경
from audio_io.mic_speaker_io import AudioIO
from engine import WhisperSTTEngine, UnifiedTTSEngine
from request_handler import RequestClassifier, TCPServerClient, ResponseProcessor
from session_handler import SessionManager
from .voice_models import VoiceInteraction, AudioData, STTResult
from request_handler.request_models import (
    PilotRequest, PilotResponse, RequestStatus, 
    create_pilot_request, create_pilot_response
)

class VoiceInteractionController:
    def __init__(self, 
                 audio_io: Optional[AudioIO] = None,
                 stt_engine: Optional[WhisperSTTEngine] = None,
                 query_parser: Optional[RequestClassifier] = None,
                 main_server_client: Optional[TCPServerClient] = None,
                 response_processor: Optional[ResponseProcessor] = None,
                 tts_engine: Optional[UnifiedTTSEngine] = None,
                 session_manager: Optional[SessionManager] = None):
        """
        음성 상호작용 컨트롤러 초기화
        
        Args:
            각 모듈 인스턴스들 (None이면 기본값으로 생성)
        """
        # 모듈 초기화 (None이면 기본 인스턴스 생성)
        self.audio_io = audio_io or AudioIO()
        self.stt_engine = stt_engine or WhisperSTTEngine(model_name="small", language="en", device="auto")
        self.query_parser = query_parser or RequestClassifier()
        
        # 구조화된 질의 시스템
        self.main_server_client = main_server_client or TCPServerClient()
        self.response_processor = response_processor or ResponseProcessor()
        
        # 통합 TTS 엔진 (Coqui TTS + pyttsx3 fallback)
        self.tts_engine = tts_engine or UnifiedTTSEngine(
            use_coqui=True,
            coqui_model="tts_models/en/ljspeech/tacotron2-DDC",
            fallback_to_pyttsx3=True,
            device="cuda"
        )
        self.session_manager = session_manager or SessionManager()
        
        # STT 완료 콜백 함수
        self.stt_callback = None
        
        # TTS 텍스트 생성 완료 콜백 함수
        self.tts_callback = None
        
        # LLM 하이브리드 분류 활성화
        if hasattr(self.query_parser, 'enable_llm'):
            llm_success = self.query_parser.enable_llm()
            if llm_success:
                print("[VoiceController] ✅ LLM 하이브리드 분류 활성화")
            else:
                print("[VoiceController] ⚠️ LLM 비활성화, 키워드 분류만 사용")
        
        # TTS 엔진 상태 출력
        if hasattr(self.tts_engine, 'get_status'):
            tts_status = self.tts_engine.get_status()
            print(f"[VoiceController] 🎵 TTS 엔진: {tts_status.get('current_engine', 'Unknown')}")
        
        print(f"[VoiceController] 음성 상호작용 컨트롤러 초기화 완료")

    def handle_voice_interaction(self, callsign: str = "UNKNOWN", 
                               recording_duration: float = 5.0) -> VoiceInteraction:
        """
        전체 음성 상호작용 처리 (동기 방식) - 구조화된 질의 시스템
        
        Args:
            callsign: 항공기 콜사인
            recording_duration: 녹음 시간 (초)
            
        Returns:
            VoiceInteraction 객체
        """
        # 새 세션 생성
        session_id = self.session_manager.new_session_id()
        
        # 상호작용 객체 생성
        interaction = VoiceInteraction(
            session_id=session_id,
            callsign=callsign
        )
        
        try:
            print(f"[VoiceController] 🎯 음성 상호작용 시작: {session_id}")
            
            # 1. 음성 녹음
            print("[VoiceController] 1️⃣ 음성 녹음")
            audio_data = self._record_audio(recording_duration)
            if not audio_data:
                interaction.mark_failed("음성 녹음 실패")
                return interaction
            
            interaction.audio_input = AudioData(audio_bytes=audio_data)
            
            # 2. STT 처리
            print("[VoiceController] 2️⃣ 음성 인식")
            stt_result = self._process_stt(audio_data, session_id)
            if not stt_result or not stt_result.text.strip():
                interaction.mark_failed("음성 인식 실패")
                return interaction
            
            interaction.stt_result = stt_result
            
            # STT 완료 즉시 콜백 호출
            if self.stt_callback:
                print("[VoiceController] 🚀 STT 완료 즉시 콜백 호출")
                self.stt_callback(stt_result)
            
            # 3. 쿼리 분류 (하이브리드 방식)
            print("[VoiceController] 3️⃣ 요청 분류 (하이브리드)")
            request_code, parameters = self._classify_request_hybrid(stt_result.text, session_id)
            
            # PilotRequest 생성
            pilot_request = create_pilot_request(
                session_id=session_id,
                callsign=callsign,
                text=stt_result.text,
                request_code=request_code,
                parameters=parameters
            )
            pilot_request.confidence_score = stt_result.confidence_score
            interaction.pilot_request = pilot_request
            
            # 4. 구조화된 질의 처리
            print("[VoiceController] 4️⃣ 구조화된 질의 처리")
            if request_code != "UNKNOWN_REQUEST":
                response_text = self._execute_structured_query(request_code, parameters, session_id)
            else:
                response_text = self._execute_request(request_code, parameters, session_id)
            
            # PilotResponse 생성
            pilot_response = create_pilot_response(
                session_id=session_id,
                request_code=request_code,
                response_text=response_text
            )
            interaction.pilot_response = pilot_response
            interaction.tts_text = response_text
            
            # TTS 텍스트 생성 완료 즉시 콜백 호출
            if self.tts_callback:
                print("[VoiceController] 🚀 TTS 텍스트 생성 완료 즉시 콜백 호출")
                self.tts_callback(response_text)
            
            # 5. TTS 처리
            print("[VoiceController] 5️⃣ 음성 합성 및 재생")
            self._process_tts(response_text)
            
            # 상호작용 완료
            interaction.mark_completed()
            
            # 로그 기록
            self._log_interaction(interaction)
            
            print(f"[VoiceController] ✅ 음성 상호작용 완료: {session_id}")
            return interaction
            
        except Exception as e:
            print(f"[VoiceController] ❌ 음성 상호작용 오류: {e}")
            interaction.mark_failed(str(e))
            return interaction
    
    def _classify_request_hybrid(self, text: str, session_id: str) -> Tuple[str, dict]:
        """하이브리드 요청 분류 (LLM + 키워드)"""
        try:
            if hasattr(self.query_parser, 'classify_hybrid'):
                return self.query_parser.classify_hybrid(text, session_id)
            else:
                return self.query_parser.classify(text, session_id)
        except Exception as e:
            print(f"[VoiceController] 분류 오류: {e}")
            return "UNKNOWN_REQUEST", {"error": str(e), "original_text": text}
    
    def _execute_structured_query(self, request_code: str, parameters: dict, session_id: str) -> str:
        """
        🆕 구조화된 질의 실행
        
        Args:
            request_code: 요청 코드
            parameters: 요청 파라미터
            session_id: 세션 ID
            
        Returns:
            자연어 응답 텍스트
        """
        try:
            # 1. 메인 서버에 구조화된 질의 전송
            print(f"[VoiceController] 🔄 메인 서버 질의: {request_code}")
            success, response_data = self.main_server_client.send_query(
                request_code, parameters, session_id
            )
            
            if not success:
                print(f"[VoiceController] ❌ 서버 질의 실패: {response_data}")
                # 폴백: 기존 방식 사용
                return self._execute_request(request_code, parameters, session_id)
            
            # 2. 응답 데이터 유효성 검증
            is_valid, validation_msg = self.response_processor.validate_response_data(response_data)
            if not is_valid:
                print(f"[VoiceController] ⚠️ 응답 데이터 무효: {validation_msg}")
                # 폴백: 기존 방식 사용
                return self._execute_request(request_code, parameters, session_id)
            
            # 3. 응답 처리 및 자연어 생성
            print(f"[VoiceController] 🔄 응답 처리: {self.response_processor.get_response_summary(response_data)}")
            
            original_text = parameters.get("original_text", "unknown request")
            
            # original_request 구성 (ResponseProcessor에서 콜사인 추출용)
            original_request = {
                "callsign": parameters.get("callsign", "Aircraft"),
                "request_text": original_text,
                "parameters": parameters
            }
            
            print(f"[VoiceController] 📝 original_request 구성: {original_request}")
            
            success, response_text = self.response_processor.process_response(
                response_data, original_request
            )
            
            if success:
                print(f"[VoiceController] ✅ 구조화된 응답 생성 완료: '{response_text}'")
                return response_text
            else:
                print(f"[VoiceController] ⚠️ 응답 처리 실패, 폴백 사용 (reason: '{response_text}')")
                # 폴백: 기존 방식 사용
                return self._execute_request(request_code, parameters, session_id)
                
        except Exception as e:
            print(f"[VoiceController] ❌ 구조화된 질의 오류: {e}")
            # 폴백: 기존 방식 사용
            return self._execute_request(request_code, parameters, session_id)
    
    def handle_voice_interaction_async(self, callsign: str = "UNKNOWN",
                                     recording_duration: float = 5.0,
                                     callback=None) -> str:
        """
        비동기 음성 상호작용 처리
        
        Args:
            callsign: 항공기 콜사인
            recording_duration: 녹음 시간
            callback: 완료 시 호출할 콜백 함수
            
        Returns:
            세션 ID
        """
        import threading
        
        session_id = self.session_manager.new_session_id()
        
        def async_process():
            interaction = self.handle_voice_interaction(callsign, recording_duration)
            if callback:
                callback(interaction)
        
        thread = threading.Thread(target=async_process)
        thread.daemon = True
        thread.start()
        
        return session_id
    
    def start_recording(self):
        """
        녹음 시작 (비동기)
        """
        self.audio_io.start_recording()
    
    def stop_recording_and_process(self, callsign: str = "UNKNOWN") -> VoiceInteraction:
        """
        녹음 중지 및 처리
        """
        # 녹음 중지 및 데이터 획득
        audio_data = self.audio_io.stop_recording()
        
        if not audio_data:
            session_id = self.session_manager.new_session_id()
            interaction = VoiceInteraction(session_id=session_id, callsign=callsign)
            interaction.mark_failed("녹음 데이터 없음")
            return interaction
        
        # 나머지 처리 과정
        return self._process_audio_data(audio_data, callsign)
    
    def _record_audio(self, duration: float) -> bytes:
        """음성 녹음"""
        try:
            return self.audio_io.record_audio(duration)
        except Exception as e:
            print(f"[VoiceController] 녹음 오류: {e}")
            return b""
    
    def _process_stt(self, audio_data: bytes, session_id: str) -> Optional[STTResult]:
        """STT 처리"""
        try:
            start_time = time.time()
            
            # 신뢰도 점수가 있는 경우 사용
            if hasattr(self.stt_engine, 'transcribe_with_confidence'):
                text, confidence = self.stt_engine.transcribe_with_confidence(audio_data, session_id)
            else:
                text = self.stt_engine.transcribe(audio_data, session_id)
                confidence = 0.8  # 기본값
            
            processing_time = time.time() - start_time
            
            return STTResult(
                text=text,
                confidence_score=confidence,
                processing_time=processing_time,
                model_used="whisper"
            )
        except Exception as e:
            print(f"[VoiceController] STT 처리 오류: {e}")
            return None
    
    def _classify_request(self, text: str, session_id: str) -> Tuple[str, dict]:
        """요청 분류"""
        try:
            return self.query_parser.classify(text, session_id)
        except Exception as e:
            print(f"[VoiceController] 요청 분류 오류: {e}")
            return "UNKNOWN_REQUEST", {"error": str(e)}
    
    def _execute_request(self, request_code: str, parameters: dict, session_id: str) -> str:
        """요청 실행 - MockMainServer 기반으로 통합"""
        try:
            print(f"[VoiceController] 🔄 MockMainServer 기반 요청 처리: {request_code}")
            success, response_data = self.main_server_client.send_query(
                request_code, parameters, session_id
            )
            
            if success:
                # 원본 요청 정보 구성 (ResponseProcessor에서 콜사인 추출용)
                original_request = {
                    "request_code": request_code,
                    "callsign": parameters.get("callsign", "Aircraft"),
                    "original_text": parameters.get("original_text", "")
                }
                
                # 응답 처리
                success_processed, final_response = self.response_processor.process_response(
                    response_data, original_request
                )
                
                if success_processed:
                    return final_response
                else:
                    return "응답 처리 중 오류가 발생했습니다."
            else:
                print(f"[VoiceController] ❌ 서버 질의 실패: {response_data}")
                return "요청 처리에 실패했습니다. 다시 시도해주세요."
                
        except Exception as e:
            print(f"[VoiceController] 요청 실행 오류: {e}")
            return f"요청 처리 중 오류가 발생했습니다: {str(e)}"
    
    def _process_tts(self, text: str):
        """TTS 처리"""
        try:
            print(f"[VoiceController] 🎵 TTS 처리 텍스트: '{text}'")
            # 응답 TTS로 타입 지정 (이벤트 TTS와 구분)
            if hasattr(self.tts_engine, 'speak') and 'tts_type' in self.tts_engine.speak.__code__.co_varnames:
                self.tts_engine.speak(text, blocking=True, tts_type="response")
            else:
                # 폴백: 기존 방식
                self.tts_engine.speak(text, blocking=True)
        except Exception as e:
            print(f"[VoiceController] TTS 처리 오류: {e}")
    
    def _process_audio_data(self, audio_data: bytes, callsign: str) -> VoiceInteraction:
        """오디오 데이터 처리 (녹음 완료 후)"""
        session_id = self.session_manager.new_session_id()
        interaction = VoiceInteraction(session_id=session_id, callsign=callsign)
        
        try:
            interaction.audio_input = AudioData(audio_bytes=audio_data)
            
            # STT 처리
            stt_result = self._process_stt(audio_data, session_id)
            if not stt_result:
                interaction.mark_failed("STT 처리 실패")
                return interaction
            
            interaction.stt_result = stt_result
            
            # 나머지 처리 과정
            request_code, parameters = self._classify_request(stt_result.text, session_id)
            
            pilot_request = create_pilot_request(
                session_id=session_id,
                callsign=callsign,
                text=stt_result.text,
                request_code=request_code,
                parameters=parameters
            )
            interaction.pilot_request = pilot_request
            
            response_text = self._execute_request(request_code, parameters, session_id)
            
            pilot_response = create_pilot_response(
                session_id=session_id,
                request_code=request_code,
                response_text=response_text
            )
            interaction.pilot_response = pilot_response
            interaction.tts_text = response_text
            
            # TTS 처리
            self._process_tts(response_text)
            
            interaction.mark_completed()
            self._log_interaction(interaction)
            
            return interaction
            
        except Exception as e:
            interaction.mark_failed(str(e))
            return interaction
    
    def _log_interaction(self, interaction: VoiceInteraction):
        """상호작용 로그 기록"""
        try:
            if interaction.stt_result and interaction.pilot_request and interaction.pilot_response:
                self.session_manager.log_interaction(
                    session_id=interaction.session_id,
                    callsign=interaction.callsign,
                    stt_text=interaction.stt_result.text,
                    request_code=interaction.pilot_request.request_code,
                    parameters=interaction.pilot_request.parameters,
                    response_text=interaction.pilot_response.response_text,
                    processing_time=interaction.total_processing_time,
                    confidence_score=interaction.stt_result.confidence_score
                )
        except Exception as e:
            print(f"[VoiceController] 로그 기록 오류: {e}")
    
    def get_system_status(self) -> dict:
        """시스템 상태 조회 - 구조화된 질의 시스템 포함"""
        status = {
            "audio_io": "OPERATIONAL" if self.audio_io else "FAILED",
            "stt_engine": "OPERATIONAL" if self.stt_engine.is_model_loaded() else "FAILED",
            "query_parser": "OPERATIONAL" if self.query_parser else "FAILED",
            "tts_engine": "OPERATIONAL" if self.tts_engine.is_engine_ready() else "FAILED",
            "session_manager": "OPERATIONAL" if self.session_manager else "FAILED",
            
            # 🆕 구조화된 질의 시스템 상태
            "structured_query_enabled": True,
            "main_server_client": "OPERATIONAL" if self.main_server_client else "FAILED",
            "response_processor": "OPERATIONAL" if self.response_processor else "FAILED",
        }
        
        # LLM 상태 추가
        if hasattr(self.query_parser, 'get_llm_status'):
            llm_status = self.query_parser.get_llm_status()
            status["llm_enabled"] = llm_status.get("enabled", False)
            status["llm_model"] = llm_status.get("model", "unknown")
        
        # 메인 서버 연결 상태 확인
        if self.main_server_client:
            if hasattr(self.main_server_client, 'server_available'):
                status["main_server_available"] = self.main_server_client.server_available
            else:
                status["main_server_available"] = "unknown"
        
        return status
    
    def test_main_server_connection(self) -> bool:
        """
        메인 서버 연결 테스트
        
        Returns:
            연결 성공 여부
        """
        if self.main_server_client:
            return self.main_server_client.test_connection()
        return False
    
    def get_supported_requests(self) -> list:
        """
        지원하는 요청 유형 목록 반환
        
        Returns:
            지원하는 요청 유형 리스트
        """
        if self.query_parser:
            return self.query_parser.get_supported_requests()
        return []
    
    def create_tts_request_payload(self, text: str, session_id: str) -> dict:
        """
        TTS 요청 페이로드 생성 (외부 TTS 서비스용)
        
        Args:
            text: 음성으로 변환할 텍스트
            session_id: 세션 ID
            
        Returns:
            TTS 요청 페이로드
        """
        if self.response_processor:
            return self.response_processor.create_tts_request(text, session_id)
        else:
            # 기본 페이로드
            return {
                "type": "command",
                "command": "synthesize_speech",
                "text": text,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
        }
    
    def process_external_tts_response(self, tts_response: dict) -> bool:
        """
        외부 TTS 서비스 응답 처리
        
        Args:
            tts_response: TTS 서비스 응답 (audio 데이터 포함)
            
        Returns:
            처리 성공 여부
        """
        try:
            if tts_response.get("type") == "response" and "audio" in tts_response:
                # Base64 오디오 데이터를 디코딩하여 재생
                import base64
                audio_data = base64.b64decode(tts_response["audio"])
                
                # 오디오 재생 (AudioIO 사용)
                if hasattr(self.audio_io, 'play_audio'):
                    self.audio_io.play_audio(audio_data)
                    return True
                else:
                    print("[VoiceController] ⚠️ 오디오 재생 기능 없음")
                    return False
            else:
                print(f"[VoiceController] ❌ 잘못된 TTS 응답 형식: {tts_response}")
                return False
                
        except Exception as e:
            print(f"[VoiceController] ❌ TTS 응답 처리 오류: {e}")
            return False
    
    def shutdown(self):
        """
        시스템 종료 및 리소스 정리
        """
        print("[VoiceController] 시스템 종료 중...")
        
        try:
            # TTS 엔진 정지 및 종료
            if self.tts_engine:
                if hasattr(self.tts_engine, 'shutdown'):
                    self.tts_engine.shutdown()
                else:
                    self.tts_engine.stop_speaking()
            
            # 메인 서버 클라이언트 종료
            if self.main_server_client and hasattr(self.main_server_client, 'shutdown'):
                self.main_server_client.shutdown()
            
            # 오디오 시스템 정리
            if self.audio_io:
                # 녹음 중이면 중지
                if hasattr(self.audio_io, 'stop_recording'):
                    self.audio_io.stop_recording()
                
                # 오디오 시스템 종료
                if hasattr(self.audio_io, 'shutdown'):
                    self.audio_io.shutdown()
            
            print("[VoiceController] 시스템 종료 완료")
            
        except Exception as e:
            print(f"[VoiceController] 시스템 종료 중 오류: {e}")

    def set_stt_callback(self, callback):
        """STT 완료 콜백 설정"""
        self.stt_callback = callback
        print("[VoiceController] ✅ STT 완료 콜백 설정됨")

    def set_tts_callback(self, callback):
        """TTS 텍스트 생성 완료 콜백 설정"""
        self.tts_callback = callback
        print("[VoiceController] ✅ TTS 텍스트 생성 콜백 설정됨")

# 편의 함수들
def create_voice_controller(
    server_host: str = "localhost",
    server_port: int = 5300,
    use_simulator: bool = True,
    stt_model: str = "small"
) -> VoiceInteractionController:
    """
    VoiceInteractionController 생성 (TCP 기반 구조화된 질의 시스템)
    
    Args:
        server_host: TCP 서버 호스트 (기본값: localhost)
        server_port: TCP 서버 포트 (기본값: 5300)
        use_simulator: 연결 실패 시 시뮬레이터 사용 여부
        stt_model: STT 모델 크기
        
    Returns:
        VoiceInteractionController 인스턴스
    """
    try:
        print(f"[VoiceController] 🔧 TCP 기반 구조화된 질의 시스템 초기화")
        print(f"  서버: {server_host}:{server_port}")
        print(f"  시뮬레이터 폴백: {'활성화' if use_simulator else '비활성화'}")
        
        # 각 모듈 초기화
        audio_io = AudioIO()
        stt_engine = WhisperSTTEngine(model_name=stt_model, language="en", device="auto")
        query_parser = RequestClassifier()
        
        # TCP 기반 서버 클라이언트
        main_server_client = TCPServerClient(
            server_host=server_host,
            server_port=server_port,
            use_simulator=use_simulator
        )
        
        response_processor = ResponseProcessor()
        tts_engine = UnifiedTTSEngine(
            use_coqui=True,
            coqui_model="tts_models/en/ljspeech/tacotron2-DDC",
            fallback_to_pyttsx3=True,
            device="cuda"
        )
        session_manager = SessionManager()
        
        # VoiceInteractionController 생성
        controller = VoiceInteractionController(
            audio_io=audio_io,
            stt_engine=stt_engine,
            query_parser=query_parser,
            main_server_client=main_server_client,
            response_processor=response_processor,
            tts_engine=tts_engine,
            session_manager=session_manager
        )
        
        print(f"[VoiceController] ✅ TCP 기반 구조화된 질의 시스템 초기화 완료")
        return controller
        
    except Exception as e:
        print(f"[VoiceController] ❌ 초기화 실패: {e}")
        raise
