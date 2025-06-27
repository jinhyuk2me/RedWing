# -*- coding: utf-8 -*-
"""
TCN Model for Gesture Recognition
시계열 제스처 인식을 위한 TCN 모델
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import os
from typing import List
from config import TCN_CONFIG

class TemporalBlock(nn.Module):
    """TCN의 기본 블록"""
    
    def __init__(self, n_inputs: int, n_outputs: int, kernel_size: int, stride: int, 
                 dilation: int, padding: int, dropout: float = 0.2):
        super(TemporalBlock, self).__init__()
        
        self.conv1 = nn.utils.weight_norm(nn.Conv1d(n_inputs, n_outputs, kernel_size,
                                                   stride=stride, padding=padding, dilation=dilation))
        self.chomp1 = Chomp1d(padding)
        self.relu1 = nn.ReLU()
        self.dropout1 = nn.Dropout(dropout)

        self.conv2 = nn.utils.weight_norm(nn.Conv1d(n_outputs, n_outputs, kernel_size,
                                                   stride=stride, padding=padding, dilation=dilation))
        self.chomp2 = Chomp1d(padding)
        self.relu2 = nn.ReLU()
        self.dropout2 = nn.Dropout(dropout)

        self.net = nn.Sequential(self.conv1, self.chomp1, self.relu1, self.dropout1,
                                self.conv2, self.chomp2, self.relu2, self.dropout2)
        self.downsample = nn.Conv1d(n_inputs, n_outputs, 1) if n_inputs != n_outputs else None
        self.relu = nn.ReLU()
        self.init_weights()

    def init_weights(self):
        """가중치 초기화"""
        self.conv1.weight.data.normal_(0, 0.01)
        self.conv2.weight.data.normal_(0, 0.01)
        if self.downsample is not None:
            self.downsample.weight.data.normal_(0, 0.01)

    def forward(self, x):
        out = self.net(x)
        res = x if self.downsample is None else self.downsample(x)
        return self.relu(out + res)

class Chomp1d(nn.Module):
    """패딩 제거를 위한 모듈"""
    
    def __init__(self, chomp_size):
        super(Chomp1d, self).__init__()
        self.chomp_size = chomp_size

    def forward(self, x):
        return x[:, :, :-self.chomp_size].contiguous()

class TemporalConvNet(nn.Module):
    """TCN 네트워크"""
    
    def __init__(self, num_inputs: int, num_channels: List[int], kernel_size: int = 2, dropout: float = 0.2):
        super(TemporalConvNet, self).__init__()
        layers = []
        num_levels = len(num_channels)
        
        for i in range(num_levels):
            dilation_size = 2 ** i
            in_channels = num_inputs if i == 0 else num_channels[i-1]
            out_channels = num_channels[i]
            layers += [TemporalBlock(in_channels, out_channels, kernel_size, stride=1, dilation=dilation_size,
                                   padding=(kernel_size-1) * dilation_size, dropout=dropout)]

        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)

class TCNGestureClassifier(nn.Module):
    """제스처 분류를 위한 TCN 모델"""
    
    def __init__(self, input_size: int = None, num_channels: List[int] = None, 
                 num_classes: int = None, kernel_size: int = None, dropout: float = None):
        super(TCNGestureClassifier, self).__init__()
        
        # 설정값 로드
        if input_size is None:
            input_size = TCN_CONFIG['input_size']
        if num_channels is None:
            num_channels = TCN_CONFIG['num_channels']
        if num_classes is None:
            num_classes = TCN_CONFIG['num_classes']
        if kernel_size is None:
            kernel_size = TCN_CONFIG['kernel_size']
        if dropout is None:
            dropout = TCN_CONFIG['dropout']
        
        self.tcn = TemporalConvNet(input_size, num_channels, kernel_size, dropout)
        
        # 분류 헤드
        self.classifier = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),  # Global Average Pooling
            nn.Flatten(),
            nn.Linear(num_channels[-1], 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes)
        )
        
        self.num_classes = num_classes
        
    def forward(self, x):
        """
        Args:
            x: (batch_size, sequence_length, input_size)
        Returns:
            logits: (batch_size, num_classes)
        """
        # TCN은 (batch, channels, sequence) 형태를 요구
        x = x.transpose(1, 2)  # (batch, input_size, sequence_length)
        
        # TCN 통과
        tcn_out = self.tcn(x)  # (batch, num_channels[-1], sequence_length)
        
        # 분류
        logits = self.classifier(tcn_out)
        
        return logits
    
    def predict(self, x):
        """예측 수행"""
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            probabilities = F.softmax(logits, dim=1)
            predictions = torch.argmax(logits, dim=1)
            confidences = torch.max(probabilities, dim=1)[0]
            
        return predictions, confidences, probabilities

class GestureModelManager:
    """모델 관리자"""
    
    def __init__(self, model_path: str = None):
        from config import PATHS
        
        self.model_path = model_path or PATHS['model_file']
        self.model = None
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
    def create_model(self):
        """새 모델 생성"""
        self.model = TCNGestureClassifier()
        self.model.to(self.device)
        return self.model
    
    def save_model(self, model: nn.Module, epoch: int = None, loss: float = None):
        """모델 저장"""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        
        checkpoint = {
            'model_state_dict': model.state_dict(),
            'model_config': {
                'input_size': TCN_CONFIG['input_size'],
                'num_channels': TCN_CONFIG['num_channels'],
                'num_classes': TCN_CONFIG['num_classes'],
                'kernel_size': TCN_CONFIG['kernel_size'],
                'dropout': TCN_CONFIG['dropout']
            }
        }
        
        if epoch is not None:
            checkpoint['epoch'] = epoch
        if loss is not None:
            checkpoint['loss'] = loss
            
        torch.save(checkpoint, self.model_path)
        print(f"모델 저장 완료: {self.model_path}")
    
    def load_model(self):
        """모델 로드"""
        if not os.path.exists(self.model_path):
            print(f"모델 파일을 찾을 수 없습니다: {self.model_path}")
            return None
            
        checkpoint = torch.load(self.model_path, map_location=self.device)
        
        # 모델 생성
        config = checkpoint.get('model_config', {})
        self.model = TCNGestureClassifier(**config)
        
        # 가중치 로드
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.to(self.device)
        self.model.eval()
        
        epoch = checkpoint.get('epoch', 'Unknown')
        loss = checkpoint.get('loss', 'Unknown')
        print(f"모델 로드 완료: epoch {epoch}, loss {loss}")
        
        return self.model
    
    def get_model_info(self):
        """모델 정보 반환"""
        if self.model is None:
            return None
            
        total_params = sum(p.numel() for p in self.model.parameters())
        trainable_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        
        return {
            'total_parameters': total_params,
            'trainable_parameters': trainable_params,
            'device': str(self.device),
            'num_classes': self.model.num_classes
        }

if __name__ == "__main__":
    # 모델 테스트
    model = TCNGestureClassifier()
    
    # 더미 데이터로 테스트
    batch_size = 4
    sequence_length = 30
    input_size = 34  # 17 joints * 2 (x, y)
    
    dummy_input = torch.randn(batch_size, sequence_length, input_size)
    
    print(f"입력 형태: {dummy_input.shape}")
    
    # Forward pass
    output = model(dummy_input)
    print(f"출력 형태: {output.shape}")
    
    # 예측
    predictions, confidences, probabilities = model.predict(dummy_input)
    print(f"예측: {predictions}")
    print(f"신뢰도: {confidences}")
    
    # 모델 정보
    manager = GestureModelManager()
    model_info = manager.get_model_info()
    if model_info:
        print(f"모델 정보: {model_info}") 