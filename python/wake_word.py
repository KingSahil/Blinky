import argparse
import time
import sys
import os
import threading

# Configure ONNX Runtime and OpenMP to be passive and single-threaded to prevent CPU starvation of Ollama
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OMP_WAIT_POLICY"] = "PASSIVE"
os.environ["ORT_MAX_NUM_THREADS"] = "1"

if sys.platform == "win32":
    try:
        import ctypes
        # Set process priority to BELOW_NORMAL_PRIORITY_CLASS (0x4000) so Ollama gets CPU priority
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    except Exception:
        pass

is_paused = False

def stdin_listener():
    global is_paused
    try:
        for line in sys.stdin:
            command = line.strip().upper()
            if command == "PAUSE":
                is_paused = True
                print("[WakeWord] Paused via stdin", file=sys.stderr, flush=True)
            elif command == "RESUME":
                is_paused = False
                print("[WakeWord] Resumed via stdin", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"Error in stdin listener: {e}", file=sys.stderr)

def start_wake_word_detector(model_name="hey_blinky.onnx", threshold=0.25, verbose=False):
    threading.Thread(target=stdin_listener, daemon=True).start()
    try:
        # pyrefly: ignore [missing-import]
        import sounddevice as sd
        import numpy as np
        from openwakeword.model import Model
    except ImportError as e:
        print(f"Error importing dependencies: {e}", file=sys.stderr)
        return

    try:
        # Resolve absolute path to model if it's relative
        if not os.path.isabs(model_name):
            if not os.path.exists(model_name):
                # Try relative to this script's directory
                script_dir = os.path.dirname(os.path.abspath(__file__))
                candidate = os.path.join(script_dir, os.path.basename(model_name))
                if os.path.exists(candidate):
                    model_name = candidate

        print(f"Loading openwakeword model: {model_name}", file=sys.stderr)
        
        # Ensure openwakeword required feature models (melspectrogram.onnx, embedding_model.onnx) are downloaded
        import openwakeword.utils
        openwakeword.utils.download_models()
        
        if os.path.exists(model_name) and model_name.endswith('.onnx'):
            owwModel = Model(wakeword_models=[model_name])
        else:
            owwModel = Model(wakeword_models=[model_name])
            
        print(f"Model loaded successfully. Listening for wake word... (Model: {os.path.basename(model_name)}, Threshold: {threshold})", file=sys.stderr, flush=True)
        if verbose:
            print(f"{'Time':<8} | {'Audio RMS':<12} | {'Wake Word Score':<18} | {'Status'}", file=sys.stderr, flush=True)
            print("-" * 75, file=sys.stderr, flush=True)

        audio_queue = []

        # OpenWakeWord expects 16kHz, 16-bit PCM audio.
        # Windows mic arrays distort heavily if PortAudio forces resampling/downmixing.
        # Therefore, we capture at native samplerate and native channel count, then resample in Python.
        import math
        import scipy.signal

        device_info = sd.query_devices(sd.default.device[0], 'input')
        native_sr = int(device_info['default_samplerate'])
        native_channels = int(device_info['max_input_channels'])
        
        target_sr = 16000
        gcd = math.gcd(target_sr, native_sr)
        up = target_sr // gcd
        down = native_sr // gcd
        
        # 80ms blocksize at native samplerate
        native_blocksize = int(native_sr * 0.08)

        def audio_callback(indata, frames, time_info, status):
            if status:
                print(status, file=sys.stderr)
            if is_paused:
                return
            
            # Take primary microphone channel directly to avoid Windows downmix phase cancellation
            raw_channel = indata[:, 0]
            
            # Resample to 16kHz using high-quality polyphase filtering
            if native_sr != 16000:
                resampled = scipy.signal.resample_poly(raw_channel, up, down)
            else:
                resampled = raw_channel
                
            audio_data = (resampled * 32767).astype(np.int16)
            audio_queue.append(audio_data)
            # Avoid dropping small numbers of frames so OpenWakeWord's ring buffer stays contiguous.
            # Only reset if severe backlog accumulates (e.g. >30 frames / 2.4s lag).
            if len(audio_queue) > 30:
                audio_queue.clear()

        stream = None

        def start_stream():
            nonlocal stream
            if stream is None:
                try:
                    stream = sd.InputStream(samplerate=native_sr, blocksize=native_blocksize, channels=native_channels, dtype='float32', callback=audio_callback)
                    stream.start()
                except Exception as e:
                    print(f"Error starting audio stream: {e}", file=sys.stderr)

        def stop_stream():
            nonlocal stream
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                stream = None

        start_time = time.time()
        last_debug_time = start_time

        start_stream()

        try:
            while True:
                if is_paused:
                    if stream is not None:
                        stop_stream()
                    if len(audio_queue) > 0:
                        audio_queue.clear()
                    time.sleep(0.1)
                    continue
                else:
                    if stream is None:
                        start_stream()
                        audio_queue.clear()

                if len(audio_queue) > 0:
                    audio_chunk = audio_queue.pop(0)
                    
                    # Calculate Root Mean Square (RMS) energy for noise/speech diagnostics
                    rms = np.sqrt(np.mean(audio_chunk.astype(np.float32)**2))
                    
                    # Always feed audio to openwakeword to maintain internal ring buffer continuity
                    prediction = owwModel.predict(audio_chunk)
                    score = list(prediction.values())[0] if prediction else 0.0
                    
                    if score > threshold:
                        elapsed = int(time.time() - start_time)
                        status_text = f"!!! WAKE_WORD_DETECTED (>{threshold}) !!!"
                        print(f"{elapsed:>5}s  | {rms:>10.1f}   | {score:>16.4f}   | {status_text}", file=sys.stderr, flush=True)
                        print("WAKE_WORD_DETECTED", flush=True)
                        owwModel.reset()
                        audio_queue.clear()
                        time.sleep(2)
                        continue
                    
                    # Print live debugging messages to sys.stderr every 1 second in beautiful descriptive table format
                    now = time.time()
                    if verbose and now - last_debug_time >= 1.0:
                        elapsed = int(now - start_time)
                        status_text = "Hearing speech..." if rms > 200 else ("Background noise" if rms > 50 else "Listening (silence)...")
                        print(f"{elapsed:>5}s  | {rms:>10.1f}   | {score:>16.4f}   | {status_text} (Threshold: {threshold})", file=sys.stderr, flush=True)
                        last_debug_time = now
                    
                    # Yield CPU briefly so Ollama and Tauri threads are not starved
                    time.sleep(0.005)
                else:
                    time.sleep(0.01)
        finally:
            stop_stream()

    except KeyboardInterrupt:
        print("Stopping wake word detector.", file=sys.stderr)
    except Exception as e:
        print(f"Error in wake word detector: {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenWakeWord Detector")
    parser.add_argument("--model", type=str, default="hey_blinky.onnx", help="Built-in model name or path to a custom .onnx model (e.g., hey_blinky.onnx)")
    parser.add_argument("--threshold", type=float, default=0.25, help="Confidence threshold for wake word detection")
    parser.add_argument("--verbose", action="store_true", help="Show live audio debug logs")
    args = parser.parse_args()
    
    start_wake_word_detector(args.model, args.threshold, args.verbose)
