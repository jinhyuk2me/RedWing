import whisper
import io
import tempfile
import os
import torch
from typing import Optional

class WhisperSTTEngine:
    def __init__(self, model_name: str = "medium", language: str = "en", device: str = "auto"):
        """
        Whisper STT 엔진 초기화 (활주로 상태 & 조류 위험도 전용)
        
        Args:
            model_name: whisper 모델 크기 (tiny, base, small, medium, large, large-v2, large-v3)
            language: 인식할 언어 코드 (ko, en 등)
            device: 실행 장치 ("auto", "cuda", "cpu")
        """
        self.model_name = model_name
        self.language = language
        self.device = self._determine_device(device)
        self.model = None
        self.aviation_prompt = ""
        
        self._setup_gpu_memory()
        self._load_model()
    
    def _determine_device(self, device: str) -> str:
        """
        최적의 실행 장치 결정
        """
        if device == "auto":
            if torch.cuda.is_available():
                # GPU 메모리 확인
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3  # GB
                print(f"[WhisperSTT] GPU 메모리: {gpu_memory:.1f}GB")
                
                # Large 모델을 위해 임계값을 5.5GB로 조정 (100% 사용으로 여유 확보)
                if gpu_memory >= 5.5:
                    return "cuda"
                else:
                    print(f"[WhisperSTT] GPU 메모리 부족 ({gpu_memory:.1f}GB < 5.5GB), CPU 사용")
                    return "cpu"
            else:
                return "cpu"
        return device
    
    def _setup_gpu_memory(self):
        """
        GPU 메모리 최적화 설정
        """
        if self.device == "cuda" and torch.cuda.is_available():
            # GPU 메모리 캐시 정리
            torch.cuda.empty_cache()
            
            # 메모리 할당 전략 설정 - 분할 크기 제한으로 Large 모델 지원
            os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True,max_split_size_mb:256'
            
            # 메모리 분할 방지 - Large 모델을 위해 98%로 설정 (약간의 여유)
            torch.cuda.set_per_process_memory_fraction(0.98)  # GPU 메모리의 98% 사용
            
            print(f"[WhisperSTT] GPU 메모리 최적화 설정 완료 (98% 사용, 분할 제한)")
    
    def _load_model(self):
        """
        Whisper 모델 로딩 - GPU 메모리 최적화 버전
        """
        try:
            print(f"[WhisperSTT] {self.model_name} 모델 로딩 중... (장치: {self.device})")
            
            if self.device == "cuda":
                print(f"[WhisperSTT] GPU 메모리 정리 중...")
                torch.cuda.empty_cache()
                
                # 현재 GPU 메모리 사용량 확인
                allocated = torch.cuda.memory_allocated() / 1024**3
                cached = torch.cuda.memory_reserved() / 1024**3
                print(f"[WhisperSTT] GPU 메모리 - 할당됨: {allocated:.2f}GB, 캐시됨: {cached:.2f}GB")
            
            print(f"[WhisperSTT] 주의: {self.model_name} 모델은 약 3GB 크기로 처음 다운로드 시 시간이 걸릴 수 있습니다.")
            
            # 모델 로딩 시 장치 지정
            self.model = whisper.load_model(self.model_name, device=self.device)
            print(f"[WhisperSTT] {self.model_name} 모델 로딩 완료 - 활주로/조류 요청 최적화 ({self.device})")
            
        except RuntimeError as e:
            if "CUDA out of memory" in str(e):
                print(f"[WhisperSTT] GPU 메모리 부족: {e}")
                print(f"[WhisperSTT] medium 모델로 폴백합니다...")
                try:
                    torch.cuda.empty_cache()  # 메모리 정리
                    self.model = whisper.load_model("medium", device=self.device)
                    self.model_name = "medium"
                    print(f"[WhisperSTT] medium 모델 로딩 완료 ({self.device})")
                except RuntimeError as e2:
                    if "CUDA out of memory" in str(e2):
                        print(f"[WhisperSTT] medium 모델도 실패, CPU로 전환: {e2}")
                        try:
                            self.device = "cpu"
                            self.model = whisper.load_model("medium", device="cpu")
                            self.model_name = "medium"
                            print(f"[WhisperSTT] medium 모델 로딩 완료 (CPU)")
                        except Exception as e3:
                            print(f"[WhisperSTT] CPU에서도 실패, base 모델로 폴백: {e3}")
                            try:
                                self.model = whisper.load_model("base", device="cpu")
                                self.model_name = "base"
                                self.device = "cpu"
                                print(f"[WhisperSTT] base 모델 로딩 완료 (CPU)")
                            except Exception as e4:
                                print(f"[WhisperSTT] 모든 모델 로딩 실패: {e4}")
                                self.model = None
                    else:
                        raise e2
            else:
                raise e
        except Exception as e:
            print(f"[WhisperSTT] 예상치 못한 오류: {e}")
            print(f"[WhisperSTT] base 모델로 폴백합니다...")
            try:
                self.model = whisper.load_model("base", device="cpu")
                self.model_name = "base"
                self.device = "cpu"
                print(f"[WhisperSTT] base 모델 로딩 완료 (CPU)")
            except Exception as e2:
                print(f"[WhisperSTT] 모든 모델 로딩 실패: {e2}")
                self.model = None

    def transcribe(self, audio_bytes: bytes, session_id: str = "") -> str:
        """
        음성 데이터(WAV 바이트) → 텍스트 반환 (활주로/조류 요청 최적화)
        """
        if self.model is None:
            print("[WhisperSTT] 모델이 로드되지 않았습니다.")
            return ""
        
        try:
            # GPU 메모리 정리 (GPU 사용 시)
            if self.device == "cuda":
                torch.cuda.empty_cache()
            
            # 임시 파일에 오디오 데이터 저장
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            
            print(f"[WhisperSTT] 음성 인식 시작... (모델: {self.model_name}, 장치: {self.device}, 세션: {session_id})")
            
            # 모델 크기에 따른 최적화 설정 (환각 방지 강화)
            if "large" in self.model_name:
                # large 모델용 고품질 설정
                transcribe_options = {
                    "language": "en",  # 영어로 명시적 고정
                    "task": "transcribe",  # 번역 방지, 전사만 수행
                    "fp16": self.device == "cuda",  # GPU에서만 fp16 사용
                    "verbose": False,
                    "temperature": 0.0,  # 완전 결정적 출력
                    "beam_size": 5,
                    "best_of": 5,
                    "no_speech_threshold": 0.95,  # 더 높임 (0.9 → 0.95)
                    "logprob_threshold": -0.3,   # 더 엄격함 (-0.5 → -0.3)
                    "compression_ratio_threshold": 1.8,  # 더 엄격함 (2.0 → 1.8)
                    "condition_on_previous_text": False,  # 이전 텍스트 영향 차단
                    "initial_prompt": "English aviation communication only. No foreign languages.",  # 영어 전용 힌트
                    "suppress_tokens": [1, 2, 7, 8, 9, 10, 14, 25, 26, 27, 28, 29, 31, 58, 59, 60, 61, 62, 63, 90, 91, 92, 93, 359, 503, 522, 542, 873, 893, 902, 918, 922, 931, 1350, 1853, 1982, 2460, 2627, 3246, 3253, 3268, 3536, 3846, 3961, 4183, 4667, 6585, 6647, 7273, 9061, 9383, 10428, 10929, 11938, 12033, 12331, 12562, 13793, 14157, 14635, 15265, 15618, 16553, 16604, 18362, 18956, 20075, 21675, 22520, 26130, 26161, 26435, 28279, 29464, 31650, 32302, 32470, 36865, 42863, 47425, 49870, 50254, 50258, 50358, 50359, 50360, 50361, 50362]  # 환각 방지 토큰들
                }
            else:
                # medium/small 모델용 기본 설정
                transcribe_options = {
                    "language": "en",  # 영어로 명시적 고정
                    "task": "transcribe",  # 번역 방지, 전사만 수행
                    "fp16": False,  # 안정성을 위해 fp16 비활성화
                    "verbose": False,
                    "temperature": 0.0,  # 완전 결정적 출력
                    "no_speech_threshold": 0.95,  # 더 높임 (0.9 → 0.95)
                    "logprob_threshold": -0.3,   # 더 엄격함 (-0.5 → -0.3)
                    "compression_ratio_threshold": 1.8,  # 더 엄격함 (2.0 → 1.8)
                    "condition_on_previous_text": False,  # 이전 텍스트 영향 차단
                    "initial_prompt": "English aviation communication only. No foreign languages.",  # 영어 전용 힌트
                    "suppress_tokens": [1, 2, 7, 8, 9, 10, 14, 25, 26, 27, 28, 29, 31, 58, 59, 60, 61, 62, 63, 90, 91, 92, 93, 359, 503, 522, 542, 873, 893, 902, 918, 922, 931, 1350, 1853, 1982, 2460, 2627, 3246, 3253, 3268, 3536, 3846, 3961, 4183, 4667, 6585, 6647, 7273, 9061, 9383, 10428, 10929, 11938, 12033, 12331, 12562, 13793, 14157, 14635, 15265, 15618, 16553, 16604, 18362, 18956, 20075, 21675, 22520, 26130, 26161, 26435, 28279, 29464, 31650, 32302, 32470, 36865, 42863, 47425, 49870, 50254, 50258, 50358, 50359, 50360, 50361, 50362]  # 환각 방지 토큰들
                }
            
            # Whisper로 음성 인식
            result = self.model.transcribe(temp_file_path, **transcribe_options)
            
            # 임시 파일 삭제
            os.unlink(temp_file_path)
            
            transcribed_text = result["text"].strip()
            
            # 환각 결과 검증 및 필터링
            transcribed_text = self._validate_transcription_result(transcribed_text)
            
            # 2가지 요청에 특화된 후처리
            transcribed_text = self._postprocess_specialized_terms(transcribed_text)
            
            print(f"[WhisperSTT] 인식 결과: '{transcribed_text}'")
            
            return transcribed_text
            
        except Exception as e:
            print(f"[WhisperSTT] 음성 인식 오류: {e}")
            # 임시 파일 정리
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            return ""
    
    def _postprocess_specialized_terms(self, text: str) -> str:
        """
        활주로 상태 & 조류 위험도 요청에 특화된 후처리
        """
        if not text:
            return text
        
        # 대소문자 정규화
        processed_text = text.strip()
        
        # 콜사인 정규화 (FALCON 우선)
        import re
        
        # FALCON 콜사인 패턴 강화
        falcon_patterns = [
            (r'\b(?:falcon|falkon|faulcon|folcon)\s*(\d{1,4}[a-z]?)\b', r'FALCON \1'),
            (r'\b(?:f\s*a\s*l\s*c\s*o\s*n)\s*(\d{1,4}[a-z]?)\b', r'FALCON \1'),
        ]
        
        for pattern, replacement in falcon_patterns:
            processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
        
        # 활주로 번호 정규화 (주요 활주로만)
        runway_patterns = [
            (r'\brunway\s*(\d{1,2})\s*([lrc]?)\b', r'runway \1\2'),
            (r'\brwy\s*(\d{1,2})\s*([lrc]?)\b', r'runway \1\2'),
            (r'\b(\d{1,2})\s*([lrc]?)\s*runway\b', r'runway \1\2'),
            # 특정 활주로 번호 강화
            (r'\b(?:25|twenty.?five)\s*([lrc]?)\b', r'25\1'),
            (r'\b(?:07|seven|oh.?seven)\s*([lrc]?)\b', r'07\1'),
        ]
        
        for pattern, replacement in runway_patterns:
            processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
        
        # 핵심 키워드 정규화 (2가지 요청에 특화)
        keyword_corrections = {
            # 조류 관련
            r'\b(?:bird|birds|burd|berds|bert)\b': 'bird',
            r'\b(?:wildlife|wild.?life|wildlive)\b': 'wildlife',
            r'\b(?:risk|risks|risc)\b': 'risk',
            r'\b(?:activity|activities|activety)\b': 'activity',
            r'\b(?:assessment|assesment|asessment)\b': 'assessment',
            
            # 활주로 관련
            r'\b(?:runway|run.?way|runaway)\b': 'runway',
            r'\b(?:status|state|condition)\b': 'status',
            r'\b(?:check|chek|cheque)\b': 'check',
            r'\b(?:clear|cleared|cler)\b': 'clear',
            r'\b(?:operational|operation|operatinal)\b': 'operational',
            
            # 공통
            r'\b(?:request|reqest|reques)\b': 'request',
        }
        
        for pattern, replacement in keyword_corrections.items():
            processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
        
        # 숫자 정규화
        number_corrections = {
            r'\b(?:one|won)\b': '1',
            r'\b(?:two|too|to)\b': '2', 
            r'\b(?:three|tree)\b': '3',
            r'\b(?:four|for|fore)\b': '4',
            r'\b(?:five|fiv)\b': '5',
            r'\b(?:six|siks)\b': '6',
            r'\b(?:seven|sevn)\b': '7',
            r'\b(?:eight|ate)\b': '8',
            r'\b(?:nine|nien)\b': '9',
            r'\b(?:zero|oh)\b': '0',
        }
        
        for pattern, replacement in number_corrections.items():
            processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
        
        # 최종 정리
        processed_text = re.sub(r'\s+', ' ', processed_text).strip()
        
        return processed_text

    def transcribe_with_confidence(self, audio_bytes: bytes, session_id: str = "") -> tuple[str, float]:
        """
        음성 인식과 함께 신뢰도 점수 반환 (활주로/조류 요청 최적화)
        """
        if self.model is None:
            return "", 0.0
        
        try:
            # GPU 메모리 정리
            if self.device == "cuda":
                torch.cuda.empty_cache()
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            
            print(f"[WhisperSTT] 신뢰도 포함 음성 인식... (모델: {self.model_name}, 장치: {self.device})")
            
            # 모델 크기에 따른 최적화 설정 (환각 방지 강화)
            if "large" in self.model_name:
                # large 모델용 고품질 설정
                transcribe_options = {
                    "language": "en",  # 영어로 명시적 고정
                    "task": "transcribe",  # 번역 방지, 전사만 수행
                    "fp16": self.device == "cuda",  # GPU에서만 fp16 사용
                    "verbose": False,
                    "temperature": 0.0,  # 완전 결정적 출력
                    "beam_size": 5,
                    "best_of": 5,
                    "no_speech_threshold": 0.95,  # 더 높임 (0.9 → 0.95)
                    "logprob_threshold": -0.3,   # 더 엄격함 (-0.5 → -0.3)
                    "compression_ratio_threshold": 1.8,  # 더 엄격함 (2.0 → 1.8)
                    "condition_on_previous_text": False,  # 이전 텍스트 영향 차단
                    "initial_prompt": "English aviation communication only. No foreign languages.",  # 영어 전용 힌트
                    "suppress_tokens": [1, 2, 7, 8, 9, 10, 14, 25, 26, 27, 28, 29, 31, 58, 59, 60, 61, 62, 63, 90, 91, 92, 93, 359, 503, 522, 542, 873, 893, 902, 918, 922, 931, 1350, 1853, 1982, 2460, 2627, 3246, 3253, 3268, 3536, 3846, 3961, 4183, 4667, 6585, 6647, 7273, 9061, 9383, 10428, 10929, 11938, 12033, 12331, 12562, 13793, 14157, 14635, 15265, 15618, 16553, 16604, 18362, 18956, 20075, 21675, 22520, 26130, 26161, 26435, 28279, 29464, 31650, 32302, 32470, 36865, 42863, 47425, 49870, 50254, 50258, 50358, 50359, 50360, 50361, 50362]  # 환각 방지 토큰들
                }
            else:
                # medium/small 모델용 기본 설정
                transcribe_options = {
                    "language": "en",  # 영어로 명시적 고정
                    "task": "transcribe",  # 번역 방지, 전사만 수행
                    "fp16": False,  # 안정성을 위해 fp16 비활성화
                    "verbose": False,
                    "temperature": 0.0,  # 완전 결정적 출력
                    "no_speech_threshold": 0.95,  # 더 높임 (0.9 → 0.95)
                    "logprob_threshold": -0.3,   # 더 엄격함 (-0.5 → -0.3)
                    "compression_ratio_threshold": 1.8,  # 더 엄격함 (2.0 → 1.8)
                    "condition_on_previous_text": False,  # 이전 텍스트 영향 차단
                    "initial_prompt": "English aviation communication only. No foreign languages.",  # 영어 전용 힌트
                    "suppress_tokens": [1, 2, 7, 8, 9, 10, 14, 25, 26, 27, 28, 29, 31, 58, 59, 60, 61, 62, 63, 90, 91, 92, 93, 359, 503, 522, 542, 873, 893, 902, 918, 922, 931, 1350, 1853, 1982, 2460, 2627, 3246, 3253, 3268, 3536, 3846, 3961, 4183, 4667, 6585, 6647, 7273, 9061, 9383, 10428, 10929, 11938, 12033, 12331, 12562, 13793, 14157, 14635, 15265, 15618, 16553, 16604, 18362, 18956, 20075, 21675, 22520, 26130, 26161, 26435, 28279, 29464, 31650, 32302, 32470, 36865, 42863, 47425, 49870, 50254, 50258, 50358, 50359, 50360, 50361, 50362]  # 환각 방지 토큰들
                }
            
            result = self.model.transcribe(temp_file_path, **transcribe_options)
            
            os.unlink(temp_file_path)
            
            text = result["text"].strip()
            
            # 환각 결과 검증 및 필터링
            text = self._validate_transcription_result(text)
            
            # 2가지 요청에 특화된 후처리
            text = self._postprocess_specialized_terms(text)
            
            # 신뢰도 계산 (segments 기반)
            avg_confidence = self._calculate_confidence_score(result)
            
            print(f"[WhisperSTT] 인식 결과: '{text}' (신뢰도: {avg_confidence:.3f})")
            
            return text, avg_confidence
            
        except Exception as e:
            print(f"[WhisperSTT] 음성 인식 오류: {e}")
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            return "", 0.0
    
    def _calculate_confidence_score(self, result: dict) -> float:
        """
        Whisper 결과에서 신뢰도 점수 계산 (개선된 알고리즘)
        """
        try:
            # segments가 있는 경우 사용
            if "segments" in result and result["segments"]:
                confidences = []
                total_duration = 0
                
                for segment in result["segments"]:
                    segment_duration = segment.get("end", 0) - segment.get("start", 0)
                    total_duration += segment_duration
                    
                    if "avg_logprob" in segment:
                        # log probability를 0-1 범위로 변환 (개선된 공식)
                        logprob = segment["avg_logprob"]
                        # -2.0 ~ 0.0 범위를 0.0 ~ 1.0으로 매핑
                        confidence = max(0.0, min(1.0, (logprob + 2.0) / 2.0))
                        
                        # 세그먼트 길이로 가중평균
                        confidences.append((confidence, segment_duration))
                    
                    # no_speech_prob 반영
                    if "no_speech_prob" in segment:
                        speech_confidence = 1.0 - segment["no_speech_prob"]
                        confidences.append((speech_confidence, segment_duration))
                
                if confidences and total_duration > 0:
                    # 가중평균 계산
                    weighted_sum = sum(conf * duration for conf, duration in confidences)
                    total_weight = sum(duration for _, duration in confidences)
                    return weighted_sum / total_weight if total_weight > 0 else 0.5
            
            # segments가 없는 경우 전체 결과에서 추정
            if "text" in result and result["text"].strip():
                # 텍스트 길이 기반 기본 신뢰도
                text_length = len(result["text"].strip())
                if text_length > 10:
                    return 0.7  # 긴 텍스트는 높은 신뢰도
                elif text_length > 5:
                    return 0.6  # 중간 길이
                else:
                    return 0.5  # 짧은 텍스트
            
            return 0.5  # 기본값
                
        except Exception as e:
            print(f"[WhisperSTT] 신뢰도 계산 오류: {e}")
            return 0.5

    def is_model_loaded(self) -> bool:
        """
        모델 로딩 상태 확인
        """
        return self.model is not None
    
    def get_model_info(self) -> dict:
        """
        현재 모델 정보 반환
        """
        gpu_info = ""
        if torch.cuda.is_available() and self.device == "cuda":
            allocated = torch.cuda.memory_allocated() / 1024**3
            cached = torch.cuda.memory_reserved() / 1024**3
            gpu_info = f" (GPU 메모리: {allocated:.2f}GB 할당, {cached:.2f}GB 캐시)"
        
        return {
            "model_name": self.model_name,
            "language": self.language,
            "device": self.device,
            "is_loaded": self.is_model_loaded(),
            "model_size": "~3GB" if "large" in self.model_name else "~1GB" if "medium" in self.model_name else "~150MB",
            "gpu_memory": gpu_info
        }
    
    def clear_gpu_memory(self):
        """
        GPU 메모리 정리
        """
        if self.device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
            print("[WhisperSTT] GPU 메모리 정리 완료")
    
    def reload_model(self, model_name: Optional[str] = None, device: Optional[str] = None):
        """
        모델 재로딩
        """
        if model_name:
            self.model_name = model_name
        if device:
            self.device = self._determine_device(device)
        
        # 기존 모델 정리
        if self.model is not None:
            del self.model
            self.model = None
        
        # GPU 메모리 정리
        self.clear_gpu_memory()
        
        # 새 모델 로딩
        self._setup_gpu_memory()
        self._load_model()

    def _validate_transcription_result(self, text: str) -> str:
        """
        환각 결과 검증 및 필터링 - 영어 전용 강화
        """
        if not text:
            return text
        
        import re
        
        # 1. 의미없는 반복 문자 제거 (~~, ..., ---, 등)
        if re.match(r'^[~\-_.!@#$%^&*()+=\[\]{}|\\:";\'<>?,./\s]*$', text):
            print(f"[WhisperSTT] 환각 감지: 의미없는 반복 문자 '{text}'")
            return ""
        
        # 2. 너무 짧은 텍스트 (1-2글자)
        if len(text.strip()) <= 2:
            print(f"[WhisperSTT] 환각 감지: 너무 짧은 텍스트 '{text}'")
            return ""
        
        # 3. 비영어 문자 완전 제거 (수정된 패턴)
        # 각 언어별로 개별 패턴 사용하여 범위 오류 방지
        korean_pattern = r'[가-힣]'
        chinese_pattern = r'[一-龯㐀-䶵豈-龎]'
        japanese_hiragana_pattern = r'[ひらがな]'
        japanese_katakana_pattern = r'[カタカナァ-ヾ]'
        fullwidth_pattern = r'[ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ]'
        special_brackets_pattern = r'[《》「」『』【】〈〉〔〕［］｛｝（）〖〗〘〙〚〛＜＞‹›«»""''‚„‛‟]'
        greek_pattern = r'[αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ]'
        cyrillic_pattern = r'[абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ]'
        
        # 각 패턴별로 개별 검사
        non_english_patterns = [
            korean_pattern, chinese_pattern, japanese_hiragana_pattern, 
            japanese_katakana_pattern, fullwidth_pattern, special_brackets_pattern,
            greek_pattern, cyrillic_pattern
        ]
        
        for pattern in non_english_patterns:
            if re.search(pattern, text):
                print(f"[WhisperSTT] 환각 감지: 비영어 문자 포함 '{text}'")
                return ""
        
        # 4. 특수 유니코드 문자 제거 (환각에서 자주 나타나는 문자들)
        unicode_hallucination_pattern = r'[^\x00-\x7F]'  # ASCII 범위 외 모든 문자
        if re.search(unicode_hallucination_pattern, text):
            print(f"[WhisperSTT] 환각 감지: 비ASCII 문자 포함 '{text}'")
            return ""
        
        # 5. 숫자만 있는 경우
        if re.match(r'^[\d\s]*$', text):
            print(f"[WhisperSTT] 환각 감지: 숫자만 포함 '{text}'")
            return ""
        
        # 6. 특수문자만 있는 경우
        if re.match(r'^[^\w\s]*$', text):
            print(f"[WhisperSTT] 환각 감지: 특수문자만 포함 '{text}'")
            return ""
        
        # 7. 의미없는 단어 반복
        words = text.split()
        if len(words) > 1:
            # 같은 단어가 3번 이상 반복
            for word in set(words):
                if words.count(word) >= 3:
                    print(f"[WhisperSTT] 환각 감지: 단어 반복 '{text}'")
                    return ""
        
        # 8. 알려진 환각 패턴들 (정규식)
        hallucination_patterns = [
            r'^[a-z]{1,2}$',  # 단일 알파벳
            r'^\s*$',         # 공백만
            r'^[.]{3,}$',     # 점만 반복
            r'^[-]{3,}$',     # 대시만 반복
            r'^[~]{2,}$',     # 틸드 반복
            r'^[*]{2,}$',     # 별표 반복
            r'^[#]{2,}$',     # 해시 반복
        ]
        
        for pattern in hallucination_patterns:
            if re.match(pattern, text):
                print(f"[WhisperSTT] 환각 감지: 패턴 매치 '{text}'")
                return ""
        
        # 9. Whisper 특정 환각 문구들 (대소문자 무관)
        whisper_hallucinations = [
            "no foreign languages",
            "no foreign language",
            "foreign languages",
            "foreign language",
            "thank you for watching",
            "thanks for watching", 
            "please subscribe",
            "like and subscribe",
            "don't forget to subscribe",
            "see you next time",
            "see you later",
            "goodbye",
            "bye bye",
            "music",
            "applause",
            "laughter",
            "silence",
            "inaudible",
            "unintelligible",
            "unclear",
            "background noise",
            "static",
            "beep",
            "beeping",
            "uh uh uh",
            "um um um",
            "ah ah ah",
            "oh oh oh",
            "hmm hmm",
            "mm mm",
            "you know",
            "i mean",
            "like you know",
            "so yeah",
            "okay okay",
            "alright alright",
            "test test",
            "testing testing",
            "hello hello",
            "can you hear me",
            "is this working",
            "one two three",
            "check check",
            "mic check"
        ]
        
        text_lower = text.lower().strip()
        for hallucination in whisper_hallucinations:
            if text_lower == hallucination or text_lower.startswith(hallucination + ".") or text_lower.startswith(hallucination + "?"):
                print(f"[WhisperSTT] 환각 감지: Whisper 특정 환각 문구 '{text}'")
                return ""
        
        # 10. 영어 단어 비율 체크 (간단한 영어 단어 사전)
        common_english_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
            'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'can', 'may', 'might', 'must',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
            'this', 'that', 'these', 'those', 'here', 'there', 'where', 'when', 'why', 'how',
            'falcon', 'runway', 'bird', 'check', 'status', 'risk', 'assessment', 'clear', 'request',
            'alpha', 'bravo', 'charlie', 'delta', 'echo', 'foxtrot', 'golf', 'hotel', 'india',
            'juliet', 'kilo', 'lima', 'mike', 'november', 'oscar', 'papa', 'quebec', 'romeo',
            'sierra', 'tango', 'uniform', 'victor', 'whiskey', 'xray', 'yankee', 'zulu'
        }
        
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        if words:
            english_word_count = sum(1 for word in words if word in common_english_words or len(word) >= 3)
            english_ratio = english_word_count / len(words)
            
            if english_ratio < 0.4:  # 영어 단어 비율을 40%로 상향 조정
                print(f"[WhisperSTT] 환각 감지: 영어 단어 비율 부족 '{text}' (비율: {english_ratio:.2f})")
                return ""
        
        print(f"[WhisperSTT] 유효한 텍스트 검증 통과: '{text}'")
        return text
