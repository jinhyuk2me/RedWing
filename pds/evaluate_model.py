#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TCN 모델 평가 스크립트
학습된 모델의 성능을 종합적으로 평가
"""

import torch
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, classification_report, accuracy_score
from sklearn.metrics import precision_recall_fscore_support
import logging
from pathlib import Path
import json
from datetime import datetime

from config import TCN_CONFIG, GESTURE_CLASSES, GESTURE_CLASSES_KR, PATHS, TRAINING_CONFIG
from model import TCNGestureClassifier
from dataset import GestureDataset
from torch.utils.data import DataLoader

# 한글 폰트 설정
plt.rcParams['font.family'] = 'DejaVu Sans'
sns.set_style("whitegrid")

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelEvaluator:
    """TCN 모델 종합 평가 클래스"""
    
    def __init__(self, model_path: str = None):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model_path = model_path or PATHS['model_file']
        self.model = None
        self.test_loader = None
        
        # 결과 저장 폴더
        self.results_dir = Path("evaluation_results")
        self.results_dir.mkdir(exist_ok=True)
        
    def load_model(self):
        """학습된 모델 로드"""
        try:
            self.model = TCNGestureClassifier(
                input_size=TCN_CONFIG['input_size'],
                num_channels=TCN_CONFIG['num_channels'],
                kernel_size=TCN_CONFIG['kernel_size'],
                dropout=TCN_CONFIG['dropout'],
                num_classes=TCN_CONFIG['num_classes']
            )
            
            if Path(self.model_path).exists():
                checkpoint = torch.load(self.model_path, map_location=self.device)
                if 'model_state_dict' in checkpoint:
                    # checkpoint 형태로 저장된 경우
                    self.model.load_state_dict(checkpoint['model_state_dict'])
                else:
                    # state_dict만 저장된 경우
                    self.model.load_state_dict(checkpoint)
                
                self.model.to(self.device)
                self.model.eval()
                logger.info(f"모델 로드 완료: {self.model_path}")
                return True
            else:
                logger.error(f"모델 파일을 찾을 수 없습니다: {self.model_path}")
                return False
                
        except Exception as e:
            logger.error(f"모델 로드 오류: {e}")
            return False
    
    def load_test_data(self):
        """테스트 데이터 로드"""
        try:
            test_dataset = GestureDataset(
                data_root=PATHS['processed_data'],
                split='test',
                test_size=1.0 - TRAINING_CONFIG['train_test_split']
            )
            
            self.test_loader = DataLoader(
                test_dataset,
                batch_size=TRAINING_CONFIG['batch_size'],
                shuffle=False,
                num_workers=2
            )
            
            logger.info(f"테스트 데이터 로드 완료: {len(test_dataset)}개 샘플")
            return True
            
        except Exception as e:
            logger.error(f"테스트 데이터 로드 오류: {e}")
            return False
    
    def evaluate_model(self):
        """모델 성능 평가"""
        if not self.model or not self.test_loader:
            logger.error("모델 또는 데이터가 로드되지 않았습니다")
            return None
        
        all_predictions = []
        all_targets = []
        all_confidences = []
        
        with torch.no_grad():
            for batch_data, batch_targets in self.test_loader:
                batch_data = batch_data.to(self.device)
                batch_targets = batch_targets.to(self.device)
                
                # 예측
                outputs = self.model(batch_data)
                probabilities = torch.softmax(outputs, dim=1)
                predictions = torch.argmax(outputs, dim=1)
                
                # 결과 저장
                all_predictions.extend(predictions.cpu().numpy())
                all_targets.extend(batch_targets.cpu().numpy())
                all_confidences.extend(torch.max(probabilities, dim=1)[0].cpu().numpy())
        
        return {
            'predictions': np.array(all_predictions),
            'targets': np.array(all_targets),
            'confidences': np.array(all_confidences)
        }
    
    def calculate_metrics(self, results):
        """상세 성능 지표 계산"""
        predictions = results['predictions']
        targets = results['targets']
        confidences = results['confidences']
        
        # 기본 지표
        accuracy = accuracy_score(targets, predictions)
        precision, recall, f1, _ = precision_recall_fscore_support(
            targets, predictions, average='weighted'
        )
        
        # 클래스별 지표
        class_report = classification_report(
            targets, predictions,
            target_names=[GESTURE_CLASSES_KR[i] for i in range(len(GESTURE_CLASSES))],
            output_dict=True
        )
        
        # 신뢰도 통계
        confidence_stats = {
            'mean': np.mean(confidences),
            'std': np.std(confidences),
            'min': np.min(confidences),
            'max': np.max(confidences)
        }
        
        return {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'class_report': class_report,
            'confidence_stats': confidence_stats
        }
    
    def plot_confusion_matrix(self, results, save_path=None):
        """Confusion Matrix 시각화"""
        predictions = results['predictions']
        targets = results['targets']
        
        # Confusion Matrix 계산
        cm = confusion_matrix(targets, predictions)
        
        # 시각화
        plt.figure(figsize=(10, 8))
        sns.heatmap(
            cm, 
            annot=True, 
            fmt='d',
            cmap='Blues',
            xticklabels=[GESTURE_CLASSES_KR[i] for i in range(len(GESTURE_CLASSES))],
            yticklabels=[GESTURE_CLASSES_KR[i] for i in range(len(GESTURE_CLASSES))]
        )
        plt.title('제스처 인식 Confusion Matrix', fontsize=14, fontweight='bold')
        plt.xlabel('예측 제스처', fontsize=12)
        plt.ylabel('실제 제스처', fontsize=12)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"Confusion Matrix 저장: {save_path}")
        
        plt.show()
    
    def plot_confidence_distribution(self, results, save_path=None):
        """신뢰도 분포 시각화"""
        confidences = results['confidences']
        predictions = results['predictions']
        
        plt.figure(figsize=(12, 8))
        
        # 전체 신뢰도 히스토그램
        plt.subplot(2, 2, 1)
        plt.hist(confidences, bins=30, alpha=0.7, color='skyblue', edgecolor='black')
        plt.title('전체 신뢰도 분포')
        plt.xlabel('신뢰도')
        plt.ylabel('빈도')
        
        # 클래스별 신뢰도 박스플롯
        plt.subplot(2, 2, 2)
        confidence_by_class = [confidences[predictions == i] for i in range(len(GESTURE_CLASSES))]
        plt.boxplot(confidence_by_class, labels=[GESTURE_CLASSES_KR[i] for i in range(len(GESTURE_CLASSES))])
        plt.title('클래스별 신뢰도 분포')
        plt.ylabel('신뢰도')
        plt.xticks(rotation=45)
        
        # 신뢰도 vs 정확도
        plt.subplot(2, 2, 3)
        correct = (predictions == results['targets'])
        plt.scatter(confidences[correct], [1]*sum(correct), alpha=0.5, label='정답', color='green')
        plt.scatter(confidences[~correct], [0]*sum(~correct), alpha=0.5, label='오답', color='red')
        plt.title('신뢰도 vs 정답/오답')
        plt.xlabel('신뢰도')
        plt.ylabel('정답 여부')
        plt.legend()
        
        # 신뢰도 임계값별 정확도
        plt.subplot(2, 2, 4)
        thresholds = np.arange(0.5, 1.0, 0.05)
        accuracies = []
        for threshold in thresholds:
            mask = confidences >= threshold
            if sum(mask) > 0:
                acc = accuracy_score(results['targets'][mask], predictions[mask])
                accuracies.append(acc)
            else:
                accuracies.append(0)
        
        plt.plot(thresholds, accuracies, marker='o')
        plt.title('신뢰도 임계값별 정확도')
        plt.xlabel('신뢰도 임계값')
        plt.ylabel('정확도')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"신뢰도 분포 저장: {save_path}")
        
        plt.show()
    
    def save_evaluation_report(self, metrics, save_path=None):
        """평가 보고서 저장"""
        if not save_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = self.results_dir / f"evaluation_report_{timestamp}.json"
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'model_path': str(self.model_path),
            'overall_metrics': {
                'accuracy': float(metrics['accuracy']),
                'precision': float(metrics['precision']),
                'recall': float(metrics['recall']),
                'f1_score': float(metrics['f1_score'])
            },
            'confidence_stats': metrics['confidence_stats'],
            'class_report': metrics['class_report']
        }
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"평가 보고서 저장: {save_path}")
        return save_path
    
    def run_full_evaluation(self):
        """전체 평가 실행"""
        logger.info("=== TCN 모델 종합 평가 시작 ===")
        
        # 1. 모델 및 데이터 로드
        if not self.load_model():
            return False
        
        if not self.load_test_data():
            return False
        
        # 2. 모델 평가
        logger.info("모델 평가 중...")
        results = self.evaluate_model()
        if not results:
            return False
        
        # 3. 성능 지표 계산
        logger.info("성능 지표 계산 중...")
        metrics = self.calculate_metrics(results)
        
        # 4. 결과 출력
        print("\n" + "="*50)
        print("📊 TCN 모델 평가 결과")
        print("="*50)
        print(f"✅ 전체 정확도: {metrics['accuracy']:.4f} ({metrics['accuracy']*100:.2f}%)")
        print(f"📈 정밀도: {metrics['precision']:.4f}")
        print(f"📉 재현율: {metrics['recall']:.4f}")
        print(f"🎯 F1-Score: {metrics['f1_score']:.4f}")
        print(f"🔍 평균 신뢰도: {metrics['confidence_stats']['mean']:.4f}")
        print("="*50)
        
        # 5. 시각화
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Confusion Matrix
        cm_path = self.results_dir / f"confusion_matrix_{timestamp}.png"
        self.plot_confusion_matrix(results, cm_path)
        
        # 신뢰도 분포
        conf_path = self.results_dir / f"confidence_distribution_{timestamp}.png"
        self.plot_confidence_distribution(results, conf_path)
        
        # 6. 보고서 저장
        report_path = self.save_evaluation_report(metrics)
        
        logger.info("=== 평가 완료 ===")
        return True

if __name__ == "__main__":
    evaluator = ModelEvaluator()
    evaluator.run_full_evaluation() 