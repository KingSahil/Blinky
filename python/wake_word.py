import argparse
import time
import sys
import os
import threading
import logging
import ctypes

# Suppress ALSA C-level error noise on Linux
if sys.platform.startswith("linux"):
    try:
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
            None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
        )
        def _alsa_noop_handler(filename, line, function, err, fmt):
            pass
        _c_alsa_handler = ERROR_HANDLER_FUNC(_alsa_noop_handler)
        asound.snd_lib_error_set_handler(_c_alsa_handler)
    except Exception:
        pass

# Suppress warning noise
logging.getLogger().setLevel(logging.ERROR)

# Configure ONNX Runtime and OpenMP to prevent CPU starvation
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OMP_WAIT_POLICY"] = "PASSIVE"
os.environ["ORT_MAX_NUM_THREADS"] = "1"

if sys.platform == "win32":
    try:
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


def get_best_microphone_index(sd):
    """Scans sounddevice input devices to select an active physical microphone over Stereo Mix loopbacks."""
    try:
        devices = sd.query_devices()
        mic_candidates = []
        default_input = sd.default.device[0]

        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                name = dev.get("name", "").lower()
                # Exclude loopback output streams like Stereo Mix
                if "stereo mix" in name or "wave out" in name:
                    continue
                if "microphone" in name or "mic" in name or "headset" in name:
                    mic_candidates.append(idx)

        if mic_candidates:
            selected = mic_candidates[0]
            dev_name = devices[selected]["name"]
            print(f"[WakeWord] Selected Microphone Device [{selected}]: {dev_name}", file=sys.stderr, flush=True)
            return selected

        # Fallback to default input device if valid
        if default_input is not None and default_input >= 0:
            dev_name = devices[default_input]["name"]
            print(f"[WakeWord] Using Default Input Device [{default_input}]: {dev_name}", file=sys.stderr, flush=True)
            return default_input

    except Exception as exc:
        print(f"[WakeWord] Warning resolving microphone device: {exc}", file=sys.stderr, flush=True)
    return None


def start_wake_word_detector(model_name="hey_blinky.onnx", threshold=0.25, verbose=True):
    """Captures microphone audio and emits WAKE_WORD_DETECTED when the target wake word is spoken."""
    threading.Thread(target=stdin_listener, daemon=True).start()

    try:
        import sounddevice as sd
        import numpy as np
        from openwakeword.model import Model
    except ImportError as e:
        print(f"Error importing dependencies: {e}", file=sys.stderr)
        return

    try:
        # Resolve model path
        if not os.path.isabs(model_name):
            if not os.path.exists(model_name):
                script_dir = os.path.dirname(os.path.abspath(__file__))
                candidate = os.path.join(script_dir, os.path.basename(model_name))
                if os.path.exists(candidate):
                    model_name = candidate

        print(f"[WakeWord] Loading model: {model_name}", file=sys.stderr, flush=True)

        try:
            import openwakeword.utils
            if hasattr(openwakeword.utils, "download_models"):
                openwakeword.utils.download_models()
        except Exception as exc:
            print(f"[WakeWord] Feature model check: {exc}", file=sys.stderr)

        owwModel = Model(wakeword_models=[model_name])
        print(f"[WakeWord] Model loaded successfully. Threshold: {threshold}", file=sys.stderr, flush=True)

        selected_device = get_best_microphone_index(sd)
        audio_queue = []

        def audio_callback(indata, frames, time_info, status):
            if is_paused:
                return
            # indata is float32 [-1.0, 1.0]. Convert to int16 PCM for openwakeword.
            audio_data = (indata[:, 0] * 32767).astype(np.int16)
            audio_queue.append(audio_data)
            # Maintain tight 5-block queue (400ms max backlog) for real-time sub-100ms response
            if len(audio_queue) > 5:
                del audio_queue[:-5]

        stream_kwargs = {
            "samplerate": 16000,
            "blocksize": 1280,
            "channels": 1,
            "dtype": "float32",
            "callback": audio_callback,
        }
        if selected_device is not None:
            stream_kwargs["device"] = selected_device
        if sys.platform.startswith("linux"):
            stream_kwargs["latency"] = "high"

        print(f"[WakeWord] Listening for 'Hey Blinky'...", file=sys.stderr, flush=True)
        if verbose:
            print(f"{'Time':<8} | {'Audio RMS':<12} | {'Wake Word Score':<18} | {'Status'}", file=sys.stderr, flush=True)
            print("-" * 75, file=sys.stderr, flush=True)

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

                    # Calculate Root Mean Square (RMS) energy
                    rms = np.sqrt(np.mean(audio_chunk.astype(np.float32)**2))

                    prediction = owwModel.predict(audio_chunk)
                    score = list(prediction.values())[0] if prediction else 0.0

                    if score > threshold:
                        elapsed = int(time.time() - start_time)
                        status_text = f"*** WAKE_WORD_DETECTED (Score: {score:.4f} > {threshold}) ***"
                        print(f"{elapsed:>5}s  | {rms:>10.1f}   | {score:>16.4f}   | {status_text}", file=sys.stderr, flush=True)
                        print("WAKE_WORD_DETECTED", flush=True)
                        owwModel.reset()
                        audio_queue.clear()
                        time.sleep(2)
                        continue

                    now = time.time()
                    if verbose and now - last_debug_time >= 1.0:
                        elapsed = int(now - start_time)
                        status_text = "[SPEECH] Hearing speech..." if rms > 150 else ("[LOW] Quiet sound" if rms > 30 else "[WAIT] Listening...")
                        print(f"{elapsed:>5}s  | {rms:>10.1f}   | {score:>16.4f}   | {status_text}", file=sys.stderr, flush=True)
                        last_debug_time = now

                    time.sleep(0.005)
                else:
                    time.sleep(0.01)

    except KeyboardInterrupt:
        print("[WakeWord] Detector stopped.", file=sys.stderr)
    except Exception as e:
        print(f"[WakeWord] Error in detector loop: {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenWakeWord Detector")
    parser.add_argument("--model", type=str, default="hey_blinky.onnx", help="Model name or path to custom .onnx model")
    parser.add_argument("--threshold", type=float, default=0.25, help="Confidence threshold for wake word detection")
    parser.add_argument("--verbose", action="store_true", help="Show live audio debug logs")
    args = parser.parse_args()

    start_wake_word_detector(args.model, args.threshold, args.verbose)
