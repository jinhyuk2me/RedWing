# -*- coding: utf-8 -*-
"""
PDS TCN Configuration
TCN 기반 자세 검출 서버 설정 (Main Server와 완전 독립적)
"""

# 🎯 독립적 서버 설정 (Main Server와 무관)
SERVER_CONFIG = {
    'host': '0.0.0.0',           # 모든 인터페이스에서 접근 가능
    'port': 8001,                # PDS 전용 포트 (독립적)
    'redwing_host': 'localhost', # RedWing GUI Server 연결용
    'redwing_port': 8000,        # RedWing GUI Server 포트
    'max_clients': 5,
    'buffer_size': 4096,
    'encoding': 'utf-8',
    'delimiter': '\n',
    'independent_mode': True,     # Main Server와 완전 독립
    'auto_connect_redwing': True  # RedWing에 자동 연결
}

# TCN 모델 설정
TCN_CONFIG = {
    'input_size': 17 * 2,        # 17개 관절 x (x, y) 좌표
    'num_channels': [64, 64, 64, 64],  # TCN 채널 수
    'kernel_size': 3,
    'dropout': 0.2,
    'sequence_length': 30,       # 입력 시퀀스 길이 (프레임 수)
    'num_classes': 4             # 제스처 클래스 수
}

# 데이터 처리 설정
DATA_CONFIG = {
    'fps': 30,                   # 프레임 레이트
    'normalize': True,           # 데이터 정규화 여부
    'window_size': 30,           # 슬라이딩 윈도우 크기
    'stride': 5,                 # 윈도우 이동 간격
    'filter_confidence': 0.5,    # 관절 신뢰도 임계값
    'min_detection_confidence': 0.5,
    'min_tracking_confidence': 0.5
}

# MediaPipe 관절 설정 (33개 → 17개 주요 관절)
MEDIAPIPE_CONFIG = {
    'key_landmarks': [
        0,   # nose
        2,   # left_eye
        5,   # right_eye
        11,  # left_shoulder
        12,  # right_shoulder
        13,  # left_elbow
        14,  # right_elbow
        15,  # left_wrist
        16,  # right_wrist
        23,  # left_hip
        24,  # right_hip
        25,  # left_knee
        26,  # right_knee
        27,  # left_ankle
        28,  # right_ankle
        29,  # left_heel
        32   # right_heel
    ]
}

# 제스처 클래스 정의
GESTURE_CLASSES = {
    0: 'stop',
    1: 'forward', 
    2: 'left',
    3: 'right'
}

GESTURE_CLASSES_KR = {
    0: '정지',
    1: '전진',
    2: '좌회전',
    3: '우회전'
}

# 폴더명과 제스처 매핑
FOLDER_TO_GESTURE = {
    'stop': 0,
    'forward': 1,
    'left': 2,
    'right': 3
}

# TCP 통신용 제스처 이름 매핑 (대문자 변환)
TCP_GESTURE_NAMES = {
    'stop': 'STOP',
    'forward': 'MOVE_FORWARD',
    'left': 'TURN_LEFT', 
    'right': 'TURN_RIGHT'
}

# TTS 메시지 (RedWing이 처리하므로 참고용)
TTS_MESSAGES = {
    'stop': 'Stop',
    'forward': 'Move forward',
    'left': 'Turn left',
    'right': 'Turn right'
}

# 🎯 개선된 제스처 확신도 설정
IMPROVED_GESTURE_CONFIG = {
    'multi_window_sizes': [30, 45, 60, 90],  # 1초, 1.5초, 2초, 3초
    'smart_window_selection': True,
    'dynamic_threshold': {
        'high': 0.95,      # 높은 정확도 요구 시
        'medium': 0.85,    # 기본 설정
        'low': 0.75        # 빠른 응답 요구 시
    },
    'motion_completion_detection': True,
    'prediction_consistency_check': True,
    'consistency_threshold': 0.7,  # 70% 이상 일관성
    'confirmation_requirements': {
        'min_confirmations': 5,
        'completion_required': True,
        'cooldown_seconds': 3.0
    },
    'confidence_trend_analysis': True,
    'gesture_transition_detection': True,
    
    # 제스처별 최적 윈도우 크기
    'gesture_optimal_windows': {
        'stop': [45, 60],      # 정지: 중간 윈도우
        'forward': [60, 90],   # 전진: 긴 윈도우  
        'left': [30, 45],      # 좌회전: 짧은 윈도우
        'right': [30, 45]      # 우회전: 짧은 윈도우
    },
    
    # 일반적인 제스처 전환 패턴
    'common_transitions': {
        'stop_to_forward': ['stop', 'stop', 'forward', 'forward'],
        'left_to_stop': ['left', 'left', 'stop', 'stop'],
        'right_to_stop': ['right', 'right', 'stop', 'stop'],
        'forward_to_left': ['forward', 'forward', 'left', 'left'],
        'forward_to_right': ['forward', 'forward', 'right', 'right']
    },
    
    # 동적 신뢰도 임계값
    'dynamic_thresholds': {
        'early_stage': 0.95,    # 초기 단계 (< 0.5초)
        'mid_stage': 0.85,      # 중간 단계 (0.5-1.0초)
        'late_stage': 0.80,     # 후반 단계 (1.0-2.0초)
        'completion': 0.75      # 완료 단계 (> 2.0초)
    },
    
    # 동작 완료 판단 설정
    'min_motion_duration': 2.0,        # 최소 동작 지속시간 (초)
    'completion_stable_frames': 30,     # 완료 판단 안정 프레임 수
    'completion_motion_threshold': 0.005,  # 완료 판단 움직임 임계값
    'consistency_window_frames': 30,    # 일관성 분석 윈도우 (프레임)
    'confidence_gradient_min': 0.02,    # 최소 신뢰도 증가율
    'transition_detection': True,       # 전환 감지 활성화
}

# 🔧 네트워크 재시도 설정
NETWORK_CONFIG = {
    'redwing_connect_retries': 10,
    'redwing_connect_delay': 3.0,
    'heartbeat_interval': 30.0,
    'reconnect_on_failure': True,
    'connection_timeout': 10.0
}

def get_port_info():
    """포트 사용 정보 출력"""
    print("🎯 Independent PDS Server Configuration")
    print("=" * 50)
    print(f"🤚 PDS Server Port       : {SERVER_CONFIG['port']}")
    print(f"🖥️  RedWing GUI Server   : {SERVER_CONFIG['redwing_port']}")
    print("=" * 50)
    print("📊 서버 역할:")
    print("   - PDS Server: 제스처 인식, 카메라 처리 (Main Server와 완전 독립)")
    print("   - RedWing GUI Server: 클라이언트 연결 관리, 이벤트 수신")
    print("=" * 50)

# 모델 및 데이터 경로
PATHS = {
    'model_file': 'models/tcn_gesture_model.pth',
    'raw_data': '../pose_data_rotated',  # 회전된 데이터 사용
    'processed_data': '../processed_pose_data_rotated',  # 회전된 데이터용 새 처리 폴더
    'logs': 'logs'  # pds 폴더 기준 상대경로 (일관된 로그 위치 보장)
}

# 학습 설정
TRAINING_CONFIG = {
    'batch_size': 32,
    'learning_rate': 0.001,
    'epochs': 100,
    'train_test_split': 0.8,
    'early_stopping_patience': 15,
    'device': 'cuda',  # 'cuda' or 'cpu'
    'num_workers': 4
}

# 🎬 데모 영상 모드 설정
DEMO_VIDEO_CONFIG = {
    'enabled': True,                    # 데모 모드 활성화
    'data_path': '../pose_data',        # 영상 데이터 경로
    'videos_per_gesture': 2,            # 각 제스처당 영상 수
    'gesture_order': ['forward', 'left', 'right', 'stop'],  # 재생 순서
    'video_selection': 'random',        # 'random' 또는 'sequential'
    'loop_demo': True,                  # 데모 반복 여부
    'gesture_change_delay': 0.5,        # 제스처 변경시 대기 시간(초)
}

# 로깅 설정
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'log_file': 'logs/pds.log'
} 