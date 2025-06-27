#!/usr/bin/env python3
"""
GPU 메모리 완전 정리 스크립트
"""

import torch
import gc
import os

def clear_gpu_memory():
    """GPU 메모리 완전 정리"""
    print("=== GPU 메모리 완전 정리 ===")
    
    if not torch.cuda.is_available():
        print("❌ CUDA를 사용할 수 없습니다.")
        return
    
    # 현재 상태 확인
    allocated = torch.cuda.memory_allocated() / 1024**3
    cached = torch.cuda.memory_reserved() / 1024**3
    total = torch.cuda.get_device_properties(0).total_memory / 1024**3
    
    print(f"정리 전 GPU 메모리:")
    print(f"  할당됨: {allocated:.2f}GB")
    print(f"  캐시됨: {cached:.2f}GB")
    print(f"  총 용량: {total:.2f}GB")
    print(f"  사용률: {(allocated + cached)/total*100:.1f}%")
    
    # 1단계: PyTorch 캐시 정리
    print("\n1. PyTorch 캐시 정리...")
    torch.cuda.empty_cache()
    
    # 2단계: Python 가비지 컬렉션
    print("2. Python 가비지 컬렉션...")
    gc.collect()
    
    # 3단계: 메모리 분할 해제
    print("3. 메모리 분할 해제...")
    torch.cuda.memory.empty_cache()
    
    # 4단계: 메모리 할당 전략 재설정
    print("4. 메모리 할당 전략 재설정...")
    os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True,max_split_size_mb:512'
    
    # 5단계: 메모리 제한 해제 후 재설정
    print("5. 메모리 제한 재설정...")
    torch.cuda.set_per_process_memory_fraction(0.95)  # 95%로 설정
    
    # 정리 후 상태 확인
    allocated_after = torch.cuda.memory_allocated() / 1024**3
    cached_after = torch.cuda.memory_reserved() / 1024**3
    
    print(f"\n정리 후 GPU 메모리:")
    print(f"  할당됨: {allocated_after:.2f}GB")
    print(f"  캐시됨: {cached_after:.2f}GB")
    print(f"  사용률: {(allocated_after + cached_after)/total*100:.1f}%")
    print(f"  사용 가능: {total - allocated_after - cached_after:.2f}GB")
    
    # 정리 효과
    freed_memory = (allocated + cached) - (allocated_after + cached_after)
    print(f"\n✅ {freed_memory:.2f}GB 메모리 정리 완료")
    
    if freed_memory > 4.0:
        print("🏆 Large 모델 실행 가능!")
    elif freed_memory > 2.0:
        print("🚀 Medium 모델 실행 가능!")
    else:
        print("⚠️ 추가 정리 필요")

def check_gpu_processes():
    """GPU 사용 프로세스 확인"""
    print("\n=== GPU 사용 프로세스 확인 ===")
    os.system("nvidia-smi")

if __name__ == "__main__":
    clear_gpu_memory()
    check_gpu_processes() 