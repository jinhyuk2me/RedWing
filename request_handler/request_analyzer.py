import re
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass

@dataclass
class RequestPattern:
    """요청 패턴 정의"""
    request_code: str
    keywords: List[str]
    patterns: List[str]
    description: str

class RequestClassifier:
    def __init__(self):
        """
        영어 항공 통신 요청 분류기 초기화 (4개 카테고리 지원)
        키워드 기반 분류가 기본값 (LLM은 선택적 활성화)
        """
        # LLM 기본 설정 - 60초 타임아웃으로 안정적 사용
        self.llm_enabled = False
        self.use_llm_by_default = True  # LLM을 더 적극 활용
        self.llm_timeout = 60  # 60초 타임아웃
        
        # STT 오인식 보정 맵 (항공 용어 특화)
        self.correction_map = {
            # bird 관련 오인식
            "bolt": "bird",
            "board": "bird", 
            "both": "bird",
            "birth": "bird",
            "bert": "bird",
            "burt": "bird",
            "world": "bird",  # world → bird 오인식 보정
            "birds": "birds",
            "bolts": "birds",
            "boards": "birds",
            
            # runway 관련 오인식
            "run way": "runway",
            "runaway": "runway",
            "run-way": "runway",
            "runway": "runway",
            "running": "runway",           # running → runway 오인식 보정
            "runnyalpha": "runway alpha",  # 새로운 오인식 패턴
            "runnybravo": "runway bravo",  # 예상되는 유사 패턴
            "runny": "runway",  # 부분 오인식
            
            # alpha 관련 오인식
            "alfa": "alpha",
            "alpa": "alpha",
            "alpha": "alpha",
            
            # bravo 관련 오인식
            "bravo": "bravo",
            "brabo": "bravo",
            "breva": "bravo",
            
            # activity 관련 오인식
            "activity": "activity",
            "activities": "activity",
            "acticity": "activity",
            "activty": "activity",
            
            # status 관련 오인식
            "status": "status",
            "states": "status",
            "statue": "status",
            "state": "status",
            
            # Korean Air 관련 오인식 추가
            "airwad": "air",  # Korean Airwad → Korean Air
            "airway": "air",  # Korean Airway → Korean Air
            "airways": "air", # Korean Airways → Korean Air
            
            # check 관련 오인식
            "check": "check",
            "chuck": "check",
            "cheque": "check",
            "chek": "check",
            
            # report 관련 오인식
            "report": "report",
            "reprot": "report",
            "repo": "report",
            
            # assessment 관련 오인식
            "assessment": "assessment",
            "assessement": "assessment",
            "assesment": "assessment",
            "asessment": "assessment",
            
            # available 관련 오인식
            "available": "available",
            "availabe": "available",
            "availible": "available",
            "avialable": "available",
            
            # FALCON 관련 오인식 (기존 유지)
            "balcony": "falcon",
            "balcon": "falcon",
            "falkon": "falcon",
            "falco": "falcon",
            "pack": "falcon",
            "packet": "falcon",
            "packing": "falcon"
        }
        
        # 영어 항공 통신 키워드 매핑 (4가지 요청)
        self.request_patterns = {
            "BIRD_RISK_INQUIRY": [
                "bird", "birds", "wildlife", "bird strike", "bird risk", "bird hazard",
                "bird activity", "wildlife report", "bird check", "bird assessment",
                "bird situation", "bird status", "avian", "bird warning", "wildlife hazard"
            ],
            "RUNWAY_ALPHA_STATUS": [
                "runway alpha", "runway a", "alpha runway", "rwy alpha", "rwy a",
                "runway alpha status", "runway alpha condition", "runway alpha check",
                "alpha status", "alpha condition", "alpha hazard", "alpha assessment"
            ],
            "RUNWAY_BRAVO_STATUS": [
                "runway bravo", "runway b", "bravo runway", "rwy bravo", "rwy b",
                "runway bravo status", "runway bravo condition", "runway bravo check",
                "bravo status", "bravo condition", "bravo hazard", "bravo assessment"
            ],
            "AVAILABLE_RUNWAY_INQUIRY": [
                "available runway", "runway available", "active runway", "which runway",
                "runway availability", "available runway information", "runway status",
                "runway condition", "runway clear", "runway inspection", "runway report",
                "runway check", "runway state", "runway situation", "runway info",
                "runway please", "status please", "condition please"  # 일반적인 요청 패턴 추가
            ]
        }
        
        # 콜사인 패턴 (영어) - 🆕 우선순위 재정렬 (구체적인 패턴을 먼저!)
        self.callsign_patterns = [
            r'\b(FALCON)\s*([\d\-]{1,10}[A-Z]?)\b',     # FALCON 123 (최우선)
            # 🆕 2단어 항공사명 패턴을 더 정확하게 - Korean Air, Asiana Airlines 등
            r'\b(Korean\s+Air)\s+([\d\-]{1,10}[A-Z]?)\b',  # Korean Air 1-2-3 (최우선!)
            r'\b(Asiana\s+Airlines?)\s+([\d\-]{1,10}[A-Z]?)\b',  # Asiana Airlines 7-8-9
            r'\b(Hotel\s+Lima)\s+([\d\-]{1,10}[A-Z]?)\b',  # 🆕 Hotel Lima 23 (HL 콜사인)
            r'\b(China\s+Eastern|Air\s+France|British\s+Airways)\s+([\d\-]{1,10}[A-Z]?)\b',  # 기타 2단어 항공사
            r'\b(KAL|AAR|ASIANA|KOREAN)\s*([\d\-]{1,10}[A-Z]?)\b',  # 주요 항공사 코드
            r'\b(PACK\s+ON)\s*([\d\-]{1,10}[A-Z]?)\b',  # Pack on 456 패턴 추가
            r'\b(HL)([\d\-]{1,10})\b',                  # HL90233 패턴 (한국 민간 항공기)
            # 🆕 혼합 대소문자 패턴을 대문자 패턴보다 먼저! (더 구체적이므로)
            r'\b([A-Z][a-z]+[a-z]*)\s+([\d\-]{1,10}[A-Z]?)\b',  # Hotelima 123, Stator 34 등 (우선 매칭!)
            r'\b([A-Z]{2,6})\s+([\d\-]{1,10}[A-Z]?)\b', # 공백 있는 일반 콜사인 (대문자만) - 후순위
            r'\b([A-Z]{2,6})([\d\-]{1,10}[A-Z]?)\b'     # 공백 없는 일반 콜사인 (HL90233 등) - 최후순위
        ]
        
        # 활주로 패턴 (영어) - Alpha/Bravo 포함
        self.runway_patterns = [
            r'\brunway\s*(alpha|a)\b',
            r'\brunway\s*(bravo|b)\b',
            r'\brwy\s*(alpha|a)\b',
            r'\brwy\s*(bravo|b)\b',
            r'\b(alpha|bravo)\s*runway\b',
            r'\b(alpha|bravo)\s*rwy\b',
            r'\brunway\s*(\d{1,2}[LRC]?)\b',
            r'\brwy\s*(\d{1,2}[LRC]?)\b',
            r'\b(\d{1,2}[LRC]?)\s*runway\b',
            r'\b(\d{1,2}[LRC]?)\s*rwy\b'
        ]
    
    def _correct_stt_errors(self, text: str) -> str:
        """
        STT 오인식 보정 함수
        
        Args:
            text: 원본 STT 텍스트
            
        Returns:
            보정된 텍스트
        """
        corrected_text = text.lower()
        original_text = corrected_text
        
        # 단어별 보정 적용
        words = corrected_text.split()
        corrected_words = []
        
        for word in words:
            # 구두점 제거 후 보정
            clean_word = re.sub(r'[^\w]', '', word)
            if clean_word in self.correction_map:
                corrected_word = self.correction_map[clean_word]
                # 원래 구두점 유지
                if word != clean_word:
                    punctuation = word.replace(clean_word, '')
                    corrected_word += punctuation
                corrected_words.append(corrected_word)
                print(f"[RequestClassifier] 오인식 보정: '{clean_word}' → '{self.correction_map[clean_word]}'")
            else:
                corrected_words.append(word)
        
        corrected_text = ' '.join(corrected_words)
        
        # 구문 단위 보정 (더 복잡한 오인식 패턴)
        phrase_corrections = {
            r'\bbolt\s+activity\b': 'bird activity',
            r'\bboard\s+activity\b': 'bird activity',
            r'\bboth\s+activity\b': 'bird activity',
            r'\brun\s+way\b': 'runway',
            r'\balfa\s+runway\b': 'alpha runway',
            r'\brunway\s+alfa\b': 'runway alpha',
            r'\bbrabo\s+runway\b': 'bravo runway',
            r'\brunway\s+brabo\b': 'runway bravo',
            r'\brunnyalpha\b': 'runway alpha',  # runnyalpha → runway alpha
            r'\brunnybravo\b': 'runway bravo',  # runnybravo → runway bravo
            r'\brunny\s+alpha\b': 'runway alpha',  # runny alpha → runway alpha
            r'\brunny\s+bravo\b': 'runway bravo',   # runny bravo → runway bravo
            # running 관련 보정
            r'\brunning\s+status\b': 'runway status',    # running status → runway status
            r'\brunning\s+condition\b': 'runway condition',  # running condition → runway condition
            r'\brunning\s+check\b': 'runway check',      # running check → runway check
            # 🆕 Korean Air 오인식 보정 추가
            r'\bkorean\s+airwad\b': 'korean air',        # Korean Airwad → Korean Air
            r'\bkorean\s+airway\b': 'korean air',        # Korean Airway → Korean Air  
            r'\bkorean\s+airways\b': 'korean air',       # Korean Airways → Korean Air
            r'\bkorean\s+airline\b': 'korean air',       # Korean Airline → Korean Air
            # 🆕 HL 콜사인 오인식 보정 (Hotel Lima)
            r'\bhotel\s+name\s+is\s+(\d+)\b': r'HL\1',  # Hotel name is 90233 → HL90233
            r'\bhotel\s+lima\s+(\d+)\b': r'HL\1',       # Hotel Lima 90233 → HL90233
            r'\bhotel\s+(\d+)\b': r'HL\1',              # Hotel 90233 → HL90233
            # 🆕 Hotelimao STT 오인식 보정 (가장 빈번한 패턴)
            r'\bhotelimao\s+(\d+)\b': r'hotel lima \1',  # Hotelimao 23 → hotel lima 23
            r'\bhotelima\s+(\d+)\b': r'hotel lima \1',   # Hotelima 23 → hotel lima 23 (부분 오인식)
            r'\bhotelimao\b': 'hotel lima',              # Hotelimao → hotel lima (숫자 없는 경우)
            # FALCON 콜사인 보정 패턴들
            r'\bpack\s+on\s+(\d+)\b': r'falcon \1',  # Pack on 789 → FALCON 789
            r'\bpark\s+on\s+(\d+)\b': r'falcon \1',  # Park on 789 → FALCON 789 (STT 오인식)
            r'\bfalcon\s+on\s+(\d+)\b': r'falcon \1',  # falcon on 789 → FALCON 789 (단어 보정 후)
            r'\bpacking\s+(\d+)\b': r'falcon \1',    # Packing 789 → FALCON 789
            r'\bpacket\s+(\d+)\b': r'falcon \1',     # Packet 789 → FALCON 789
            r'\bbalcony\s+(\d+)\b': r'falcon \1',    # Balcony 789 → FALCON 789
            r'\bfalco\s+(\d+)\b': r'falcon \1',       # Falco 789 → FALCON 789
            # 🆕 쉼표로 구분된 콜사인 숫자 보정 (Korean Air 1, 2, 3 → Korean Air 123)
            r'\b(korean\s+air|falcon|kal|asiana|hl)\s+(\d+),?\s*(\d+),?\s*(\d+)\b': r'\1 \2\3\4',  # 3자리
            r'\b(korean\s+air|falcon|kal|asiana|hl)\s+(\d+),?\s*(\d+)\b': r'\1 \2\3',  # 2자리
            # 🆕 일반적인 쉼표 구분 숫자도 처리
            r'\b(\d+),\s*(\d+),\s*(\d+)\b': r'\1\2\3',  # 1, 2, 3 → 123
            r'\b(\d+),\s*(\d+)\b': r'\1\2'  # 1, 2 → 12
        }
        
        for pattern, replacement in phrase_corrections.items():
            if re.search(pattern, corrected_text):
                old_text = corrected_text
                corrected_text = re.sub(pattern, replacement, corrected_text)
                if old_text != corrected_text:
                    print(f"[RequestClassifier] 구문 보정: '{pattern}' → '{replacement}'")
        
        if original_text != corrected_text:
            print(f"[RequestClassifier] 전체 보정 결과:")
            print(f"  원본: '{text}'")
            print(f"  보정: '{corrected_text}'")
        
        return corrected_text
    
    def classify(self, query_text: str, session_id: str = "") -> Tuple[str, Dict]:
        """
        영어 항공 통신 텍스트를 분류 (4개 카테고리)
        
        Args:
            query_text: 분류할 영어 텍스트
            session_id: 세션 ID
            
        Returns:
            (request_code, parameters) 튜플
        """
        if not query_text or not query_text.strip():
            return "UNKNOWN_REQUEST", {"error": "Empty request"}
        
        print(f"[RequestClassifier] Classifying request: '{query_text}' (Session: {session_id})")
        
        # 1. STT 오인식 보정
        corrected_text = self._correct_stt_errors(query_text)
        query_lower = corrected_text.lower().strip()
        
        # 콜사인 추출 (보정된 텍스트 우선, 실패시 원본 텍스트)
        callsign = self._extract_callsign(corrected_text)
        if not callsign:
            callsign = self._extract_callsign(query_text)
        
        # 🆕 콜사인이 애매하거나 없으면 그냥 "Aircraft"로 통일
        if not callsign or callsign == "UNKNOWN":
            callsign = "Aircraft"
        
        # 활주로 정보 추출 (보정된 텍스트에서)
        runway_info = self._extract_runway_info(corrected_text)
        
        # 패턴 매칭으로 요청 유형 분류 (보정된 텍스트 사용)
        best_match = None
        best_score = 0
        
        for request_code, keywords in self.request_patterns.items():
            # 키워드 매칭 점수 계산
            keyword_matches = sum(1 for keyword in keywords if keyword in query_lower)
            
            # 구문 매칭 (더 정확한 매칭)
            phrase_matches = 0
            for keyword in keywords:
                if len(keyword.split()) > 1:  # 구문인 경우
                    if keyword in query_lower:
                        phrase_matches += 3  # 구문 매칭에 높은 점수
                
            total_score = keyword_matches + phrase_matches
            
            # 특정 키워드 보너스 (4가지 요청에 최적화)
            if request_code == "BIRD_RISK_INQUIRY" and "bird" in query_lower:
                total_score += 3
                if "risk" in query_lower or "hazard" in query_lower or "assessment" in query_lower:
                    total_score += 2
            elif request_code == "RUNWAY_ALPHA_STATUS" and ("alpha" in query_lower or " a " in query_lower):
                total_score += 3
                if "runway" in query_lower:
                    total_score += 2
                if "status" in query_lower or "condition" in query_lower or "check" in query_lower:
                    total_score += 2
            elif request_code == "RUNWAY_BRAVO_STATUS" and ("bravo" in query_lower or " b " in query_lower):
                total_score += 3
                if "runway" in query_lower:
                    total_score += 2
                if "status" in query_lower or "condition" in query_lower or "check" in query_lower:
                    total_score += 2
            elif request_code == "AVAILABLE_RUNWAY_INQUIRY" and "runway" in query_lower:
                total_score += 2
                if "available" in query_lower or "which" in query_lower or "active" in query_lower:
                    total_score += 3
                if "availability" in query_lower or "information" in query_lower:
                    total_score += 2
            
            # 최고 점수 업데이트
            if total_score > best_score:
                best_score = total_score
                best_match = request_code
        
        # 최소 점수 임계값 확인
        if best_match and best_score >= 1:
            parameters = {
                "original_text": query_text,
                "corrected_text": corrected_text if corrected_text != query_text.lower() else None,
                "confidence_score": best_score,
                "matched_keywords": [kw for kw in self.request_patterns[best_match] if kw in query_lower]
            }
            
            # 콜사인 추가 (항상 "Aircraft" 또는 실제 콜사인)
            parameters["callsign"] = callsign
            
            # 활주로 정보 추가
            if runway_info:
                parameters["runway"] = runway_info
            
            print(f"[RequestClassifier] Classification result: {best_match} (Score: {best_score})")
            return best_match, parameters
        
        # 🆕 요청 내용이 있지만 점수가 낮은 경우 또는 콜사인만 있는 경우 기본 활주로 문의로 처리
        if best_score == 0:
            # 콜사인이 있거나 요청 내용이 있으면 기본 활주로 문의로 처리
            has_callsign = callsign and callsign != "Aircraft"
            has_content = len(query_lower.split()) >= 2
            
            if has_callsign or has_content:
                reason = "콜사인만 있어서" if has_callsign and not has_content else "요청 내용이 있지만 명확하지 않아서"
                print(f"[RequestClassifier] {reason} 기본 활주로 상태 문의로 처리")
                return "AVAILABLE_RUNWAY_INQUIRY", {
                    "original_text": query_text,
                    "corrected_text": corrected_text if corrected_text != query_text.lower() else None,
                    "callsign": callsign,
                    "runway": runway_info,
                    "confidence_score": 0.3,  # 낮은 신뢰도
                    "default_classification": True,
                    "reasoning": f"{reason} 기본 활주로 상태 문의로 분류"
                }
        
        # 매칭되지 않은 경우
        print(f"[RequestClassifier] Unknown request: '{query_text}' (Best score: {best_score})")
        return "UNKNOWN_REQUEST", {
            "original_text": query_text,
            "corrected_text": corrected_text if corrected_text != query_text.lower() else None,
            "callsign": callsign,
            "runway": runway_info,
            "best_score": best_score
        }
    
    def _extract_callsign(self, text: str) -> Optional[str]:
        """
        텍스트에서 콜사인 추출 - 🆕 여러 콜사인이 있을 때 가장 먼저 나타나는 것 선택
        """
        print(f"[RequestClassifier] 콜사인 추출 시도: '{text}'")
        
        # 🆕 STT 할루시네이션 의심 단어들 (Whisper가 자주 만들어내는 가짜 콜사인)
        hallucination_callsigns = {
            'STATOR', 'ROTOR', 'MOTOR', 'FACTOR', 'ACTOR', 'VECTOR', 
            'ALPHA', 'BRAVO', 'CHARLIE', 'DELTA', 'ECHO', 'FOXTROT',
            'GOLF', 'INDIA', 'JULIET', 'KILO', 
            'MIKE', 'NOVEMBER', 'OSCAR', 'PAPA', 'QUEBEC', 'ROMEO',
            'SIERRA', 'TANGO', 'UNIFORM', 'VICTOR', 'WHISKEY', 'XRAY', 'YANKEE', 'ZULU'
        }
        
        # 🆕 모든 패턴에서 매칭되는 콜사인들을 수집하고 위치별로 정렬
        callsign_candidates = []
        
        for i, pattern in enumerate(self.callsign_patterns):
            # 🆕 대소문자 구분 없이 매칭 (Korean Air → korean air 문제 해결)
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                # 매칭 위치와 콜사인 정보 저장
                start_pos = match.start()
                
                if len(match.groups()) >= 2:
                    airline = match.group(1)
                    number = match.group(2)
                    
                    # 🆕 STT 할루시네이션 필터링 (대소문자 무시)
                    if airline.upper() in hallucination_callsigns:
                        print(f"[RequestClassifier] 🚫 STT 할루시네이션 의심: '{airline} {number}' - 건너뜀")
                        continue
                    
                    # 🆕 하이픈이 포함된 숫자 정리 (1-2-3 → 123)
                    clean_number = number.replace('-', '') if '-' in number else number
                    
                    # 🆕 표준화된 형태로 변환 (키워드 분류와 일관성 유지)
                    if airline.upper() == "KOREAN AIR":
                        callsign = f"Korean Air {clean_number}"
                    elif airline.upper() == "ASIANA" or airline.upper() == "ASIANA AIRLINES":
                        callsign = f"Asiana Airlines {clean_number}"
                    elif airline.upper() == "HOTEL LIMA":
                        callsign = f"Hotel Lima {clean_number}"
                    elif airline.upper() == "FALCON":
                        callsign = f"Falcon {clean_number}"
                    elif airline.upper() == "PACK ON":
                        callsign = f"Falcon {clean_number}"
                    else:
                        callsign = f"{airline.title()} {clean_number}"
                else:
                    airline = match.group(1)
                    
                    # 🆕 STT 할루시네이션 필터링 (대소문자 무시)
                    if airline.upper() in hallucination_callsigns:
                        print(f"[RequestClassifier] 🚫 STT 할루시네이션 의심: '{airline}' - 건너뜀")
                        continue
                    
                    # 🆕 표준화된 형태로 변환 (키워드 분류와 일관성 유지)
                    if airline.upper() == "KOREAN AIR":
                        callsign = "Korean Air"
                    elif airline.upper() == "ASIANA" or airline.upper() == "ASIANA AIRLINES":
                        callsign = "Asiana Airlines"
                    elif airline.upper() == "HOTEL LIMA":
                        callsign = "Hotel Lima"
                    elif airline.upper() == "FALCON":
                        callsign = "Falcon"
                    elif airline.upper() == "PACK ON":
                        callsign = "Falcon"
                    else:
                        callsign = airline.title()
                
                callsign_candidates.append((start_pos, callsign, i, pattern))
                print(f"[RequestClassifier] 후보 발견: 위치 {start_pos}, 콜사인 '{callsign}', 패턴 {i}")
        
        if not callsign_candidates:
            print(f"[RequestClassifier] ❌ 콜사인 추출 실패: 패턴 매칭 안됨")
            return None
        
        # 🆕 위치가 가장 앞선 콜사인 선택 (먼저 나타나는 것 우선)
        callsign_candidates.sort(key=lambda x: x[0])  # 위치별 정렬
        
        selected = callsign_candidates[0]
        start_pos, callsign, pattern_idx, pattern = selected
        
        print(f"[RequestClassifier] ✅ 첫 번째 콜사인 선택: 위치 {start_pos}, '{callsign}', 패턴 {pattern_idx}")
        
        # 🆕 다른 후보들도 로그로 출력
        if len(callsign_candidates) > 1:
            print(f"[RequestClassifier] 다른 후보들:")
            for pos, cs, idx, pat in callsign_candidates[1:]:
                print(f"  위치 {pos}: '{cs}' (패턴 {idx}) - 건너뜀")
        
        return callsign
    
    def _extract_runway_info(self, text: str) -> Optional[str]:
        """
        텍스트에서 활주로 정보 추출 (Alpha/Bravo 포함)
        """
        for pattern in self.runway_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                runway_id = match.group(1).upper()
                if runway_id in ['ALPHA', 'A']:
                    return "RWY ALPHA"
                elif runway_id in ['BRAVO', 'B']:
                    return "RWY BRAVO"
                else:
                    return f"RWY {runway_id}"
        
        return None
    
    def get_supported_requests(self) -> List[Dict]:
        """
        지원하는 요청 유형 목록 반환 (4가지)
        """
        return [
            {
                "code": "BIRD_RISK_INQUIRY",
                "description": "조류 위험도 문의",
                "keywords": self.request_patterns["BIRD_RISK_INQUIRY"],
                "example": "FALCON 123, bird risk assessment"
            },
            {
                "code": "RUNWAY_ALPHA_STATUS", 
                "description": "런웨이 A 위험도 문의",
                "keywords": self.request_patterns["RUNWAY_ALPHA_STATUS"],
                "example": "FALCON 456, runway Alpha status check"
            },
            {
                "code": "RUNWAY_BRAVO_STATUS", 
                "description": "런웨이 B 위험도 문의",
                "keywords": self.request_patterns["RUNWAY_BRAVO_STATUS"],
                "example": "FALCON 789, runway Bravo status check"
            },
            {
                "code": "AVAILABLE_RUNWAY_INQUIRY", 
                "description": "사용 가능한 런웨이 문의",
                "keywords": self.request_patterns["AVAILABLE_RUNWAY_INQUIRY"],
                "example": "FALCON 321, available runway status"
            }
        ]
    
    def get_classification_stats(self) -> Dict:
        """
        분류기 통계 정보 반환
        """
        total_keywords = sum(len(keywords) for keywords in self.request_patterns.values())
        return {
            "supported_requests": len(self.request_patterns),
            "total_keywords": total_keywords,
            "request_types": list(self.request_patterns.keys())
        }

    # ========== LLM 기반 분류 기능 추가 ==========
    
    def enable_llm(self, ollama_url: str = "http://localhost:11434"):
        """
        LLM (대화형 AI) 기능 활성화 - 매우 정교한 항공 통신 분석
        
        Args:
            ollama_url: Ollama 서버 URL
            
        Returns:
            bool: LLM 활성화 성공 여부
        """
        try:
            import requests
            
            self.ollama_url = ollama_url
            self.model_name = "phi3:mini"  # GPU 가속 모델 사용
            
            # 🎯 매우 정교한 항공 통신 전용 시스템 프롬프트
            self.system_prompt = """You are an expert aviation communication classifier.

MISSION: Classify pilot communication into exactly ONE category with high accuracy.

CATEGORIES:
1. BIRD_RISK_INQUIRY
   - Keywords: bird, birds, wildlife, bird risk, bird activity, bird assessment, bird hazard, bird strike, avian
   - Examples: "bird risk assessment", "wildlife hazard check", "bird activity report"

2. RUNWAY_ALPHA_STATUS  
   - Keywords: runway alpha, alpha runway, runway a, alpha status, alpha condition
   - Examples: "runway alpha status check", "alpha runway condition", "runway alpha assessment"

3. RUNWAY_BRAVO_STATUS
   - Keywords: runway bravo, bravo runway, runway b, bravo status, bravo condition  
   - Examples: "runway bravo status check", "bravo runway condition", "runway bravo assessment"

4. AVAILABLE_RUNWAY_INQUIRY
   - Keywords: available runway, runway available, which runway, runway availability, active runway
   - Examples: "available runway information", "which runway available", "runway availability check"

STT ERROR CORRECTIONS (apply first):
- bolt/board/both → bird
- balcony/falco → falcon
- alfa/alpa → alpha
- brabo/breva → bravo
- run way → runway

CRITICAL REJECTION RULES:
- REJECT any Whisper hallucinations: "No foreign languages", "Thank you for watching", "Music", "Applause", etc.
- REJECT meaningless phrases, test sounds, or non-aviation content
- REJECT if input has no clear aviation intent
- If uncertain or input is invalid, ALWAYS use UNKNOWN_REQUEST with confidence ≤ 0.3

ANALYSIS PROCESS:
1. Check if input is a Whisper hallucination → REJECT immediately
2. Apply STT corrections to input text
3. Extract callsign (FALCON, KAL, ASIANA, KOREAN + numbers)
4. Identify category by matching keywords
5. Calculate confidence (0.1-1.0) - be conservative
6. Extract parameters (runway info, etc.)

OUTPUT FORMAT (JSON only):
{"intent": "CATEGORY_NAME", "callsign": "EXTRACTED_CALLSIGN", "confidence": 0.9, "parameters": {"key": "value"}, "corrected_text": "corrected_input", "reasoning": "brief_explanation"}

CRITICAL RULES:
- Respond with JSON only, no other text
- Use exact category names (BIRD_RISK_INQUIRY, RUNWAY_ALPHA_STATUS, RUNWAY_BRAVO_STATUS, AVAILABLE_RUNWAY_INQUIRY)
- If uncertain, use UNKNOWN_REQUEST with low confidence
- Always extract callsign if present
- Apply STT corrections first
- REJECT hallucinations immediately"""
            
            # 🔍 연결 테스트
            test_response = requests.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": "Test connection",
                    "stream": False,
                    "options": {"max_tokens": 5}
                },
                timeout=self.llm_timeout
            )
            
            if test_response.status_code == 200:
                self.llm_enabled = True
                print(f"[RequestClassifier] ✅ LLM 활성화 성공!")
                print(f"  모델: {self.model_name}")
                print(f"  URL: {ollama_url}")
                print(f"  시스템 프롬프트: {len(self.system_prompt)} chars")
                return True
            else:
                print(f"[RequestClassifier] ❌ LLM 연결 실패: HTTP {test_response.status_code}")
                return False
                
        except Exception as e:
            print(f"[RequestClassifier] ❌ LLM 활성화 실패: {e}")
            self.llm_enabled = False
            return False
    
    def classify_with_llm(self, query_text: str, session_id: str = "") -> Tuple[str, Dict]:
        """
        LLM 기반 영어 프롬프트로 분류
        
        Args:
            query_text: 분류할 텍스트
            session_id: 세션 ID
            
        Returns:
            (request_code, parameters) 튜플
        """
        if not hasattr(self, 'llm_enabled') or not self.llm_enabled:
            print("[RequestClassifier] LLM 비활성화됨, 기본 분류 사용")
            return self.classify(query_text, session_id)
        
        print(f"[RequestClassifier] 🧠 LLM 분류 시작: '{query_text}'")
        
        try:
            # LLM 분석 수행
            analysis_result = self._analyze_with_llm(query_text)
            
            # 결과 변환
            intent = analysis_result.get("intent", "UNKNOWN_REQUEST")
            callsign = analysis_result.get("callsign", "UNKNOWN")
            parameters = analysis_result.get("parameters", {})
            confidence = analysis_result.get("confidence", 0.0)
            corrected_text = analysis_result.get("corrected_text", query_text)
            reasoning = analysis_result.get("reasoning", "LLM analysis")
            
            # 파라미터 구성
            result_params = {
                "original_text": query_text,
                "corrected_text": corrected_text if corrected_text != query_text else None,
                "callsign": callsign,
                "confidence_score": confidence,
                "reasoning": reasoning,
                "llm_analysis": True
            }
            
            # LLM 파라미터 병합
            result_params.update(parameters)
            
            print(f"[RequestClassifier] ✅ LLM 분류 완료: {intent} (신뢰도: {confidence})")
            return intent, result_params
            
        except Exception as e:
            print(f"❌ LLM 분류 실패: {e}")
            print("[RequestClassifier] 🔄 기본 분류로 대체")
            return self.classify(query_text, session_id)
    
    def _analyze_with_llm(self, query_text: str) -> Dict:
        """LLM을 사용한 정교한 항공 통신 분석 - 60초 타임아웃"""
        import requests
        
        if not hasattr(self, 'llm_enabled') or not self.llm_enabled:
            raise Exception("LLM not enabled")
        
        # 🎯 정교한 사용자 프롬프트 - 시스템 프롬프트와 연계
        user_prompt = f"""AVIATION COMMUNICATION TO ANALYZE:
"{query_text}"

Please analyze this aviation communication following the process outlined in your instructions.
Apply STT corrections first, then classify into one of the 4 categories.
Respond with JSON only."""

        # 최적화된 API 호출 설정
        payload = {
            "model": self.model_name,
            "prompt": self.system_prompt + "\n\n" + user_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,     # 약간의 창의성 허용
                "max_tokens": 200,      # 더 상세한 응답 허용
                "top_p": 0.2,           # 정확성 우선
                "seed": 42,             # 재현 가능성
                "stop": ["\n\n", "---", "Note:"]  # 불필요한 텍스트 차단
            }
        }
        
        print(f"[LLM] 🤖 분석 시작 (60초 대기): '{query_text[:30]}...'")
        
        response = requests.post(
            f"{self.ollama_url}/api/generate",
            json=payload,
            timeout=self.llm_timeout  # 60초 타임아웃 사용
        )
        
        if response.status_code != 200:
            raise Exception(f"LLM API error: {response.status_code} - {response.text}")
        
        result = response.json()
        llm_response = result.get("response", "").strip()
        
        print(f"[LLM] ✅ 분석 완료 ({len(llm_response)} chars): {llm_response[:100]}...")
        
        # 정교한 JSON 파싱
        return self._parse_llm_response(llm_response, query_text)
    
    def _parse_llm_response(self, llm_response: str, original_text: str) -> Dict:
        """LLM 응답 파싱 - 매우 정교한 분석"""
        import json
        import re
        
        print(f"[LLM] 🔍 파싱 시작: '{llm_response[:80]}...'")
        
        try:
            # 1. 완전한 JSON 블록 추출 시도
            json_patterns = [
                r'\{[^{}]*"intent"[^{}]*\}',  # 기본 JSON 패턴
                r'\{.*?"intent".*?\}',        # 더 관대한 패턴
                r'\{.*\}',                    # 가장 관대한 패턴
            ]
            
            parsed_data = None
            
            for pattern in json_patterns:
                matches = re.findall(pattern, llm_response, re.DOTALL)
                for match in matches:
                    try:
                        # JSON 정리
                        clean_json = match.strip()
                        # 불필요한 문자 제거
                        clean_json = re.sub(r'[\n\r\t]', ' ', clean_json)
                        clean_json = re.sub(r'\s+', ' ', clean_json)
                        
                        parsed_data = json.loads(clean_json)
                        print(f"[LLM] ✅ JSON 파싱 성공: {clean_json}")
                        break
                    except json.JSONDecodeError:
                        continue
                if parsed_data:
                    break
            
            # 2. JSON이 없으면 텍스트 기반 분석
            if not parsed_data:
                print(f"[LLM] ⚠️ JSON 실패, 텍스트 분석 시도...")
                parsed_data = self._extract_from_text(llm_response, original_text)
            
            # 3. 필수 필드 보정 및 검증
            if parsed_data:
                parsed_data = self._validate_and_correct_fields(parsed_data, original_text)
                
                # 신뢰도 검증 및 조정
                confidence = float(parsed_data.get('confidence', 0.5))
                if confidence > 1.0:
                    confidence = confidence / 10.0  # 10점 척도를 1점으로 변환
                elif confidence < 0.1:
                    confidence = 0.1
                parsed_data['confidence'] = confidence
                
                print(f"[LLM] ✅ 최종 분석 결과: {parsed_data}")
                return parsed_data
            else:
                raise Exception("No valid data extracted")
                
        except Exception as e:
            print(f"❌ LLM 응답 파싱 완전 실패: {e}")
            
            # 최후의 대안: 키워드 기반 추출
            return self._emergency_keyword_extraction(llm_response, original_text)
    
    def _extract_from_text(self, text: str, original_text: str) -> Dict:
        """JSON이 없을 때 텍스트에서 정보 추출"""
        text_upper = text.upper()
        original_upper = original_text.upper()  # 🆕 원본 텍스트도 대문자로
        
        # 🆕 카테고리 추출 (LLM 응답과 원본 텍스트 모두에서 검색)
        combined_text = text_upper + " " + original_upper
        intent = "UNKNOWN_REQUEST"
        confidence = 0.3
        
        if any(word in combined_text for word in ["BIRD", "WILDLIFE", "AVIAN"]):
            intent = "BIRD_RISK_INQUIRY"
            confidence = 0.7
        elif any(word in combined_text for word in ["ALPHA", "ALFA", "RUNWAY A"]):
            intent = "RUNWAY_ALPHA_STATUS"
            confidence = 0.7
        elif any(word in combined_text for word in ["BRAVO", "BRABO", "RUNWAY B"]):
            intent = "RUNWAY_BRAVO_STATUS"
            confidence = 0.7
        elif any(word in combined_text for word in ["AVAILABLE", "WHICH", "ACTIVE"]):
            intent = "AVAILABLE_RUNWAY_INQUIRY"
            confidence = 0.7
        
        # 🆕 콜사인 추출 (Korean Air 우선 처리) - 하이픈 포함 숫자 지원 강화
        callsign = "UNKNOWN"
        callsign_patterns = [
            # 🆕 Korean Air 패턴을 최우선으로 (대소문자 무관, 하이픈 포함 숫자 지원)
            r'\b(KOREAN\s+AIR)\s*([\d\-]+)\b',  # Korean Air 1-2-3, Korean Air 123
            r'\b(FALCON)\s*([\d\-]+)\b',         # FALCON 1-2-3, FALCON 123  
            r'\b(KAL|ASIANA|KOREAN)\s*([\d\-]+)\b',  # KAL1-2-3, ASIANA1-2-3
            r'\b([A-Z]{3,6})\s*([\d\-]+)\b'     # 일반 콜사인 (맨 마지막)
        ]
        
        for pattern in callsign_patterns:
            match = re.search(pattern, original_text.upper())
            if match:
                if len(match.groups()) >= 2:
                    airline = match.group(1)
                    numbers = match.group(2)
                    # 🆕 하이픈이 있는 숫자는 하이픈을 제거하여 붙여서 처리
                    clean_numbers = numbers.replace('-', '') if '-' in numbers else numbers
                    
                    # 🆕 표준화된 형태로 변환 (키워드 분류와 일관성 유지)
                    if airline.upper() == "KOREAN AIR":
                        callsign = f"Korean Air {clean_numbers}"
                    elif airline.upper() == "ASIANA" or airline.upper() == "ASIANA AIRLINES":
                        callsign = f"Asiana Airlines {clean_numbers}"
                    elif airline.upper() == "HOTEL LIMA":
                        callsign = f"Hotel Lima {clean_numbers}"
                    elif airline.upper() == "FALCON":
                        callsign = f"Falcon {clean_numbers}"
                    elif airline.upper() == "PACK ON":
                        callsign = f"Falcon {clean_numbers}"
                    else:
                        callsign = f"{airline.title()} {clean_numbers}"
                    
                    print(f"[LLM] 🎯 텍스트 추출에서 콜사인 발견: '{callsign}' (원본: {airline} {numbers}, 패턴: {pattern})")
                else:
                    airline = match.group(1)
                    
                    # 🆕 표준화된 형태로 변환 (키워드 분류와 일관성 유지)
                    if airline.upper() == "KOREAN AIR":
                        callsign = "Korean Air"
                    elif airline.upper() == "ASIANA" or airline.upper() == "ASIANA AIRLINES":
                        callsign = "Asiana Airlines"
                    elif airline.upper() == "HOTEL LIMA":
                        callsign = "Hotel Lima"
                    elif airline.upper() == "FALCON":
                        callsign = "Falcon"
                    elif airline.upper() == "PACK ON":
                        callsign = "Falcon"
                    else:
                        callsign = airline.title()
                
                print(f"[LLM] 🎯 텍스트 추출에서 콜사인 발견: '{callsign}' (패턴: {pattern})")
                break
        
        print(f"[LLM] 🔍 텍스트 추출 결과: intent={intent}, callsign={callsign} (키워드 검색: '{combined_text[:50]}...')")
        
        return {
            "intent": intent,
            "callsign": callsign,
            "confidence": confidence,
            "parameters": {"original_text": original_text},
            "corrected_text": original_text,
            "reasoning": f"Text-based extraction: {intent}"
        }
    
    def _validate_and_correct_fields(self, data: Dict, original_text: str) -> Dict:
        """필드 검증 및 보정"""
        # 필수 필드 확인
        required_fields = {
            "intent": "UNKNOWN_REQUEST",
            "callsign": "UNKNOWN",
            "confidence": 0.5,
            "parameters": {},
            "corrected_text": original_text,
            "reasoning": "LLM analysis"
        }
        
        for field, default in required_fields.items():
            if field not in data or data[field] is None:
                data[field] = default
        
        # 인텐트 검증
        valid_intents = [
            "BIRD_RISK_INQUIRY",
            "RUNWAY_ALPHA_STATUS", 
            "RUNWAY_BRAVO_STATUS",
            "AVAILABLE_RUNWAY_INQUIRY",
            "UNKNOWN_REQUEST"
        ]
        
        if data["intent"] not in valid_intents:
            # 유사한 인텐트 찾기
            intent_upper = data["intent"].upper()
            if "BIRD" in intent_upper or "WILDLIFE" in intent_upper:
                data["intent"] = "BIRD_RISK_INQUIRY"
            elif "ALPHA" in intent_upper:
                data["intent"] = "RUNWAY_ALPHA_STATUS"
            elif "BRAVO" in intent_upper:
                data["intent"] = "RUNWAY_BRAVO_STATUS"
            elif "AVAILABLE" in intent_upper or "RUNWAY" in intent_upper:
                data["intent"] = "AVAILABLE_RUNWAY_INQUIRY"
            else:
                data["intent"] = "UNKNOWN_REQUEST"
                data["confidence"] = min(data["confidence"], 0.3)
        
        return data
    
    def _emergency_keyword_extraction(self, llm_response: str, original_text: str) -> Dict:
        """비상 상황: 키워드 기반 추출"""
        print(f"[LLM] 🚨 비상 키워드 추출 모드")
        
        # 간단한 키워드 매칭
        text_combined = (llm_response + " " + original_text).upper()
        
        if any(word in text_combined for word in ["BIRD", "WILDLIFE", "BOLT", "AVIAN"]):
            intent = "BIRD_RISK_INQUIRY"
        elif any(word in text_combined for word in ["ALPHA", "ALFA"]):
            intent = "RUNWAY_ALPHA_STATUS"
        elif any(word in text_combined for word in ["BRAVO", "BRABO"]):
            intent = "RUNWAY_BRAVO_STATUS"
        elif any(word in text_combined for word in ["AVAILABLE", "WHICH", "RUNWAY"]):
            intent = "AVAILABLE_RUNWAY_INQUIRY"
        else:
            intent = "UNKNOWN_REQUEST"
        
        return {
            "intent": intent,
            "callsign": "UNKNOWN",
            "confidence": 0.2,  # 낮은 신뢰도
            "parameters": {"original_text": original_text},
            "corrected_text": original_text,
            "reasoning": "Emergency keyword extraction from LLM failure"
        }

    def classify_hybrid(self, query_text: str, session_id: str = "") -> Tuple[str, Dict]:
        """
        하이브리드 분류: LLM 우선 활용 (60초 타임아웃, 더 적극적 사용)
        
        Args:
            query_text: 분류할 텍스트
            session_id: 세션 ID
            
        Returns:
            (request_code, parameters) 튜플
        """
        print(f"[RequestClassifier] 🔀 하이브리드 분류 시작: '{query_text}'")
        
        # 0. 빈 텍스트나 너무 짧은 텍스트는 LLM 건너뛰기
        if not query_text or len(query_text.strip()) < 3:
            print(f"[RequestClassifier] ⚠️ 텍스트가 너무 짧음, LLM 건너뛰기")
            return "UNKNOWN_REQUEST", {
                "original_text": query_text,
                "error": "Text too short for analysis",
                "classification_method": "early_rejection"
            }
        
        # 1. 먼저 키워드 기반 분류 시도
        keyword_result, keyword_params = self.classify(query_text, session_id)
        keyword_confidence = keyword_params.get('confidence_score', 0)
        
        # 2. LLM이 활성화되어 있으면 적극 사용 (신뢰도 10 미만이면 LLM 시도)
        if hasattr(self, 'llm_enabled') and self.llm_enabled:
            # 매우 확실한 경우(신뢰도 10 이상)만 키워드 결과 바로 사용
            if keyword_confidence >= 10:
                print(f"[RequestClassifier] ✅ 키워드 분류 매우 확실: {keyword_result} (신뢰도: {keyword_confidence})")
                keyword_params['classification_method'] = 'keyword_high_confidence'
                return keyword_result, keyword_params
            
            # 그 외는 LLM으로 검증/개선 시도
            print(f"[RequestClassifier] 🧠 LLM 분석 시도 (키워드 신뢰도: {keyword_confidence})")
            
            try:
                # 60초 타임아웃으로 LLM 분류 시도
                llm_result, llm_params = self._enhanced_llm_classify(query_text)
                llm_confidence = llm_params.get('confidence_score', 0)
                
                # 🎯 개선된 판단 로직: 키워드와 LLM 결과 비교
                if keyword_result != "UNKNOWN_REQUEST" and llm_result != keyword_result:
                    print(f"[RequestClassifier] ⚖️ 분류 결과 불일치:")
                    print(f"  키워드: {keyword_result} (신뢰도: {keyword_confidence})")
                    print(f"  LLM: {llm_result} (신뢰도: {llm_confidence})")
                    
                    # 키워드 신뢰도가 5 이상이고 LLM 신뢰도가 0.8 미만이면 키워드 우선
                    if keyword_confidence >= 5 and llm_confidence < 0.8:
                        print(f"[RequestClassifier] 📊 키워드 분류 채택 (더 신뢰할만함)")
                        keyword_params['classification_method'] = 'keyword_over_llm'
                        keyword_params['llm_alternative'] = (llm_result, llm_confidence)
                        return keyword_result, keyword_params
                    
                    # LLM 신뢰도가 0.9 이상이면 LLM 우선
                    elif llm_confidence >= 0.9:
                        print(f"[RequestClassifier] 🎯 LLM 분류 채택 (매우 높은 신뢰도)")
                        
                        # 🔧 키워드에서 추출한 콜사인이 더 좋으면 덮어쓰기
                        keyword_callsign = keyword_params.get('callsign', 'UNKNOWN')
                        llm_callsign = llm_params.get('callsign', 'UNKNOWN')
                        
                        if keyword_callsign != 'UNKNOWN' and keyword_callsign != 'Aircraft' and llm_callsign == 'UNKNOWN':
                            print(f"[RequestClassifier] 🔄 콜사인 병합: LLM '{llm_callsign}' → 키워드 '{keyword_callsign}'")
                            llm_params['callsign'] = keyword_callsign
                        
                        llm_params['classification_method'] = 'llm_high_confidence'
                        llm_params['keyword_alternative'] = (keyword_result, keyword_confidence)
                        return llm_result, llm_params
                    
                    # 애매한 경우 키워드 우선 (더 안전)
                    else:
                        print(f"[RequestClassifier] 🛡️ 키워드 분류 채택 (안전 우선)")
                        keyword_params['classification_method'] = 'keyword_safety_first'
                        keyword_params['llm_alternative'] = (llm_result, llm_confidence)
                        return keyword_result, keyword_params
                
                # 결과가 일치하거나 키워드가 UNKNOWN인 경우 LLM 사용
                elif llm_confidence >= 0.5:
                    print(f"[RequestClassifier] 🎯 LLM 분류 채택: {llm_result} (신뢰도: {llm_confidence})")
                    
                    # 🔧 키워드에서 추출한 콜사인이 더 좋으면 덮어쓰기
                    keyword_callsign = keyword_params.get('callsign', 'UNKNOWN')
                    llm_callsign = llm_params.get('callsign', 'UNKNOWN')
                    
                    if keyword_callsign != 'UNKNOWN' and keyword_callsign != 'Aircraft' and llm_callsign == 'UNKNOWN':
                        print(f"[RequestClassifier] 🔄 콜사인 병합: LLM '{llm_callsign}' → 키워드 '{keyword_callsign}'")
                        llm_params['callsign'] = keyword_callsign
                    
                    llm_params['classification_method'] = 'llm_primary'
                    llm_params['keyword_fallback'] = (keyword_result, keyword_confidence)
                    return llm_result, llm_params
                else:
                    print(f"[RequestClassifier] 📊 키워드 분류 유지: {keyword_result}")
                    
            except Exception as e:
                print(f"[RequestClassifier] ⚠️ LLM 분류 실패 (60초): {e}")
        else:
            print(f"[RequestClassifier] 📊 LLM 비활성화, 키워드만 사용")
        
        # 3. 기본적으로 키워드 결과 반환
        keyword_params['classification_method'] = 'keyword_fallback'
        return keyword_result, keyword_params
    
    def _enhanced_llm_classify(self, query_text: str) -> Tuple[str, Dict]:
        """향상된 LLM 분류 (60초 타임아웃, 캐시 활용)"""
        import requests
        import json
        
        # 📊 응답 캐시 확인
        if hasattr(self, '_llm_cache'):
            if query_text in self._llm_cache:
                print("[LLM] 🚀 캐시 히트!")
                return self._llm_cache[query_text]
        else:
            self._llm_cache = {}
        
        # LLM 분석 수행
        analysis_result = self._analyze_with_llm(query_text)
        
        # 결과 변환
        intent = analysis_result.get("intent", "UNKNOWN_REQUEST")
        callsign = analysis_result.get("callsign", "UNKNOWN")
        parameters = analysis_result.get("parameters", {})
        confidence = analysis_result.get("confidence", 0.0)
        corrected_text = analysis_result.get("corrected_text", query_text)
        reasoning = analysis_result.get("reasoning", "Enhanced LLM analysis")
        
        # 파라미터 구성
        result_params = {
            "original_text": query_text,
            "corrected_text": corrected_text if corrected_text != query_text else None,
            "callsign": callsign,
            "confidence_score": confidence,
            "reasoning": reasoning,
            "llm_enhanced": True
        }
        
        # LLM 파라미터 병합
        result_params.update(parameters)
        
        result_tuple = (intent, result_params)
        
        # 결과를 캐시에 저장 (최대 50개로 확대)
        if len(self._llm_cache) < 50:
            self._llm_cache[query_text] = result_tuple
        
        return result_tuple

    def get_llm_status(self) -> Dict:
        """LLM 상태 정보 반환"""
        return {
            "enabled": getattr(self, 'llm_enabled', False),
            "model": getattr(self, 'model_name', None),
            "url": getattr(self, 'ollama_url', None),
            "system_prompt_length": len(getattr(self, 'system_prompt', ''))
        }
