# -*- coding: utf-8 -*-
"""
RedWing System Port Configuration
포트 충돌 방지를 위한 시스템 포트 설정
"""

# 🎯 최적화된 포트 구조
REDWING_PORTS = {
    # RedWing GUI Server (클라이언트들이 연결)
    'GUI_SERVER': 8000,
    
    # PDS 제스처 인식 서버 (완전 독립적)
    'PDS_SERVER': 8001,
    
    # 기존 Main Server (변경 없음)
    'MAIN_SERVER': 5300,  # tcp_server_sim.py
    
    # 개발/테스트용 예비 포트들
    'DEVELOPMENT': {
        'TEST_CLIENT': 8002,
        'DEBUG_SERVER': 8003,
        'MONITOR_TOOL': 8004
    }
}

# 🌐 네트워크 설정
NETWORK_CONFIG = {
    'HOST': 'localhost',
    'FALLBACK_HOST': '127.0.0.1',
    'BUFFER_SIZE': 4096,
    'TIMEOUT': 10.0,
    'MAX_CLIENTS': 10,
    'RECONNECT_DELAY': 5.0,
    'MAX_RETRIES': 5
}

# 📡 통신 프로토콜 설정
PROTOCOL_CONFIG = {
    'ENCODING': 'utf-8',
    'DELIMITER': '\n',
    'MESSAGE_FORMAT': 'json',
    'HEARTBEAT_INTERVAL': 30.0,
    'KEEP_ALIVE': True
}

# 🎮 PDS 독립적 설정
PDS_CONFIG = {
    'HOST': NETWORK_CONFIG['HOST'],
    'PORT': REDWING_PORTS['PDS_SERVER'],
    'REDWING_HOST': NETWORK_CONFIG['HOST'],
    'REDWING_PORT': REDWING_PORTS['GUI_SERVER'],
    'INDEPENDENT_MODE': True,  # Main Server와 무관
    'AUTO_CONNECT_REDWING': True
}

# 🖥️ RedWing GUI Server 설정
GUI_SERVER_CONFIG = {
    'HOST': '0.0.0.0',  # 모든 인터페이스에서 접근 가능
    'PORT': REDWING_PORTS['GUI_SERVER'],
    'MAIN_SERVER_HOST': NETWORK_CONFIG['HOST'],
    'MAIN_SERVER_PORT': REDWING_PORTS['MAIN_SERVER'],
    'PDS_SERVER_HOST': NETWORK_CONFIG['HOST'],
    'PDS_SERVER_PORT': REDWING_PORTS['PDS_SERVER']
}

def get_port_info():
    """포트 사용 정보 출력"""
    print("🎯 RedWing System Port Configuration")
    print("=" * 50)
    print(f"🖥️  RedWing GUI Server    : {REDWING_PORTS['GUI_SERVER']}")
    print(f"🤚 PDS Gesture Server    : {REDWING_PORTS['PDS_SERVER']}")
    print(f"✈️  Main Server (기존)    : {REDWING_PORTS['MAIN_SERVER']}")
    print("=" * 50)
    print("📊 서버별 역할:")
    print("   - GUI Server: 클라이언트 연결 관리, 이벤트 브로드캐스트")
    print("   - PDS Server: 제스처 인식, 카메라 처리 (완전 독립적)")
    print("   - Main Server: 항공 데이터, 활주로/조류 정보 (기존 유지)")
    print("=" * 50)

if __name__ == "__main__":
    get_port_info() 