"""Microphone listener: finds speech, transcribes it, and measures how it sounds.

Speech detection is energy based with an adaptive noise floor. It cannot tell
your voice from someone else's in the room; every segment is attributed to you.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from typing import Callable

import numpy as np
import sounddevice as sd

from . import config

logger = logging.getLogger(__name__)

SR = 16000
FRAME = 480  # 30 ms
START_FRAMES = 5  # 150 ms of speech opens a segment
END_FRAMES = 25  # 750 ms of silence closes it
MAX_SECONDS = 15.0
MIN_SECONDS = 0.7
SPEECH_DB = -42.0  # quieter than this is room noise, not someone talking at the desk
FILLER = {"mm", "hmm", "mhm", "mm-hmm", "uh-huh", "mm-mm", "hm", "ooh", "oh", "uh", "um", "ah", "huh", "yeah", "okay", "ok"}


def is_filler(text: str) -> bool:
    """Ignore empty transcripts and up to two standalone filler words."""
    bare = [w.strip(".,!?\"'").lower() for w in text.split()]
    return not bare or (len(bare) <= 2 and all(w in FILLER for w in bare))


def pick_input_device() -> int | None:
    devices = sd.query_devices()
    for want in config.MIC_PREFERENCE:
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0 and want.lower() in d["name"].lower():
                return i
    return None


def prosody(audio: np.ndarray, words: int) -> dict[str, float]:
    import librosa

    duration = len(audio) / SR
    rms = librosa.feature.rms(y=audio, frame_length=1024, hop_length=256)[0]
    loud = rms > max(1e-4, np.percentile(rms, 30))
    f0 = librosa.yin(audio, fmin=70, fmax=400, sr=SR, frame_length=1024, hop_length=256)
    n = min(len(f0), len(loud))
    voiced = f0[:n][loud[:n]]
    voiced = voiced[(voiced > 70) & (voiced < 400)]
    semitones = 12 * np.log2(voiced / np.median(voiced)) if len(voiced) > 5 else np.array([0.0])
    return {
        "duration_s": round(duration, 2),
        "words_per_minute": round(words / duration * 60, 1) if duration > 0 else 0.0,
        "pitch_hz": round(float(np.median(voiced)), 1) if len(voiced) > 5 else 0.0,
        "pitch_variation_semitones": round(float(np.std(semitones)), 2),
        "loudness_db": round(float(20 * np.log10(np.sqrt(np.mean(audio**2)) + 1e-9)), 1),
        "pause_ratio": round(float(1 - loud.mean()), 2),
    }


class EmotionModel:
    """Speech emotion classifier (HuBERT fine-tuned on IEMOCAP: neutral, happy, angry, sad), on CPU."""

    def __init__(self) -> None:
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        self.torch = torch
        self.extractor = AutoFeatureExtractor.from_pretrained(config.VOICE_EMOTION_REPO)
        self.model = AutoModelForAudioClassification.from_pretrained(config.VOICE_EMOTION_REPO).eval()

    def __call__(self, audio: np.ndarray) -> dict[str, float]:
        inputs = self.extractor(audio, sampling_rate=SR, return_tensors="pt")
        with self.torch.inference_mode():
            probs = self.model(**inputs).logits.softmax(-1)[0].tolist()
        labels = self.model.config.id2label
        return {labels[i]: round(p, 3) for i, p in enumerate(probs)}


class VoiceListener(threading.Thread):
    def __init__(self, on_segment: Callable[[dict], None]):
        super().__init__(daemon=True, name="voice")
        self.on_segment = on_segment
        self.blocks: queue.Queue[np.ndarray] = queue.Queue()
        self.paused = threading.Event()
        self.stopped = threading.Event()
        self.status = "loading"
        self.error: str | None = None
        self.device_name = ""
        self.level_db = -90.0
        self.speaking = False
        self.speech_seconds_today = 0.0
        self._segments: queue.Queue[np.ndarray] = queue.Queue()
        self.analysis_thread: threading.Thread | None = None

    def _callback(self, indata, frames, t, status) -> None:
        self.blocks.put(indata[:, 0].copy())

    def run(self) -> None:
        self.analysis_thread = threading.Thread(target=self._analyze_loop, daemon=True, name="voice-analyze")
        self.analysis_thread.start()
        stream = None
        noise: deque[float] = deque(maxlen=330)  # ~10 s of frame energies
        buf = np.zeros(0, dtype=np.float32)
        segment: list[np.ndarray] = []
        speech_run = silence_run = 0
        in_speech = False
        try:
            while not self.stopped.is_set():
                if self.paused.is_set():
                    if stream is not None:
                        stream.stop()
                        stream.close()
                        stream = None
                        self.speaking = False
                    self.stopped.wait(0.2)
                    continue
                if stream is None:
                    try:
                        device = pick_input_device()
                        self.device_name = sd.query_devices(device if device is not None else sd.default.device[0])["name"]
                        stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME, device=device, callback=self._callback)
                        stream.start()
                        if self.status == "loading":
                            self.status = "listening (loading transcriber)"
                    except Exception as exc:
                        self.error = f"mic: {exc}"
                        logger.exception("Could not open microphone")
                        self.stopped.wait(3)
                        continue
                try:
                    block = self.blocks.get(timeout=0.2)
                except queue.Empty:
                    continue
                buf = np.concatenate([buf, block])
                while len(buf) >= FRAME:
                    frame, buf = buf[:FRAME], buf[FRAME:]
                    db = float(20 * np.log10(np.sqrt(np.mean(frame**2)) + 1e-9))
                    self.level_db = db
                    floor = float(np.percentile(noise, 20)) if len(noise) > 30 else -60.0
                    loud = db > max(floor + 12.0, SPEECH_DB)
                    if not loud or not in_speech:
                        noise.append(db)
                    if in_speech:
                        segment.append(frame)
                        silence_run = 0 if loud else silence_run + 1
                        length = len(segment) * FRAME / SR
                        if silence_run >= END_FRAMES or length >= MAX_SECONDS:
                            audio = np.concatenate(segment)
                            if length >= MIN_SECONDS:
                                self._segments.put(audio)
                            segment, in_speech, silence_run = [], False, 0
                    else:
                        speech_run = speech_run + 1 if loud else 0
                        segment = (segment + [frame])[-START_FRAMES - 3 :]
                        if speech_run >= START_FRAMES:
                            in_speech, speech_run = True, 0
                    self.speaking = in_speech
        except Exception as exc:
            self.error = f"mic: {exc}"
            logger.exception("Microphone listener failed")
        finally:
            self.stopped.set()
            try:
                if stream is not None:
                    try:
                        stream.stop()
                    finally:
                        stream.close()
            except Exception as exc:
                self.error = f"mic cleanup: {exc}"
                logger.exception("Microphone cleanup failed")
            finally:
                self.speaking = False

    def stop(self) -> None:
        self.stopped.set()

    def join(self, timeout: float | None = None) -> None:
        super().join(timeout)
        if self.analysis_thread is not None:
            self.analysis_thread.join(timeout)

    def _analyze_loop(self) -> None:
        if self.stopped.is_set():
            return
        try:
            import mlx.core as mx
            from parakeet_mlx import from_pretrained
            from parakeet_mlx.audio import get_logmel

            asr = from_pretrained(config.PARAKEET_REPO)
        except Exception as exc:
            self.status, self.error = "transcriber failed", str(exc)
            logger.exception("Voice analysis failed")
            return
        if self.stopped.is_set():
            return
        emotion = None
        try:
            emotion = EmotionModel()
        except Exception as exc:  # optional; transcript and prosody still work
            self.error = f"voice emotion model unavailable: {exc}"
            logger.exception("Voice emotion model unavailable")
        self.status = "listening"
        labels = {"neu": "neutral", "hap": "happy", "ang": "angry", "sad": "sad"}
        while not self.stopped.is_set():
            try:
                audio = self._segments.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                peak = float(np.abs(audio).max())
                norm = audio / peak * 0.9 if peak > 0 else audio
                result = asr.generate(get_logmel(mx.array(norm), asr.preprocessor_config))[0]
                text = result.text.strip()
                if is_filler(text):
                    continue  # noise or a lone filler sound, not worth judging
                words = len(text.split())
                seg = {"ts": time.time(), "text": text, "prosody": prosody(audio, words), "emotion": {}}
                if emotion is not None:
                    seg["emotion"] = {labels.get(k, k): v for k, v in emotion(norm).items()}
                self.speech_seconds_today += seg["prosody"]["duration_s"]
                self.on_segment(seg)
            except Exception as exc:
                self.error = f"analyze: {exc}"
                logger.exception("Voice analysis failed")
