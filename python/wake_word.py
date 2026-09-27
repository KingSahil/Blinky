import argparse
import time
import sys
import os
import threading
import logging
import ctypes

# Suppress ALSA C-level error noise on Linux (PipeWire / ALSA xruns)
if sys.platform.startswith("linux"):
    try:
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
            None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
        )
        def _alsa_noop_handler(filename, line, function, err, fmt):
            """Discard ALSA diagnostic callbacks already handled by the app."""
            pass
        _c_alsa_handler = ERROR_HANDLER_FUNC(_alsa_noop_handler)
        asound.snd_lib_error_set_handler(_c_alsa_handler)
    except Exception:
        pass

# Suppress tflite/openwakeword warning logs at startup
logging.getLogger().setLevel(logging.ERROR)

# Configure ONNX Runtime and OpenMP to be passive and single-threaded to prevent CPU starvation of Ollama
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OMP_WAIT_POLICY"] = "PASSIVE"
os.environ["ORT_MAX_NUM_THREADS"] = "1"

if sys.platform == "win32":
    try:
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

def start_wake_word_detector(model_name="hey_blinky.onnx", threshold=0.25, verbose=True):
    """Capture microphone audio and emit an event when the wake word is detected."""
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
        
        # Ensure openwakeword required feature models are available.
        try:
            import openwakeword.utils
            if hasattr(openwakeword.utils, "download_models"):
                openwakeword.utils.download_models()
        except Exception as exc:
            print(f"openwakeword feature-model check skipped: {exc}", file=sys.stderr)
        
        model_kwargs: dict = {}
        try:
            import inspect
            from openwakeword.model import Model as _Model
            sig = inspect.signature(_Model.__init__)
            if "wakeword_model_paths" in sig.parameters:
                model_kwargs["wakeword_model_paths"] = [model_name]
            else:
                model_kwargs["wakeword_models"] = [model_name]
        except Exception:
            model_kwargs = {"wakeword_models": [model_name]}
        owwModel = Model(**model_kwargs)
            
        print(f"Model loaded successfully. Listening for wake word... (Model: {os.path.basename(model_name)}, Threshold: {threshold})", file=sys.stderr, flush=True)
        if verbose:
            print(f"{'Time':<8} | {'Audio RMS':<12} | {'Wake Word Score':<18} | {'Status'}", file=sys.stderr, flush=True)
            print("-" * 75, file=sys.stderr, flush=True)

        audio_queue = []

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
            """Resample an input block and enqueue it for wake-word inference."""
            if is_paused:
                return
            
            # Take primary microphone channel directly
            raw_channel = indata[:, 0]
            
            # Resample to 16kHz using high-quality polyphase filtering
            if native_sr != 16000:
                resampled = scipy.signal.resample_poly(raw_channel, up, down)
            else:
                resampled = raw_channel
                
            audio_data = (resampled * 32767).astype(np.int16)
            audio_queue.append(audio_data)
            if len(audio_queue) > 30:
                audio_queue.clear()

        stream_kwargs = {
            "samplerate": native_sr,
            "blocksize": native_blocksize,
            "channels": native_channels,
            "dtype": "float32",
            "callback": audio_callback,
        }
        if sys.platform.startswith("linux"):
            stream_kwargs["latency"] = "high"

        with sd.InputStream(**stream_kwargs) as stream:
            start_time = time.time()
            last_debug_time = start_time

            while True:
                if is_paused:
                    if len(audio_queue) > 0:
                        audio_queue.clear()
                    time.sleep(0.1)
                    continue

                if len(audio_queue) > 0:
                    audio_chunk = audio_queue.pop(0)
                    
                    # Calculate Root Mean Square (RMS) energy for noise/speech diagnostics
                    rms = np.sqrt(np.mean(audio_chunk.astype(np.float32)**2))
                    
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
                    
                    now = time.time()
                    if verbose and now - last_debug_time >= 1.0:
                        elapsed = int(now - start_time)
                        status_text = "Hearing speech..." if rms > 200 else ("Background noise" if rms > 50 else "Listening (silence)...")
                        print(f"{elapsed:>5}s  | {rms:>10.1f}   | {score:>16.4f}   | {status_text} (Threshold: {threshold})", file=sys.stderr, flush=True)
                        last_debug_time = now
                    
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
    parser.add_argument("--verbose", action="store_true", help="Show live audio debug logs")
    args = parser.parse_args()
    
    start_wake_word_detector(args.model, args.threshold, args.verbose)
