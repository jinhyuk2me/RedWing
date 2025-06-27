# 모델들은 별도로 import 가능
from .voice_models import VoiceInteraction, AudioData, STTResult, SystemStatus

# 메인 컨트롤러는 필요할 때만 import (의존성 때문에)
def get_voice_controller():
    """VoiceInteractionController를 지연 로딩"""
    from .main_controller import VoiceInteractionController, create_voice_controller
    return VoiceInteractionController, create_voice_controller

__all__ = [
    'VoiceInteraction',
    'AudioData', 
    'STTResult',
    'SystemStatus',
    'get_voice_controller'
] 