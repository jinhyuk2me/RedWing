#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시각적 데모 영상 생성
학습된 TCN 모델의 예측을 실시간으로 오버레이하는 데모 영상 생성
"""

import cv2
import numpy as np
import torch
import json
import mediapipe as mp
from pathlib import Path
from collections import deque
from datetime import datetime

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import GESTURE_CLASSES, MEDIAPIPE_CONFIG
from model import GestureModelManager
from utils import setup_logging

class VisualDemoCreator:
    """시각적 데모 영상 생성기"""
    
    def __init__(self):
        self.logger = setup_logging()
        
        # MediaPipe 초기화
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        
        # 모델 로드
        self.model_manager = GestureModelManager()
        self.model = self.model_manager.load_model()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)
        self.model.eval()
        
        # 자세 버퍼
        self.pose_buffer = deque(maxlen=30)
        self.key_landmarks = MEDIAPIPE_CONFIG['key_landmarks']
        
        # 색상 정의
        self.colors = {
            'stop': (0, 0, 255),      # Red
            'forward': (0, 255, 0),   # Green  
            'left': (255, 0, 0),      # Blue
            'right': (0, 255, 255),   # Yellow
            'background': (0, 0, 0),   # Black
            'text': (255, 255, 255),   # White
            'skeleton': (255, 128, 0)  # Orange
        }
        
        self.logger.info("시각적 데모 생성기 초기화 완료")
    
    def extract_pose_landmarks(self, frame):
        """자세 추출 (학습 데이터와 동일한 방식)"""
        height, width = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False
        
        results = self.pose.process(rgb_frame)
        
        if results.pose_landmarks:
            pose_data = []
            for idx in self.key_landmarks:
                landmark = results.pose_landmarks.landmark[idx]
                pose_data.append([landmark.x, landmark.y, landmark.visibility])
            
            return np.array(pose_data, dtype=np.float32), results
        
        return None, results
    
    def normalize_pose_data(self, pose_data):
        """정규화 (학습 데이터와 동일한 방식)"""
        if pose_data.shape[0] == 0:
            return pose_data
            
        normalized_pose = pose_data.copy()
        
        # Hip 중심점 계산
        left_hip = pose_data[9]
        right_hip = pose_data[10]
        
        if left_hip[2] > 0.5 and right_hip[2] > 0.5:
            center = (left_hip[:2] + right_hip[:2]) / 2
            
            # 상대 좌표로 변환
            for joint_idx in range(len(self.key_landmarks)):
                if pose_data[joint_idx][2] > 0.5:
                    normalized_pose[joint_idx][:2] -= center
            
            # 스케일 정규화
            left_shoulder = pose_data[3]
            right_shoulder = pose_data[4]
            
            if left_shoulder[2] > 0.5 and right_shoulder[2] > 0.5:
                shoulder_width = np.linalg.norm(left_shoulder[:2] - right_shoulder[:2])
                if shoulder_width > 0:
                    normalized_pose[:, :2] /= shoulder_width
        
        return normalized_pose
    
    def predict_gesture(self, pose_sequence):
        """제스처 예측"""
        if len(pose_sequence) < 30:
            return None, 0.0
        
        # 최근 30프레임 사용
        input_sequence = np.array(pose_sequence[-30:])  # (30, 17, 3)
        input_sequence = input_sequence[:, :, :2]  # (30, 17, 2) - x,y만
        input_sequence = input_sequence.reshape(input_sequence.shape[0], -1)  # (30, 34)
        
        # 예측
        input_tensor = torch.FloatTensor(input_sequence).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            output = self.model(input_tensor)
            probabilities = torch.softmax(output, dim=1)
            confidence, predicted_class = torch.max(probabilities, 1)
            
            predicted_gesture = GESTURE_CLASSES[predicted_class.item()]
            confidence_score = confidence.item()
        
        return predicted_gesture, confidence_score
    
    def draw_enhanced_overlay(self, frame, gt_gesture, prediction, confidence, frame_info, pose_results):
        """향상된 시각적 오버레이"""
        height, width = frame.shape[:2]
        
        # 반투명 오버레이 패널 생성
        overlay = frame.copy()
        
        # 상단 정보 패널 (반투명 검은 배경)
        cv2.rectangle(overlay, (0, 0), (width, 120), self.colors['background'], -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # 하단 정보 패널
        cv2.rectangle(overlay, (0, height-80), (width, height), self.colors['background'], -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # 자세 스켈레톤 그리기 (개선된 스타일)
        if pose_results.pose_landmarks:
            # 스켈레톤을 더 굵고 눈에 띄게
            self.mp_drawing.draw_landmarks(
                frame, 
                pose_results.pose_landmarks, 
                self.mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=self.mp_drawing.DrawingSpec(
                    color=self.colors['skeleton'], thickness=4, circle_radius=6),
                connection_drawing_spec=self.mp_drawing.DrawingSpec(
                    color=self.colors['skeleton'], thickness=3)
            )
        
        # Ground Truth (왼쪽 상단)
        if gt_gesture:
            gt_color = self.colors[gt_gesture]
            cv2.rectangle(frame, (10, 10), (300, 50), gt_color, 3)
            cv2.putText(frame, f'GROUND TRUTH: {gt_gesture.upper()}', (20, 35), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, gt_color, 2)
        
        # Prediction (오른쪽 상단)
        if prediction:
            pred_color = self.colors[prediction]
            cv2.rectangle(frame, (width-350, 10), (width-10, 50), pred_color, 3)
            cv2.putText(frame, f'PREDICTION: {prediction.upper()}', (width-340, 35), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, pred_color, 2)
            
            # 신뢰도 바 (오른쪽 상단)
            bar_width = int(300 * confidence)
            cv2.rectangle(frame, (width-350, 60), (width-50, 85), (64, 64, 64), -1)
            cv2.rectangle(frame, (width-350, 60), (width-350+bar_width, 85), pred_color, -1)
            cv2.putText(frame, f'Confidence: {confidence:.1%}', (width-340, 100), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['text'], 2)
        
        # 정확성 표시 (중앙 상단)
        if prediction and gt_gesture:
            is_correct = prediction == gt_gesture
            status_color = (0, 255, 0) if is_correct else (0, 0, 255)
            status_text = "CORRECT" if is_correct else "WRONG"
            
            # 큰 상태 표시
            cv2.rectangle(frame, (width//2-100, 10), (width//2+100, 50), status_color, 3)
            cv2.putText(frame, status_text, (width//2-80, 35), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
        
        # 프레임 정보 (하단 왼쪽)
        frame_text = f"Frame: {frame_info['current']}/{frame_info['total']} ({frame_info['progress']:.1f}%)"
        cv2.putText(frame, frame_text, (10, height-50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['text'], 2)
        
        # 세그먼트 정보 (하단 중앙)
        if 'segment' in frame_info:
            segment_text = f"Segment: {frame_info['segment']['gesture']} ({frame_info['segment']['progress']:.0f}%)"
            cv2.putText(frame, segment_text, (width//2-100, height-50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['text'], 2)
        
        # 모델 정보 (하단 오른쪽)
        cv2.putText(frame, "TCN Model", (width-150, height-50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['text'], 2)
        cv2.putText(frame, "89.6% Accuracy", (width-150, height-25), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['text'], 1)
        
        return frame
    
    def create_visual_demo(self, demo_path: str, segments_path: str):
        """시각적 데모 영상 생성"""
        
        # 세그먼트 정보 로드
        with open(segments_path, 'r', encoding='utf-8') as f:
            segments = json.load(f)
        
        self.logger.info(f"시각적 데모 영상 생성 시작: {demo_path}")
        
        cap = cv2.VideoCapture(demo_path)
        
        # 비디오 속성
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 출력 영상 설정
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f'demo_videos/visual_demo_{timestamp}.mp4'
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        frame_idx = 0
        correct_count = 0
        total_predictions = 0
        
        self.logger.info("시각적 오버레이 영상 생성 중...")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 현재 프레임의 ground truth 찾기
            current_gt = None
            current_segment = None
            for segment in segments:
                if segment['start_frame'] <= frame_idx <= segment['end_frame']:
                    current_gt = segment['gesture']
                    current_segment = segment
                    break
            
            # 자세 추정 및 예측
            pose_data, pose_results = self.extract_pose_landmarks(frame)
            
            prediction = None
            confidence = 0.0
            
            if pose_data is not None:
                normalized_pose = self.normalize_pose_data(pose_data)
                self.pose_buffer.append(normalized_pose)
                
                if len(self.pose_buffer) == 30:
                    prediction, confidence = self.predict_gesture(list(self.pose_buffer))
            
            # 프레임 정보 구성
            frame_info = {
                'current': frame_idx,
                'total': total_frames,
                'progress': (frame_idx / total_frames) * 100
            }
            
            if current_segment:
                segment_progress = ((frame_idx - current_segment['start_frame']) / 
                                  (current_segment['end_frame'] - current_segment['start_frame'])) * 100
                frame_info['segment'] = {
                    'gesture': current_segment['gesture'],
                    'progress': segment_progress
                }
            
            # 정확도 추적
            if prediction and current_gt:
                total_predictions += 1
                if prediction == current_gt:
                    correct_count += 1
            
            # 시각적 오버레이 적용
            visual_frame = self.draw_enhanced_overlay(
                frame, current_gt, prediction, confidence, frame_info, pose_results)
            
            out.write(visual_frame)
            
            # 진행 상황 로그
            if frame_idx % 100 == 0:
                current_accuracy = (correct_count / total_predictions * 100) if total_predictions > 0 else 0
                self.logger.info(f"  프레임 {frame_idx}/{total_frames} ({frame_info['progress']:.1f}%) - 현재 정확도: {current_accuracy:.1f}%")
            
            frame_idx += 1
        
        cap.release()
        out.release()
        
        # 최종 결과
        final_accuracy = (correct_count / total_predictions * 100) if total_predictions > 0 else 0
        
        self.logger.info(f"\n🎬 시각적 데모 영상 생성 완료!")
        self.logger.info(f"📹 출력 파일: {output_path}")
        self.logger.info(f"🎯 최종 정확도: {final_accuracy:.2f}% ({correct_count}/{total_predictions})")
        self.logger.info(f"📊 총 프레임: {total_frames}개")
        
        return output_path, final_accuracy

if __name__ == "__main__":
    # 가장 최근 데모 영상 찾기
    demo_dir = Path('demo_videos')
    if demo_dir.exists():
        demo_files = list(demo_dir.glob('concatenated_demo_*.mp4'))
        if demo_files:
            # 가장 최근 파일
            latest_demo = sorted(demo_files)[-1]
            segments_file = str(latest_demo).replace('.mp4', '_segments.json')
            
            if Path(segments_file).exists():
                print(f"🎬 시각적 데모 영상 생성 시작: {latest_demo.name}")
                
                creator = VisualDemoCreator()
                output_path, accuracy = creator.create_visual_demo(str(latest_demo), segments_file)
                
                print(f"\n✅ 시각적 데모 생성 완료!")
                print(f"📹 결과 영상: {output_path}")
                print(f"🎯 정확도: {accuracy:.2f}%")
                print(f"\n🎥 영상을 재생해서 실시간 예측 결과를 확인하세요!")
            else:
                print(f"❌ 세그먼트 파일을 찾을 수 없습니다: {segments_file}")
        else:
            print("❌ 데모 영상이 없습니다.")
    else:
        print("❌ demo_videos 폴더가 없습니다.") 