#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
데모 영상 생성 및 실시간 모델 검증
랜덤하게 선택된 제스처 영상들을 이어붙여서 연속적인 데모를 만들고,
학습된 TCN 모델로 실시간 예측하여 성능을 검증
"""

import cv2
import numpy as np
import torch
import random
import os
from pathlib import Path
from collections import deque
import time
from datetime import datetime

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import GESTURE_CLASSES, MEDIAPIPE_CONFIG, PATHS
from model import GestureModelManager
from pose_estimator import RealTimePoseDetector
from utils import setup_logging

class DemoVideoCreator:
    """데모 영상 생성 및 실시간 검증"""
    
    def __init__(self):
        self.logger = setup_logging()
        self.pose_data_path = Path('../pose_data_rotated')
        self.gesture_classes = GESTURE_CLASSES
        self.gesture_colors = {
            'stop': (0, 0, 255),      # Red
            'forward': (0, 255, 0),   # Green
            'left': (255, 0, 0),      # Blue
            'right': (0, 255, 255)    # Yellow
        }
        
        # 모델 로드
        self.model_manager = GestureModelManager()
        self.model = self.model_manager.load_model()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)
        self.model.eval()
        
        # 자세 추정기
        self.pose_estimator = RealTimePoseDetector()
        
        # 실시간 예측을 위한 버퍼
        self.pose_buffer = deque(maxlen=30)  # 30프레임 = 1초
        
        self.logger.info("데모 검증 시스템 초기화 완료")
    
    def select_random_videos(self, videos_per_gesture: int = 3) -> list:
        """각 제스처별로 랜덤하게 영상 선택"""
        selected_videos = []
        
        for gesture_name in self.gesture_classes.values():
            gesture_folder = self.pose_data_path / gesture_name
            
            if not gesture_folder.exists():
                self.logger.warning(f"{gesture_name} 폴더가 없습니다: {gesture_folder}")
                continue
            
            # 해당 제스처의 모든 영상 파일
            video_files = list(gesture_folder.glob("*.mp4"))
            
            if len(video_files) < videos_per_gesture:
                self.logger.warning(f"{gesture_name}에 충분한 영상이 없습니다. {len(video_files)}개만 사용")
                selected = video_files
            else:
                selected = random.sample(video_files, videos_per_gesture)
            
            for video_file in selected:
                selected_videos.append({
                    'path': video_file,
                    'gesture': gesture_name,
                    'expected_label': list(self.gesture_classes.keys())[list(self.gesture_classes.values()).index(gesture_name)]
                })
        
        # 랜덤하게 섞기
        random.shuffle(selected_videos)
        
        self.logger.info(f"총 {len(selected_videos)}개 영상 선택됨")
        for video in selected_videos:
            self.logger.info(f"  - {video['gesture']}: {video['path'].name}")
        
        return selected_videos
    
    def create_concatenated_demo(self, selected_videos: list, output_path: str = None) -> str:
        """선택된 영상들을 이어붙여서 데모 영상 생성"""
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f'demo_videos/concatenated_demo_{timestamp}.mp4'
        
        # 출력 디렉토리 생성
        os.makedirs('demo_videos', exist_ok=True)
        
        # 첫 번째 영상의 속성 확인
        cap = cv2.VideoCapture(str(selected_videos[0]['path']))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        cap.release()
        
        # 비디오 라이터 설정
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        # 각 영상별 정보 저장 (나중에 예측 결과와 비교용)
        video_segments = []
        frame_count = 0
        
        self.logger.info("영상 이어붙이기 시작...")
        
        for i, video_info in enumerate(selected_videos):
            video_path = video_info['path']
            gesture = video_info['gesture']
            
            cap = cv2.VideoCapture(str(video_path))
            segment_start = frame_count
            
            self.logger.info(f"  [{i+1}/{len(selected_videos)}] {gesture}: {video_path.name}")
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 프레임에 제스처 정보 오버레이 (ground truth)
                color = self.gesture_colors[gesture]
                cv2.putText(frame, f'GT: {gesture.upper()}', (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
                
                out.write(frame)
                frame_count += 1
            
            cap.release()
            
            video_segments.append({
                'gesture': gesture,
                'start_frame': segment_start,
                'end_frame': frame_count - 1,
                'video_file': video_path.name
            })
        
        out.release()
        
        self.logger.info(f"데모 영상 생성 완료: {output_path}")
        self.logger.info(f"총 프레임 수: {frame_count}")
        
        # 세그먼트 정보 저장
        segments_info_path = output_path.replace('.mp4', '_segments.json')
        import json
        with open(segments_info_path, 'w', encoding='utf-8') as f:
            json.dump(video_segments, f, indent=2, ensure_ascii=False)
        
        return output_path, video_segments
    
    def predict_pose_sequence(self, pose_sequence: np.ndarray) -> tuple:
        """자세 시퀀스에 대한 TCN 모델 예측"""
        if len(pose_sequence) < 30:
            return None, 0.0
        
        # 최근 30프레임 사용
        input_sequence = pose_sequence[-30:]  # (30, 17, 2)
        
        # 텐서로 변환
        input_tensor = torch.FloatTensor(input_sequence).unsqueeze(0).to(self.device)  # (1, 30, 17, 2)
        
        with torch.no_grad():
            output = self.model(input_tensor)
            probabilities = torch.softmax(output, dim=1)
            confidence, predicted_class = torch.max(probabilities, 1)
            
            predicted_gesture = self.gesture_classes[predicted_class.item()]
            confidence_score = confidence.item()
        
        return predicted_gesture, confidence_score
    
    def run_realtime_validation(self, demo_video_path: str, video_segments: list):
        """데모 영상에 대한 실시간 예측 및 검증"""
        self.logger.info("실시간 검증 시작...")
        
        cap = cv2.VideoCapture(demo_video_path)
        
        # 결과 저장용
        results = []
        frame_idx = 0
        
        # 예측 결과 영상 저장
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        
        output_path = demo_video_path.replace('.mp4', '_with_predictions.mp4')
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        self.logger.info("프레임별 예측 시작...")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 현재 프레임의 ground truth 찾기
            current_gt = None
            for segment in video_segments:
                if segment['start_frame'] <= frame_idx <= segment['end_frame']:
                    current_gt = segment['gesture']
                    break
            
            # 자세 추정
            pose_landmarks = self.pose_estimator.process_frame(frame)
            
            prediction = None
            confidence = 0.0
            
            if pose_landmarks is not None:
                # 정규화된 자세 데이터 추출
                pose_data = self.pose_estimator.extract_keypoints(pose_landmarks)
                self.pose_buffer.append(pose_data)
                
                # 충분한 프레임이 모이면 예측
                if len(self.pose_buffer) == 30:
                    pose_sequence = np.array(list(self.pose_buffer))
                    prediction, confidence = self.predict_pose_sequence(pose_sequence)
            
            # 결과 기록
            result = {
                'frame': frame_idx,
                'ground_truth': current_gt,
                'prediction': prediction,
                'confidence': confidence,
                'correct': prediction == current_gt if prediction else False
            }
            results.append(result)
            
            # 프레임에 예측 결과 오버레이
            display_frame = frame.copy()
            
            # Ground Truth (위쪽)
            if current_gt:
                gt_color = self.gesture_colors[current_gt]
                cv2.putText(display_frame, f'GT: {current_gt.upper()}', (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, gt_color, 2)
            
            # Prediction (아래쪽)
            if prediction:
                pred_color = self.gesture_colors[prediction]
                cv2.putText(display_frame, f'PRED: {prediction.upper()} ({confidence:.2f})', 
                           (10, height - 40), cv2.FONT_HERSHEY_SIMPLEX, 1, pred_color, 2)
                
                # 정확성 표시
                if result['correct']:
                    cv2.putText(display_frame, 'CORRECT', (width - 150, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                else:
                    cv2.putText(display_frame, 'WRONG', (width - 120, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # 프레임 번호
            cv2.putText(display_frame, f'Frame: {frame_idx}', (10, height - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            out.write(display_frame)
            
            if frame_idx % 100 == 0:
                self.logger.info(f"  처리된 프레임: {frame_idx}")
            
            frame_idx += 1
        
        cap.release()
        out.release()
        
        # 결과 분석
        self.analyze_results(results, demo_video_path, video_segments)
        
        self.logger.info(f"예측 결과 영상 저장: {output_path}")
        
        return results, output_path
    
    def analyze_results(self, results: list, demo_video_path: str, video_segments: list):
        """검증 결과 분석 및 출력"""
        self.logger.info("\n" + "="*60)
        self.logger.info("📊 실시간 검증 결과 분석")
        self.logger.info("="*60)
        
        # 전체 정확도
        total_frames = len([r for r in results if r['prediction'] is not None])
        correct_predictions = len([r for r in results if r['correct']])
        
        if total_frames > 0:
            overall_accuracy = correct_predictions / total_frames
            self.logger.info(f"🎯 전체 정확도: {overall_accuracy:.4f} ({correct_predictions}/{total_frames})")
        
        # 제스처별 정확도
        self.logger.info("\n📈 제스처별 성능:")
        for gesture in self.gesture_classes.values():
            gesture_results = [r for r in results if r['ground_truth'] == gesture and r['prediction'] is not None]
            if gesture_results:
                gesture_correct = len([r for r in gesture_results if r['correct']])
                gesture_accuracy = gesture_correct / len(gesture_results)
                avg_confidence = np.mean([r['confidence'] for r in gesture_results])
                
                self.logger.info(f"  {gesture:8s}: {gesture_accuracy:.4f} ({gesture_correct:3d}/{len(gesture_results):3d}) | 평균 신뢰도: {avg_confidence:.3f}")
        
        # 세그먼트별 분석
        self.logger.info("\n📋 영상 세그먼트별 성능:")
        for i, segment in enumerate(video_segments):
            segment_results = [r for r in results 
                             if segment['start_frame'] <= r['frame'] <= segment['end_frame'] 
                             and r['prediction'] is not None]
            
            if segment_results:
                segment_correct = len([r for r in segment_results if r['correct']])
                segment_accuracy = segment_correct / len(segment_results)
                
                self.logger.info(f"  [{i+1:2d}] {segment['gesture']:8s} ({segment['video_file']}): "
                               f"{segment_accuracy:.4f} ({segment_correct:3d}/{len(segment_results):3d})")
        
        # 혼동행렬 데이터
        self.logger.info("\n🔍 혼동 행렬 (예측 vs 실제):")
        confusion_data = {}
        for gesture in self.gesture_classes.values():
            confusion_data[gesture] = {g: 0 for g in self.gesture_classes.values()}
        
        for result in results:
            if result['prediction'] and result['ground_truth']:
                confusion_data[result['ground_truth']][result['prediction']] += 1
        
        # 혼동행렬 출력
        header = "     " + "".join([f"{g:8s}" for g in self.gesture_classes.values()])
        self.logger.info(header)
        for true_gesture in self.gesture_classes.values():
            row = f"{true_gesture:8s}:"
            for pred_gesture in self.gesture_classes.values():
                count = confusion_data[true_gesture][pred_gesture]
                row += f"{count:8d}"
            self.logger.info(row)
    
    def run_full_validation(self, videos_per_gesture: int = 2):
        """전체 검증 파이프라인 실행"""
        self.logger.info("🎯 데모 영상 검증 시작")
        self.logger.info("="*60)
        
        # 1. 랜덤 영상 선택
        selected_videos = self.select_random_videos(videos_per_gesture)
        
        # 2. 데모 영상 생성
        demo_path, segments = self.create_concatenated_demo(selected_videos)
        
        # 3. 실시간 검증
        results, prediction_video = self.run_realtime_validation(demo_path, segments)
        
        self.logger.info("\n✅ 검증 완료!")
        self.logger.info(f"📹 원본 데모: {demo_path}")
        self.logger.info(f"🎯 예측 결과: {prediction_video}")
        
        return {
            'demo_video': demo_path,
            'prediction_video': prediction_video,
            'results': results,
            'segments': segments
        }

if __name__ == "__main__":
    print("🎯 데모 영상 생성 및 검증 스크립트")
    
    # 간단한 테스트
    creator = DemoVideoCreator()
    selected = creator.select_random_videos(videos_per_gesture=2)
    demo_path, segments = creator.create_concatenated_demo(selected)
    
    print(f"✅ 데모 영상 생성 완료: {demo_path}") 