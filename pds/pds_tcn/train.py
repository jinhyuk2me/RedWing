# -*- coding: utf-8 -*-
"""
TCN Model Training Script
TCN 모델 학습 스크립트
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.tensorboard import SummaryWriter
import numpy as np
import os
import time
from datetime import datetime
import json
from pathlib import Path

from config import TRAINING_CONFIG, PATHS, GESTURE_CLASSES
from model import TCNGestureClassifier, GestureModelManager
from dataset import create_dataloaders, GestureDataset
from utils import setup_logging, EarlyStopping, MetricsTracker

def train_model():
    """모델 학습 메인 함수"""
    
    # 로깅 설정
    logger = setup_logging()
    logger.info("=== TCN 제스처 인식 모델 학습 시작 ===")
    
    # 디바이스 설정
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f"사용 디바이스: {device}")
    
    # 데이터 로더 생성
    try:
        train_loader, test_loader = create_dataloaders()
        logger.info(f"데이터 로더 생성 완료 - 학습: {len(train_loader)}, 테스트: {len(test_loader)}")
    except Exception as e:
        logger.error(f"데이터 로더 생성 실패: {e}")
        return
    
    # 모델 생성
    model_manager = GestureModelManager()
    model = model_manager.create_model()
    logger.info(f"모델 생성 완료: {model_manager.get_model_info()}")
    
    # 손실 함수 및 옵티마이저
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=TRAINING_CONFIG['learning_rate'])
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=10
    )
    
    # 조기 종료 및 메트릭 추적
    early_stopping = EarlyStopping(patience=TRAINING_CONFIG['early_stopping_patience'])
    metrics_tracker = MetricsTracker()
    
    # TensorBoard
    log_dir = f"runs/tcn_training_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    writer = SummaryWriter(log_dir)
    
    # 학습 시작
    best_accuracy = 0.0
    
    for epoch in range(TRAINING_CONFIG['epochs']):
        logger.info(f"\n=== Epoch {epoch+1}/{TRAINING_CONFIG['epochs']} ===")
        
        # 학습
        train_loss, train_acc = train_epoch(model, train_loader, criterion, optimizer, device)
        
        # 검증
        val_loss, val_acc, val_metrics = validate_epoch(model, test_loader, criterion, device)
        
        # 스케줄러 업데이트
        scheduler.step(val_loss)
        
        # 메트릭 기록
        metrics_tracker.update(epoch, train_loss, train_acc, val_loss, val_acc, val_metrics)
        
        # TensorBoard 로깅
        writer.add_scalars('Loss', {'Train': train_loss, 'Val': val_loss}, epoch)
        writer.add_scalars('Accuracy', {'Train': train_acc, 'Val': val_acc}, epoch)
        writer.add_scalar('Learning_Rate', optimizer.param_groups[0]['lr'], epoch)
        
        # 로그 출력
        logger.info(f"Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.4f}")
        logger.info(f"Val Loss: {val_loss:.4f}, Val Acc: {val_acc:.4f}")
        
        # 최고 성능 모델 저장
        if val_acc > best_accuracy:
            best_accuracy = val_acc
            model_manager.save_model(model, epoch, val_loss)
            logger.info(f"새로운 최고 성능 모델 저장: {val_acc:.4f}")
        
        # 조기 종료 체크
        if early_stopping(val_loss):
            logger.info(f"조기 종료: {early_stopping.patience}회 연속 개선 없음")
            break
    
    # 학습 완료
    writer.close()
    logger.info(f"\n학습 완료! 최고 정확도: {best_accuracy:.4f}")
    
    # 최종 평가
    final_metrics = evaluate_model(model, test_loader, device)
    logger.info(f"최종 평가 정확도: {final_metrics['overall_accuracy']:.4f}")
    
    # 클래스별 정확도 출력
    logger.info("클래스별 정확도:")
    for gesture_name, accuracy in final_metrics['class_accuracies'].items():
        logger.info(f"  {gesture_name}: {accuracy:.4f}")
    
    metrics_tracker.save_metrics(final_metrics)
    
    return model, metrics_tracker

def train_epoch(model, train_loader, criterion, optimizer, device):
    """한 에포크 학습"""
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0
    
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        
        optimizer.zero_grad()
        output = model(data)
        loss = criterion(output, target)
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item()
        pred = output.argmax(dim=1)
        correct += pred.eq(target).sum().item()
        total += target.size(0)
        
        if batch_idx % 20 == 0:
            print(f'  Batch {batch_idx}/{len(train_loader)}: Loss {loss.item():.4f}')
    
    avg_loss = total_loss / len(train_loader)
    accuracy = correct / total
    
    return avg_loss, accuracy

def validate_epoch(model, test_loader, criterion, device):
    """한 에포크 검증"""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    
    # 클래스별 정확도 추적
    class_correct = [0] * len(GESTURE_CLASSES)
    class_total = [0] * len(GESTURE_CLASSES)
    
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            loss = criterion(output, target)
            
            total_loss += loss.item()
            pred = output.argmax(dim=1)
            correct += pred.eq(target).sum().item()
            total += target.size(0)
            
            # 클래스별 정확도
            for i in range(target.size(0)):
                label = target[i].item()
                class_correct[label] += (pred[i] == target[i]).item()
                class_total[label] += 1
    
    avg_loss = total_loss / len(test_loader)
    accuracy = correct / total
    
    # 클래스별 정확도 계산
    class_accuracies = {}
    for i, (gesture_id, gesture_name) in enumerate(GESTURE_CLASSES.items()):
        if class_total[i] > 0:
            class_acc = class_correct[i] / class_total[i]
            class_accuracies[gesture_name] = class_acc
    
    return avg_loss, accuracy, class_accuracies

def evaluate_model(model, test_loader, device):
    """최종 모델 평가"""
    model.eval()
    correct = 0
    total = 0
    
    # 클래스별 정확도 추적
    class_correct = [0] * len(GESTURE_CLASSES)
    class_total = [0] * len(GESTURE_CLASSES)
    
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            pred = output.argmax(dim=1)
            correct += pred.eq(target).sum().item()
            total += target.size(0)
            
            # 클래스별 정확도
            for i in range(target.size(0)):
                label = target[i].item()
                class_correct[label] += (pred[i] == target[i]).item()
                class_total[label] += 1
    
    overall_accuracy = correct / total
    
    # 클래스별 정확도 계산
    class_accuracies = {}
    for i, (gesture_id, gesture_name) in enumerate(GESTURE_CLASSES.items()):
        if class_total[i] > 0:
            class_acc = class_correct[i] / class_total[i]
            class_accuracies[gesture_name] = class_acc
    
    return {
        'overall_accuracy': overall_accuracy,
        'class_accuracies': class_accuracies,
        'total_samples': total
    }

if __name__ == "__main__":
    train_model() 