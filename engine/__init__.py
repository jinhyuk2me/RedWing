"""
음성 처리 엔진 패키지

이 패키지는 STT(Speech-to-Text)와 TTS(Text-to-Speech) 엔진을 포함합니다.
"""

from .stt_engine import WhisperSTTEngine
from .tts_engine import UnifiedTTSEngine, create_tts_engine

# 편의를 위한 별칭
STTEngine = WhisperSTTEngine
TTSEngine = UnifiedTTSEngine

__all__ = [
    'WhisperSTTEngine',
    'UnifiedTTSEngine', 
    'create_tts_engine',
    'STTEngine',
    'TTSEngine'
] 