# -*- coding: utf-8 -*-
"""
Gesture Dataset for PyTorch Training
제스처 데이터셋 로더
"""

import torch
from torch.utils.data import Dataset, DataLoader
import numpy as np
import os
import json
from pathlib import Path
from typing import Tuple, List, Dict
from sklearn.model_selection import train_test_split
from config import GESTURE_CLASSES, PATHS, TRAINING_CONFIG

class GestureDataset(Dataset):
    """제스처 데이터셋"""
    
    def __init__(self, data_root: str = None, split: str = 'train', test_size: float = 0.2, 
                 random_state: int = 42, transform=None):
        """
        Args:
            data_root: 처리된 데이터 루트 폴더
            split: 'train', 'test', 'all'
            test_size: 테스트 데이터 비율
            random_state: 랜덤 시드
            transform: 데이터 변환 함수
        """
        if data_root is None:
            data_root = PATHS['processed_data']
            
        self.data_root = Path(data_root)
        self.split = split
        self.transform = transform
        
        # 데이터 로드
        self.data_paths, self.labels = self._load_data_paths()
        
        # Train/Test 분할
        if split in ['train', 'test']:
            self._split_data(test_size, random_state)
    
    def _load_data_paths(self) -> Tuple[List[str], List[int]]:
        """데이터 파일 경로와 라벨 로드"""
        data_paths = []
        labels = []
        
        # 각 제스처 폴더에서 .npy 파일 수집
        for gesture_id, gesture_name in GESTURE_CLASSES.items():
            gesture_folder = self.data_root / gesture_name.lower()
            
            if not gesture_folder.exists():
                print(f"경고: 폴더를 찾을 수 없습니다 - {gesture_folder}")
                continue
                
            npy_files = list(gesture_folder.glob("*.npy"))
            
            for npy_file in npy_files:
                data_paths.append(str(npy_file))
                labels.append(gesture_id)
                
            print(f"{gesture_name}: {len(npy_files)}개 샘플")
        
        print(f"총 {len(data_paths)}개 샘플 로드 완료")
        return data_paths, labels
    
    def _split_data(self, test_size: float, random_state: int):
        """데이터 분할"""
        if len(self.data_paths) == 0:
            return
            
        # Stratified split (클래스별 비율 유지)
        train_paths, test_paths, train_labels, test_labels = train_test_split(
            self.data_paths, self.labels, 
            test_size=test_size, 
            random_state=random_state,
            stratify=self.labels
        )
        
        if self.split == 'train':
            self.data_paths = train_paths
            self.labels = train_labels
        elif self.split == 'test':
            self.data_paths = test_paths
            self.labels = test_labels
            
        print(f"{self.split.upper()} 데이터: {len(self.data_paths)}개")
    
    def __len__(self) -> int:
        return len(self.data_paths)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """데이터 샘플 반환"""
        # .npy 파일 로드
        data_path = self.data_paths[idx]
        pose_data = np.load(data_path)  # shape: (30, 17, 2)
        
        # (30, 17, 2) -> (30, 34) 변환
        pose_data = pose_data.reshape(pose_data.shape[0], -1)
        
        # 텐서 변환
        pose_tensor = torch.FloatTensor(pose_data)
        label_tensor = torch.LongTensor([self.labels[idx]])[0]
        
        # 변환 적용
        if self.transform:
            pose_tensor = self.transform(pose_tensor)
            
        return pose_tensor, label_tensor
    
    def get_class_weights(self) -> torch.Tensor:
        """클래스 불균형 해결을 위한 가중치 계산"""
        label_counts = torch.bincount(torch.tensor(self.labels))
        total_samples = len(self.labels)
        
        # 역수 가중치 계산
        weights = total_samples / (len(label_counts) * label_counts.float())
        
        return weights
    
    def get_dataset_stats(self) -> Dict:
        """데이터셋 통계 정보"""
        stats = {
            'total_samples': len(self.data_paths),
            'classes': {},
            'class_distribution': {}
        }
        
        # 클래스별 샘플 수
        for gesture_id, gesture_name in GESTURE_CLASSES.items():
            count = self.labels.count(gesture_id)
            stats['classes'][gesture_name] = count
            stats['class_distribution'][gesture_name] = count / len(self.labels) if len(self.labels) > 0 else 0
        
        return stats

class DataAugmentation:
    """데이터 증강"""
    
    def __init__(self, noise_std: float = 0.01, rotation_angle: float = 5.0):
        self.noise_std = noise_std
        self.rotation_angle = rotation_angle
    
    def add_noise(self, pose_data: torch.Tensor) -> torch.Tensor:
        """가우시안 노이즈 추가"""
        noise = torch.randn_like(pose_data) * self.noise_std
        return pose_data + noise
    
    def temporal_shift(self, pose_data: torch.Tensor, max_shift: int = 3) -> torch.Tensor:
        """시간축 이동"""
        shift = torch.randint(-max_shift, max_shift + 1, (1,)).item()
        
        if shift > 0:
            # 앞쪽으로 이동 (뒤쪽 패딩)
            padded = torch.cat([pose_data[shift:], pose_data[-shift:]])
        elif shift < 0:
            # 뒤쪽으로 이동 (앞쪽 패딩)  
            shift = abs(shift)
            padded = torch.cat([pose_data[:shift], pose_data[:-shift]])
        else:
            padded = pose_data
            
        return padded
    
    def scale_transform(self, pose_data: torch.Tensor, scale_factor: float = 0.1) -> torch.Tensor:
        """스케일 변환"""
        scale = 1.0 + (torch.rand(1) * 2 * scale_factor - scale_factor).item()
        return pose_data * scale
    
    def __call__(self, pose_data: torch.Tensor) -> torch.Tensor:
        """랜덤 증강 적용"""
        # 50% 확률로 각 증강 적용
        if torch.rand(1) < 0.5:
            pose_data = self.add_noise(pose_data)
        
        if torch.rand(1) < 0.3:
            pose_data = self.temporal_shift(pose_data)
            
        if torch.rand(1) < 0.3:
            pose_data = self.scale_transform(pose_data)
        
        return pose_data

def create_dataloaders(data_root: str = None, batch_size: int = None, 
                      num_workers: int = None, augment_train: bool = True) -> Tuple[DataLoader, DataLoader]:
    """데이터 로더 생성"""
    
    if batch_size is None:
        batch_size = TRAINING_CONFIG['batch_size']
    if num_workers is None:
        num_workers = TRAINING_CONFIG['num_workers']
    
    # 데이터 증강
    transform = DataAugmentation() if augment_train else None
    
    # 데이터셋 생성
    train_dataset = GestureDataset(
        data_root=data_root, 
        split='train', 
        test_size=1 - TRAINING_CONFIG['train_test_split'],
        transform=transform
    )
    
    test_dataset = GestureDataset(
        data_root=data_root,
        split='test',
        test_size=1 - TRAINING_CONFIG['train_test_split']
    )
    
    # 데이터 로더 생성
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=True
    )
    
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )
    
    return train_loader, test_loader

def analyze_dataset(data_root: str = None):
    """데이터셋 분석"""
    dataset = GestureDataset(data_root=data_root, split='all')
    
    if len(dataset) == 0:
        print("데이터셋이 비어있습니다!")
        return
    
    stats = dataset.get_dataset_stats()
    
    print("=== 데이터셋 분석 ===")
    print(f"총 샘플 수: {stats['total_samples']}")
    print("\n클래스별 분포:")
    
    for gesture_name, count in stats['classes'].items():
        percentage = stats['class_distribution'][gesture_name] * 100
        print(f"  {gesture_name}: {count}개 ({percentage:.1f}%)")
    
    # 샘플 데이터 확인
    sample_data, sample_label = dataset[0]
    print(f"\n샘플 데이터 형태: {sample_data.shape}")
    print(f"샘플 라벨: {sample_label} ({GESTURE_CLASSES[sample_label.item()]})")

if __name__ == "__main__":
    # 데이터셋 분석
    analyze_dataset()
    
    # 데이터 로더 테스트
    try:
        train_loader, test_loader = create_dataloaders()
        
        print(f"\n학습 배치 수: {len(train_loader)}")
        print(f"테스트 배치 수: {len(test_loader)}")
        
        # 첫 번째 배치 확인
        for batch_data, batch_labels in train_loader:
            print(f"배치 데이터 형태: {batch_data.shape}")
            print(f"배치 라벨 형태: {batch_labels.shape}")
            print(f"라벨 값: {batch_labels}")
            break
            
    except Exception as e:
        print(f"데이터 로더 생성 실패: {e}")
        print("먼저 데이터 전처리를 실행하세요: python data_preprocessor.py") 