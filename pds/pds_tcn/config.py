# -*- coding: utf-8 -*-
"""
PDS TCN Configuration
TCN 기반 자세 검출 서버 설정
"""

# 서버 설정
SERVER_CONFIG = {
    'redwing_host': '127.0.0.1',  # RedWing 서버 주소
    'command_port': 5301,         # RedWing → PDS 명령 수신 포트
    'event_port': 5300,          # PDS → RedWing 이벤트 송신 포트
    'max_clients': 5,
    'buffer_size': 4096,
    'encoding': 'utf-8',
    'delimiter': '\n'
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

# TTS 메시지 (TCP 통신용 대문자 매핑)
TCP_GESTURE_NAMES = {
    'stop': 'STOP',
    'forward': 'MOVE_FORWARD',
    'left': 'TURN_LEFT',
    'right': 'TURN_RIGHT'
}

TTS_MESSAGES = {
    'STOP': 'Stop',
    'MOVE_FORWARD': 'Move forward',
    'TURN_LEFT': 'Turn left',
    'TURN_RIGHT': 'Turn right',
    'MARSHALING_ACTIVATED': 'Marshaling recognition activated',
    'MARSHALING_DEACTIVATED': 'Marshaling recognition deactivated'
}

# 모델 및 데이터 경로
PATHS = {
    'model_file': 'models/tcn_gesture_model.pth',
    'raw_data': '../pose_data',
    'processed_data': '../processed_pose_data', 
    'logs': 'logs'
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

# 로깅 설정
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'log_file': 'logs/pds_tcn.log'
}

# 개선된 제스처 인식 설정
IMPROVED_GESTURE_CONFIG = {
    'min_motion_duration': 1.2,        # 최소 동작 지속시간 (초)
    'completion_stable_frames': 20,     # 완료 판단 안정 프레임 수
    'completion_motion_threshold': 0.005,  # 완료 판단 움직임 임계값
    'consistency_threshold': 0.8,       # 일관성 임계값
    'consistency_window_frames': 30,    # 일관성 분석 윈도우 (프레임)
    'confidence_gradient_min': 0.02,    # 최소 신뢰도 증가율
    'transition_detection': True,       # 전환 감지 활성화
    'smart_window_selection': True,     # 스마트 윈도우 선택
    
    # 동적 신뢰도 임계값
    'dynamic_thresholds': {
        'early_stage': 0.95,    # 초기 단계 (< 0.5초)
        'mid_stage': 0.85,      # 중간 단계 (0.5-1.0초)
        'late_stage': 0.80,     # 후반 단계 (1.0-2.0초)
        'completion': 0.75      # 완료 단계 (> 2.0초)
    },
    
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
    }
} 