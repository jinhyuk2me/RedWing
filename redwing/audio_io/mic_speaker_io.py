import pyaudio
import wave
import io
import base64
import threading
import time
from typing import Optional
import os
import numpy as np
import signal

class AudioIO:
    def __init__(self, sample_rate=44100, chunk_size=1024, channels=1, format=pyaudio.paInt16, input_device_index=None):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.format = format
        self.input_device_index = input_device_index
        self.audio = pyaudio.PyAudio()
        self.is_recording = False
        self.recorded_frames = []
        self.current_stream = None  # 현재 활성 스트림 추적
        
        # 마이크 장치 정보 출력
        self._print_audio_device_info()
    
    # 현재 사용할 마이크 장치 정보 출력
    def _print_audio_device_info(self):
        try:
            if self.input_device_index is not None:
                device_info = self.audio.get_device_info_by_index(self.input_device_index)
                print(f"[AudioIO] 지정된 마이크: {device_info['name']} (인덱스: {self.input_device_index})")
            else:
                device_info = self.audio.get_default_input_device_info()
                print(f"[AudioIO] 기본 마이크: {device_info['name']} (인덱스: {device_info['index']})")
        except Exception as e:
            print(f"[AudioIO] 마이크 정보 조회 실패: {e}")
    
    @classmethod
    def list_input_devices(cls):
        audio = pyaudio.PyAudio()
        devices = []
        
        print("\n=== 사용 가능한 마이크 장치 ===")
        for i in range(audio.get_device_count()):
            try:
                device_info = audio.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:  # 입력 가능한 장치만
                    devices.append({
                        'index': i,
                        'name': device_info['name'],
                        'channels': device_info['maxInputChannels'],
                        'sample_rate': device_info['defaultSampleRate']
                    })
                    # USB 마이크 후보 표시
                    usb_indicator = ""
                    name_lower = device_info['name'].lower()
                    if any(keyword in name_lower for keyword in ['usb', 'n550', 'abko', 'hw:2']):
                        usb_indicator = " 🎤 [USB 마이크 후보]"
                    
                    print(f"  {i}: {device_info['name']} (채널: {device_info['maxInputChannels']}){usb_indicator}")
            except Exception as e:
                print(f"  {i}: 장치 정보 조회 실패 - {e}")
        
        audio.terminate()
        return devices
    
    # USB 마이크 우선으로 AudioIO 생성
    @classmethod
    def create_with_usb_mic(cls, **kwargs):
        audio = pyaudio.PyAudio()
        usb_device_index = None
        
        print("[AudioIO] USB 마이크 검색 중...")
        
        # USB 마이크 찾기 (더 넓은 검색 조건)
        for i in range(audio.get_device_count()):
            try:
                device_info = audio.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    name_lower = device_info['name'].lower()
                    # 더 넓은 USB 마이크 검색 조건
                    usb_keywords = ['usb', 'n550', 'abko', 'hw:2', 'card 2']
                    if any(keyword in name_lower for keyword in usb_keywords):
                        usb_device_index = i
                        print(f"[AudioIO] USB 마이크 발견: {device_info['name']} (인덱스: {i})")
                        break
                    # 내장 마이크가 아닌 것들도 체크 (hw:0,0이 아닌 것)
                    elif 'hw:0,0' not in name_lower and 'alc233' not in name_lower and 'intel' not in name_lower:
                        print(f"[AudioIO] 외장 마이크 후보: {device_info['name']} (인덱스: {i})")
            except:
                continue
        
        audio.terminate()
        
        if usb_device_index is not None:
            return cls(input_device_index=usb_device_index, **kwargs)
        else:
            print("[AudioIO] USB 마이크를 찾을 수 없어 기본 마이크를 사용합니다.")
            print("[AudioIO] 사용 가능한 마이크 목록:")
            cls.list_input_devices()
            return cls(**kwargs)
    
    @classmethod
    def create_with_alsa_device(cls, card=2, device=0, **kwargs):
        """ALSA 장치를 직접 지정하여 AudioIO 생성 (USB 마이크용)"""
        import subprocess
        
        # ALSA 장치 존재 확인
        try:
            result = subprocess.run(['arecord', '-l'], capture_output=True, text=True)
            if f'card {card}:' in result.stdout:
                print(f"[AudioIO] ALSA 카드 {card} 발견됨")
                
                # PyAudio에서 해당 ALSA 장치 찾기
                audio = pyaudio.PyAudio()
                for i in range(audio.get_device_count()):
                    try:
                        device_info = audio.get_device_info_by_index(i)
                        if (device_info['maxInputChannels'] > 0 and 
                            f'hw:{card},{device}' in device_info['name']):
                            print(f"[AudioIO] ALSA 장치 발견: {device_info['name']} (인덱스: {i})")
                            audio.terminate()
                            return cls(input_device_index=i, **kwargs)
                    except:
                        continue
                audio.terminate()
                
                print(f"[AudioIO] PyAudio에서 hw:{card},{device} 장치를 찾을 수 없습니다.")
            else:
                print(f"[AudioIO] ALSA 카드 {card}가 존재하지 않습니다.")
        except Exception as e:
            print(f"[AudioIO] ALSA 장치 확인 실패: {e}")
        
        return cls(**kwargs)
    
    @classmethod
    def create_with_usb_mic_force(cls, **kwargs):
        """USB 마이크를 강제로 사용 (환경 변수 설정)"""
        print("[AudioIO] USB 마이크 강제 설정 시도...")
        
        # ALSA 환경 변수로 USB 마이크 강제 지정
        original_pcm_card = os.environ.get('ALSA_PCM_CARD')
        original_pcm_device = os.environ.get('ALSA_PCM_DEVICE')
        
        try:
            # USB 마이크를 기본 장치로 설정
            os.environ['ALSA_PCM_CARD'] = '2'  # ABKO N550이 카드 2
            os.environ['ALSA_PCM_DEVICE'] = '0'
            
            print("[AudioIO] ALSA 환경 변수 설정: CARD=2, DEVICE=0")
            
            # PyAudio 재초기화
            audio_io = cls(**kwargs)
            
            print(f"[AudioIO] USB 마이크 강제 설정 완료")
            return audio_io
            
        except Exception as e:
            print(f"[AudioIO] USB 마이크 강제 설정 실패: {e}")
            
            # 환경 변수 복원
            if original_pcm_card:
                os.environ['ALSA_PCM_CARD'] = original_pcm_card
            else:
                os.environ.pop('ALSA_PCM_CARD', None)
                
            if original_pcm_device:
                os.environ['ALSA_PCM_DEVICE'] = original_pcm_device
            else:
                os.environ.pop('ALSA_PCM_DEVICE', None)
            
            return cls(**kwargs)
    
    @classmethod
    def create_with_pipewire_usb(cls, **kwargs):
        """PipeWire에서 USB 마이크 찾기"""
        print("[AudioIO] PipeWire USB 마이크 검색...")
        
        audio = pyaudio.PyAudio()
        usb_device_index = None
        
        # PipeWire 환경에서 USB 마이크 검색
        for i in range(audio.get_device_count()):
            try:
                device_info = audio.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    name_lower = device_info['name'].lower()
                    print(f"[AudioIO] 장치 {i}: {device_info['name']}")
                    
                    # PipeWire에서 보이는 USB 마이크 패턴 검색
                    usb_patterns = [
                        'abko', 'n550', 'usb', 
                        'alsa_input.usb', 'mono-fallback',
                        'pipewire'  # PipeWire 자체도 USB 마이크를 포함할 수 있음
                    ]
                    
                    if any(pattern in name_lower for pattern in usb_patterns):
                        # 내장 마이크가 아닌 것 확인
                        if not any(builtin in name_lower for builtin in ['built-in', 'alc233', 'intel', 'hw:0']):
                            usb_device_index = i
                            print(f"[AudioIO] PipeWire USB 마이크 발견: {device_info['name']} (인덱스: {i})")
                            break
            except Exception as e:
                print(f"[AudioIO] 장치 {i} 정보 조회 실패: {e}")
        
        audio.terminate()
        
        if usb_device_index is not None:
            return cls(input_device_index=usb_device_index, **kwargs)
        else:
            print("[AudioIO] PipeWire에서 USB 마이크를 찾을 수 없습니다.")
            return cls(**kwargs)
    
    @classmethod
    def create_with_best_mic(cls, **kwargs):
        """시스템에서 가장 적합한 마이크 선택 (pipewire 우선)"""
        print("[AudioIO] 최적 마이크 검색...")
        
        audio = pyaudio.PyAudio()
        best_device_index = None
        device_priority = {}
        
        # 디바이스 우선순위 점수 시스템
        for i in range(audio.get_device_count()):
            try:
                device_info = audio.get_device_info_by_index(i)
                if device_info['maxInputChannels'] > 0:
                    name_lower = device_info['name'].lower()
                    score = 0
                    
                    # pipewire는 최고 우선순위
                    if 'pipewire' in name_lower:
                        score += 100
                        print(f"[AudioIO] 🎯 pipewire 디바이스 발견: {device_info['name']} (점수: 100)")
                    
                    # USB 마이크 (ABKO N550) 두 번째 우선순위
                    elif any(keyword in name_lower for keyword in ['abko', 'n550', 'usb']):
                        score += 80
                        print(f"[AudioIO] 🎤 USB 마이크 발견: {device_info['name']} (점수: 80)")
                    
                    # 외장 디바이스 (hw:2 등)
                    elif 'hw:2' in name_lower or 'card 2' in name_lower:
                        score += 60
                        print(f"[AudioIO] 🔌 외장 디바이스 발견: {device_info['name']} (점수: 60)")
                    
                    # 일반 외장 마이크
                    elif not any(builtin in name_lower for builtin in ['built-in', 'alc233', 'alc897', 'intel', 'hw:0']):
                        score += 40
                        print(f"[AudioIO] 🎙️ 외장 마이크 후보: {device_info['name']} (점수: 40)")
                    
                    # 내장 마이크는 낮은 점수
                    else:
                        score += 10
                        print(f"[AudioIO] 🔊 내장 마이크: {device_info['name']} (점수: 10)")
                    
                    device_priority[i] = (score, device_info)
                    
            except Exception as e:
                print(f"[AudioIO] ⚠️ 디바이스 {i} 정보 조회 실패: {e}")
        
        audio.terminate()
        
        if device_priority:
            # 점수가 가장 높은 디바이스 선택
            best_device_index = max(device_priority.keys(), key=lambda x: device_priority[x][0])
            best_score, best_device_info = device_priority[best_device_index]
            
            print(f"[AudioIO] 🏆 최적 디바이스 선택: {best_device_info['name']} (인덱스: {best_device_index}, 점수: {best_score})")
            return cls(input_device_index=best_device_index, **kwargs)
        else:
            print("[AudioIO] ⚠️ 사용 가능한 마이크를 찾을 수 없어 기본 설정을 사용합니다.")
            return cls(**kwargs)
    
    def start_recording(self):
        """
        마이크 녹음 시작 (비동기)
        """
        if self.is_recording:
            return
            
        self.is_recording = True
        self.recorded_frames = []
        
        try:
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.input_device_index,  # 지정된 장치 사용
                frames_per_buffer=self.chunk_size
            )
            
            # 별도 스레드에서 녹음
            self.recording_thread = threading.Thread(target=self._record_audio)
            self.recording_thread.start()
            
        except Exception as e:
            print(f"[AudioIO] 녹음 시작 오류: {e}")
            self.is_recording = False
    
    def _record_audio(self):
        """
        실제 녹음 처리 (내부 메서드)
        """
        while self.is_recording:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                self.recorded_frames.append(data)
            except Exception as e:
                print(f"[AudioIO] 녹음 중 오류: {e}")
                break
    
    def stop_recording(self) -> bytes:
        """
        마이크 녹음 중지 및 WAV 데이터 반환
        """
        if not self.is_recording:
            return b""
            
        self.is_recording = False
        
        # 녹음 스레드 종료 대기
        if hasattr(self, 'recording_thread'):
            self.recording_thread.join(timeout=1.0)
        
        # 스트림 정리
        if hasattr(self, 'stream'):
            self.stream.stop_stream()
            self.stream.close()
        
        # WAV 파일 생성
        if not self.recorded_frames:
            return b""
            
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(self.recorded_frames))
        
        wav_data = wav_buffer.getvalue()
        wav_buffer.close()
        
        return wav_data
    
    def record_audio(self, duration: float = 5.0) -> bytes:
        """
        지정된 시간 동안 마이크로부터 WAV 포맷 음성 녹음 (개선된 안정성)
        """
        print(f"[AudioIO] 🎤 {duration}초 녹음 시작 (개선된 방식)")
        frames = []
        
        # 기존 스트림 정리
        self._close_existing_stream()
        
        # PyAudio 재초기화로 디바이스 충돌 방지
        try:
            if hasattr(self, 'audio'):
                self.audio.terminate()
            self.audio = pyaudio.PyAudio()
            print("[AudioIO] 🔄 PyAudio 재초기화 완료")
        except Exception as e:
            print(f"[AudioIO] ⚠️ PyAudio 재초기화 중 오류: {e}")
        
        # 표준 샘플 레이트 목록 (호환성 우선순위)
        sample_rates = [44100, 48000, 16000, 22050]
        
        for sample_rate in sample_rates:
            try:
                # 📋 디바이스 가용성 사전 확인
                if not self._check_device_availability():
                    print("[AudioIO] ❌ 디바이스 사용 불가 - 대안 방법 시도")
                    return self._fallback_recording(duration)
                
                print(f"[AudioIO] 📊 샘플 레이트 시도: {sample_rate}Hz")
                
                # 기본적인 설정으로 스트림 열기
                self.current_stream = self.audio.open(
                    format=pyaudio.paInt16,  # 명시적으로 16비트
                    channels=1,              # 모노
                    rate=sample_rate,        # 호환성 있는 샘플 레이트
                    input=True,
                    input_device_index=self.input_device_index,
                    frames_per_buffer=1024   # 작은 버퍼 크기
                )
                
                print(f"[AudioIO] ✅ 스트림 열기 성공 ({sample_rate}Hz, 1024 버퍼)")
                
                # 간단한 동기 녹음
                chunk_size = 1024
                total_chunks = int(sample_rate / chunk_size * duration)
                
                print(f"[AudioIO] 📊 총 {total_chunks}개 청크 녹음 예정...")
                
                # 실제 녹음 루프
                for i in range(total_chunks):
                    try:
                        data = self.current_stream.read(chunk_size, exception_on_overflow=False)
                        frames.append(data)
                        
                        # 진행률 표시 (25% 단위)
                        if i % (total_chunks // 4) == 0:
                            progress = (i + 1) / total_chunks * 100
                            print(f"[AudioIO] 📈 진행률: {progress:.0f}% ({i+1}/{total_chunks})")
                            
                    except Exception as e:
                        print(f"[AudioIO] ⚠️ 청크 {i+1} 오류: {e}")
                        # 오류 시 무음 데이터 추가
                        frames.append(b'\x00' * (chunk_size * 2))
                
                print(f"[AudioIO] ✅ 녹음 완료: {len(frames)}개 청크 ({sample_rate}Hz)")
                
                # WAV 파일 생성
                if not frames:
                    print("[AudioIO] ❌ 녹음된 데이터가 없습니다")
                    return b""
                
                try:
                    wav_buffer = io.BytesIO()
                    with wave.open(wav_buffer, 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)  # 16비트 = 2바이트
                        wf.setframerate(sample_rate)
                        wf.writeframes(b''.join(frames))
                    
                    wav_data = wav_buffer.getvalue()
                    wav_buffer.close()
                    
                    wav_size = len(wav_data)
                    print(f"[AudioIO] 🎵 WAV 파일 생성: {wav_size} bytes ({sample_rate}Hz)")
                    
                    return wav_data
                except Exception as e:
                    print(f"[AudioIO] ❌ WAV 생성 오류: {e}")
                    return b""
                
            except Exception as e:
                print(f"[AudioIO] ❌ {sample_rate}Hz 녹음 오류: {e}")
                if sample_rate == sample_rates[-1]:  # 마지막 샘플 레이트도 실패한 경우
                    print(f"[AudioIO] 🔧 디바이스 정보 재확인:")
                    self._print_audio_device_info()
                    # 디바이스 충돌 시 대안 시도
                    return self._fallback_recording(duration)
                else:
                    print(f"[AudioIO] 🔄 다음 샘플 레이트 시도...")
                    continue
                
            finally:
                # 스트림 정리
                self._close_existing_stream()
        
        # 모든 샘플 레이트 실패 시
        print("[AudioIO] ❌ 모든 샘플 레이트 실패 - 대안 방법 시도")
        return self._fallback_recording(duration)

    def _check_device_availability(self) -> bool:
        """지정된 디바이스가 사용 가능한지 확인"""
        try:
            if self.input_device_index is None:
                device_info = self.audio.get_default_input_device_info()
                print(f"[AudioIO] 📋 기본 디바이스 확인: {device_info['name']}")
                return True
            else:
                device_info = self.audio.get_device_info_by_index(self.input_device_index)
                print(f"[AudioIO] 📋 지정 디바이스 확인: {device_info['name']} (인덱스: {self.input_device_index})")
                
                # 디바이스가 입력을 지원하는지 확인
                if device_info['maxInputChannels'] > 0:
                    print(f"[AudioIO] ✅ 디바이스 입력 채널 수: {device_info['maxInputChannels']}")
                    return True
                else:
                    print(f"[AudioIO] ❌ 디바이스가 입력을 지원하지 않음")
                    return False
                    
        except Exception as e:
            print(f"[AudioIO] ❌ 디바이스 확인 실패: {e}")
            return False

    def _fallback_recording(self, duration: float) -> bytes:
        """디바이스 충돌 시 대안 녹음 방법 (개선된 샘플 레이트 호환성)"""
        print("[AudioIO] 🔄 대안 녹음 방법 시도...")
        
        # 표준 샘플 레이트 목록 (호환성 우선순위)
        sample_rates = [44100, 48000, 16000, 22050, 8000]
        
        # 다른 마이크 디바이스 시도
        audio = pyaudio.PyAudio()
        try:
            # pipewire 디바이스 우선 검색
            pipewire_devices = []
            other_devices = []
            
            for i in range(audio.get_device_count()):
                try:
                    device_info = audio.get_device_info_by_index(i)
                    if (device_info['maxInputChannels'] > 0 and 
                        i != self.input_device_index):
                        
                        device_name = device_info['name'].lower()
                        if 'pipewire' in device_name:
                            pipewire_devices.append((i, device_info))
                            print(f"[AudioIO] 🎯 pipewire 디바이스 발견: {device_info['name']} (인덱스: {i})")
                        else:
                            other_devices.append((i, device_info))
                            
                except Exception as e:
                    print(f"[AudioIO] ⚠️ 디바이스 {i} 정보 조회 실패: {e}")
                    continue
            
            # pipewire 디바이스를 먼저 시도
            all_devices = pipewire_devices + other_devices
            
            for device_idx, device_info in all_devices:
                print(f"[AudioIO] 🎯 대안 디바이스 시도: {device_info['name']} (인덱스: {device_idx})")
                
                # 여러 샘플 레이트 시도
                for sample_rate in sample_rates:
                    try:
                        print(f"[AudioIO] 📊 샘플 레이트 시도: {sample_rate}Hz")
                        
                        # 임시로 디바이스 변경하여 녹음 시도
                        temp_stream = audio.open(
                            format=pyaudio.paInt16,
                            channels=1,
                            rate=sample_rate,
                            input=True,
                            input_device_index=device_idx,
                            frames_per_buffer=1024
                        )
                        
                        frames = []
                        chunk_size = 1024
                        total_chunks = int(sample_rate / chunk_size * duration)
                        
                        print(f"[AudioIO] 🎤 {sample_rate}Hz로 녹음 시작: {total_chunks}개 청크")
                        
                        for j in range(total_chunks):
                            try:
                                data = temp_stream.read(chunk_size, exception_on_overflow=False)
                                frames.append(data)
                                
                                # 25% 단위로 진행률 표시
                                if j % (total_chunks // 4) == 0:
                                    progress = (j + 1) / total_chunks * 100
                                    print(f"[AudioIO] 📈 대안 녹음 진행률: {progress:.0f}%")
                                    
                            except Exception as chunk_error:
                                print(f"[AudioIO] ⚠️ 청크 {j+1} 오류: {chunk_error}")
                                frames.append(b'\x00' * (chunk_size * 2))
                        
                        temp_stream.stop_stream()
                        temp_stream.close()
                        
                        print(f"[AudioIO] ✅ 대안 디바이스로 녹음 성공! ({sample_rate}Hz)")
                        
                        # WAV 데이터 생성
                        wav_buffer = io.BytesIO()
                        with wave.open(wav_buffer, 'wb') as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(sample_rate)
                            wf.writeframes(b''.join(frames))
                        
                        wav_data = wav_buffer.getvalue()
                        wav_buffer.close()
                        
                        wav_size = len(wav_data)
                        print(f"[AudioIO] 🎵 대안 WAV 파일 생성: {wav_size} bytes ({sample_rate}Hz)")
                        
                        return wav_data
                        
                    except Exception as sample_rate_error:
                        print(f"[AudioIO] ❌ {sample_rate}Hz 실패: {sample_rate_error}")
                        continue
                
                print(f"[AudioIO] ❌ 디바이스 {device_idx} 모든 샘플 레이트 실패")
                    
        finally:
            audio.terminate()
        
        print("[AudioIO] ❌ 모든 대안 방법 실패")
        return b""

    def play_audio(self, audio_bytes: bytes):
        """
        WAV 바이트 데이터를 스피커로 출력
        """
        try:
            # WAV 데이터 파싱
            wav_buffer = io.BytesIO(audio_bytes)
            with wave.open(wav_buffer, 'rb') as wf:
                # 오디오 스트림 열기
                stream = self.audio.open(
                    format=self.audio.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True
                )
                
                print("[AudioIO] 오디오 재생 시작...")
                
                # 청크 단위로 재생
                data = wf.readframes(self.chunk_size)
                while data:
                    stream.write(data)
                    data = wf.readframes(self.chunk_size)
                
                stream.stop_stream()
                stream.close()
                
            wav_buffer.close()
            print("[AudioIO] 오디오 재생 완료")
            
        except Exception as e:
            print(f"[AudioIO] 재생 오류: {e}")
    
    def play_audio_base64(self, audio_base64: str):
        """
        base64 인코딩된 오디오 데이터를 디코딩 후 스피커 출력
        """
        try:
            audio_bytes = base64.b64decode(audio_base64)
            self.play_audio(audio_bytes)
        except Exception as e:
            print(f"[AudioIO] Base64 오디오 재생 오류: {e}")
    
    def audio_to_base64(self, audio_bytes: bytes) -> str:
        """
        오디오 바이트 데이터를 base64로 인코딩
        """
        return base64.b64encode(audio_bytes).decode('utf-8')
    
    def __del__(self):
        """
        소멸자 - PyAudio 정리
        """
        self._close_existing_stream()
        if hasattr(self, 'audio'):
            self.audio.terminate()

    def is_silence(self, audio_data):
        """오디오 데이터가 무음인지 판단 (개선된 알고리즘)"""
        if len(audio_data) == 0:
            return True
        
        # numpy 배열로 변환
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # 기본 통계 계산
        rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
        max_amplitude = np.max(np.abs(audio_array))
        energy = np.sum(audio_array.astype(np.float64) ** 2)
        std_dev = np.std(audio_array.astype(np.float32))
        
        # SNR 계산 (신호 대 잡음비)
        if std_dev > 0:
            snr_db = 20 * np.log10(rms / (std_dev + 1e-10))
        else:
            snr_db = -100
        
        # 에너지 변화율 계산
        if len(audio_array) > 1000:
            first_half = audio_array[:len(audio_array)//2]
            second_half = audio_array[len(audio_array)//2:]
            energy_change = abs(np.sum(first_half.astype(np.float64) ** 2) - 
                              np.sum(second_half.astype(np.float64) ** 2))
        else:
            energy_change = energy
        
        # 고주파 성분 분석 (음성 특성)
        if len(audio_array) > 100:
            diff = np.diff(audio_array.astype(np.float32))
            high_freq_ratio = np.sum(np.abs(diff)) / (np.sum(np.abs(audio_array)) + 1e-10)
        else:
            high_freq_ratio = 0
        
        # USB 마이크 환경에 최적화된 임계값 (10초 녹음에 맞게 더 관대하게)
        silence_thresholds = {
            'rms': 150,           # 200 → 150 (더 관대)
            'max_amplitude': 1500, # 2000 → 1500 (더 관대)  
            'energy': 300000,     # 500000 → 300000 (더 관대)
            'snr_db': -20.0,      # -15.0 → -20.0 (더 관대)
            'energy_change': 50000,  # 100000 → 50000 (더 관대)
            'high_freq_ratio': 0.05  # 0.1 → 0.05 (더 관대)
        }
        
        # 기본 신호 강도 체크
        basic_signal = (rms > silence_thresholds['rms'] and 
                       max_amplitude > silence_thresholds['max_amplitude'] and
                       energy > silence_thresholds['energy'])
        
        # 음성 품질 체크 (SNR과 고주파 성분)
        voice_quality = (snr_db > silence_thresholds['snr_db'] or
                        high_freq_ratio > silence_thresholds['high_freq_ratio'] or
                        energy_change > silence_thresholds['energy_change'])
        
        # 디버그 정보 출력
        print(f"오디오 품질 분석:")
        print(f"  RMS 레벨: {rms:.1f}")
        print(f"  최대 진폭: {max_amplitude}")
        print(f"  에너지: {energy:.0f}")
        print(f"  표준편차: {std_dev:.1f}")
        print(f"  SNR: {snr_db:.1f} dB")
        print(f"  에너지 변화: {energy_change:.0f}")
        print(f"  고주파 비율: {high_freq_ratio:.3f}")
        print(f"  기본 신호 강도: {'✅' if basic_signal else '❌'}")
        print(f"  음성 품질: {'✅' if voice_quality else '❌'}")
        
        # 무음 판단: 기본 신호 OR 음성 품질 중 하나만 만족해도 음성으로 인정 (더 관대하게)
        is_silent = not (basic_signal or voice_quality)
        
        if is_silent:
            print(f"  → 🔇 무음 또는 품질 불량 신호")
        else:
            print(f"  → 🎤 음성 신호 감지됨")
        
        return is_silent

    def _close_existing_stream(self):
        """기존 스트림을 안전하게 정리"""
        if self.current_stream is not None:
            try:
                if hasattr(self.current_stream, 'is_active') and self.current_stream.is_active():
                    self.current_stream.stop_stream()
                if hasattr(self.current_stream, 'is_stopped') and not self.current_stream.is_stopped():
                    self.current_stream.close()
                print("[AudioIO] 🧹 기존 스트림 정리 완료")
            except Exception as e:
                print(f"[AudioIO] ⚠️ 스트림 정리 중 오류: {e}")
            finally:
                self.current_stream = None
