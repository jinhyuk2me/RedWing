import json
import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from queue import Queue, Empty

# 통합된 TCP 클라이언트 사용
from network import TCPClient
from simulator import TCPSimulator

class TCPServerClient:
    """
    기존 ServerClient와 호환되는 TCP 기반 서버 클라이언트
    """
    
    def __init__(self, server_host: str = "localhost", server_port: int = 5300, use_simulator: bool = True):
        """
        TCP 서버 클라이언트 초기화
        
        Args:
            server_host: 서버 호스트
            server_port: 서버 포트
            use_simulator: 연결 실패 시 시뮬레이터 사용 여부
        """
        self.tcp_client = TCPClient(server_host, server_port)
        self.use_simulator = use_simulator
        self.server_available = False
        
        # 로컬 시뮬레이터 (폴백용)
        if use_simulator:
            self.simulator = TCPSimulator()
        else:
            self.simulator = None
        
        # 서버 연결 시도
        self._check_server_availability()
        
        print(f"[TCPServerClient] 초기화 완료: {server_host}:{server_port}")
    
    def _check_server_availability(self):
        """서버 연결 상태 확인"""
        self.server_available = self.tcp_client.connect()
        
        if self.server_available:
            print(f"[TCPServerClient] ✅ TCP 서버 사용")
        elif self.use_simulator:
            print(f"[TCPServerClient] 🔄 시뮬레이터로 폴백")
        else:
            print(f"[TCPServerClient] ❌ 서버 사용 불가")
    
    def send_query(self, request_code: str, parameters: Dict[str, Any], session_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        질의 전송 (기존 ServerClient와 호환)
        
        Args:
            request_code: 요청 코드
            parameters: 요청 파라미터 (TCP에서는 사용하지 않음)
            session_id: 세션 ID (TCP에서는 사용하지 않음)
            
        Returns:
            (성공 여부, 응답 데이터) 튜플
        """
        # 1. TCP 서버 시도
        if self.server_available:
            success, result = self.tcp_client.send_command(request_code)
            if success:
                # TCP 응답을 기존 형태로 변환
                converted_result = self._convert_tcp_response(result, request_code)
                return True, converted_result
            else:
                print(f"[TCPServerClient] TCP 서버 실패, 폴백 시도...")
                self.server_available = False
        
        # 2. 시뮬레이터 폴백
        if self.use_simulator and self.simulator:
            intent = self._get_intent_from_request_code(request_code)
            structured_params = self._structure_parameters(request_code, parameters)
            
            simulator_result = self.simulator.process_query(intent, structured_params)
            simulator_result["session_id"] = session_id
            simulator_result["source"] = "simulator"
            
            print(f"[TCPServerClient] 🔄 시뮬레이터 응답 생성")
            return True, simulator_result
        
        # 3. 모든 방법 실패
        return False, {
            "error": "all_servers_failed",
            "message": "TCP 서버와 시뮬레이터 모두 사용할 수 없습니다."
        }
    
    def _convert_tcp_response(self, tcp_response: Dict[str, Any], request_code: str) -> Dict[str, Any]:
        """
        TCP 응답을 기존 HTTP 응답 형태로 변환
        
        Args:
            tcp_response: TCP 서버 응답
            request_code: 원본 요청 코드
            
        Returns:
            변환된 응답 데이터
        """
        result = tcp_response.get("result", "UNKNOWN")
        
        # TCP 결과를 기존 응답 코드로 매핑 (TCP 프로토콜 스펙 기준)
        response_code_mapping = {
            # 조류 위험도
            "BR_HIGH": "BIRD_RISK_HIGH",
            "BR_MEDIUM": "BIRD_RISK_MEDIUM", 
            "BR_LOW": "BIRD_RISK_LOW",
            
            # 활주로 알파 상태 (TCP 스펙: CLEAR/WARNING)
            "CLEAR": "RWY_A_CLEAR",
            "WARNING": "RWY_A_WARNING",
            "BLOCKED": "RWY_A_BLOCKED",
            
            # 활주로 브라보 상태 (TCP 스펙: CLEAR/WARNING)  
            "RWY_B_CLEAR": "RUNWAY_BRAVO_CLEAR",
            "RWY_B_BLOCKED": "RUNWAY_BRAVO_BLOCKED",
            
            # 가용 활주로 (TCP 스펙: ALL/A_ONLY/B_ONLY/NONE)
            "ALL": "ALL_RUNWAYS_AVAILABLE",
            "A_ONLY": "RUNWAY_ALPHA_ONLY",
            "B_ONLY": "RUNWAY_BRAVO_ONLY",
            "NONE": "NO_RUNWAYS_AVAILABLE"
        }
        
        # 활주로 상태는 요청 코드에 따라 다르게 처리 (BLOCKED/WARNING 모두 WARNING으로 통일)
        if request_code == "RUNWAY_ALPHA_STATUS":
            if result == "CLEAR":
                response_code = "RWY_A_CLEAR"
            elif result in ["WARNING", "BLOCKED"]:
                response_code = "RWY_A_WARNING"  # BLOCKED도 WARNING으로 처리
            else:
                response_code = response_code_mapping.get(result, result)
        elif request_code == "RUNWAY_BRAVO_STATUS":
            if result == "CLEAR":
                response_code = "RWY_B_CLEAR"
            elif result in ["WARNING", "BLOCKED"]:
                response_code = "RWY_B_WARNING"  # BLOCKED도 WARNING으로 처리
            else:
                response_code = response_code_mapping.get(result, result)
        else:
            response_code = response_code_mapping.get(result, result)
        
        return {
            "type": "response",
            "status": "success",
            "intent": self._get_intent_from_request_code(request_code),
            "response_code": response_code,
            "source": "tcp_server",
            "original_tcp_result": result
        }
    
    def _get_intent_from_request_code(self, request_code: str) -> str:
        """요청 코드를 인텐트로 변환"""
        intent_mapping = {
            "BIRD_RISK_INQUIRY": "bird_risk_inquiry",
            "RUNWAY_ALPHA_STATUS": "runway_alpha_status",
            "RUNWAY_BRAVO_STATUS": "runway_bravo_status", 
            "AVAILABLE_RUNWAY_INQUIRY": "available_runway_inquiry"
        }
        return intent_mapping.get(request_code, "unknown_request")
    
    def _structure_parameters(self, request_code: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """파라미터 구조화 (모의 서버용)"""
        structured = {}
        
        # 공통 파라미터
        if "callsign" in parameters:
            structured["callsign"] = parameters["callsign"]
        if "original_text" in parameters:
            structured["original_text"] = parameters["original_text"]
        
        return structured
    
    def test_connection(self) -> bool:
        """연결 테스트"""
        return self.tcp_client.is_connected()
    
    def get_server_status(self) -> Dict[str, Any]:
        """서버 상태 조회"""
        return self.tcp_client.get_server_status()
    
    def shutdown(self):
        """클라이언트 종료"""
        self.tcp_client.disconnect()