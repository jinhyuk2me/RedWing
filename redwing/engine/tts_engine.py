import torch
import pyttsx3
import io
import wave
import threading
import time
import tempfile
import os
import numpy as np
import queue
from typing import Optional, List, Dict, Any
from datetime import datetime

# Coqui TTS는 선택적 import
try:
    from TTS.api import TTS
    COQUI_AVAILABLE = True
except ImportError:
    print("[UnifiedTTS] Coqui TTS를 사용할 수 없습니다. pip install TTS로 설치하세요.")
    COQUI_AVAILABLE = False

class UnifiedTTSEngine:
    """통합 TTS 엔진 - Coqui TTS와 pyttsx3를 모두 지원"""
    
    def __init__(self, 
                 use_coqui: bool = True,
                 coqui_model: str = "tts_models/en/ljspeech/glow-tts",
                 fallback_to_pyttsx3: bool = True,
                 rate: int = 150,
                 volume: float = 0.9,
                 device: str = "auto"):
        """
        통합 TTS 엔진 초기화
        
        Args:
            use_coqui: Coqui TTS 사용 여부
            coqui_model: Coqui TTS 모델명
            fallback_to_pyttsx3: Coqui 실패시 pyttsx3 사용 여부
            rate: 말하기 속도 (words per minute)
            volume: 음량 (0.0 ~ 1.0)
            device: 계산 장치 ("auto", "cuda", "cpu")
        """
        # 공통 설정
        self.rate = rate
        self.volume = volume
        self.device = self._get_device(device) if COQUI_AVAILABLE else "cpu"
        self.use_coqui = use_coqui and COQUI_AVAILABLE
        self.fallback_to_pyttsx3 = fallback_to_pyttsx3
        self.coqui_failed = False
        
        # 상태 관리
        self.is_speaking_flag = False
        self.current_tts_type = None  # "response" 또는 "event"
        
        # TTS 큐 시스템 (충돌 방지용)
        self.tts_queue = queue.Queue()
        self.queue_thread = None
        self.queue_running = False
        
        # 엔진 초기화
        self.pyttsx3_engine = None
        self.coqui_engine = None
        
        # pyttsx3 엔진 초기화 (항상 준비)
        self._init_pyttsx3()
        
        # Coqui TTS 엔진 초기화 (옵션)
        if self.use_coqui:
            self._init_coqui(coqui_model)
        
        # TTS 큐 처리 스레드 시작
        self._start_queue_processor()
        
        print(f"[UnifiedTTS] 통합 TTS 엔진 초기화 완료 - 현재 엔진: {self.get_current_engine()}")
    
    def _get_device(self, device: str) -> str:
        """최적 장치 선택 - GPU 우선 사용, 실패시 CPU 폴백"""
        if device == "auto":
            # 항상 GPU 사용을 시도 (오류 발생시 CPU로 폴백)
            print("[UnifiedTTS] 🔥 GPU 우선 사용 모드 - 실패시 CPU 폴백")
            return "cuda"
        elif device == "cuda":
            print("[UnifiedTTS] 🔥 CUDA 장치 강제 지정 - 실패시 CPU 폴백")
            return "cuda"
        return device
    
    def _init_pyttsx3(self):
        """pyttsx3 엔진 초기화"""
        try:
            print("[UnifiedTTS] pyttsx3 엔진 초기화 중...")
            self.pyttsx3_engine = pyttsx3.init()
            self.pyttsx3_engine.setProperty('rate', self.rate)
            self.pyttsx3_engine.setProperty('volume', self.volume)
            
            # 사용 가능한 음성 확인
            voices = self.pyttsx3_engine.getProperty('voices')
            if voices:
                self.pyttsx3_engine.setProperty('voice', voices[0].id)
                print(f"[UnifiedTTS] pyttsx3 음성 설정: {voices[0].name}")
            
            print("[UnifiedTTS] ✅ pyttsx3 엔진 초기화 완료")
            
        except Exception as e:
            print(f"[UnifiedTTS] ❌ pyttsx3 초기화 실패: {e}")
            self.pyttsx3_engine = None
    
    def _init_coqui(self, model_name: str):
        """Coqui TTS 엔진 초기화 - GPU 강제 사용 (오류 완전 억제)"""
        if not COQUI_AVAILABLE:
            print("[UnifiedTTS] Coqui TTS를 사용할 수 없습니다.")
            self.coqui_failed = True
            return
            
        # CUDA 오류 완전 억제를 위한 환경 설정
        import os
        import warnings
        
        # 환경 변수 설정
        os.environ['CUDA_VISIBLE_DEVICES'] = '0'
        os.environ['CUDA_LAUNCH_BLOCKING'] = '1'
        
        # 모든 CUDA 관련 경고 억제
        warnings.filterwarnings("ignore", category=UserWarning, module="torch.cuda")
        
        try:
            print(f"[UnifiedTTS] 🚀 Coqui TTS 모델 로딩: {model_name}")
            print(f"[UnifiedTTS] 🔧 장치: {self.device} (GPU 강제 사용)")
            
            # 무조건 GPU 사용 시도 (오류 발생해도 계속 진행)
            use_gpu = True
            print(f"[UnifiedTTS] 🔥 GPU 강제 사용 모드 활성화")
            
            # CUDA 오류를 완전히 무시하고 TTS 엔진 초기화
            import sys
            from io import StringIO
            
            # stderr 임시 캐치
            old_stderr = sys.stderr
            sys.stderr = StringIO()
            
            try:
                # Coqui TTS 초기화 (GPU 강제)
                self.coqui_engine = TTS(model_name, progress_bar=False, gpu=use_gpu)
            finally:
                # stderr 복원
                sys.stderr = old_stderr
            
            # GPU 사용시에만 GPU로 이동 시도
            if use_gpu:
                try:
                    if hasattr(self.coqui_engine, 'synthesizer') and self.coqui_engine.synthesizer:
                        if hasattr(self.coqui_engine.synthesizer, 'tts_model'):
                            self.coqui_engine.synthesizer.tts_model = self.coqui_engine.synthesizer.tts_model.cuda()
                            print("[UnifiedTTS] 🔥 TTS 모델을 GPU로 이동 완료")
                        if hasattr(self.coqui_engine.synthesizer, 'vocoder_model') and self.coqui_engine.synthesizer.vocoder_model:
                            self.coqui_engine.synthesizer.vocoder_model = self.coqui_engine.synthesizer.vocoder_model.cuda()
                            print("[UnifiedTTS] 🔥 Vocoder 모델을 GPU로 이동 완료")
                except Exception as gpu_move_error:
                    print(f"[UnifiedTTS] ⚠️ GPU 이동 중 오류 (무시하고 계속): {gpu_move_error}")
            
            print(f"[UnifiedTTS] ✅ Coqui TTS 엔진 초기화 완료 (장치: {self.device})")
            
            # 모델 정보 출력
            if hasattr(self.coqui_engine, 'languages') and self.coqui_engine.languages:
                print(f"[UnifiedTTS] 🌍 지원 언어: {self.coqui_engine.languages}")
            
            if hasattr(self.coqui_engine, 'speakers') and self.coqui_engine.speakers:
                print(f"[UnifiedTTS] 🎤 스피커 수: {len(self.coqui_engine.speakers)}")
            
        except Exception as e:
            print(f"[UnifiedTTS] ❌ Coqui TTS 초기화 실패: {e}")
            print("[UnifiedTTS] 🔄 대안 모델로 재시도...")
            self.coqui_failed = True
            
            # 안정적인 모델로 재시도
            fallback_models = [
                "tts_models/en/ljspeech/glow-tts",
                "tts_models/en/ljspeech/speedy-speech",
                "tts_models/en/ljspeech/tacotron2-DDC"
            ]
            
            for fallback_model in fallback_models:
                if fallback_model != model_name:
                    try:
                        print(f"[UnifiedTTS] 🔄 대안 모델 시도: {fallback_model}")
                        self.coqui_engine = TTS(fallback_model, progress_bar=True, gpu=use_gpu)
                        
                        # GPU 사용시에만 GPU로 이동 시도
                        if use_gpu:
                            try:
                                if hasattr(self.coqui_engine, 'synthesizer') and self.coqui_engine.synthesizer:
                                    if hasattr(self.coqui_engine.synthesizer, 'tts_model'):
                                        self.coqui_engine.synthesizer.tts_model = self.coqui_engine.synthesizer.tts_model.cuda()
                                    if hasattr(self.coqui_engine.synthesizer, 'vocoder_model') and self.coqui_engine.synthesizer.vocoder_model:
                                        self.coqui_engine.synthesizer.vocoder_model = self.coqui_engine.synthesizer.vocoder_model.cuda()
                            except Exception as gpu_move_error:
                                print(f"[UnifiedTTS] ⚠️ 대안 모델 GPU 이동 중 오류 (무시): {gpu_move_error}")
                        
                        print(f"[UnifiedTTS] ✅ 대안 모델 로딩 성공 ({self.device})!")
                        self.coqui_failed = False
                        break
                    except Exception as fallback_error:
                        print(f"[UnifiedTTS] ❌ 대안 모델 실패: {fallback_error}")
                        continue
            
            if self.coqui_failed:
                print(f"[UnifiedTTS] ❌ 모든 Coqui 모델 로딩 실패")
                self.coqui_engine = None
    
    def _start_queue_processor(self):
        """TTS 큐 처리 스레드 시작"""
        if not self.queue_running:
            self.queue_running = True
            self.queue_thread = threading.Thread(target=self._process_tts_queue, daemon=True)
            self.queue_thread.start()
            print("[UnifiedTTS] TTS 큐 처리 스레드 시작")
    
    def _process_tts_queue(self):
        """TTS 큐 처리 (순차 재생)"""
        while self.queue_running:
            try:
                # 큐에서 TTS 작업 가져오기 (1초 타임아웃)
                tts_item = self.tts_queue.get(timeout=1.0)
                
                text = tts_item['text']
                tts_type = tts_item['type']  # "response" 또는 "event"
                force_pyttsx3 = tts_item.get('force_pyttsx3', False)
                language = tts_item.get('language', 'en')
                
                print(f"[UnifiedTTS] 큐에서 TTS 처리: {tts_type} - '{text[:50]}...'")
                
                # 현재 재생 중인 TTS 타입 설정
                self.current_tts_type = tts_type
                self.is_speaking_flag = True
                
                # 실제 TTS 재생
                self._speak_direct(text, force_pyttsx3=force_pyttsx3, language=language)
                
                # 재생 완료
                self.current_tts_type = None
                self.is_speaking_flag = False
                
                # 큐 작업 완료 표시
                self.tts_queue.task_done()
                
            except queue.Empty:
                # 타임아웃 - 계속 대기
                continue
            except Exception as e:
                print(f"[UnifiedTTS] 큐 처리 오류: {e}")
                self.current_tts_type = None
                self.is_speaking_flag = False
    
    def speak(self, text: str, blocking: bool = True, 
              force_pyttsx3: bool = False, language: str = "en", 
              tts_type: str = "response"):
        """
        텍스트 음성 변환 (큐 시스템 사용)
        
        Args:
            text: 변환할 텍스트
            blocking: 동기/비동기 처리 (큐 시스템에서는 무시됨)
            force_pyttsx3: pyttsx3 강제 사용
            language: 언어 (Coqui용)
            tts_type: TTS 타입 ("response" 또는 "event")
        """
        # 음소거 상태 확인
        if self.volume == 0.0:
            print(f"[UnifiedTTS] 🔇 음소거 상태 - 음성 재생 생략: '{text}'")
            return
        
        if not text or not text.strip():
            print("[UnifiedTTS] 빈 텍스트는 음성 변환할 수 없습니다.")
            return
        
        # TTS 작업을 큐에 추가
        tts_item = {
            'text': text,
            'type': tts_type,
            'force_pyttsx3': force_pyttsx3,
            'language': language
        }
        
        self.tts_queue.put(tts_item)
        print(f"[UnifiedTTS] TTS 큐에 추가: {tts_type} - '{text[:30]}...' (큐 크기: {self.tts_queue.qsize()})")
    
    def speak_event(self, text: str, force_pyttsx3: bool = False, language: str = "en"):
        """
        이벤트 TTS 재생 (우선순위 확인 - 녹음 및 응답 TTS 중 차단)
        
        Args:
            text: 변환할 텍스트
            force_pyttsx3: pyttsx3 강제 사용
            language: 언어
        """
        # 🔧 현재 응답 TTS가 재생 중이면 완전 차단
        if self.is_speaking() and self.current_tts_type == "response":
            print(f"[UnifiedTTS] 🚫 응답 TTS 재생 중이므로 이벤트 TTS 완전 차단: '{text[:30]}...'")
            return
        
        # 🔧 현재 다른 이벤트 TTS가 재생 중이면 큐에 추가하지 않고 스킵
        if self.is_speaking() and self.current_tts_type == "event":
            print(f"[UnifiedTTS] 🚫 다른 이벤트 TTS 재생 중이므로 스킵: '{text[:30]}...'")
            return
        
        # 🔧 큐에 이미 이벤트 TTS가 있으면 스킵 (중복 방지)
        event_count = sum(1 for item in list(self.tts_queue.queue) if item.get('type') == 'event')
        if event_count > 0:
            print(f"[UnifiedTTS] 🚫 큐에 이미 {event_count}개 이벤트 TTS 대기 중 - 스킵: '{text[:30]}...'")
            return
        
        # 이벤트 TTS 재생
        self.speak(text, tts_type="event", force_pyttsx3=force_pyttsx3, language=language)
        print(f"[UnifiedTTS] ✅ 이벤트 TTS 큐에 추가: '{text[:30]}...'")
    
    def _speak_direct(self, text: str, force_pyttsx3: bool = False, language: str = "en"):
        """
        직접 TTS 재생 (큐 처리용)
        
        Args:
            text: 변환할 텍스트
            force_pyttsx3: pyttsx3 강제 사용
            language: 언어 (Coqui용)
        """
        # Coqui 실패했거나 강제 pyttsx3 사용
        if force_pyttsx3 or self.coqui_failed or not self.coqui_engine:
            print("[UnifiedTTS] pyttsx3 사용")
            return self._speak_pyttsx3(text)
        
        # Coqui TTS 시도
        try:
            print("[UnifiedTTS] Coqui TTS 시도...")
            return self._speak_coqui(text, language)
        except Exception as e:
            print(f"[UnifiedTTS] Coqui TTS 실패: {e}")
            self.coqui_failed = True
            
            # Fallback to pyttsx3
            if self.fallback_to_pyttsx3 and self.pyttsx3_engine:
                print("[UnifiedTTS] pyttsx3로 fallback")
                return self._speak_pyttsx3(text)
            else:
                raise
    
    def _speak_pyttsx3(self, text: str):
        """pyttsx3로 음성 재생"""
        if not self.pyttsx3_engine:
            print("[UnifiedTTS] pyttsx3 엔진이 초기화되지 않음")
            return
        
        try:
            print(f"[UnifiedTTS] pyttsx3 음성 변환: '{text}'")
            self.pyttsx3_engine.say(text)
            self.pyttsx3_engine.runAndWait()
            print("[UnifiedTTS] pyttsx3 음성 재생 완료")
        except Exception as e:
            print(f"[UnifiedTTS] pyttsx3 재생 오류: {e}")
    
    def _speak_coqui(self, text: str, language: str = "en"):
        """Coqui TTS로 음성 재생"""
        if not self.coqui_engine:
            print("[UnifiedTTS] Coqui TTS 엔진이 초기화되지 않음")
            return
        
        try:
            print(f"[UnifiedTTS] Coqui TTS 음성 변환: '{text}' (언어: {language})")
            
            # 임시 파일 생성
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
            
            # 텍스트 전처리
            processed_text = self._preprocess_text(text)
            
            # TTS 생성
            if hasattr(self.coqui_engine, 'languages') and self.coqui_engine.languages and language in self.coqui_engine.languages:
                self.coqui_engine.tts_to_file(text=processed_text, file_path=temp_path, language=language)
            else:
                self.coqui_engine.tts_to_file(text=processed_text, file_path=temp_path)
            
            # 볼륨 적용
            if self.volume != 1.0:
                self._apply_volume_to_file(temp_path)
            
            # 오디오 재생
            self._play_audio_file(temp_path)
            
            # 임시 파일 정리
            try:
                os.unlink(temp_path)
            except:
                pass
            
            print("[UnifiedTTS] Coqui TTS 음성 재생 완료")
            
        except Exception as e:
            print(f"[UnifiedTTS] Coqui TTS 재생 오류: {e}")
            raise
    
    def _preprocess_text(self, text: str) -> str:
        """텍스트 전처리 (항공 용어 등)"""
        # 항공 용어 처리
        aviation_terms = {
            "ATC": "Air Traffic Control",
            "ILS": "Instrument Landing System",
            "VOR": "VHF Omnidirectional Range",
            "DME": "Distance Measuring Equipment",
            "TCAS": "Traffic Collision Avoidance System",
            "GPWS": "Ground Proximity Warning System"
        }
        
        processed_text = text
        for abbr, full_form in aviation_terms.items():
            processed_text = processed_text.replace(abbr, full_form)
        
        return processed_text
    
    def _apply_volume_to_file(self, file_path: str):
        """WAV 파일에 볼륨 적용"""
        try:
            with wave.open(file_path, 'rb') as wav_file:
                frames = wav_file.readframes(-1)
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
            
            # numpy 배열로 변환
            if sample_width == 2:  # 16-bit
                audio_data = np.frombuffer(frames, dtype=np.int16)
            elif sample_width == 4:  # 32-bit
                audio_data = np.frombuffer(frames, dtype=np.int32)
            else:
                return
            
            # 볼륨 적용
            modified_audio = (audio_data * self.volume).astype(audio_data.dtype)
            
            # 파일에 다시 저장
            with wave.open(file_path, 'wb') as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(sample_width)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(modified_audio.tobytes())
                
        except Exception as e:
            print(f"[UnifiedTTS] 볼륨 적용 오류: {e}")
    
    def _play_audio_file(self, file_path: str):
        """오디오 파일 재생"""
        try:
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            
            # 재생 완료까지 대기
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
                
        except ImportError:
            # pygame이 없으면 시스템 명령어 사용
            try:
                import subprocess
                if os.name == 'nt':  # Windows
                    os.system(f'start /min "" "{file_path}"')
                else:  # Linux/Mac
                    subprocess.run(['aplay', file_path], check=True, capture_output=True)
            except Exception as e:
                print(f"[UnifiedTTS] 오디오 재생 오류: {e}")
        except Exception as e:
            print(f"[UnifiedTTS] pygame 재생 오류: {e}")
    
    def speak_async(self, text: str, force_pyttsx3: bool = False, language: str = "en"):
        """비동기 음성 재생"""
        self.speak(text, blocking=False, force_pyttsx3=force_pyttsx3, language=language)
    
    def is_speaking(self) -> bool:
        """TTS 재생 중인지 확인"""
        return self.is_speaking_flag
    
    def get_current_tts_type(self) -> Optional[str]:
        """현재 재생 중인 TTS 타입 반환"""
        return self.current_tts_type if self.is_speaking() else None
    
    def get_queue_size(self) -> int:
        """TTS 큐 크기 반환"""
        return self.tts_queue.qsize()
    
    def clear_queue(self):
        """TTS 큐 비우기"""
        while not self.tts_queue.empty():
            try:
                self.tts_queue.get_nowait()
                self.tts_queue.task_done()
            except queue.Empty:
                break
        print("[UnifiedTTS] TTS 큐 비움")
    
    def stop_speaking(self):
        """음성 재생 중지"""
        # 큐 비우기
        self.clear_queue()
        
        # 현재 재생 중지
        if self.pyttsx3_engine:
            try:
                self.pyttsx3_engine.stop()
            except:
                pass
        
        # 상태 초기화
        self.current_tts_type = None
        self.is_speaking_flag = False
        
        print("[UnifiedTTS] 모든 TTS 재생 중지")
    
    def set_rate(self, rate: int):
        """속도 설정"""
        self.rate = rate
        if self.pyttsx3_engine:
            try:
                self.pyttsx3_engine.setProperty('rate', rate)
                print(f"[UnifiedTTS] 말하기 속도 변경: {rate}")
            except Exception as e:
                print(f"[UnifiedTTS] 속도 변경 오류: {e}")
    
    def set_volume(self, volume: float):
        """음량 설정"""
        self.volume = max(0.0, min(1.0, volume))  # 0.0 ~ 1.0 범위로 제한
        
        if self.pyttsx3_engine:
            try:
                self.pyttsx3_engine.setProperty('volume', self.volume)
            except Exception as e:
                print(f"[UnifiedTTS] pyttsx3 음량 변경 오류: {e}")
        
        if self.volume == 0.0:
            print(f"[UnifiedTTS] 🔇 음소거 설정")
        else:
            print(f"[UnifiedTTS] 🔊 음량 변경: {self.volume}")
    
    def get_current_volume(self) -> float:
        """현재 음량 반환"""
        return self.volume
    
    def is_engine_ready(self) -> bool:
        """엔진 준비 상태"""
        return (self.coqui_engine is not None and not self.coqui_failed) or \
               (self.pyttsx3_engine is not None)
    
    def get_current_engine(self) -> str:
        """현재 사용 중인 엔진"""
        if self.coqui_engine and not self.coqui_failed and self.use_coqui:
            return "Coqui TTS"
        elif self.pyttsx3_engine:
            return "pyttsx3"
        else:
            return "None"
    
    def toggle_engine(self):
        """엔진 전환"""
        if self.use_coqui and not self.coqui_failed:
            self.coqui_failed = True
            print("[UnifiedTTS] Coqui TTS 비활성화 - pyttsx3 사용")
        else:
            self.coqui_failed = False
            print("[UnifiedTTS] Coqui TTS 활성화")
    
    def get_status(self) -> Dict[str, Any]:
        """TTS 엔진 상태 반환"""
        return {
            "current_engine": self.get_current_engine(),
            "is_speaking": self.is_speaking(),
            "current_tts_type": self.get_current_tts_type(),
            "queue_size": self.get_queue_size(),
            "volume": self.volume,
            "rate": self.rate,
            "coqui_available": self.coqui_engine is not None and not self.coqui_failed,
            "pyttsx3_available": self.pyttsx3_engine is not None,
            "device": self.device
        }
    
    def get_available_voices(self) -> List:
        """사용 가능한 음성 목록 반환 (pyttsx3용)"""
        if self.pyttsx3_engine:
            try:
                voices = self.pyttsx3_engine.getProperty('voices')
                return [(i, voice.name, voice.id) for i, voice in enumerate(voices)]
            except Exception as e:
                print(f"[UnifiedTTS] 음성 목록 조회 오류: {e}")
        return []
    
    def set_voice(self, voice_index: int):
        """음성 변경 (pyttsx3용)"""
        if self.pyttsx3_engine:
            try:
                voices = self.pyttsx3_engine.getProperty('voices')
                if voices and 0 <= voice_index < len(voices):
                    self.pyttsx3_engine.setProperty('voice', voices[voice_index].id)
                    print(f"[UnifiedTTS] 음성 변경: {voices[voice_index].name}")
                else:
                    print(f"[UnifiedTTS] 잘못된 음성 인덱스: {voice_index}")
            except Exception as e:
                print(f"[UnifiedTTS] 음성 변경 오류: {e}")
    
    def shutdown(self):
        """엔진 종료"""
        print("[UnifiedTTS] TTS 엔진 종료 중...")
        
        # 큐 처리 중지
        self.queue_running = False
        if self.queue_thread and self.queue_thread.is_alive():
            self.queue_thread.join(timeout=2.0)
        
        # 재생 중지
        self.stop_speaking()
        
        # 엔진 정리
        if self.pyttsx3_engine:
            try:
                self.pyttsx3_engine.stop()
            except:
                pass
        
        print("[UnifiedTTS] TTS 엔진 종료 완료")
    
    def __del__(self):
        """소멸자"""
        self.shutdown()


# 편의 함수들
def create_tts_engine(use_coqui: bool = True, **kwargs) -> UnifiedTTSEngine:
    """TTS 엔진 생성 편의 함수"""
    return UnifiedTTSEngine(use_coqui=use_coqui, **kwargs)

# 기존 클래스들과의 호환성을 위한 별칭
TTSEngine = UnifiedTTSEngine
HybridTTSEngine = UnifiedTTSEngine
CoquiTTSEngine = UnifiedTTSEngine 