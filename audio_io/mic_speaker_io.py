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
        """최적의 마이크를 자동으로 선택하여 AudioIO 생성"""
        # 1. PipeWire USB 마이크 검색
        print("[AudioIO] PipeWire USB 마이크 검색 시도...")
        pipewire_audio = cls.create_with_pipewire_usb(**kwargs)
        if pipewire_audio.input_device_index is not None:
            return pipewire_audio
        
        # 2. USB 마이크 강제 설정 시도
        print("[AudioIO] USB 마이크 강제 설정 시도...")
        usb_audio = cls.create_with_usb_mic_force(**kwargs)
        
        # 3. 일반 USB 마이크 검색
        if usb_audio.input_device_index is None:
            print("[AudioIO] 일반 USB 마이크 검색...")
            usb_audio = cls.create_with_usb_mic(**kwargs)
            if usb_audio.input_device_index is not None:
                return usb_audio
        
        # 4. ALSA USB 장치 시도 (카드 2)
        print("[AudioIO] ALSA 직접 접근 시도...")
        alsa_audio = cls.create_with_alsa_device(card=2, device=0, **kwargs)
        if alsa_audio.input_device_index is not None:
            return alsa_audio
        
        # 5. 내장 마이크 사용 (장치 0 - 하드웨어 직접 접근)
        print("[AudioIO] 외장 마이크를 찾을 수 없어 내장 마이크를 사용합니다.")
        return cls(input_device_index=0, **kwargs)  # HDA Intel PCH 직접 사용
    
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
        지정된 시간 동안 마이크로부터 WAV 포맷 음성 녹음 (단순하고 안정적인 방식)
        """
        print(f"[AudioIO] 🎤 {duration}초 녹음 시작 (단순 방식)")
        frames = []
        
        try:
            # 🆕 가장 기본적인 설정으로 스트림 열기
            stream = self.audio.open(
                format=pyaudio.paInt16,  # 명시적으로 16비트
                channels=1,              # 모노
                rate=22050,              # 낮은 샘플레이트로 안정성 확보
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=1024   # 작은 버퍼 크기
            )
            
            print(f"[AudioIO] ✅ 스트림 열기 성공 (22050Hz, 1024 버퍼)")
            
            # 🆕 간단한 동기 녹음
            chunk_size = 1024
            sample_rate = 22050
            total_chunks = int(sample_rate / chunk_size * duration)
            
            print(f"[AudioIO] 📊 총 {total_chunks}개 청크 녹음 예정...")
            
            # 🆕 실제 녹음 루프 (타임아웃 없는 단순 방식)
            for i in range(total_chunks):
                try:
                    data = stream.read(chunk_size)
                    frames.append(data)
                    
                    # 진행률 표시 (25% 단위)
                    if i % (total_chunks // 4) == 0:
                        progress = (i + 1) / total_chunks * 100
                        print(f"[AudioIO] 📈 진행률: {progress:.0f}% ({i+1}/{total_chunks})")
                        
                except Exception as e:
                    print(f"[AudioIO] ⚠️ 청크 {i+1} 오류: {e}")
                    # 오류 시 무음 데이터 추가
                    frames.append(b'\x00' * (chunk_size * 2))
            
            # 스트림 정리
            stream.stop_stream()
            stream.close()
            
            print(f"[AudioIO] ✅ 녹음 완료: {len(frames)}개 청크")
            
            # WAV 파일 생성
            if not frames:
                print("[AudioIO] ❌ 녹음된 데이터가 없습니다")
                return b""
            
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16비트 = 2바이트
                wf.setframerate(22050)
                wf.writeframes(b''.join(frames))
            
            wav_data = wav_buffer.getvalue()
            wav_buffer.close()
            
            wav_size = len(wav_data)
            print(f"[AudioIO] 🎵 WAV 파일 생성: {wav_size} bytes")
            
            return wav_data
            
        except Exception as e:
            print(f"[AudioIO] ❌ 녹음 전체 오류: {e}")
            import traceback
            traceback.print_exc()
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
