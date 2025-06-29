# -*- coding: utf-8 -*-
"""
Real-time Pose Detection and Gesture Recognition
실시간 자세 검출 및 제스처 인식
"""

import cv2
import mediapipe as mp
import numpy as np
import torch
import os
from collections import deque
from typing import Optional, Tuple, List
import time

from config import DATA_CONFIG, MEDIAPIPE_CONFIG, GESTURE_CLASSES, TCN_CONFIG
from model import GestureModelManager

class RealTimePoseDetector:
    """실시간 자세 검출 및 제스처 인식"""
    
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
        
        # 시계열 버퍼 (30프레임)
        self.pose_buffer = deque(maxlen=TCN_CONFIG['sequence_length'])
        
        # 모델 로드
        self.model_manager = GestureModelManager(model_path)
        self.model = self.model_manager.load_model()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # 예측 결과 추적
        self.last_prediction = None
        self.last_confidence = 0.0
        self.prediction_history = deque(maxlen=10)  # 스무딩용
        
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
    
    def predict_gesture(self) -> Tuple[Optional[str], float]:
        """현재 버퍼 상태로 제스처 예측"""
        if len(self.pose_buffer) < TCN_CONFIG['sequence_length'] or self.model is None:
            return None, 0.0
        
        # 버퍼를 텐서로 변환
        pose_sequence = np.array(list(self.pose_buffer))  # (30, 17, 2)
        pose_sequence = pose_sequence.reshape(pose_sequence.shape[0], -1)  # (30, 34)
        
        # 배치 차원 추가
        input_tensor = torch.FloatTensor(pose_sequence).unsqueeze(0).to(self.device)  # (1, 30, 34)
        
        # 예측
        predictions, confidences, probabilities = self.model.predict(input_tensor)
        
        predicted_class = predictions[0].item()
        confidence = confidences[0].item()
        
        # 예측 이력에 추가 (스무딩)
        self.prediction_history.append((predicted_class, confidence))
        
        # 스무딩된 예측 (최빈값 + 평균 신뢰도)
        if len(self.prediction_history) >= 5:
            recent_predictions = list(self.prediction_history)[-5:]
            classes = [pred[0] for pred in recent_predictions]
            confidences_list = [pred[1] for pred in recent_predictions]
            
            # 최빈 클래스
            most_common_class = max(set(classes), key=classes.count)
            avg_confidence = np.mean(confidences_list)
            
            gesture_name = GESTURE_CLASSES[most_common_class]
            return gesture_name, avg_confidence
        
        gesture_name = GESTURE_CLASSES[predicted_class]
        return gesture_name, confidence
    
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, Optional[str], float]:
        """프레임 처리 및 제스처 인식"""
        # 자세 추출
        pose_result = self.extract_pose_landmarks(frame)
        
        if pose_result[0] is not None:
            pose_data, results = pose_result
            
            # 정규화
            normalized_pose = self.normalize_pose_data(pose_data)
            
            # 버퍼에 추가 (x, y 좌표만)
            self.pose_buffer.append(normalized_pose[:, :2])
            
            # 스켈레톤 그리기
            annotated_frame = frame.copy()
            self.mp_drawing.draw_landmarks(
                annotated_frame, results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS)
            
            # 제스처 예측
            gesture, confidence = self.predict_gesture()
            
            # 결과 업데이트
            if gesture and confidence > 0.7:  # 신뢰도 임계값
                self.last_prediction = gesture
                self.last_confidence = confidence
            
            return annotated_frame, self.last_prediction, self.last_confidence
        
        return frame, self.last_prediction, self.last_confidence
    
    def draw_info(self, frame: np.ndarray, gesture: Optional[str], confidence: float) -> np.ndarray:
        """정보 오버레이 그리기"""
        height, width = frame.shape[:2]
        
        # FPS 계산
        self.fps_counter += 1
        if time.time() - self.fps_start_time >= 1.0:
            fps = self.fps_counter / (time.time() - self.fps_start_time)
            self.fps_counter = 0
            self.fps_start_time = time.time()
            self.current_fps = fps
        
        # 정보 텍스트
        info_text = [
            f"FPS: {getattr(self, 'current_fps', 0):.1f}",
            f"Buffer: {len(self.pose_buffer)}/{TCN_CONFIG['sequence_length']}",
        ]
        
        if gesture:
            info_text.append(f"Gesture: {gesture}")
            info_text.append(f"Confidence: {confidence:.2f}")
        
        # 텍스트 그리기
        y_offset = 30
        for text in info_text:
            cv2.putText(frame, text, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, (0, 255, 0), 2)
            y_offset += 25
        
        # 제스처 상태 표시
        if gesture and confidence > 0.8:
            # 고신뢰도 제스처는 빨간색 박스로 강조
            cv2.rectangle(frame, (width-200, 10), (width-10, 100), (0, 0, 255), 2)
            cv2.putText(frame, gesture, (width-190, 40), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.8, (0, 0, 255), 2)
            cv2.putText(frame, f"{confidence:.2f}", (width-190, 70), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, (0, 0, 255), 2)
        
        return frame
    
    def run_camera(self, camera_index: int = 0):
        """카메라 실시간 처리"""
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            print(f"카메라를 열 수 없습니다: {camera_index}")
            return
        
        print("실시간 제스처 인식 시작 (q 키로 종료)")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 프레임 처리
            processed_frame, gesture, confidence = self.process_frame(frame)
            
            # 정보 오버레이
            final_frame = self.draw_info(processed_frame, gesture, confidence)
            
            # 화면 출력
            cv2.imshow('PDS TCN - Gesture Recognition', final_frame)
            
            # 종료 조건
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # 실시간 테스트
    detector = RealTimePoseDetector()
    detector.run_camera() 