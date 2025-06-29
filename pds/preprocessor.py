# -*- coding: utf-8 -*-
"""
PDS TCN Data Preprocessor
MP4 영상에서 자세 데이터 추출 및 전처리
"""

import cv2
import mediapipe as mp
import numpy as np
import os
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging
from config import DATA_CONFIG, MEDIAPIPE_CONFIG, GESTURE_CLASSES, PATHS

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PoseDataPreprocessor:
    """MP4 영상에서 자세 데이터 추출 및 전처리"""
    
    def __init__(self):
        # MediaPipe 설정 (경고 해결을 위한 개선된 설정)
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
        
        # 제스처 클래스 매핑 (폴더명과 ID 매핑)
        self.gesture_classes = {v: k for k, v in GESTURE_CLASSES.items()}
        
        # MediaPipe 관절 인덱스
        self.key_landmarks = MEDIAPIPE_CONFIG['key_landmarks']
    
    def validate_paths(self) -> bool:
        """
        경로 검증 및 필요한 폴더 생성
        
        Returns:
            bool: 모든 경로가 유효하면 True
        """
        logger.info("=== 경로 검증 시작 ===")
        
        # 원본 데이터 경로 확인
        raw_data_path = Path(PATHS['raw_data'])
        if not raw_data_path.exists():
            logger.error(f"❌ 원본 데이터 폴더를 찾을 수 없습니다: {raw_data_path.absolute()}")
            return False
        
        logger.info(f"✅ 원본 데이터 폴더: {raw_data_path.absolute()}")
        
        # 제스처 폴더 확인
        missing_gestures = []
        gesture_stats = {}
        
        for gesture_name in GESTURE_CLASSES.values():
            gesture_folder = raw_data_path / gesture_name
            if gesture_folder.exists():
                mp4_files = list(gesture_folder.glob("*.mp4"))
                gesture_stats[gesture_name] = len(mp4_files)
                logger.info(f"✅ {gesture_name}: {len(mp4_files)}개 영상 파일")
            else:
                missing_gestures.append(gesture_name)
                logger.warning(f"❌ {gesture_name} 폴더 없음: {gesture_folder}")
        
        if missing_gestures:
            logger.error(f"❌ 누락된 제스처 폴더들: {missing_gestures}")
            return False
        
        # 처리된 데이터 경로 생성
        processed_data_path = Path(PATHS['processed_data'])
        if not processed_data_path.exists():
            logger.info(f"📁 처리된 데이터 폴더 생성: {processed_data_path.absolute()}")
            processed_data_path.mkdir(parents=True, exist_ok=True)
        else:
            logger.info(f"✅ 처리된 데이터 폴더: {processed_data_path.absolute()}")
        
        # 로그 폴더 확인
        logs_path = Path(PATHS['logs'])
        if not logs_path.exists():
            logs_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 로그 폴더 생성: {logs_path.absolute()}")
        
        # 요약 출력
        total_videos = sum(gesture_stats.values())
        logger.info("=== 경로 검증 완료 ===")
        logger.info(f"📊 총 영상 파일: {total_videos}개")
        for gesture, count in gesture_stats.items():
            logger.info(f"   - {gesture}: {count}개")
        
        return True
    
    def cleanup_existing_data(self, output_root: str = None) -> bool:
        """
        기존 처리된 데이터 정리
        
        Args:
            output_root: 정리할 데이터 폴더 경로
            
        Returns:
            bool: 정리 성공시 True
        """
        if output_root is None:
            output_root = PATHS['processed_data']
            
        output_path = Path(output_root)
        
        if not output_path.exists():
            logger.info(f"🆕 새로운 처리: {output_path.absolute()}")
            return True
        
        logger.info("🧹 기존 처리된 데이터 정리 시작...")
        logger.info(f"📁 대상 폴더: {output_path.absolute()}")
        
        try:
            # 기존 .npy 파일들 삭제
            npy_files = list(output_path.rglob("*.npy"))
            json_files = list(output_path.rglob("*.json"))
            
            total_files = len(npy_files) + len(json_files)
            
            if total_files == 0:
                logger.info("✅ 정리할 파일이 없습니다.")
                return True
            
            logger.info(f"🗑️ 삭제할 파일들:")
            logger.info(f"   - .npy 파일: {len(npy_files)}개")
            logger.info(f"   - .json 파일: {len(json_files)}개")
            logger.info(f"   - 총 {total_files}개 파일")
            
            # .npy 파일들 삭제
            for npy_file in npy_files:
                npy_file.unlink()
                
            # .json 파일들 삭제  
            for json_file in json_files:
                json_file.unlink()
            
            # 빈 폴더들 정리
            for gesture_name in GESTURE_CLASSES.values():
                gesture_folder = output_path / gesture_name
                if gesture_folder.exists() and not any(gesture_folder.iterdir()):
                    gesture_folder.rmdir()
                    logger.info(f"📂 빈 폴더 삭제: {gesture_name}/")
            
            logger.info(f"✅ 정리 완료: {total_files}개 파일 삭제")
            return True
            
        except Exception as e:
            logger.error(f"❌ 파일 정리 중 오류 발생: {e}")
            return False
    
    def extract_pose_from_video(self, video_path: str) -> Optional[np.ndarray]:
        """
        MP4 영상에서 자세 좌표 추출
        
        Args:
            video_path: MP4 파일 경로
            
        Returns:
            shape: (frames, 17, 3) - 3D 좌표 (x, y, visibility)
        """
        try:
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                logger.error(f"영상 파일을 열 수 없습니다: {video_path}")
                return None
                
            poses = []
            frame_count = 0
            max_frames = 600  # 최대 20초 (30fps * 20초) 제한
            
            while frame_count < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # BGR -> RGB 변환 (MediaPipe 경고 해결을 위한 이미지 크기 정보 설정)
                height, width = frame.shape[:2]
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb_frame.flags.writeable = False
                
                # 자세 검출
                results = self.pose.process(rgb_frame)
                
                if results.pose_landmarks:
                    # 17개 주요 관절 좌표 추출
                    pose_data = []
                    for idx in self.key_landmarks:
                        landmark = results.pose_landmarks.landmark[idx]
                        pose_data.append([landmark.x, landmark.y, landmark.visibility])
                    
                    poses.append(pose_data)
                else:
                    # 자세 검출 실패 시 해당 프레임 건너뛰기 (누적 방지)
                    logger.debug(f"자세 검출 실패 - 프레임 {frame_count} 건너뛰기")
                    continue
                
                frame_count += 1
                
            cap.release()
            
            if not poses:
                logger.warning(f"자세를 검출할 수 없습니다: {video_path}")
                return None
                
            poses_array = np.array(poses, dtype=np.float32)
            logger.info(f"자세 추출 완료: {video_path} -> {poses_array.shape}")
            
            return poses_array
            
        except Exception as e:
            logger.error(f"자세 추출 오류 ({video_path}): {e}")
            return None
    
    def normalize_pose_data(self, pose_data: np.ndarray) -> np.ndarray:
        """
        자세 데이터 정규화
        - 중심점(hip) 기준으로 상대 좌표 변환
        - 스케일 정규화
        """
        if pose_data.shape[0] == 0:
            return pose_data
            
        normalized_poses = pose_data.copy()
        
        for frame_idx in range(pose_data.shape[0]):
            frame_pose = pose_data[frame_idx]
            
            # Hip 중심점 계산 (left_hip + right_hip) / 2
            left_hip = frame_pose[9]   # left_hip
            right_hip = frame_pose[10] # right_hip
            
            if left_hip[2] > 0.5 and right_hip[2] > 0.5:  # visibility 체크
                center = (left_hip[:2] + right_hip[:2]) / 2
                
                # 상대 좌표로 변환
                for joint_idx in range(len(self.key_landmarks)):
                    if frame_pose[joint_idx][2] > 0.5:  # visibility > 0.5
                        normalized_poses[frame_idx][joint_idx][:2] -= center
                
                # 스케일 정규화 (어깨 너비 기준)
                left_shoulder = frame_pose[3]   # left_shoulder
                right_shoulder = frame_pose[4]  # right_shoulder
                
                if left_shoulder[2] > 0.5 and right_shoulder[2] > 0.5:
                    shoulder_width = np.linalg.norm(left_shoulder[:2] - right_shoulder[:2])
                    if shoulder_width > 0:
                        normalized_poses[frame_idx][:, :2] /= shoulder_width
        
        return normalized_poses
    
    def create_sliding_windows(self, pose_data: np.ndarray, window_size: int = None, stride: int = None) -> List[np.ndarray]:
        """
        슬라이딩 윈도우로 시계열 데이터 생성
        """
        if window_size is None:
            window_size = DATA_CONFIG['window_size']
        if stride is None:
            stride = DATA_CONFIG['stride']
            
        if len(pose_data) < window_size:
            logger.warning(f"영상이 너무 짧습니다 ({len(pose_data)} < {window_size})")
            return []
        
        windows = []
        for i in range(0, len(pose_data) - window_size + 1, stride):
            window = pose_data[i:i + window_size]
            windows.append(window)
            
        return windows
    
    def process_video_folder(self, input_folder: str, output_folder: str, gesture_name: str):
        """
        폴더 내 모든 MP4 파일 처리
        """
        input_path = Path(input_folder)
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        
        gesture_id = self.gesture_classes.get(gesture_name, -1)
        if gesture_id == -1:
            logger.error(f"알 수 없는 제스처: {gesture_name}")
            return
        
        mp4_files = list(input_path.glob("*.mp4"))
        logger.info(f"{gesture_name} 제스처 처리 시작: {len(mp4_files)}개 파일")
        
        processed_count = 0
        for mp4_file in mp4_files:
            logger.info(f"처리 중: {mp4_file.name}")
            
            # 자세 추출
            pose_data = self.extract_pose_from_video(str(mp4_file))
            if pose_data is None:
                continue
                
            # 정규화
            normalized_pose = self.normalize_pose_data(pose_data)
            
            # 슬라이딩 윈도우
            windows = self.create_sliding_windows(normalized_pose)
            
            # 각 윈도우를 별도 파일로 저장
            for window_idx, window_data in enumerate(windows):
                output_filename = f"{gesture_name}_{mp4_file.stem}_w{window_idx:03d}.npy"
                output_file_path = output_path / output_filename
                
                # 데이터 저장 (x, y 좌표만 사용)
                window_xy = window_data[:, :, :2]  # shape: (30, 17, 2)
                np.save(output_file_path, window_xy)
                
            processed_count += 1
            logger.info(f"완료: {mp4_file.name} -> {len(windows)}개 윈도우")
        
        logger.info(f"{gesture_name} 제스처 처리 완료: {processed_count}/{len(mp4_files)}")
    
    def process_all_gestures(self, data_root: str = None, output_root: str = None):
        """
        모든 제스처 폴더 처리
        """
        if data_root is None:
            data_root = PATHS['raw_data']
        if output_root is None:
            output_root = PATHS['processed_data']
        
        # 🔍 경로 검증 먼저 수행
        if not self.validate_paths():
            logger.error("❌ 경로 검증 실패! 처리를 중단합니다.")
            return
        
        # 🧹 기존 데이터 정리
        if not self.cleanup_existing_data(output_root):
            logger.error("❌ 기존 데이터 정리 실패! 처리를 중단합니다.")
            return
            
        data_path = Path(data_root)
        logger.info(f"🎯 회전된 영상 데이터 처리 시작: {data_path.absolute()}")
        
        for gesture_name in GESTURE_CLASSES.values():
            gesture_folder = data_path / gesture_name
            
            if gesture_folder.exists():
                logger.info(f"=== {gesture_name.upper()} 제스처 처리 ===")
                self.process_video_folder(
                    str(gesture_folder),
                    f"{output_root}/{gesture_name}",
                    gesture_name
                )
            else:
                logger.warning(f"폴더를 찾을 수 없습니다: {gesture_folder}")
    
    def create_dataset_summary(self, output_root: str = None):
        """
        처리된 데이터셋 요약 정보 생성
        """
        if output_root is None:
            output_root = PATHS['processed_data']
            
        output_path = Path(output_root)
        summary = {
            "total_samples": 0,
            "gestures": {}
        }
        
        for gesture_id, gesture_name in GESTURE_CLASSES.items():
            gesture_folder = output_path / gesture_name
            if gesture_folder.exists():
                npy_files = list(gesture_folder.glob("*.npy"))
                sample_count = len(npy_files)
                
                summary["gestures"][gesture_name] = {
                    "id": gesture_id,
                    "samples": sample_count,
                    "folder": str(gesture_folder)
                }
                summary["total_samples"] += sample_count
                logger.info(f"{gesture_name}: {sample_count}개 샘플")
        
        # 요약 정보 저장
        summary_file = output_path / "dataset_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        logger.info(f"데이터셋 요약: 총 {summary['total_samples']}개 샘플")
        logger.info(f"요약 파일 저장: {summary_file}")
        
        return summary

    @staticmethod
    def cleanup_only(output_root: str = None):
        """
        정리 작업만 수행하는 독립적인 메서드
        
        Args:
            output_root: 정리할 데이터 폴더 경로
        """
        if output_root is None:
            output_root = PATHS['processed_data']
            
        logger.info("🧹 데이터 정리 모드")
        logger.info("=" * 40)
        
        # 임시 인스턴스 생성하여 정리 수행
        temp_preprocessor = PoseDataPreprocessor()
        
        if temp_preprocessor.cleanup_existing_data(output_root):
            logger.info("🎉 정리 완료!")
        else:
            logger.error("❌ 정리 실패!")

if __name__ == "__main__":
    import sys
    
    # 정리 모드 체크
    if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
        # 🧹 정리 모드
        PoseDataPreprocessor.cleanup_only()
    else:
        # 🎯 회전된 영상 데이터 전처리 시작
        logger.info("🎯 PDS TCN 전처리기 시작 - 회전된 영상 데이터 처리")
        logger.info("=" * 60)
        logger.info("💡 정리만 하려면: python preprocessor.py cleanup")
        logger.info("=" * 60)
        
        preprocessor = PoseDataPreprocessor()
        
        # 모든 제스처 처리
        logger.info("📹 회전된 영상에서 자세 데이터 추출 중...")
        preprocessor.process_all_gestures()
        
        # 데이터셋 요약
        logger.info("📊 처리된 데이터셋 요약 생성 중...")
        summary = preprocessor.create_dataset_summary()
        
        if summary and summary['total_samples'] > 0:
            logger.info("🎉 전처리 완료!")
            logger.info(f"✅ 총 {summary['total_samples']}개 학습 샘플 생성")
            logger.info("🚀 이제 train.py로 모델 학습을 시작할 수 있습니다!")
        else:
            logger.warning("⚠️ 처리된 샘플이 없습니다. 데이터를 확인해주세요.") 