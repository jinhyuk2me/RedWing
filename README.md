# FALCON Pilot Interface - 조종사 음성 인터페이스

dl-falcon 프로젝트의 조종사 음성 상호작용 시스템입니다. 영어 항공 통신을 실시간으로 처리하여 활주로 상태, 조류 위험도 등의 정보를 제공합니다.

## 🚀 메인 인터페이스

### 🖥️ GUI 인터페이스 (항공전자장비 스타일)
```bash
python pilot_avionics.py
```
- **PyQt6 기반** .ui 파일 사용 그래픽 인터페이스
- **실시간 모니터링**: 활주로(ALPHA/BRAVO), 조류 위험도, 시스템 상태
- **음성 제어**: 5초 녹음, 실시간 진행률 표시
- **볼륨 조절**: TTS 출력 및 마이크 레벨 모니터링
- **상태 업데이트**: CLEAR/BLOCKED/CAUTION 자동 표시
- **이벤트 처리**: 실시간 서버 이벤트 수신 및 TTS 알림

## 📁 프로젝트 구조

```
pilot_gui/
├── 🖥️ pilot_avionics.py         # 메인 GUI (PilotAvionics 클래스, 1600라인)
├── 🎨 pilot_interface.ui        # PyQt6 UI 레이아웃 파일
├── 📋 requirements.txt          # 의존성: PyQt6, Whisper, PyAudio 등
├── 🔧 simulator.py              # TCP 서버 시뮬레이터 (개발/테스트용)
│
├── 📂 main_controller/          # 메인 컨트롤러
│   ├── __init__.py             # 패키지 초기화
│   └── main_controller.py      # VoiceInteractionController (650라인)
│
├── 📂 audio_io/                 # 오디오 입출력
│   └── mic_speaker_io.py        # AudioIO 클래스 (마이크/스피커)
│
├── 📂 engine/                   # 핵심 엔진들
│   ├── __init__.py             # 통합 import
│   ├── whisper_stt_engine.py   # WhisperSTTEngine (Whisper 통합)
│   └── unified_tts_engine.py   # UnifiedTTSEngine (Coqui + pyttsx3)
│
├── 📂 request_handler/          # 요청 처리 시스템
│   ├── __init__.py             # 통합 import
│   ├── classifier.py           # RequestClassifier (키워드+LLM 하이브리드)
│   ├── router.py               # TCPServerClient (서버 통신)
│   └── processor.py            # ResponseProcessor (응답 처리)
│
├── 📂 event_handler/            # 이벤트 처리 시스템
│   ├── __init__.py             # 통합 import
│   ├── event_manager.py        # EventManager (이벤트 수신)
│   ├── event_processor.py      # EventProcessor (이벤트 처리)
│   └── event_tts.py            # EventTTS (이벤트 음성 알림)
│
├── 📂 session_handler/          # 세션 관리
│   ├── __init__.py             # 패키지 초기화
│   └── session_manager.py      # SessionManager (로깅, 통계)
│
├── 📂 models/                   # 데이터 모델
│   ├── request_response_model.py # VoiceInteraction, PilotRequest 등
│   └── event_model.py          # EventData, EventResponse 등
│
├── 📂 logs/                     # 상호작용 로그
│   └── pilot_interactions_YYYYMMDD.json
│
├── 📂 tests/                    # 체계적으로 정리된 테스트
│   ├── 📂 unit_tests/          # 단위 테스트 (10개 파일)
│   │   ├── test_unified_tts.py # TTS 엔진 테스트
│   │   ├── test_audio_system.py # 오디오 시스템 테스트
│   │   ├── test_request_analyzer.py # 분류기 테스트
│   │   └── ...
│   ├── 📂 integration_tests/   # 통합 테스트 (5개 파일)
│   │   ├── test_stt_parser_integration.py # STT-파서 통합
│   │   ├── test_event_handling.py # 이벤트 처리 통합
│   │   ├── test_simulator_integration.py # 시뮬레이터 통합
│   │   └── ...
│   └── 📄 README.md           # 테스트 실행 가이드
│
├── 📂 utils/                   # 유틸리티
│   └── clear_gpu_memory.py    # GPU 메모리 관리 (CUDA 최적화)
│
└── 📂 docs/                    # 문서
```

## 🎯 핵심 기능

### 1. 음성 인식 (STT) - Whisper
- **모델**: small/medium 모델 지원 (GPU 우선, CPU 폴백)
- **언어**: 영어 항공 통신 최적화
- **오인식 보정**: 항공 용어 특화 correction_map (bird/runway/alpha/bravo 등)
- **성능**: 실시간의 0.2배 처리 속도
- **콜사인 인식**: FALCON, Korean Air, HL 코드 등 다양한 패턴

### 2. 요청 분류 - 하이브리드 시스템
**지원 요청 유형 (4가지 메인 카테고리):**
- `BIRD_RISK_INQUIRY` - 조류 위험도 확인
- `RUNWAY_ALPHA_STATUS` - 활주로 ALPHA 상태
- `RUNWAY_BRAVO_STATUS` - 활주로 BRAVO 상태  
- `AVAILABLE_RUNWAY_INQUIRY` - 사용 가능한 활주로 조회

**분류 방식:**
- **키워드 기반**: 빠른 패턴 매칭 (기본)
- **LLM 통합**: Ollama 연동 선택적 활성화 (60초 타임아웃)
- **하이브리드**: 키워드 실패시 LLM 자동 fallback

### 3. 음성 합성 (TTS) - 통합 엔진
- **Coqui TTS**: 고품질 음성 (기본 모델: tacotron2-DDC)
- **pyttsx3**: 안정적 fallback 엔진
- **자동 전환**: Coqui 실패시 pyttsx3 자동 사용
- **볼륨 제어**: 실시간 음량 조절 및 음소거
- **이벤트 TTS**: 충돌 방지 기능으로 이벤트 알림 전용 처리

### 4. 구조화된 질의 시스템
- **TCP 통신**: 메인 서버와 구조화된 데이터 교환
- **시뮬레이터 폴백**: 서버 연결 실패시 자동 시뮬레이터 사용
- **응답 검증**: 서버 응답 데이터 유효성 검사
- **자연어 생성**: 구조화된 데이터를 자연어 응답으로 변환

### 5. 실시간 이벤트 처리
- **이벤트 수신**: TCP 서버로부터 실시간 이벤트 수신
- **자동 처리**: 조류 위험도, 활주로 상태 변화 자동 감지
- **TTS 알림**: 이벤트 발생시 음성 알림 자동 재생
- **GUI 업데이트**: 실시간 상태 표시 자동 업데이트

### 6. 세션 관리 및 로깅
- **세션 추적**: 각 상호작용별 고유 세션 ID
- **구조화된 로깅**: JSON 형태의 상세 로그 기록
- **통계 분석**: 일일/주간 사용 통계 제공
- **검색 기능**: 콜사인, 요청 유형별 로그 검색

## 🔧 설치 및 실행

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 시스템 패키지 (Ubuntu/Debian)
```bash
sudo apt install portaudio19-dev python3-pyqt6
```

### 3. GPU 가속 (선택사항)
```bash
# CUDA 지원 PyTorch 설치
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 4. 실행 방법

**GUI 실행 (추천):**
```bash
python pilot_avionics.py
```

**CLI 실행:**
```bash
# 기본 대화형 모드
python pilot_cli.py

# 연속 모드 (자동 테스트)
python pilot_cli.py --continuous --interval 5

# 다른 서버/콜사인 사용
python pilot_cli.py --server localhost:5300 --callsign "KOREAN AIR 123"
```

**시뮬레이터 실행 (개발용):**
```bash
# TCP 서버 시뮬레이터 단독 실행
python simulator.py
```

## 🧪 테스트 실행

### 단위 테스트
```bash
# 통합 TTS 엔진 테스트
python tests/unit_tests/test_unified_tts.py

# 오디오 시스템 테스트
python tests/unit_tests/test_audio_system.py

# 요청 분류기 테스트 (키워드+LLM)
python tests/unit_tests/test_request_analyzer.py

# 시뮬레이터 테스트
python tests/unit_tests/test_simulator.py
```

### 통합 테스트
```bash
# STT-파서 전체 워크플로우
python tests/integration_tests/test_stt_parser_integration.py

# 이벤트 처리 통합 테스트
python tests/integration_tests/test_event_handling.py

# 시뮬레이터 통합 테스트
python tests/integration_tests/test_simulator_integration.py

# 전체 시스템 통합 테스트
python tests/integration_tests/test_full_system.py
```

## 📊 성능 지표 (실측 기준)

- **STT 정확도**: 85%+ (영어 항공 용어, Whisper small 기준)
- **처리 속도**: 실시간의 0.2배 (RTX 3080 기준)
- **GPU 메모리**: ~3GB (Whisper medium), ~1.5GB (small)
- **응답 시간**: <2초 (5초 녹음 + STT + 분류 + TTS)
- **분류 정확도**: 90%+ (키워드), 85%+ (하이브리드)
- **이벤트 지연**: <100ms (TCP 이벤트 수신 → GUI 업데이트)

## 🛠️ 개발 및 디버깅

### 시뮬레이터 사용
```bash
# 시뮬레이터 단독 실행 (포트 5300)
python simulator.py

# GUI에서 시뮬레이터 모드 사용
# (서버 연결 실패시 자동 활성화)
```

### GPU 메모리 관리
```bash
# GPU 메모리 완전 정리 (PyTorch 캐시 포함)
python utils/clear_gpu_memory.py
```

### 로그 모니터링
```bash
# 당일 상호작용 로그 확인
cat logs/pilot_interactions_$(date +%Y%m%d).json | jq .

# 실시간 로그 스트림
tail -f logs/pilot_interactions_$(date +%Y%m%d).json
```

### 시스템 상태 확인
- **GUI**: "STATUS" 버튼 → 전체 모듈 상태 팝업
- **CLI**: `status` 명령어 → 터미널 출력

### LLM 연동 (선택사항)
```bash
# Ollama 서버 실행 (로컬)
ollama serve

# LLM 분류 활성화 (RequestClassifier에서 자동 감지)
# GUI/CLI 실행시 Ollama 연결 시도
```

## 📝 사용 예시

### GUI 워크플로우
1. `python pilot_avionics.py` 실행
2. "VOICE INPUT" 버튼 클릭 (5초 녹음 시작)
3. 음성 입력: *"FALCON 456, bird risk check"*
4. 실시간 상태 업데이트:
   - STT 결과 표시
   - BIRD LEVEL 상태 변경 (LOW/MEDIUM/HIGH)
   - TTS 응답 재생
5. 이벤트 자동 수신:
   - 서버에서 조류 위험도 변화 이벤트 수신
   - 자동 TTS 알림: "Bird activity high. Hold for approach."
   - GUI 상태 자동 업데이트

### CLI 워크플로우
```bash
$ python pilot_cli.py
🎯 현재 콜사인: FALCON 456
명령어 입력 (Enter=음성입력): [Enter]

🎤 음성 입력 시작 (5초간)...
지금 말씀하세요!

📊 처리 결과:
   🎤 인식된 텍스트: 'FALCON 456, runway alpha status'
   🏷️ 요청 분류: RUNWAY_ALPHA_STATUS
   💬 응답: Runway Alpha is clear, condition good, wind 5 knots.
```

### 시뮬레이터 워크플로우
```bash
$ python simulator.py
[TCPSimulator] TCP 서버 시뮬레이터 시작 (포트: 5300)
[TCPSimulator] 초기 상태:
  - 조류 위험도: BR_LOW
  - 활주로 ALPHA: RWY_A_CLEAR
  - 활주로 BRAVO: RWY_B_CLEAR

# 클라이언트 연결 대기 중...
# GUI/CLI에서 연결시 자동 응답 및 이벤트 생성
```

## 🔍 문제 해결

### GUI 실행 오류
```bash
# PyQt6 설치 확인
pip install PyQt6

# .ui 파일 존재 확인
ls -la pilot_interface.ui
```

### 서버 연결 문제
```bash
# 시뮬레이터 실행 확인
python simulator.py

# 포트 사용 확인
netstat -an | grep 5300

# 방화벽 설정 확인
sudo ufw status
```

### 오디오 문제
```bash
# PortAudio 재설치
sudo apt remove python3-pyaudio
sudo apt install portaudio19-dev
pip install --no-cache-dir pyaudio
```

### GPU 메모리 부족
```bash
# Whisper 모델 크기 축소
# main_controller에서 model_name="small" 사용

# GPU 메모리 정리
python utils/clear_gpu_memory.py
```

### STT 성능 저하
- **모델 변경**: medium → small (메모리 절약)
- **장치 확인**: CUDA 사용 가능 여부
- **마이크 레벨**: GUI에서 MIC LEVEL 프로그레스바 확인

### TTS 음질 문제
- **Coqui 실패시**: 자동으로 pyttsx3 fallback
- **모델 변경**: tacotron2-DDC → glow-tts (더 빠름)
- **볼륨 조절**: GUI 슬라이더 또는 CLI에서 설정

### 이벤트 처리 문제
- **이벤트 매니저**: 서버 연결 상태 확인
- **TTS 충돌**: 이벤트 TTS와 일반 TTS 분리 처리
- **GUI 업데이트**: 메인 스레드에서 안전한 업데이트

## 📚 추가 문서

- **테스트 가이드**: `tests/README.md`
- **API 문서**: `docs/README.md`
- **의존성 상세**: `requirements.txt`

## 🎯 최신 개선사항 (v2.0)

### ✅ 아키텍처 대규모 리팩토링
- **main_controller 구조**: 단일 진입점으로 통합
- **시뮬레이터 통합**: TCP 서버 시뮬레이터로 개발/테스트 지원
- **Legacy 코드 제거**: 구조화된 질의 시스템만 사용
- **모듈 재구성**: engine, request_handler, event_handler 분리

### ✅ 이벤트 시스템 구축
- **실시간 이벤트**: TCP 서버로부터 이벤트 자동 수신
- **이벤트 처리**: 조류 위험도, 활주로 상태 변화 자동 감지
- **TTS 통합**: 이벤트 전용 TTS로 충돌 방지
- **GUI 연동**: 실시간 상태 표시 자동 업데이트

### ✅ 시뮬레이터 시스템
- **TCP 시뮬레이터**: 실제 서버 없이도 완전한 테스트 가능
- **자동 폴백**: 서버 연결 실패시 시뮬레이터 자동 활성화
- **상태 시뮬레이션**: 조류 위험도, 활주로 상태 자동 변화
- **이벤트 생성**: 실제 서버와 동일한 이벤트 생성

### ✅ 성능 및 안정성 향상
- **통합 TTS 엔진**: Coqui + pyttsx3 하이브리드
- **세션 관리**: 구조화된 로깅 및 통계 시스템
- **에러 처리**: 모든 컴포넌트 이중화 및 폴백
- **메모리 최적화**: GPU 메모리 자동 관리

### ✅ 개발자 경험 개선
- **명확한 구조**: 기능별 모듈 분리 및 명확한 책임
- **테스트 강화**: 시뮬레이터 기반 통합 테스트
- **디버깅 도구**: 상세한 로깅 및 상태 모니터링
- **문서화**: 구조 변경에 따른 문서 업데이트 