import argparse
import time
import sys
import os
import threading
import logging
import ctypes
from collections import deque
from fractions import Fraction
import numpy as np

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
pause_lock = threading.Lock()
last_pause_time = 0.0


def stdin_listener():
    global is_paused, last_pause_time
    try:
        for line in sys.stdin:
            command = line.strip().upper()
            with pause_lock:
                if command == "PAUSE":
                    is_paused = True
                    last_pause_time = time.time()
                elif command == "RESUME":
                    is_paused = False
    except Exception as e:
        print(f"[WakeWord] Stdin listener error: {e}", file=sys.stderr, flush=True)


def find_best_input_device(sd):
    """
    Tests and selects the best active physical microphone over Stereo Mix loopbacks.
    Returns (device_index, device_name, native_sample_rate).
    """
    try:
        apis = sd.query_hostapis()
        devices = sd.query_devices()
        candidates = []

        default_dev_idx = sd.default.device[0]
        default_dev_name = devices[default_dev_idx]["name"].lower() if default_dev_idx is not None and default_dev_idx >= 0 and default_dev_idx < len(devices) else ""
        is_default_loopback = any(bad in default_dev_name for bad in ["stereo mix", "wave out", "what u hear", "loopback", "virtual"])

        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                name = dev.get("name", "").lower()
                # Exclude loopback streams
                if any(bad in name for bad in ["stereo mix", "wave out", "what u hear", "loopback", "virtual"]):
                    continue

                api_name = apis[dev["hostapi"]]["name"] if dev.get("hostapi") < len(apis) else ""
                score = 0
                if "microphone" in name or "mic" in name or "headset" in name:
                    score += 35
                if "realtek" in name or "conexant" in name:
                    score += 8
                if "mapper" in name or "primary" in name:
                    if is_default_loopback:
                        score -= 50  # Heavily penalize mapper if Windows mapped it to Stereo Mix
                    else:
                        score += 5
                if api_name in ["Windows DirectSound", "MME", "Windows WASAPI"]:
                    score += 5

                candidates.append((score, idx, dev["name"], int(dev.get("default_samplerate", 44100))))

        candidates.sort(key=lambda x: x[0], reverse=True)

        for score, idx, dev_name, sr in candidates:
            try:
                captured = []
                def test_cb(indata, frames, time_info, status):
                    captured.append(True)
                test_block = max(256, int(sr * 0.05))
                with sd.InputStream(device=idx, samplerate=sr, channels=1, blocksize=test_block, callback=test_cb):
                    time.sleep(0.12)
                if len(captured) > 0:
                    if is_default_loopback and ("mapper" in dev_name.lower() or "primary" in dev_name.lower()):
                        print(
                            "⚠️ [WakeWord] ATTENTION: Windows default recording device is 'Stereo Mix'!\n"
                            "   Audio is currently capturing PC speaker output instead of your physical voice.\n"
                            "   To fix: Open Windows Sound Settings (mmsys.cpl) and set 'Microphone' as Default Device.",
                            file=sys.stderr,
                            flush=True,
                        )
                    return idx, dev_name, sr
            except Exception:
                continue

        default_input = sd.default.device[0]
        if default_input is not None and default_input >= 0:
            dev = devices[default_input]
            if is_default_loopback:
                print(
                    "⚠️ [WakeWord] ATTENTION: Windows default recording device is 'Stereo Mix'!\n"
                    "   Audio is currently capturing PC speaker output instead of your physical voice.\n"
                    "   To fix: Open Windows Sound Settings (mmsys.cpl) and set 'Microphone' as Default Device.",
                    file=sys.stderr,
                    flush=True,
                )
            return default_input, dev["name"], int(dev.get("default_samplerate", 44100))

    except Exception as exc:
        print(f"[WakeWord] Warning detecting audio devices: {exc}", file=sys.stderr, flush=True)

    return None, "Default Input", 44100


def resample_to_16k(audio_data, native_sr, resample_poly_fn):
    """Accurately downsamples native audio to 16,000 Hz using polyphase resampling."""
    if native_sr == 16000:
        return audio_data

    if native_sr == 48000:
        up, down = 1, 3
    elif native_sr == 44100:
        up, down = 160, 441
    else:
        frac = Fraction(16000, native_sr).limit_denominator(500)
        up, down = frac.numerator, frac.denominator

    return resample_poly_fn(audio_data, up, down).astype(np.int16)


def start_wake_word_detector(model_name="hey_blinky.onnx", threshold=0.25, verbose=True):
    """Captures microphone audio, resamples cleanly to 16kHz, and emits WAKE_WORD_DETECTED."""
    threading.Thread(target=stdin_listener, daemon=True).start()

    try:
        import sounddevice as sd
        import numpy as np
        import scipy.signal
        from openwakeword.model import Model
    except ImportError as e:
        print(f"[WakeWord] Missing dependencies: {e}", file=sys.stderr, flush=True)
        return

    # Resolve model path
    candidate_paths = [
        model_name,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.basename(model_name)),
        os.path.join(os.getcwd(), "python", os.path.basename(model_name)),
        os.path.join(os.getcwd(), "common", "python", os.path.basename(model_name)),
    ]
    resolved_model = next((p for p in candidate_paths if os.path.exists(p)), model_name)

    print(f"[WakeWord] Loading model: {resolved_model}", file=sys.stderr, flush=True)
    try:
        owwModel = Model(wakeword_models=[resolved_model])
    except Exception as exc:
        print(f"[WakeWord] Failed to instantiate OpenWakeWord model: {exc}", file=sys.stderr, flush=True)
        return

    device_idx, device_name, native_sr = find_best_input_device(sd)
    native_block_size = int(native_sr * 0.08)  # 80ms chunk
    audio_queue = deque(maxlen=24)  # ~1.9s rolling window

    print(f"[WakeWord] Locked Device [{device_idx}]: '{device_name}' ({native_sr}Hz -> 16000Hz)", file=sys.stderr, flush=True)
    print(f"[WakeWord] Listening for 'Hey Blinky' (Threshold: {threshold})...", file=sys.stderr, flush=True)

    def audio_callback(indata, frames, time_info, status):
        if is_paused:
            return
        # Convert float32 [-1.0, 1.0] to int16 PCM
        pcm_native = (indata[:, 0] * 32767).astype(np.int16)
        # Polyphase resample to 16kHz
        pcm_16k = resample_to_16k(pcm_native, native_sr, scipy.signal.resample_poly)
        if len(pcm_16k) == 1280:
            audio_queue.append(pcm_16k)
        elif len(pcm_16k) > 1280:
            audio_queue.append(pcm_16k[:1280])

    stream_kwargs = {
        "samplerate": native_sr,
        "blocksize": native_block_size,
        "channels": 1,
        "dtype": "float32",
        "callback": audio_callback,
    }
    if device_idx is not None:
        stream_kwargs["device"] = device_idx
    if sys.platform.startswith("linux"):
        stream_kwargs["latency"] = "high"

    last_badge_time = 0.0

    try:
        with sd.InputStream(**stream_kwargs):
            while True:
                if is_paused:
                    time.sleep(0.08)
                    continue

                if len(audio_queue) > 0:
                    chunk = audio_queue.popleft()

                    # Real-time RMS calculation
                    rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

                    # Adaptive noise gating: skip heavy neural net inference on silence
                    if rms < 30.0:
                        score = 0.0
                    else:
                        prediction = owwModel.predict(chunk)
                        score = float(list(prediction.values())[0]) if prediction else 0.0

                    if score >= threshold:
                        # Print trigger event to stdout for Tauri
                        print("WAKE_WORD_DETECTED", flush=True)
                        print(
                            f"\n⚡ [WAKE_WORD_DETECTED] \"Hey Blinky\" triggered! (Score: {score:.3f} >= {threshold}, RMS: {rms:.1f})\n",
                            file=sys.stderr,
                            flush=True,
                        )
                        owwModel.reset()
                        audio_queue.clear()
                        time.sleep(1.2)  # Refractory cooldown
                        continue

                    now = time.time()
                    if verbose and now - last_badge_time >= 1.0:
                        status_tag = "🗣️ Speech" if rms > 120 else ("🔉 Voice" if rms > 45 else "💤 Ambient")
                        sys.stderr.write(
                            f"\r[WakeWord] {status_tag} | RMS: {rms:>5.1f} | Score: {score:>6.3f} | Target: {threshold}   "
                        )
                        sys.stderr.flush()
                        last_badge_time = now

                    time.sleep(0.005)
                else:
                    time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[WakeWord] Detector stopped.", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"\n[WakeWord] Error in audio stream: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenWakeWord Detector")
    parser.add_argument("--model", type=str, default="hey_blinky.onnx", help="Model name or path to custom .onnx model")
    parser.add_argument("--threshold", type=float, default=0.25, help="Confidence threshold for wake word detection")
    parser.add_argument("--verbose", action="store_true", help="Show live audio debug logs")
    args = parser.parse_args()

    start_wake_word_detector(args.model, args.threshold, args.verbose)
