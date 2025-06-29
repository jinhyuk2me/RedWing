# 🎬 PDS TCN 데모 및 검증 도구

이 폴더에는 학습된 TCN 모델의 성능을 검증하고 시각적 데모를 생성하는 도구들이 있습니다.

## 📁 파일 설명

### 🎯 `demo_validator.py`
**목적**: 데모 영상 생성 및 실시간 모델 검증

**주요 기능**:
- 각 제스처별로 랜덤하게 영상 선택
- 선택된 영상들을 이어붙여서 연속적인 데모 영상 생성
- 생성된 데모 영상에 TCN 모델을 적용하여 예측 성능 측정
- 정확도, 제스처별 성능, 혼동행렬 등 상세 분석

**사용법**:
```bash
cd demos
python demo_validator.py
```

**출력 파일**:
- `demo_videos/concatenated_demo_YYYYMMDD_HHMMSS.mp4` - 연결된 데모 영상
- `demo_videos/concatenated_demo_YYYYMMDD_HHMMSS_segments.json` - 세그먼트 정보
- `demo_videos/concatenated_demo_YYYYMMDD_HHMMSS_with_predictions.mp4` - 예측 결과 영상

---

### 🎨 `demo_visualizer.py`
**목적**: 시각적 데모 영상 생성

**주요 기능**:
- 예측 결과를 아름답게 시각화
- Ground Truth, 예측 결과, 신뢰도, 정확성 표시
- MediaPipe 자세 스켈레톤 오버레이
- 진행 상황 및 세그먼트 정보 표시

**사용법**:
```bash
cd demos
python demo_visualizer.py
```

**출력 파일**:
- `demo_videos/visual_demo_YYYYMMDD_HHMMSS.mp4` - 시각적 데모 영상

**시각적 요소**:
- **Ground Truth**: 왼쪽 상단에 실제 제스처 표시
- **Prediction**: 오른쪽 상단에 예측 결과 표시
- **신뢰도 바**: 예측 신뢰도를 시각적 막대로 표시
- **정확성**: 중앙에 CORRECT/WRONG 표시
- **자세 스켈레톤**: 주황색으로 자세 추정 결과 표시
- **진행 정보**: 하단에 프레임 정보 표시

## 🚀 전체 워크플로우

### 1단계: 데모 영상 생성 및 검증
```bash
cd pds/demos
python demo_validator.py
```

### 2단계: 시각적 데모 영상 생성
```bash
cd pds/demos  
python demo_visualizer.py
```

## 📊 결과 분석

### 성능 지표
- **전체 정확도**: 모든 예측에 대한 정확도
- **제스처별 성능**: 각 제스처별 정확도 및 평균 신뢰도
- **세그먼트별 성능**: 각 영상 세그먼트별 성능
- **혼동행렬**: 예측 vs 실제 제스처 분포

### 시각적 피드백
- 실시간 예측 결과 확인
- 모델이 실패하는 구간 식별
- 신뢰도 변화 패턴 분석

## ⚠️ 주의사항

1. **데이터 경로**: `../pose_data_rotated` 폴더가 존재해야 함
2. **모델 파일**: `../models/tcn_gesture_model.pth` 모델이 학습되어 있어야 함  
3. **실행 위치**: pds 폴더에서 `cd demos` 후 실행
4. **출력 폴더**: `demo_videos` 폴더가 자동 생성됨

## 🎯 활용 방안

- **모델 검증**: 새로 학습된 모델의 성능 확인
- **클라이언트 시연**: 시각적으로 멋진 데모 영상 제작
- **디버깅**: 모델이 어떤 상황에서 실패하는지 확인
- **성능 분석**: 정량적 지표를 통한 모델 평가 