# -*- coding: utf-8 -*-
"""
Utility Functions
유틸리티 함수들
"""

import logging
import os
import json
import torch
import numpy as np
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from config import LOGGING_CONFIG, PATHS

def setup_logging():
    """로깅 설정"""
    log_dir = Path(PATHS['logs'])
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / LOGGING_CONFIG['log_file'].split('/')[-1]
    
    logging.basicConfig(
        level=getattr(logging, LOGGING_CONFIG['level']),
        format=LOGGING_CONFIG['format'],
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"로깅 설정 완료: {log_file}")
    
    return logger

class EarlyStopping:
    """조기 종료 클래스"""
    
    def __init__(self, patience=15, min_delta=0.001):
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_loss = float('inf')
        
    def __call__(self, val_loss):
        if val_loss < self.best_loss - self.min_delta:
            self.best_loss = val_loss
            self.counter = 0
        else:
            self.counter += 1
            
        return self.counter >= self.patience

class MetricsTracker:
    """메트릭 추적 클래스"""
    
    def __init__(self):
        self.history = {
            'epoch': [],
            'train_loss': [],
            'train_acc': [],
            'val_loss': [],
            'val_acc': [],
            'class_metrics': []
        }
        
    def update(self, epoch, train_loss, train_acc, val_loss, val_acc, class_metrics):
        """메트릭 업데이트"""
        self.history['epoch'].append(epoch)
        self.history['train_loss'].append(train_loss)
        self.history['train_acc'].append(train_acc)
        self.history['val_loss'].append(val_loss)
        self.history['val_acc'].append(val_acc)
        self.history['class_metrics'].append(class_metrics)
        
    def save_metrics(self, final_metrics=None):
        """메트릭 저장"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        metrics_file = Path(PATHS['logs']) / f'training_metrics_{timestamp}.json'
        
        save_data = {
            'training_history': self.history,
            'timestamp': timestamp
        }
        
        if final_metrics:
            save_data['final_evaluation'] = final_metrics
            
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
            
        print(f"메트릭 저장 완료: {metrics_file}")

def evaluate_model(model, test_loader, device):
    """모델 평가"""
    from sklearn.metrics import classification_report, confusion_matrix
    from config import GESTURE_CLASSES
    
    model.eval()
    all_preds = []
    all_labels = []
    
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            pred = output.argmax(dim=1)
            
            all_preds.extend(pred.cpu().numpy())
            all_labels.extend(target.cpu().numpy())
    
    # 분류 리포트
    target_names = [GESTURE_CLASSES[i] for i in range(len(GESTURE_CLASSES))]
    class_report = classification_report(all_labels, all_preds, target_names=target_names, output_dict=True)
    
    # 혼동 행렬
    conf_matrix = confusion_matrix(all_labels, all_preds)
    
    return {
        'classification_report': class_report,
        'confusion_matrix': conf_matrix.tolist(),
        'accuracy': class_report['accuracy']
    } 