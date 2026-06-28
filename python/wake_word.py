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

def start_wake_word_detector(model_name="hey_blinky.onnx", threshold=0.25):
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
            
        print("Model loaded successfully. Listening for wake word...", file=sys.stderr)

        audio_queue = []

        def audio_callback(indata, frames, time_info, status):
            if status:
                print(status, file=sys.stderr)
            if is_paused:
                return
            # The indata is float32 between -1 and 1. OpenWakeWord expects int16.
            audio_data = (indata[:, 0] * 32767).astype(np.int16)
            audio_queue.append(audio_data)
            # Prevent queue accumulation/latency lag during heavy LLM activity
            if len(audio_queue) > 5:
                del audio_queue[:-5]

        # OpenWakeWord expects 16kHz, 1-channel, 16-bit PCM audio
        stream = sd.InputStream(samplerate=16000, blocksize=1280, channels=1, dtype='float32', callback=audio_callback)
        
        last_debug_time = time.time()

        with stream:
            while True:
                if is_paused:
                    if len(audio_queue) > 0:
                        audio_queue.clear()
                    time.sleep(0.1)
                    continue

                if len(audio_queue) > 0:
                    audio_chunk = audio_queue.pop(0)
                    
                    # Gate 1: Calculate Root Mean Square (RMS) energy to check if there is actual sound/speech
                    rms = np.sqrt(np.mean(audio_chunk.astype(np.float32)**2))
                    
                    # Run prediction if rms > 50.0 (lowered threshold to ensure speech is caught)
                    score = 0.0
                    if rms > 50.0:
                        prediction = owwModel.predict(audio_chunk)
                        
                        for mdl, s in prediction.items():
                            score = s
                            if s > threshold:
                                print(f"[WakeWord] DETECTED! Score: {s:.4f} | RMS: {rms:.1f}", file=sys.stderr, flush=True)
                                print("WAKE_WORD_DETECTED", flush=True)
                                owwModel.reset()
                                audio_queue.clear()
                                time.sleep(2)
                                break
                    
                    # Print live debugging messages to sys.stderr every 1 second
                    now = time.time()
                    if now - last_debug_time >= 1.0:
                        print(f"[WakeWord Debug] Mic RMS: {rms:.1f} | Score: {score:.4f} (Threshold: {threshold}) | Queue Backlog: {len(audio_queue)}", file=sys.stderr, flush=True)
                        last_debug_time = now
                    
                    # Yield CPU briefly so Ollama and Tauri threads are not starved
                    time.sleep(0.005)
                else:
                    time.sleep(0.01)

    except KeyboardInterrupt:
        print("Stopping wake word detector.", file=sys.stderr)
    except Exception as e:
        print(f"Error in wake word detector: {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenWakeWord Detector")
    parser.add_argument("--model", type=str, default="hey_blinky.onnx", help="Built-in model name or path to a custom .onnx model (e.g., hey_blinky.onnx)")
    parser.add_argument("--threshold", type=float, default=0.25, help="Confidence threshold for wake word detection")
    args = parser.parse_args()
    
    start_wake_word_detector(args.model, args.threshold)
