# -*- coding: utf-8 -*-
"""
Improved Adaptive Window Gesture Detection
오동작 방지를 위한 개선된 적응형 제스처 인식
"""

import cv2
import mediapipe as mp
import numpy as np
import torch
import os
from collections import deque
from typing import Optional, Tuple, List, Dict
import time

from config import DATA_CONFIG, MEDIAPIPE_CONFIG, GESTURE_CLASSES, TCN_CONFIG, IMPROVED_GESTURE_CONFIG
from model import GestureModelManager

class GestureTransitionDetector:
    """제스처 전환 패턴 감지"""
    
    def __init__(self):
        self.transition_buffer = deque(maxlen=60)  # 2초 버퍼
        self.common_transitions = IMPROVED_GESTURE_CONFIG['common_transitions']
    
    def detect_transition(self, current_gesture, confidence):
        """제스처 전환 패턴 감지"""
        if current_gesture is None:
            return False, None
            
        self.transition_buffer.append((current_gesture, confidence))
        
        if len(self.transition_buffer) < 20:
            return False, None
        
        # 최근 20프레임에서 전환 패턴 찾기
        recent_gestures = [g for g, c in list(self.transition_buffer)[-20:]]
        
        for pattern_name, pattern in self.common_transitions.items():
            if self._matches_pattern(recent_gestures, pattern):
                return True, pattern[-1]  # 최종 제스처 반환
        
        return False, None
    
    def _matches_pattern(self, gestures, pattern):
        """패턴 매칭"""
        if len(gestures) < len(pattern):
            return False
        
        # 끝에서부터 패턴 매칭
        for i, expected in enumerate(reversed(pattern)):
            if gestures[-(i+1)] != expected:
                return False
        return True

class ImprovedAdaptiveWindowPoseDetector:
    """개선된 다중 윈도우 크기를 사용한 적응형 실시간 포즈 검출"""
    
    def __init__(self, model_path: str = None):
        # MediaPipe 초기화 (경고 해결을 위한 개선된 설정)
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            smooth_landmarks=True,
            smooth_segmentation=True,
            min_detection_confidence=DATA_CONFIG['min_detection_confidence'],
            min_tracking_confidence=DATA_CONFIG['min_tracking_confidence']
        )
        
        self.mp_drawing = mp.solutions.drawing_utils
        
        # 관절 인덱스
        self.key_landmarks = MEDIAPIPE_CONFIG['key_landmarks']
        
        # 다중 윈도우 버퍼
        self.window_sizes = [30, 45, 60, 90]  # 1초, 1.5초, 2초, 3초
        self.pose_buffers = {
            size: deque(maxlen=size) for size in self.window_sizes
        }
        
        # 모델 로드
        self.model_manager = GestureModelManager(model_path)
        self.model = self.model_manager.load_model()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # 예측 결과 추적
        self.prediction_results = {}
        self.confidence_weights = {
            30: 0.2,   # 짧은 윈도우는 낮은 가중치
            45: 0.3,   # 중간 윈도우
            60: 0.3,   # 중간 윈도우
            90: 0.2    # 긴 윈도우는 약간 낮은 가중치 (지연 고려)
        }
        
        # 동작 상태 추적
        self.motion_state = {
            'is_moving': False,
            'motion_start_time': 0,
            'motion_intensity': 0.0,
            'stable_frames': 0
        }
        
        # 최종 예측
        self.final_prediction = None
        self.final_confidence = 0.0
        self.prediction_history = deque(maxlen=90)  # 3초 이력
        self.confidence_history = deque(maxlen=30)  # 1초 신뢰도 이력
        
        # 개선된 기능들
        self.transition_detector = GestureTransitionDetector()
        self.improved_config = IMPROVED_GESTURE_CONFIG
        
        # 성능 추적
        self.fps_counter = 0
        self.fps_start_time = time.time()
        
    def extract_pose_landmarks(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """프레임에서 자세 랜드마크 추출"""
        # 이미지 크기 정보 설정 (MediaPipe 경고 해결)
        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False
        
        results = self.pose.process(rgb_frame)
        
        if results.pose_landmarks:
            # 17개 주요 관절 좌표 추출
            pose_data = []
            for idx in self.key_landmarks:
                landmark = results.pose_landmarks.landmark[idx]
                pose_data.append([landmark.x, landmark.y, landmark.visibility])
            
            return np.array(pose_data, dtype=np.float32), results
        
        return None, results
    
    def normalize_pose_data(self, pose_data: np.ndarray) -> np.ndarray:
        """자세 데이터 정규화"""
        if pose_data.shape[0] == 0:
            return pose_data
            
        normalized_pose = pose_data.copy()
        
        # Hip 중심점 계산
        left_hip = pose_data[9]   # left_hip
        right_hip = pose_data[10] # right_hip
        
        if left_hip[2] > 0.5 and right_hip[2] > 0.5:
            center = (left_hip[:2] + right_hip[:2]) / 2
            
            # 상대 좌표로 변환
            for joint_idx in range(len(self.key_landmarks)):
                if pose_data[joint_idx][2] > 0.5:
                    normalized_pose[joint_idx][:2] -= center
            
            # 스케일 정규화 (어깨 너비 기준)
            left_shoulder = pose_data[3]   # left_shoulder
            right_shoulder = pose_data[4]  # right_shoulder
            
            if left_shoulder[2] > 0.5 and right_shoulder[2] > 0.5:
                shoulder_width = np.linalg.norm(left_shoulder[:2] - right_shoulder[:2])
                if shoulder_width > 0:
                    normalized_pose[:, :2] /= shoulder_width
        
        return normalized_pose
    
    def calculate_motion_intensity(self, pose_data: np.ndarray) -> float:
        """동작 강도 계산"""
        if len(self.pose_buffers[30]) < 2:
            return 0.0
        
        # 최근 두 프레임 비교
        prev_pose = list(self.pose_buffers[30])[-2]
        curr_pose = pose_data[:, :2]  # x, y만 사용
        
        # 관절별 움직임 계산
        motion_per_joint = []
        for joint_idx in range(len(curr_pose)):
            if pose_data[joint_idx][2] > 0.5:  # visibility check
                motion = np.linalg.norm(curr_pose[joint_idx] - prev_pose[joint_idx])
                motion_per_joint.append(motion)
        
        return np.mean(motion_per_joint) if motion_per_joint else 0.0
    
    def update_motion_state(self, motion_intensity: float):
        """동작 상태 업데이트"""
        motion_threshold = 0.02  # 움직임 임계값
        stable_threshold = 10    # 안정 프레임 수
        
        if motion_intensity > motion_threshold:
            if not self.motion_state['is_moving']:
                self.motion_state['motion_start_time'] = time.time()
                self.motion_state['is_moving'] = True
            self.motion_state['stable_frames'] = 0
        else:
            self.motion_state['stable_frames'] += 1
            if self.motion_state['stable_frames'] > stable_threshold:
                self.motion_state['is_moving'] = False
        
        self.motion_state['motion_intensity'] = motion_intensity
    
    def get_dynamic_threshold(self, motion_duration: float, motion_intensity: float) -> float:
        """동적 신뢰도 임계값 계산"""
        thresholds = self.improved_config['dynamic_thresholds']
        
        if motion_duration < 0.5:
            return thresholds['early_stage']
        elif motion_duration < 1.0:
            return thresholds['mid_stage']
        elif motion_duration < 2.0:
            return thresholds['late_stage']
        else:
            # 긴 동작: 안정성 중시
            if motion_intensity < self.improved_config['completion_motion_threshold']:
                return thresholds['completion']
            else:
                return thresholds['late_stage']
    
    def is_gesture_completed(self, motion_intensity: float, stable_frames: int, motion_duration: float) -> bool:
        """제스처 완료 여부 판단"""
        return (
            motion_intensity < self.improved_config['completion_motion_threshold'] and
            stable_frames > self.improved_config['completion_stable_frames'] and
            motion_duration > self.improved_config['min_motion_duration']
        )
    
    def analyze_prediction_consistency(self, recent_predictions: List[Tuple[str, float]]) -> Tuple[Optional[str], float]:
        """최근 예측들의 일관성 분석"""
        window_frames = self.improved_config['consistency_window_frames']
        
        if len(recent_predictions) < window_frames:
            return None, 0.0
        
        # 마지막 N프레임 분석
        last_frames = recent_predictions[-window_frames:]
        
        # 각 제스처별 빈도 계산
        gesture_counts = {}
        for gesture, conf in last_frames:
            if gesture not in gesture_counts:
                gesture_counts[gesture] = []
            gesture_counts[gesture].append(conf)
        
        # 가장 일관된 제스처 찾기
        best_gesture = None
        best_consistency = 0.0
        
        for gesture, confidences in gesture_counts.items():
            required_frames = int(window_frames * 0.7)  # 70% 이상
            if len(confidences) >= required_frames:
                consistency = len(confidences) / window_frames * np.mean(confidences)
                if consistency > best_consistency:
                    best_gesture = gesture
                    best_consistency = consistency
        
        return best_gesture, best_consistency
    
    def analyze_confidence_trend(self, recent_confidences: List[float]) -> Tuple[bool, float]:
        """신뢰도 변화 추세 분석"""
        if len(recent_confidences) < 10:
            return False, 0.0
        
        # 최근 10개 신뢰도 값
        confidences = recent_confidences[-10:]
        
        # 선형 회귀로 추세 계산
        x = np.arange(len(confidences))
        slope = np.polyfit(x, confidences, 1)[0]
        
        # 추세 판단
        is_increasing = slope > self.improved_config['confidence_gradient_min']
        stability = 1.0 - np.std(confidences)  # 안정성
        
        return is_increasing and stability > 0.8, slope
    
    def smart_window_selection(self, motion_duration: float, gesture_history: List[Tuple[str, float]]) -> List[int]:
        """스마트 윈도우 선택 전략"""
        if not self.improved_config['smart_window_selection']:
            return self.window_sizes
        
        # 제스처별 최적 윈도우 크기
        gesture_optimal_windows = self.improved_config['gesture_optimal_windows']
        
        # 최근 제스처 이력 기반 선택
        if gesture_history:
            recent_gesture = gesture_history[-1][0]
            optimal_windows = gesture_optimal_windows.get(recent_gesture, [45, 60])
        else:
            optimal_windows = [45, 60]  # 기본값
        
        # 동작 지속시간 고려
        if motion_duration < 1.0:
            return [w for w in optimal_windows if w <= 45]
        elif motion_duration > 2.0:
            return [w for w in optimal_windows if w >= 60]
        else:
            return optimal_windows
    
    def predict_with_window(self, window_size: int) -> Tuple[Optional[str], float]:
        """특정 윈도우 크기로 제스처 예측"""
        if len(self.pose_buffers[window_size]) < window_size or self.model is None:
            return None, 0.0
        
        # 버퍼를 텐서로 변환
        pose_sequence = np.array(list(self.pose_buffers[window_size]))  # (window_size, 17, 2)
        pose_sequence = pose_sequence.reshape(pose_sequence.shape[0], -1)  # (window_size, 34)
        
        # 30프레임으로 리샘플링 (모델은 30프레임으로 학습됨)
        if window_size != 30:
            indices = np.linspace(0, len(pose_sequence) - 1, 30, dtype=int)
            pose_sequence = pose_sequence[indices]
        
        # 배치 차원 추가
        input_tensor = torch.FloatTensor(pose_sequence).unsqueeze(0).to(self.device)  # (1, 30, 34)
        
        # 예측
        predictions, confidences, probabilities = self.model.predict(input_tensor)
        
        predicted_class = predictions[0].item()
        confidence = confidences[0].item()
        
        gesture_name = GESTURE_CLASSES[predicted_class]
        return gesture_name, confidence
    
    def improved_adaptive_prediction(self, motion_duration: float) -> Tuple[Optional[str], float, Dict]:
        """개선된 적응형 예측"""
        debug_info = {
            'selected_windows': [],
            'window_predictions': {},
            'consistency_info': {},
            'confidence_trend': {},
            'transition_detected': False
        }
        
        # 스마트 윈도우 선택
        selected_windows = self.smart_window_selection(motion_duration, list(self.prediction_history))
        debug_info['selected_windows'] = selected_windows
        
        # 동적 임계값 계산
        dynamic_threshold = self.get_dynamic_threshold(motion_duration, self.motion_state['motion_intensity'])
        
        predictions = {}
        total_weight = 0
        
        # 선택된 윈도우들로 예측
        for window_size in selected_windows:
            gesture, confidence = self.predict_with_window(window_size)
            debug_info['window_predictions'][f'{window_size}f'] = f'{gesture}({confidence:.2f})' if gesture else 'None'
            
            if gesture and confidence > dynamic_threshold:
                weight = self.confidence_weights[window_size] * confidence
                
                if gesture not in predictions:
                    predictions[gesture] = 0
                predictions[gesture] += weight
                total_weight += weight
        
        if not predictions:
            return None, 0.0, debug_info
        
        # 가중 평균으로 최종 예측
        best_gesture = max(predictions.keys(), key=lambda x: predictions[x])
        final_confidence = predictions[best_gesture] / total_weight if total_weight > 0 else 0.0
        
        # 예측 일관성 분석
        if len(self.prediction_history) >= 30:
            consistent_gesture, consistency = self.analyze_prediction_consistency(list(self.prediction_history))
            debug_info['consistency_info'] = {
                'consistent_gesture': consistent_gesture,
                'consistency_score': consistency
            }
            
            # 일관성이 좋으면 해당 제스처 우선
            if (consistent_gesture and 
                consistency > self.improved_config['consistency_threshold'] and
                consistent_gesture in predictions):
                best_gesture = consistent_gesture
                final_confidence = max(final_confidence, consistency)
        
        # 신뢰도 추세 분석
        if len(self.confidence_history) >= 10:
            is_stable_increasing, trend = self.analyze_confidence_trend(list(self.confidence_history))
            debug_info['confidence_trend'] = {
                'is_stable_increasing': is_stable_increasing,
                'trend_slope': trend
            }
            
            # 추세가 좋지 않으면 신뢰도 감소
            if not is_stable_increasing:
                final_confidence *= 0.9
        
        # 제스처 전환 감지
        if self.improved_config['transition_detection']:
            transition_detected, transition_gesture = self.transition_detector.detect_transition(best_gesture, final_confidence)
            debug_info['transition_detected'] = transition_detected
            
            if transition_detected and transition_gesture:
                best_gesture = transition_gesture
                final_confidence = min(final_confidence * 1.1, 1.0)  # 약간 보정
        
        return best_gesture, final_confidence, debug_info 
    
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, Optional[str], float, Dict]:
        """개선된 프레임 처리 및 적응형 제스처 인식"""
        # 자세 추출
        pose_result = self.extract_pose_landmarks(frame)
        
        debug_info = {
            'motion_intensity': 0.0,
            'motion_state': 'idle',
            'window_predictions': {},
            'final_method': 'improved_adaptive',
            'dynamic_threshold': 0.75,
            'gesture_completed': False,
            'consistency_info': {},
            'confidence_trend': {}
        }
        
        if pose_result[0] is not None:
            pose_data, results = pose_result
            
            # 정규화
            normalized_pose = self.normalize_pose_data(pose_data)
            
            # 모든 윈도우 버퍼에 추가 (x, y 좌표만)
            pose_xy = normalized_pose[:, :2]
            for window_size in self.window_sizes:
                self.pose_buffers[window_size].append(pose_xy)
            
            # 동작 강도 계산 및 상태 업데이트
            motion_intensity = self.calculate_motion_intensity(normalized_pose)
            self.update_motion_state(motion_intensity)
            
            # 스켈레톤 그리기
            annotated_frame = frame.copy()
            self.mp_drawing.draw_landmarks(
                annotated_frame, results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS)
            
            # 동작 지속시간 계산
            motion_duration = time.time() - self.motion_state['motion_start_time']
            
            # 개선된 적응형 예측
            gesture, confidence, pred_debug_info = self.improved_adaptive_prediction(motion_duration)
            
            # 디버그 정보 병합
            debug_info.update(pred_debug_info)
            debug_info.update({
                'motion_intensity': motion_intensity,
                'motion_state': 'moving' if self.motion_state['is_moving'] else 'stable',
                'motion_duration': motion_duration,
                'dynamic_threshold': self.get_dynamic_threshold(motion_duration, motion_intensity)
            })
            
            # 제스처 완료 여부 확인
            gesture_completed = self.is_gesture_completed(
                motion_intensity, 
                self.motion_state['stable_frames'], 
                motion_duration
            )
            debug_info['gesture_completed'] = gesture_completed
            
            # 예측 이력 관리
            if gesture and confidence > 0.6:
                self.prediction_history.append((gesture, confidence))
                self.confidence_history.append(confidence)
                
                # 최종 예측 업데이트 (완료된 동작만)
                if gesture_completed or motion_duration > 2.0:
                    self.final_prediction = gesture
                    self.final_confidence = confidence
            
            return annotated_frame, self.final_prediction, self.final_confidence, debug_info
        
        return frame, self.final_prediction, self.final_confidence, debug_info
    
    def draw_adaptive_info(self, frame: np.ndarray, gesture: Optional[str], confidence: float, debug_info: Dict) -> np.ndarray:
        """개선된 적응형 정보 오버레이 그리기"""
        height, width = frame.shape[:2]
        
        # FPS 계산
        self.fps_counter += 1
        if time.time() - self.fps_start_time >= 1.0:
            fps = self.fps_counter / (time.time() - self.fps_start_time)
            self.fps_counter = 0
            self.fps_start_time = time.time()
            self.current_fps = fps
        
        # 기본 정보
        info_text = [
            f"FPS: {getattr(self, 'current_fps', 0):.1f}",
            f"Motion: {debug_info['motion_state']} ({debug_info['motion_intensity']:.3f})",
            f"Duration: {debug_info.get('motion_duration', 0):.1f}s",
            f"Threshold: {debug_info.get('dynamic_threshold', 0.75):.2f}",
            f"Completed: {debug_info.get('gesture_completed', False)}"
        ]
        
        # 최종 예측
        if gesture:
            info_text.extend([
                f"Gesture: {gesture}",
                f"Confidence: {confidence:.2f}"
            ])
        
        # 선택된 윈도우 정보
        selected_windows = debug_info.get('selected_windows', [])
        window_info = [f"Selected: {selected_windows}"]
        
        # 윈도우별 예측 (작은 글씨로)
        for window, pred in debug_info.get('window_predictions', {}).items():
            window_info.append(f"{window}: {pred}")
        
        # 일관성 정보
        consistency_info = debug_info.get('consistency_info', {})
        if consistency_info:
            window_info.append(f"Consistent: {consistency_info.get('consistent_gesture', 'None')}")
            window_info.append(f"Score: {consistency_info.get('consistency_score', 0):.2f}")
        
        # 신뢰도 추세 정보
        trend_info = debug_info.get('confidence_trend', {})
        if trend_info:
            window_info.append(f"Trend: {trend_info.get('is_stable_increasing', False)}")
            window_info.append(f"Slope: {trend_info.get('trend_slope', 0):.3f}")
        
        # 전환 감지 정보
        if debug_info.get('transition_detected', False):
            window_info.append("Transition: YES")
        
        # 텍스트 그리기 (좌측)
        y_offset = 30
        for text in info_text:
            cv2.putText(frame, text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, (0, 255, 0), 2)
            y_offset += 25
        
        # 윈도우 정보 (우측)
        y_offset = 30
        for text in window_info:
            cv2.putText(frame, text, (width-300, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.4, (255, 255, 0), 1)
            y_offset += 20
        
        # 제스처 상태 표시
        if gesture and confidence > 0.8:
            # 완료된 제스처는 빨간색 박스로 강조
            color = (0, 0, 255) if debug_info.get('gesture_completed', False) else (0, 255, 255)
            cv2.rectangle(frame, (width//2-100, 10), (width//2+100, 80), color, 3)
            cv2.putText(frame, gesture, (width//2-80, 40), cv2.FONT_HERSHEY_SIMPLEX, 
                       1.0, color, 3)
            cv2.putText(frame, f"{confidence:.2f}", (width//2-50, 65), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.7, color, 2)
            
            # 완료 상태 표시
            if debug_info.get('gesture_completed', False):
                cv2.putText(frame, "COMPLETED", (width//2-60, 95), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.5, (0, 0, 255), 2)
        
        return frame
    
    def run_camera(self, camera_index: int = 0):
        """개선된 적응형 카메라 실시간 처리"""
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            print(f"카메라를 열 수 없습니다: {camera_index}")
            return
        
        print("🎯 개선된 적응형 제스처 인식 시작 (q 키로 종료)")
        print("📊 다중 윈도우: 30f(1s), 45f(1.5s), 60f(2s), 90f(3s)")
        print("🧠 스마트 윈도우 선택: 활성화")
        print("🔍 동적 임계값: 0.95 → 0.75")
        print("✅ 동작 완료 감지: 활성화")
        print("🔄 전환 패턴 감지: 활성화")
        print("📈 일관성 분석: 활성화")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 프레임 처리
            processed_frame, gesture, confidence, debug_info = self.process_frame(frame)
            
            # 정보 오버레이
            final_frame = self.draw_adaptive_info(processed_frame, gesture, confidence, debug_info)
            
            # 화면 출력
            cv2.imshow('Improved PDS - Advanced Gesture Recognition', final_frame)
            
            # 종료 조건
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # 개선된 적응형 실시간 테스트
    detector = ImprovedAdaptiveWindowPoseDetector()
    detector.run_camera() 