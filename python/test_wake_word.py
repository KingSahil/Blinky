import os
import sys
import time
import argparse

def print_header(title):
    print(f"\n{'='*60}\n{title}\n{'='*60}")

def test_dependencies():
    print_header("Test 1: Checking Dependencies")
    deps = ["sounddevice", "numpy", "openwakeword", "onnxruntime"]
    all_passed = True
    for dep in deps:
        try:
            __import__(dep)
            print(f"[PASS] {dep} imported successfully.")
        except ImportError as e:
            print(f"[FAIL] Failed to import {dep}: {e}")
            all_passed = False
    return all_passed

def test_audio_devices():
    print_header("Test 2: Checking Audio Input Devices")
    import sounddevice as sd
    import numpy as np
    
    try:
        devices = sd.query_devices()
        default_input = sd.default.device[0]
        print(f"Default input device index: {default_input}")
        
        if default_input is None or default_input < 0:
            print("[FAIL] No default input device configured in sounddevice/Windows.")
            return False
            
        device_info = sd.query_devices(default_input, 'input')
        print(f"Default Device Name: {device_info['name']}")
        print(f"Default Device Max Input Channels: {device_info['max_input_channels']}")
        print(f"Default Device Default Samplerate: {device_info['default_samplerate']}")
        
        print("\nTesting 16kHz mono recording stream for 3 seconds...")
        audio_data = []
        def callback(indata, frames, time_info, status):
            if status:
                print(f"Stream status: {status}")
            audio_data.append(indata.copy())
            
        with sd.InputStream(samplerate=16000, blocksize=1280, channels=1, dtype='float32', callback=callback):
            time.sleep(3)
            
        if not audio_data:
            print("[FAIL] No audio data received from microphone. Check Windows Privacy/Microphone permissions.")
            return False
            
        concatenated = np.concatenate(audio_data)
        rms = np.sqrt(np.mean(concatenated**2))
        max_val = np.max(np.abs(concatenated))
        print(f"[PASS] Successfully captured audio stream. RMS level: {rms:.6f}, Max absolute value: {max_val:.6f}")
        if rms < 1e-5:
            print("[WARNING] Audio level is extremely low or silent. Your microphone might be muted or recording at very low gain.")
        return True
    except Exception as e:
        print(f"[FAIL] Audio device test failed with exception: {e}")
        return False

def test_model_loading():
    print_header("Test 3: Testing openwakeword Model Loading & Inference")
    import numpy as np
    from openwakeword.model import Model
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "hey_blinky.onnx")
    
    print(f"Checking model file at: {model_path}")
    if not os.path.exists(model_path):
        print(f"[FAIL] Model file not found at {model_path}")
        return False
    print("[PASS] Model file exists on disk.")
    
    try:
        print("Ensuring openwakeword feature models are downloaded...")
        import openwakeword.utils
        openwakeword.utils.download_models()
        print("[PASS] Feature models verified/downloaded.")
        
        print("Initializing openwakeword Model...")
        oww_model = Model(wakeword_models=[model_path])
        print("[PASS] Model loaded into ONNX runtime successfully.")
        
        print("Testing synthetic inference (1280 samples of zero/noise)...")
        dummy_audio = np.zeros(1280, dtype=np.int16)
        prediction = oww_model.predict(dummy_audio)
        print(f"[PASS] Inference succeeded. Result on silence: {prediction}")
        return True
    except Exception as e:
        print(f"[FAIL] Model loading or inference failed: {e}")
        return False

def test_live_detection(duration=30, threshold=0.25):
    print_header("Test 4: Live Wake Word Detection & Score Monitoring")
    import sounddevice as sd
    import numpy as np
    from openwakeword.model import Model
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "hey_blinky.onnx")
    oww_model = Model(wakeword_models=[model_path])
    
    audio_queue = []
    def callback(indata, frames, time_info, status):
        audio_data = (indata[:, 0] * 32767).astype(np.int16)
        audio_queue.append(audio_data)
        
    print(f"Listening for 'Hey Blinky' for {duration} seconds... (Speak now to see real-time scores, Threshold: {threshold})")
    print(f"{'Time':<8} | {'Audio RMS':<12} | {'Wake Word Score':<18} | {'Status'}")
    print("-" * 65)
    
    start_time = time.time()
    try:
        with sd.InputStream(samplerate=16000, blocksize=1280, channels=1, dtype='float32', callback=callback):
            while time.time() - start_time < duration:
                if len(audio_queue) > 0:
                    chunk = audio_queue.pop(0)
                    rms = np.sqrt(np.mean(chunk.astype(np.float32)**2))
                    prediction = oww_model.predict(chunk)
                    
                    score = list(prediction.values())[0] if prediction else 0.0
                    elapsed = int(time.time() - start_time)
                    
                    status_text = f"!!! WAKE_WORD_DETECTED (>{threshold}) !!!" if score > threshold else ("Hearing speech..." if rms > 500 else "Listening...")
                    
                    # Print real-time updates
                    print(f"{elapsed:>5}s  | {rms:>10.1f}   | {score:>16.4f}   | {status_text}", flush=True)
                    if score > threshold:
                        oww_model.reset()
                        time.sleep(1) # Pause briefly after detection
                else:
                    time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nLive test stopped by user.")
    except Exception as e:
        print(f"\n[FAIL] Live detection encountered an error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wake Word Diagnostic Tests")
    parser.add_argument("--live-duration", type=int, default=30, help="Duration in seconds for the live listening test.")
    parser.add_argument("--threshold", type=float, default=0.25, help="Confidence threshold for wake word detection")
    args = parser.parse_args()
    
    deps_ok = test_dependencies()
    if not deps_ok:
        print("\n[STOP] Dependency check failed. Please install missing packages in your virtual environment.")
        sys.exit(1)
        
    audio_ok = test_audio_devices()
    if not audio_ok:
        print("\n[STOP] Audio device test failed. Check your microphone connection and Windows audio settings.")
        sys.exit(1)
        
    model_ok = test_model_loading()
    if not model_ok:
        print("\n[STOP] Model loading test failed. Check ONNX runtime and model file validity.")
        sys.exit(1)
        
    print("\nAll pre-checks passed! Starting live detection test...")
    test_live_detection(args.live_duration, args.threshold)
