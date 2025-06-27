import uuid
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class InteractionLog:
    """상호작용 로그 데이터 구조"""
    timestamp: str
    session_id: str
    callsign: str
    stt_text: str
    request_code: str
    parameters: Dict[str, Any]
    response_text: str
    processing_time: float
    confidence_score: float = 0.0

class SessionManager:
    def __init__(self, log_dir: str = "logs"):
        """
        세션 매니저 초기화
        
        Args:
            log_dir: 로그 파일을 저장할 디렉토리
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # 현재 활성 세션들
        self.active_sessions: Dict[str, Dict] = {}
        
        # 오늘 날짜의 로그 파일 경로
        today = datetime.now().strftime("%Y%m%d")
        self.daily_log_file = self.log_dir / f"pilot_interactions_{today}.json"
        
        print(f"[SessionManager] 초기화 완료. 로그 디렉토리: {self.log_dir}")
    
    def new_session_id(self) -> str:
        """
        세션 식별자 생성 (예: pilot-20250605-uuid)
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        session_id = f"pilot-{timestamp}-{uuid.uuid4().hex[:6]}"
        
        # 새 세션 등록
        self.active_sessions[session_id] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "interaction_count": 0,
            "last_activity": datetime.now(timezone.utc).isoformat()
        }
        
        print(f"[SessionManager] 새 세션 생성: {session_id}")
        return session_id
    
    def log_interaction(self, 
                       session_id: str,
                       callsign: str,
                       stt_text: str,
                       request_code: str,
                       parameters: Dict[str, Any],
                       response_text: str,
                       processing_time: float,
                       confidence_score: float = 0.0):
        """
        상호작용 로그 기록
        
        Args:
            session_id: 세션 ID
            callsign: 항공기 콜사인
            stt_text: 음성 인식 결과
            request_code: 요청 코드
            parameters: 요청 파라미터
            response_text: 응답 텍스트
            processing_time: 처리 시간 (초)
            confidence_score: 신뢰도 점수
        """
        try:
            # 로그 엔트리 생성
            log_entry = InteractionLog(
                timestamp=datetime.now(timezone.utc).isoformat(),
                session_id=session_id,
                callsign=callsign,
                stt_text=stt_text,
                request_code=request_code,
                parameters=parameters,
                response_text=response_text,
                processing_time=processing_time,
                confidence_score=confidence_score
            )
            
            # 파일에 로그 추가
            self._append_log_to_file(log_entry)
            
            # 세션 정보 업데이트
            if session_id in self.active_sessions:
                self.active_sessions[session_id]["interaction_count"] += 1
                self.active_sessions[session_id]["last_activity"] = datetime.now(timezone.utc).isoformat()
            
            print(f"[SessionManager] 상호작용 로그 기록: {session_id} - {request_code}")
            
        except Exception as e:
            print(f"[SessionManager] 로그 기록 오류: {e}")
    
    def _append_log_to_file(self, log_entry: InteractionLog):
        """
        로그 파일에 엔트리 추가
        """
        try:
            # 기존 로그 읽기
            logs = []
            if self.daily_log_file.exists():
                with open(self.daily_log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            
            # 새 로그 추가
            logs.append(asdict(log_entry))
            
            # 파일에 저장
            with open(self.daily_log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"[SessionManager] 로그 파일 쓰기 오류: {e}")
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """
        세션 정보 조회
        """
        return self.active_sessions.get(session_id)
    
    def get_active_sessions(self) -> Dict[str, Dict]:
        """
        현재 활성 세션 목록 반환
        """
        return self.active_sessions.copy()
    
    def close_session(self, session_id: str):
        """
        세션 종료
        """
        if session_id in self.active_sessions:
            session_info = self.active_sessions[session_id]
            session_info["closed_at"] = datetime.now(timezone.utc).isoformat()
            
            # 세션 요약 로그
            print(f"[SessionManager] 세션 종료: {session_id} "
                  f"(상호작용 수: {session_info['interaction_count']})")
            
            # 활성 세션에서 제거
            del self.active_sessions[session_id]
    
    def get_daily_stats(self, date: Optional[str] = None) -> Dict:
        """
        일일 통계 조회
        
        Args:
            date: 조회할 날짜 (YYYYMMDD), None이면 오늘
            
        Returns:
            통계 정보 딕셔너리
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        
        log_file = self.log_dir / f"pilot_interactions_{date}.json"
        
        if not log_file.exists():
            return {"date": date, "total_interactions": 0, "error": "로그 파일 없음"}
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            
            # 통계 계산
            total_interactions = len(logs)
            unique_sessions = len(set(log["session_id"] for log in logs))
            unique_callsigns = len(set(log["callsign"] for log in logs))
            
            # 요청 유형별 통계
            request_counts = {}
            total_processing_time = 0
            
            for log in logs:
                request_code = log["request_code"]
                request_counts[request_code] = request_counts.get(request_code, 0) + 1
                total_processing_time += log.get("processing_time", 0)
            
            avg_processing_time = total_processing_time / total_interactions if total_interactions > 0 else 0
            
            return {
                "date": date,
                "total_interactions": total_interactions,
                "unique_sessions": unique_sessions,
                "unique_callsigns": unique_callsigns,
                "request_type_counts": request_counts,
                "average_processing_time": round(avg_processing_time, 3)
            }
            
        except Exception as e:
            print(f"[SessionManager] 통계 조회 오류: {e}")
            return {"date": date, "error": str(e)}
    
    def search_logs(self, 
                   callsign: Optional[str] = None,
                   request_code: Optional[str] = None,
                   date_from: Optional[str] = None,
                   date_to: Optional[str] = None,
                   limit: int = 100) -> List[Dict]:
        """
        로그 검색
        
        Args:
            callsign: 콜사인 필터
            request_code: 요청 코드 필터
            date_from: 시작 날짜 (YYYY-MM-DD)
            date_to: 종료 날짜 (YYYY-MM-DD)
            limit: 최대 결과 수
            
        Returns:
            검색 결과 리스트
        """
        results = []
        
        try:
            # 검색할 날짜 범위의 로그 파일들 찾기
            log_files = []
            if date_from and date_to:
                # 날짜 범위가 지정된 경우
                start_date = datetime.strptime(date_from, "%Y-%m-%d")
                end_date = datetime.strptime(date_to, "%Y-%m-%d")
                
                current_date = start_date
                while current_date <= end_date:
                    date_str = current_date.strftime("%Y%m%d")
                    log_file = self.log_dir / f"pilot_interactions_{date_str}.json"
                    if log_file.exists():
                        log_files.append(log_file)
                    current_date = current_date.replace(day=current_date.day + 1)
            else:
                # 오늘 로그만 검색
                log_files = [self.daily_log_file] if self.daily_log_file.exists() else []
            
            # 각 로그 파일에서 검색
            for log_file in log_files:
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
                
                for log in logs:
                    # 필터 적용
                    if callsign and log.get("callsign") != callsign:
                        continue
                    if request_code and log.get("request_code") != request_code:
                        continue
                    
                    results.append(log)
                    
                    # 제한 수 확인
                    if len(results) >= limit:
                        break
                
                if len(results) >= limit:
                    break
            
            return results[:limit]
            
        except Exception as e:
            print(f"[SessionManager] 로그 검색 오류: {e}")
            return []
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """
        오래된 로그 파일 정리
        
        Args:
            days_to_keep: 보관할 일수
        """
        try:
            cutoff_date = datetime.now().replace(day=datetime.now().day - days_to_keep)
            
            for log_file in self.log_dir.glob("pilot_interactions_*.json"):
                # 파일명에서 날짜 추출
                filename = log_file.stem
                date_str = filename.split("_")[-1]
                
                try:
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    if file_date < cutoff_date:
                        log_file.unlink()
                        print(f"[SessionManager] 오래된 로그 파일 삭제: {log_file}")
                except ValueError:
                    # 날짜 형식이 맞지 않는 파일은 건너뛰기
                    continue
                    
        except Exception as e:
            print(f"[SessionManager] 로그 정리 오류: {e}")
