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

def get_best_microphone_index(sd):
    try:
        devices = sd.query_devices()
        mic_candidates = []
        default_input = sd.default.device[0]

        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                name = dev.get("name", "").lower()
                if "stereo mix" in name or "wave out" in name:
                    continue
                if "microphone" in name or "mic" in name or "headset" in name:
                    mic_candidates.append(idx)

        if mic_candidates:
            return mic_candidates[0]
        return default_input
    except Exception:
        return None

def test_audio_devices():
    print_header("Test 2: Checking Audio Input Devices")
    import sounddevice as sd
    import numpy as np

    try:
        selected_idx = get_best_microphone_index(sd)
        if selected_idx is None:
            print("[FAIL] No active microphone device found.")
            return False

        device_info = sd.query_devices(selected_idx, 'input')
        print(f"Selected Device Index: {selected_idx}")
        print(f"Selected Device Name: {device_info['name']}")
        print(f"Selected Device Channels: {device_info['max_input_channels']}")

        print(f"\nTesting 16000Hz 1-channel direct stream for 3 seconds...")
        audio_data = []
        def callback(indata, frames, time_info, status):
            if status:
                print(f"Stream status: {status}")
            audio_data.append(indata[:, 0].copy())

        with sd.InputStream(device=selected_idx, samplerate=16000, blocksize=1280, channels=1, dtype='float32', callback=callback):
            time.sleep(3)

        if not audio_data:
            print("[FAIL] No audio data received from microphone. Check Windows Privacy/Microphone permissions.")
            return False

        concatenated = np.concatenate(audio_data)
        pcm_int16 = (concatenated * 32767).astype(np.int16)
        rms = np.sqrt(np.mean(pcm_int16.astype(np.float32)**2))
        max_val = np.max(np.abs(pcm_int16))
        print(f"[PASS] Successfully captured audio stream. PCM RMS: {rms:.1f}, Peak amplitude: {max_val}")
        if rms < 5.0:
            print("[WARNING] Audio level is very low. Please check microphone gain settings.")
        return True
    except Exception as e:
        print(f"[FAIL] Audio device test failed: {e}")
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
        if hasattr(openwakeword.utils, "download_models"):
            openwakeword.utils.download_models()
        print("[PASS] Feature models verified.")

        print("Initializing openwakeword Model...")
        oww_model = Model(wakeword_models=[model_path])
        print("[PASS] Model loaded into ONNX runtime successfully.")

        print("Testing synthetic inference on silence...")
        dummy_audio = np.zeros(1280, dtype=np.int16)
        prediction = oww_model.predict(dummy_audio)
        print(f"[PASS] Synthetic inference result: {prediction}")
        return True
    except Exception as e:
        print(f"[FAIL] Model loading or inference failed: {e}")
        return False

def test_live_detection(duration=10, threshold=0.25):
    print_header("Test 4: Live Wake Word Detection & Score Monitoring")
    import sounddevice as sd
    import numpy as np
    from openwakeword.model import Model

    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "hey_blinky.onnx")
    oww_model = Model(wakeword_models=[model_path])

    selected_idx = get_best_microphone_index(sd)
    audio_queue = []

    def callback(indata, frames, time_info, status):
        audio_data = (indata[:, 0] * 32767).astype(np.int16)
        audio_queue.append(audio_data)
        if len(audio_queue) > 5:
            del audio_queue[:-5]

    print(f"Listening for 'Hey Blinky' for {duration} seconds... (Threshold: {threshold})")
    print(f"{'Time':<8} | {'Audio RMS':<12} | {'Wake Word Score':<18} | {'Status'}")
    print("-" * 65)

    start_time = time.time()
    try:
        with sd.InputStream(device=selected_idx, samplerate=16000, blocksize=1280, channels=1, dtype='float32', callback=callback):
            while time.time() - start_time < duration:
                if len(audio_queue) > 0:
                    chunk = audio_queue.pop(0)
                    rms = np.sqrt(np.mean(chunk.astype(np.float32)**2))
                    prediction = oww_model.predict(chunk)

                    score = list(prediction.values())[0] if prediction else 0.0
                    elapsed = int(time.time() - start_time)

                    status_text = f"⚡ WAKE_WORD_DETECTED (>{threshold})!" if score > threshold else ("🎤 Hearing speech..." if rms > 150 else "💤 Listening...")
                    print(f"{elapsed:>5}s  | {rms:>10.1f}   | {score:>16.4f}   | {status_text}", flush=True)

                    if score > threshold:
                        oww_model.reset()
                        time.sleep(1)
                else:
                    time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nLive test stopped by user.")
    except Exception as e:
        print(f"\n[FAIL] Live detection error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wake Word Diagnostic Tests")
    parser.add_argument("--live-duration", type=int, default=5, help="Duration in seconds for live test")
    parser.add_argument("--threshold", type=float, default=0.25, help="Confidence threshold")
    args = parser.parse_args()

    deps_ok = test_dependencies()
    if not deps_ok:
        sys.exit(1)

    audio_ok = test_audio_devices()
    if not audio_ok:
        sys.exit(1)

    model_ok = test_model_loading()
    if not model_ok:
        sys.exit(1)

    print("\nAll pre-checks passed! Starting live detection test...")
    test_live_detection(args.live_duration, args.threshold)
