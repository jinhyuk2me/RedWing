import json
import time
import re
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

class ResponseProcessor:
    """
    메인 서버 응답 처리 및 자연어 응답 생성
    Confluence 문서 기준 RESPONSE_TYPE 테이블 사용
    """
    
    def __init__(self):
        """응답 처리기 초기화 - Confluence 문서 기준 표준 응답 테이블 로드"""
        
        # Confluence 문서 기준 표준 응답 테이블 (RESPONSE_TYPE)
        self.standard_responses = {
            # 조류 위험도 응답 - Confluence 문서 기준
            "BIRD_RISK_HIGH": "WARNING. Bird risk high. Advise extreme vigilance.",
            "BIRD_RISK_MEDIUM": "CAUTION. Bird activity reported near runway threshold.",
            "BIRD_RISK_LOW": "Runway CLEAR of bird activity currently.",
            
            # 활주로 상태 응답 - Confluence 문서 기준
            "RWY_A_CLEAR": "Runway Alpha is clear. Cleared for operations.",
            "RWY_A_BLOCKED": "Runway Alpha is blocked. Expect delay.",
            "RWY_B_CLEAR": "Runway Bravo is clear. Cleared for operations.",
            "RWY_B_BLOCKED": "Runway Bravo is blocked. Hold position.",
            
            # TCP 프로토콜 기준 활주로 상태 응답 (WARNING 추가)
            "RWY_A_WARNING": "WARNING. Runway Alpha advisory. Proceed with vigilance.",
            "RWY_B_WARNING": "WARNING. Runway Bravo advisory. Proceed with vigilance.",
            
            # 사용 가능한 활주로 목록 응답 - Confluence 문서 기준
            "AVAILABLE_RUNWAYS_ALL": "Available runways Alpha, Bravo.",
            "AVAILABLE_RUNWAYS_A_ONLY": "Runway Alpha available.",
            "AVAILABLE_RUNWAYS_B_ONLY": "Runway Bravo available.",
            "NO_RUNWAYS_AVAILABLE": "No runways available. Hold for approach.",
            
            # TCP 프로토콜 기준 가용 활주로 응답 (간소화된 형태)
            "ALL_RUNWAYS_AVAILABLE": "Available runways Alpha, Bravo.",
            "RUNWAY_ALPHA_ONLY": "Runway Alpha available.",
            "RUNWAY_BRAVO_ONLY": "Runway Bravo available.",
            
            # 오류 응답
            "UNRECOGNIZED_COMMAND": "Unable to process request. Say again.",
            "TIMEOUT": "Communication timeout. Try again.",
            "NO_DATA_AVAILABLE": "No data available. Contact tower.",
            "INVALID_AREA": "Invalid area specified. Contact tower.",
            "PARTIAL_RESPONSE": "Partial data received. Contact tower."
        }
        
        # Confluence 문서 기준 응답 코드 설명
        self.response_descriptions = {
            "BIRD_RISK_HIGH": "조류 위험도 높음 - 착륙 대기 필요",
            "BIRD_RISK_MEDIUM": "조류 위험도 보통 - 주의 필요",
            "BIRD_RISK_LOW": "조류 위험도 낮음 - 진행 가능",
            "RWY_A_CLEAR": "활주로 알파 사용 가능",
            "RWY_A_BLOCKED": "활주로 알파 차단됨",
            "RWY_A_WARNING": "활주로 알파 주의 필요",
            "RWY_B_CLEAR": "활주로 브라보 사용 가능", 
            "RWY_B_BLOCKED": "활주로 브라보 차단됨",
            "RWY_B_WARNING": "활주로 브라보 주의 필요",
            "AVAILABLE_RUNWAYS_ALL": "모든 활주로 사용 가능",
            "AVAILABLE_RUNWAYS_A_ONLY": "활주로 알파만 사용 가능",
            "AVAILABLE_RUNWAYS_B_ONLY": "활주로 브라보만 사용 가능",
            "NO_RUNWAYS_AVAILABLE": "사용 가능한 활주로 없음",
            "ALL_RUNWAYS_AVAILABLE": "모든 활주로 사용 가능",
            "RUNWAY_ALPHA_ONLY": "활주로 알파만 사용 가능",
            "RUNWAY_BRAVO_ONLY": "활주로 브라보만 사용 가능"
        }
        
        print(f"[ResponseProcessor] Confluence 문서 기준 응답 테이블 로드 완료 ({len(self.standard_responses)}개)")
        
    def _convert_aviation_numbers(self, text: str) -> str:
        """
        항공 통신 표준에 맞게 숫자를 변환
        예: "123" → "one two three"
        """
        # 숫자를 개별 자릿수로 변환하는 매핑
        number_map = {
            '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
            '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'
        }
        
        # 연속된 숫자를 찾아서 변환
        def replace_numbers(match):
            number = match.group()
            return ' '.join([number_map[digit] for digit in number])
        
        # 2자리 이상의 숫자를 개별 자릿수로 변환
        text = re.sub(r'\b\d{2,}\b', replace_numbers, text)
        
        return text
    
    def process_response(self, response_data: Dict[str, Any], original_request: Dict[str, Any]) -> Tuple[bool, str]:
        """
        메인 서버 응답을 처리하여 표준 자연어 응답 생성 (TCP 프로토콜 지원)
        
        Args:
            response_data: 메인 서버 응답 데이터 (TCP 또는 Confluence 문서 형식)
            original_request: 원본 요청 정보 (콜사인 등)
            
        Returns:
            (성공 여부, 자연어 응답 텍스트) 튜플
        """
        try:
            # 1. 기본 정보 추출
            callsign = original_request.get("callsign", "Aircraft")
            
            print(f"[ResponseProcessor] 🆔 원본 콜사인: '{callsign}'")
            print(f"[ResponseProcessor] 📋 전체 original_request: {original_request}")
            
            # 2. TCP 프로토콜 응답 처리 (type=response, command 있음, status 없음)
            if (response_data.get("type") == "response" and 
                "command" in response_data and 
                "result" in response_data):
                
                command = response_data.get("command")
                result = response_data.get("result")
                
                print(f"[ResponseProcessor] 🔌 TCP 응답 처리: {command} = {result}")
                
                # TCP 결과를 표준 응답 코드로 변환
                response_code = self._convert_tcp_result_to_response_code(command, result)
                
                print(f"[ResponseProcessor] 🔄 TCP → 표준 변환: {result} → {response_code}")
                
                return self._generate_standard_response(response_code, callsign, {})
            
            # 3. Confluence 문서 기준 오류 응답 처리
            elif response_data.get("status") == "error":
                response_code = response_data.get("response_code", "UNRECOGNIZED_COMMAND")
                return self._generate_standard_response(response_code, callsign, {})
            
            # 4. Confluence 문서 기준 정상 응답 처리
            elif response_data.get("type") == "response" and response_data.get("status") == "success":
                response_code = response_data.get("response_code", "UNRECOGNIZED_COMMAND")
                
                print(f"[ResponseProcessor] 🎯 Confluence 표준 응답 처리: {response_code}")
                
                return self._generate_standard_response(response_code, callsign, {})
            
            else:
                # 예상하지 못한 응답 형식
                print(f"[ResponseProcessor] ⚠️ 예상하지 못한 응답 형식: {response_data}")
                return self._generate_standard_response("UNRECOGNIZED_COMMAND", callsign, {})
                
        except Exception as e:
            print(f"[ResponseProcessor] ❌ 응답 처리 오류: {e}")
            callsign = original_request.get("callsign", "Aircraft")
            return self._generate_standard_response("TIMEOUT", callsign, {})
    
    def _generate_standard_response(self, response_code: str, callsign: str, result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Confluence 문서 기준 표준 응답 코드를 사용하여 자연어 응답 생성
        
        Args:
            response_code: 표준 응답 코드 (Confluence 문서 기준)
            callsign: 항공기 콜사인
            result: 추가 데이터 (현재 사용하지 않음)
            
        Returns:
            (성공 여부, 자연어 응답 텍스트) 튜플
        """
        # 표준 응답 텍스트 조회
        if response_code in self.standard_responses:
            base_response = self.standard_responses[response_code]
            success = True
        else:
            print(f"[ResponseProcessor] ⚠️ 알 수 없는 응답 코드: {response_code}")
            base_response = self.standard_responses["UNRECOGNIZED_COMMAND"]
            success = False
        
        # 🔧 콜사인 유효성 검증 및 처리
        valid_callsign = self._validate_callsign(callsign)
        
        # 유효한 콜사인이 있으면 포함, 없으면 콜사인 없이 응답
        if valid_callsign:
            final_response = f"{valid_callsign}, {base_response}"
            print(f"[ResponseProcessor] ✅ 유효한 콜사인 사용: '{valid_callsign}'")
        else:
            final_response = base_response
            print(f"[ResponseProcessor] 🚫 콜사인 제외하고 응답: 원본 '{callsign}' → 콜사인 없음")
        
        # 항공 통신 표준에 맞게 숫자 변환 (123 → one two three)
        final_response = self._convert_aviation_numbers(final_response)
        
        print(f"[ResponseProcessor] ✅ 최종 응답: '{final_response}'")
        return success, final_response
    
    def _validate_callsign(self, callsign: str) -> Optional[str]:
        """
        콜사인 유효성 검증
        
        Args:
            callsign: 검증할 콜사인
            
        Returns:
            유효한 콜사인 또는 None (무효한 경우)
        """
        if not callsign or not callsign.strip():
            return None
        
        # 기본적으로 제외할 콜사인들
        invalid_callsigns = {
            "UNKNOWN", "Unknown", "unknown", 
            "Aircraft", "aircraft", "AIRCRAFT",
            "NULL", "null", "None", "none",
            "ERROR", "error"
        }
        
        if callsign in invalid_callsigns:
            return None
        
        # 🔧 비정상적인 콜사인 패턴 검증
        # 1. 너무 짧거나 긴 콜사인 제외
        if len(callsign.replace(" ", "")) < 2 or len(callsign) > 20:
            print(f"[ResponseProcessor] ❌ 콜사인 길이 비정상: '{callsign}' (길이: {len(callsign)})")
            return None
        
        # 2. 숫자만 있는 콜사인 제외 (예: "1", "12", "123")
        if callsign.replace(" ", "").isdigit():
            print(f"[ResponseProcessor] ❌ 숫자만 있는 콜사인: '{callsign}'")
            return None
        
        # 3. 특수문자만 있거나 이상한 패턴 제외
        import re
        if not re.match(r'^[A-Za-z0-9\s\-]+$', callsign):
            print(f"[ResponseProcessor] ❌ 특수문자 포함 콜사인: '{callsign}'")
            return None
        
        # 4. STT 오인식으로 의심되는 패턴들 제외
        suspicious_patterns = [
            r'^[A-Z]{1,2}\s*\d{1,2}$',  # "A 1", "AB 12" 같은 너무 간단한 패턴
            r'^\d+\s*[A-Z]{1,2}$',      # "1 A", "12 AB" 같은 패턴
            r'^Con\s*\d{1,2}$',         # "Con 1", "Con 12" (STT 오인식)
            r'^[A-Z]\s*\d{1,2}$'        # "A 1", "B 2" 같은 단일 문자 패턴
        ]
        
        for pattern in suspicious_patterns:
            if re.match(pattern, callsign.strip(), re.IGNORECASE):
                print(f"[ResponseProcessor] ❌ 의심스러운 콜사인 패턴: '{callsign}' (패턴: {pattern})")
                return None
        
        # 5. 유효한 콜사인으로 판단됨
        return callsign.strip()
    
    def _handle_error_response(self, response_data: Dict[str, Any], callsign: str) -> Tuple[bool, str]:
        """오류 응답 처리 - Confluence 문서 기준"""
        error_type = response_data.get("error", "unknown")
        
        # 오류 타입을 표준 응답 코드로 매핑
        error_mapping = {
            "timeout": "TIMEOUT",
            "connection_failed": "NO_DATA_AVAILABLE", 
            "unknown_intent": "UNRECOGNIZED_COMMAND",
            "invalid_area": "INVALID_AREA",
            "partial_data": "PARTIAL_RESPONSE"
        }
        
        response_code = error_mapping.get(error_type, "UNRECOGNIZED_COMMAND")
        print(f"[ResponseProcessor] 🚨 오류 응답: {error_type} → {response_code}")
        
        return self._generate_standard_response(response_code, callsign, {})
    
    def create_tts_request(self, response_text: str, session_id: str) -> Dict[str, Any]:
        """
        TTS 요청 페이로드 생성
        
        Args:
            response_text: 음성으로 변환할 텍스트
            session_id: 세션 ID
            
        Returns:
            TTS 요청 페이로드
        """
        tts_request = {
            "type": "command",
            "command": "synthesize_speech",
            "text": response_text,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "voice_settings": {
                "language": "en",
                "speed": 1.0,
                "pitch": 1.0,
                "volume": 0.8
            }
        }
        
        print(f"[ResponseProcessor] TTS 요청 생성: '{response_text[:50]}...'")
        return tts_request
    
    def validate_response_data(self, response_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Confluence 문서 기준 응답 데이터 유효성 검증
        
        Args:
            response_data: 검증할 응답 데이터
            
        Returns:
            (유효성, 오류 메시지) 튜플
        """
        # 1. 기본 구조 확인
        if not isinstance(response_data, dict):
            return False, "응답 데이터가 딕셔너리가 아닙니다"
        
        # 2. 필수 필드 확인
        if "type" not in response_data:
            return False, "응답 타입이 없습니다"
        
        if "status" not in response_data:
            return False, "상태 필드가 없습니다"
        
        # 3. 오류 응답인 경우
        if response_data.get("status") == "error":
            if "response_code" not in response_data:
                return False, "오류 응답 코드가 없습니다"
            return True, "오류 응답 (정상 처리 가능)"
        
        # 4. 정상 응답인 경우
        if response_data.get("type") == "response" and response_data.get("status") == "success":
            if "response_code" not in response_data:
                return False, "응답 코드가 없습니다"
            
            if "intent" not in response_data:
                return False, "인텐트가 없습니다"
        
        return True, "유효한 응답 데이터"
    
    def get_response_summary(self, response_data: Dict[str, Any]) -> str:
        """
        응답 데이터 요약 정보 반환 (Confluence 문서 기준)
        
        Args:
            response_data: 응답 데이터
            
        Returns:
            요약 문자열
        """
        if response_data.get("status") == "error":
            return f"오류: {response_data.get('response_code', 'unknown')}"
        
        if response_data.get("type") == "response" and response_data.get("status") == "success":
            intent = response_data.get("intent", "unknown")
            response_code = response_data.get("response_code", "unknown")
            
            return f"{intent}: {response_code}"
        
        return "알 수 없는 응답 형식"
    
    def _convert_tcp_result_to_response_code(self, command: str, result: str) -> str:
        """
        TCP 결과를 표준 응답 코드로 변환 (TCP 프로토콜 명세 기준)
        
        Args:
            command: TCP 명령어 (BR_INQ, RWY_A_STATUS, RWY_B_STATUS, RWY_AVAIL_INQ)
            result: TCP 결과
            
        Returns:
            표준 응답 코드
        """
        # TCP 프로토콜 명세 기준 매핑
        tcp_mapping = {
            # 조류 위험도 조회 (BR_INQ)
            "BR_INQ": {
                "BR_HIGH": "BIRD_RISK_HIGH",
                "BR_MEDIUM": "BIRD_RISK_MEDIUM", 
                "BR_LOW": "BIRD_RISK_LOW"
            },
            # 활주로 A 상태 조회 (RWY_A_STATUS) - BLOCKED/WARNING 모두 WARNING으로 처리
            "RWY_A_STATUS": {
                "CLEAR": "RWY_A_CLEAR",
                "WARNING": "RWY_A_WARNING",  # WARNING으로 통일
                "BLOCKED": "RWY_A_WARNING"   # BLOCKED도 WARNING으로 처리
            },
            # 활주로 B 상태 조회 (RWY_B_STATUS) - BLOCKED/WARNING 모두 WARNING으로 처리
            "RWY_B_STATUS": {
                "CLEAR": "RWY_B_CLEAR", 
                "WARNING": "RWY_B_WARNING",  # WARNING으로 통일
                "BLOCKED": "RWY_B_WARNING"   # BLOCKED도 WARNING으로 처리
            },
            # 사용 가능한 활주로 조회 (RWY_AVAIL_INQ)
            "RWY_AVAIL_INQ": {
                "ALL": "AVAILABLE_RUNWAYS_ALL",
                "A_ONLY": "AVAILABLE_RUNWAYS_A_ONLY",
                "B_ONLY": "AVAILABLE_RUNWAYS_B_ONLY",
                "NONE": "NO_RUNWAYS_AVAILABLE"
            }
        }
        
        # 명령어별 결과 매핑 확인
        if command in tcp_mapping and result in tcp_mapping[command]:
            return tcp_mapping[command][result]
        
        # 매핑되지 않은 경우 기본값
        print(f"[ResponseProcessor] ⚠️ TCP 매핑 실패: {command} - {result}")
        return "UNRECOGNIZED_COMMAND"
    