"""
AuraGen -- Native audio synthesis service.

Generates ambient background SFX/music based on a video's text prompt using
pure Python audio synthesis.  No external APIs or heavy audio libraries are
required -- only ``numpy`` for waveform math and the built-in ``wave`` module
for WAV output.
"""

from __future__ import annotations

import logging
import struct
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class AudioSynthService:
    """Synthesises ambient audio from text prompts.

    The service analyses a prompt for mood/environment keywords, maps them to
    synthesis parameters, and generates layered waveforms that are saved as
    standard PCM WAV files.
    """

    # ── Mood-keyword mappings ─────────────────────────────────────────────

    _MOOD_MAP: Dict[str, Dict[str, Any]] = {
        "ocean": {
            "keywords": ["ocean", "water", "sea", "wave", "beach", "surf"],
            "description": "Wave-like noise with low-pass filter",
            "base_freq": 80.0,
            "noise_color": "pink",
            "cutoff": 400.0,
            "envelope": {"attack": 0.3, "decay": 0.2, "sustain": 0.6, "release": 0.5},
            "modulation_freq": 0.15,
            "modulation_depth": 0.5,
            "layers": ["filtered_noise", "sine_pad"],
        },
        "city": {
            "keywords": ["city", "urban", "street", "traffic", "downtown"],
            "description": "Layered noise with rhythmic pulses",
            "base_freq": 200.0,
            "noise_color": "white",
            "cutoff": 2000.0,
            "envelope": {"attack": 0.05, "decay": 0.1, "sustain": 0.4, "release": 0.2},
            "modulation_freq": 2.0,
            "modulation_depth": 0.3,
            "layers": ["noise", "pulse", "sine_pad"],
        },
        "forest": {
            "keywords": ["forest", "nature", "garden", "tree", "woodland", "jungle"],
            "description": "Birdsong-like sine chirps + wind noise",
            "base_freq": 1200.0,
            "noise_color": "pink",
            "cutoff": 600.0,
            "envelope": {"attack": 0.01, "decay": 0.15, "sustain": 0.2, "release": 0.3},
            "modulation_freq": 0.08,
            "modulation_depth": 0.6,
            "layers": ["chirps", "wind_noise"],
        },
        "space": {
            "keywords": ["space", "cosmos", "galaxy", "star", "nebula", "void", "cosmic"],
            "description": "Deep drones + reverb-like echoes",
            "base_freq": 55.0,
            "noise_color": "pink",
            "cutoff": 200.0,
            "envelope": {"attack": 1.0, "decay": 0.5, "sustain": 0.7, "release": 1.5},
            "modulation_freq": 0.03,
            "modulation_depth": 0.4,
            "layers": ["deep_drone", "echo_pad"],
        },
        "fire": {
            "keywords": ["fire", "flame", "lava", "burn", "inferno", "ember"],
            "description": "Crackling noise bursts",
            "base_freq": 300.0,
            "noise_color": "white",
            "cutoff": 3000.0,
            "envelope": {"attack": 0.005, "decay": 0.05, "sustain": 0.1, "release": 0.1},
            "modulation_freq": 8.0,
            "modulation_depth": 0.7,
            "layers": ["crackle", "low_rumble"],
        },
        "rain": {
            "keywords": ["rain", "storm", "thunder", "drizzle", "monsoon"],
            "description": "White noise with amplitude modulation",
            "base_freq": 150.0,
            "noise_color": "white",
            "cutoff": 5000.0,
            "envelope": {"attack": 0.2, "decay": 0.3, "sustain": 0.7, "release": 0.4},
            "modulation_freq": 0.5,
            "modulation_depth": 0.35,
            "layers": ["amplitude_modulated_noise", "sine_pad"],
        },
        "calm": {
            "keywords": ["calm", "peaceful", "serene", "tranquil", "quiet", "gentle", "zen"],
            "description": "Soft pad-like sine waves",
            "base_freq": 220.0,
            "noise_color": "pink",
            "cutoff": 300.0,
            "envelope": {"attack": 0.8, "decay": 0.4, "sustain": 0.6, "release": 1.0},
            "modulation_freq": 0.05,
            "modulation_depth": 0.2,
            "layers": ["sine_pad", "filtered_noise"],
        },
    }

    _DEFAULT_MOOD: Dict[str, Any] = {
        "keywords": [],
        "description": "Gentle ambient drone",
        "base_freq": 130.0,
        "noise_color": "pink",
        "cutoff": 350.0,
        "envelope": {"attack": 0.5, "decay": 0.3, "sustain": 0.5, "release": 0.8},
        "modulation_freq": 0.07,
        "modulation_depth": 0.3,
        "layers": ["sine_pad", "filtered_noise"],
    }

    def __init__(self, sample_rate: int = 44100) -> None:
        """Initialise the audio synth service.

        Parameters
        ----------
        sample_rate:
            Output sample rate in Hz (default 44 100).
        """
        self.sample_rate: int = sample_rate

    # ═══════════════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════════════

    def generate_ambient(
        self,
        prompt: str,
        duration_seconds: float,
        output_path: str,
    ) -> str:
        """Generate ambient audio based on prompt keywords.

        Parameters
        ----------
        prompt:
            Text prompt describing the desired scene/mood.
        duration_seconds:
            Length of the generated audio in seconds.
        output_path:
            File path (including .wav extension) where the result is saved.

        Returns
        -------
        str
            The output filename (basename).
        """
        mood = self.analyze_prompt_mood(prompt)
        params = mood["params"]

        logger.info(
            "Generating ambient audio: mood=%s, duration=%.1fs, path=%s",
            mood["mood_name"],
            duration_seconds,
            output_path,
        )

        # Generate the individual layers.
        signals: List[np.ndarray] = []
        weights: List[float] = []

        layers = params.get("layers", ["sine_pad", "filtered_noise"])

        for layer_name in layers:
            signal = self._render_layer(
                layer_name=layer_name,
                duration=duration_seconds,
                params=params,
            )
            signals.append(signal)
            weights.append(1.0)

        # Mix all layers.
        if signals:
            mixed = self._mix_signals(signals, weights)
        else:
            mixed = np.zeros(int(self.sample_rate * duration_seconds), dtype=np.float64)

        # Apply global fade-in / fade-out.
        fade_in_secs = min(0.5, duration_seconds * 0.1)
        fade_out_secs = min(1.0, duration_seconds * 0.15)
        mixed = self._apply_fade(mixed, fade_in_secs, fade_out_secs)

        # Normalise to prevent clipping.
        peak = np.max(np.abs(mixed))
        if peak > 0:
            mixed = mixed / peak * 0.85

        # Save as WAV.
        self._save_wav(mixed, output_path)

        filename = Path(output_path).name
        logger.info("Ambient audio saved: %s", filename)
        return filename

    def analyze_prompt_mood(self, prompt: str) -> Dict[str, Any]:
        """Analyse a prompt string and return mood tags and synthesis parameters.

        Parameters
        ----------
        prompt:
            The text prompt to analyse.

        Returns
        -------
        dict
            A dictionary with keys:

            - ``mood_name`` (str) -- best-match mood category.
            - ``matched_keywords`` (list[str]) -- which keywords triggered it.
            - ``params`` (dict) -- synthesis parameters for the matched mood.
        """
        prompt_lower = prompt.lower()
        best_mood_name = "default"
        best_score = 0
        best_keywords: List[str] = []

        for mood_name, mood_data in self._MOOD_MAP.items():
            matched: List[str] = []
            for kw in mood_data["keywords"]:
                if kw in prompt_lower:
                    matched.append(kw)
            score = len(matched)
            if score > best_score:
                best_score = score
                best_mood_name = mood_name
                best_keywords = matched

        if best_score > 0:
            params = self._MOOD_MAP[best_mood_name]
        else:
            params = self._DEFAULT_MOOD

        return {
            "mood_name": best_mood_name,
            "matched_keywords": best_keywords,
            "params": params,
        }

    # ═══════════════════════════════════════════════════════════════════════
    # Waveform primitives
    # ═══════════════════════════════════════════════════════════════════════

    def _generate_sine_tone(
        self,
        freq: float,
        duration: float,
        sample_rate: Optional[int] = None,
    ) -> np.ndarray:
        """Generate a pure sine tone.

        Parameters
        ----------
        freq:
            Frequency in Hz.
        duration:
            Duration in seconds.
        sample_rate:
            Override sample rate (defaults to ``self.sample_rate``).

        Returns
        -------
        np.ndarray
            1-D float64 array with values in [-1, 1].
        """
        sr = sample_rate or self.sample_rate
        t = np.linspace(0.0, duration, int(sr * duration), endpoint=False)
        return np.sin(2.0 * np.pi * freq * t)

    def _generate_noise(
        self,
        duration: float,
        sample_rate: Optional[int] = None,
        color: str = "pink",
    ) -> np.ndarray:
        """Generate white or pink noise.

        Parameters
        ----------
        duration:
            Duration in seconds.
        sample_rate:
            Override sample rate (defaults to ``self.sample_rate``).
        color:
            ``"white"`` for flat-spectrum noise, ``"pink"`` for 1/f noise.

        Returns
        -------
        np.ndarray
            1-D float64 noise array normalised to [-1, 1].
        """
        sr = sample_rate or self.sample_rate
        n_samples = int(sr * duration)

        if color == "white":
            noise = np.random.default_rng().standard_normal(n_samples)
        elif color == "pink":
            # Approximate pink noise via Voss-McCartney algorithm (simplified).
            noise = self._pink_noise(n_samples)
        else:
            noise = np.random.default_rng().standard_normal(n_samples)

        # Normalise.
        peak = np.max(np.abs(noise))
        if peak > 0:
            noise = noise / peak
        return noise

    def _pink_noise(self, n_samples: int) -> np.ndarray:
        """Generate approximate pink (1/f) noise using spectral shaping.

        Uses the FFT method: generate white noise, shape the spectrum with
        a 1/sqrt(f) envelope, then IFFT back to the time domain.
        """
        rng = np.random.default_rng()
        white = rng.standard_normal(n_samples)

        # FFT.
        spectrum = np.fft.rfft(white)

        # Build 1/sqrt(f) envelope (skip DC to avoid division by zero).
        freqs = np.fft.rfftfreq(n_samples, d=1.0 / self.sample_rate)
        freqs[0] = 1.0  # avoid div-by-zero at DC
        pink_filter = 1.0 / np.sqrt(freqs)

        spectrum *= pink_filter

        # Back to time domain.
        pink = np.fft.irfft(spectrum, n=n_samples)
        return pink

    def _apply_envelope(
        self,
        signal: np.ndarray,
        attack: float,
        decay: float,
        sustain: float,
        release: float,
    ) -> np.ndarray:
        """Apply an ADSR amplitude envelope to a signal.

        Parameters
        ----------
        signal:
            Input waveform.
        attack:
            Attack time in seconds.
        decay:
            Decay time in seconds.
        sustain:
            Sustain level (0.0 -- 1.0).
        release:
            Release time in seconds.

        Returns
        -------
        np.ndarray
            The enveloped signal.
        """
        n = len(signal)
        sr = self.sample_rate

        a_samples = int(attack * sr)
        d_samples = int(decay * sr)
        r_samples = int(release * sr)
        s_samples = max(0, n - a_samples - d_samples - r_samples)

        envelope = np.ones(n, dtype=np.float64)

        # Attack: ramp from 0 to 1.
        if a_samples > 0:
            end_a = min(a_samples, n)
            envelope[:end_a] = np.linspace(0.0, 1.0, end_a)

        # Decay: ramp from 1 to sustain level.
        d_start = a_samples
        d_end = min(d_start + d_samples, n)
        if d_end > d_start:
            envelope[d_start:d_end] = np.linspace(1.0, sustain, d_end - d_start)

        # Sustain.
        s_start = d_end
        s_end = min(s_start + s_samples, n)
        if s_end > s_start:
            envelope[s_start:s_end] = sustain

        # Release: ramp from sustain to 0.
        r_start = s_end
        if r_start < n:
            envelope[r_start:] = np.linspace(sustain, 0.0, n - r_start)

        return signal * envelope

    def _low_pass_filter(
        self,
        signal: np.ndarray,
        cutoff: float,
        sample_rate: Optional[int] = None,
    ) -> np.ndarray:
        """Apply a simple low-pass filter using a rolling average.

        The kernel size is derived from the cutoff frequency:
        ``kernel_size = sample_rate / cutoff``.

        Parameters
        ----------
        signal:
            Input waveform.
        cutoff:
            Cutoff frequency in Hz.
        sample_rate:
            Override sample rate.

        Returns
        -------
        np.ndarray
            Filtered signal.
        """
        sr = sample_rate or self.sample_rate
        kernel_size = max(1, int(sr / cutoff))
        kernel = np.ones(kernel_size, dtype=np.float64) / kernel_size
        filtered = np.convolve(signal, kernel, mode="same")
        return filtered

    def _mix_signals(
        self,
        signals: List[np.ndarray],
        weights: List[float],
    ) -> np.ndarray:
        """Mix multiple audio layers with given weights.

        All signals are zero-padded to the length of the longest one.

        Parameters
        ----------
        signals:
            List of 1-D numpy arrays.
        weights:
            Per-signal amplitude weights.

        Returns
        -------
        np.ndarray
            Mixed signal.
        """
        if not signals:
            return np.array([], dtype=np.float64)

        max_len = max(len(s) for s in signals)
        mixed = np.zeros(max_len, dtype=np.float64)

        total_weight = sum(weights) or 1.0

        for sig, w in zip(signals, weights):
            padded = np.zeros(max_len, dtype=np.float64)
            padded[: len(sig)] = sig
            mixed += padded * (w / total_weight)

        return mixed

    # ═══════════════════════════════════════════════════════════════════════
    # Layer renderers
    # ═══════════════════════════════════════════════════════════════════════

    def _render_layer(
        self,
        layer_name: str,
        duration: float,
        params: Dict[str, Any],
    ) -> np.ndarray:
        """Render a named synthesis layer.

        Parameters
        ----------
        layer_name:
            One of the supported layer types.
        duration:
            Length in seconds.
        params:
            Mood-specific synthesis parameters.

        Returns
        -------
        np.ndarray
            Rendered audio waveform.
        """
        base_freq: float = params.get("base_freq", 130.0)
        noise_color: str = params.get("noise_color", "pink")
        cutoff: float = params.get("cutoff", 350.0)
        env: Dict[str, float] = params.get("envelope", {})
        mod_freq: float = params.get("modulation_freq", 0.1)
        mod_depth: float = params.get("modulation_depth", 0.3)

        attack = env.get("attack", 0.5)
        decay = env.get("decay", 0.3)
        sustain = env.get("sustain", 0.5)
        release = env.get("release", 0.8)

        if layer_name == "sine_pad":
            return self._layer_sine_pad(duration, base_freq, attack, decay, sustain, release, mod_freq, mod_depth)
        elif layer_name == "filtered_noise":
            return self._layer_filtered_noise(duration, noise_color, cutoff, mod_freq, mod_depth)
        elif layer_name == "noise":
            return self._layer_noise(duration, noise_color)
        elif layer_name == "pulse":
            return self._layer_pulse(duration, base_freq, mod_freq)
        elif layer_name == "chirps":
            return self._layer_chirps(duration, base_freq)
        elif layer_name == "wind_noise":
            return self._layer_wind_noise(duration)
        elif layer_name == "deep_drone":
            return self._layer_deep_drone(duration, base_freq, attack, decay, sustain, release)
        elif layer_name == "echo_pad":
            return self._layer_echo_pad(duration, base_freq)
        elif layer_name == "crackle":
            return self._layer_crackle(duration)
        elif layer_name == "low_rumble":
            return self._layer_low_rumble(duration)
        elif layer_name == "amplitude_modulated_noise":
            return self._layer_am_noise(duration, noise_color, mod_freq, mod_depth)
        else:
            # Fallback: gentle sine pad.
            return self._layer_sine_pad(duration, base_freq, attack, decay, sustain, release, mod_freq, mod_depth)

    # ── Individual layer implementations ──────────────────────────────────

    def _layer_sine_pad(
        self,
        duration: float,
        base_freq: float,
        attack: float,
        decay: float,
        sustain: float,
        release: float,
        mod_freq: float,
        mod_depth: float,
    ) -> np.ndarray:
        """Soft pad sound from layered detuned sine waves."""
        n = int(self.sample_rate * duration)
        t = np.linspace(0.0, duration, n, endpoint=False)

        # Three slightly detuned sines for a warm pad.
        sig = (
            0.5 * np.sin(2.0 * np.pi * base_freq * t)
            + 0.3 * np.sin(2.0 * np.pi * base_freq * 1.002 * t)
            + 0.2 * np.sin(2.0 * np.pi * base_freq * 0.998 * t)
        )

        # Slow amplitude modulation for movement.
        modulator = 1.0 - mod_depth + mod_depth * np.sin(2.0 * np.pi * mod_freq * t)
        sig *= modulator

        # ADSR envelope.
        sig = self._apply_envelope(sig, attack, decay, sustain, release)

        return sig

    def _layer_filtered_noise(
        self,
        duration: float,
        noise_color: str,
        cutoff: float,
        mod_freq: float,
        mod_depth: float,
    ) -> np.ndarray:
        """Low-pass-filtered noise with slow modulation (e.g., waves)."""
        noise = self._generate_noise(duration, color=noise_color)
        filtered = self._low_pass_filter(noise, cutoff)

        # Amplitude modulation to simulate natural ebb and flow.
        n = len(filtered)
        t = np.linspace(0.0, duration, n, endpoint=False)
        modulator = 1.0 - mod_depth + mod_depth * np.sin(2.0 * np.pi * mod_freq * t)
        filtered *= modulator

        return filtered * 0.4  # scale down

    def _layer_noise(self, duration: float, noise_color: str) -> np.ndarray:
        """Plain noise layer."""
        return self._generate_noise(duration, color=noise_color) * 0.3

    def _layer_pulse(
        self,
        duration: float,
        base_freq: float,
        mod_freq: float,
    ) -> np.ndarray:
        """Rhythmic pulses (e.g., city ambience)."""
        n = int(self.sample_rate * duration)
        t = np.linspace(0.0, duration, n, endpoint=False)

        # Create a pulsing amplitude envelope.
        pulse_env = 0.5 + 0.5 * np.sin(2.0 * np.pi * mod_freq * t)
        pulse_env = np.clip(pulse_env, 0.0, 1.0)

        # Tone burst.
        tone = np.sin(2.0 * np.pi * base_freq * t)
        return tone * pulse_env * 0.2

    def _layer_chirps(self, duration: float, base_freq: float) -> np.ndarray:
        """Bird-like chirps scattered throughout the duration."""
        n = int(self.sample_rate * duration)
        result = np.zeros(n, dtype=np.float64)
        rng = np.random.default_rng(42)

        # Generate random chirps.
        num_chirps = max(3, int(duration * 2))
        for _ in range(num_chirps):
            chirp_dur = rng.uniform(0.05, 0.15)
            chirp_freq = rng.uniform(base_freq * 0.8, base_freq * 1.5)
            chirp_samples = int(chirp_dur * self.sample_rate)
            t_chirp = np.linspace(0.0, chirp_dur, chirp_samples, endpoint=False)

            # Frequency sweep (rising chirp).
            sweep = np.sin(
                2.0 * np.pi * (chirp_freq + 500.0 * t_chirp / chirp_dur) * t_chirp
            )

            # Short envelope.
            env = np.hanning(chirp_samples)
            chirp = sweep * env * 0.3

            # Place at random position.
            start = rng.integers(0, max(1, n - chirp_samples))
            end = min(start + chirp_samples, n)
            result[start:end] += chirp[: end - start]

        return result

    def _layer_wind_noise(self, duration: float) -> np.ndarray:
        """Gentle wind noise (heavily filtered pink noise)."""
        noise = self._generate_noise(duration, color="pink")
        filtered = self._low_pass_filter(noise, 250.0)

        # Slow undulation.
        n = len(filtered)
        t = np.linspace(0.0, duration, n, endpoint=False)
        mod = 0.7 + 0.3 * np.sin(2.0 * np.pi * 0.05 * t)
        return filtered * mod * 0.3

    def _layer_deep_drone(
        self,
        duration: float,
        base_freq: float,
        attack: float,
        decay: float,
        sustain: float,
        release: float,
    ) -> np.ndarray:
        """Deep bass drone for space/cosmos moods."""
        n = int(self.sample_rate * duration)
        t = np.linspace(0.0, duration, n, endpoint=False)

        # Sub-bass fundamental + harmonic.
        drone = (
            0.6 * np.sin(2.0 * np.pi * base_freq * t)
            + 0.3 * np.sin(2.0 * np.pi * base_freq * 2.0 * t)
            + 0.1 * np.sin(2.0 * np.pi * base_freq * 3.0 * t)
        )

        # Very slow beating.
        beat = 0.9 + 0.1 * np.sin(2.0 * np.pi * 0.02 * t)
        drone *= beat

        drone = self._apply_envelope(drone, attack, decay, sustain, release)
        return drone

    def _layer_echo_pad(self, duration: float, base_freq: float) -> np.ndarray:
        """Reverb-like echo pad: delayed, attenuated copies of a tone."""
        n = int(self.sample_rate * duration)
        t = np.linspace(0.0, duration, n, endpoint=False)

        # Base tone.
        tone = 0.3 * np.sin(2.0 * np.pi * base_freq * 1.5 * t)

        # Simulate echo with delayed copies.
        result = np.copy(tone)
        delays = [0.3, 0.6, 1.0, 1.5]
        attenuation = [0.5, 0.3, 0.15, 0.08]

        for delay_s, atten in zip(delays, attenuation):
            delay_samples = int(delay_s * self.sample_rate)
            if delay_samples < n:
                delayed = np.zeros(n, dtype=np.float64)
                delayed[delay_samples:] = tone[: n - delay_samples]
                result += delayed * atten

        # Apply soft low-pass for a washed-out feel.
        result = self._low_pass_filter(result, 300.0)
        return result * 0.5

    def _layer_crackle(self, duration: float) -> np.ndarray:
        """Fire crackling: short random noise bursts."""
        n = int(self.sample_rate * duration)
        result = np.zeros(n, dtype=np.float64)
        rng = np.random.default_rng(99)

        num_crackles = max(10, int(duration * 15))
        for _ in range(num_crackles):
            burst_dur = rng.uniform(0.005, 0.03)
            burst_samples = int(burst_dur * self.sample_rate)
            burst = rng.standard_normal(burst_samples) * rng.uniform(0.1, 0.5)

            # Percussive envelope.
            env = np.exp(-np.linspace(0, 6, burst_samples))
            burst *= env

            start = rng.integers(0, max(1, n - burst_samples))
            end = min(start + burst_samples, n)
            result[start:end] += burst[: end - start]

        return result

    def _layer_low_rumble(self, duration: float) -> np.ndarray:
        """Low rumble for fire/lava scenes."""
        n = int(self.sample_rate * duration)
        t = np.linspace(0.0, duration, n, endpoint=False)

        rumble = (
            0.4 * np.sin(2.0 * np.pi * 40.0 * t)
            + 0.3 * np.sin(2.0 * np.pi * 60.0 * t)
            + 0.2 * np.sin(2.0 * np.pi * 80.0 * t)
        )

        # Irregular modulation.
        mod = 0.6 + 0.4 * np.sin(2.0 * np.pi * 0.3 * t) * np.sin(2.0 * np.pi * 0.13 * t)
        rumble *= mod

        rumble = self._low_pass_filter(rumble, 120.0)
        return rumble * 0.4

    def _layer_am_noise(
        self,
        duration: float,
        noise_color: str,
        mod_freq: float,
        mod_depth: float,
    ) -> np.ndarray:
        """Amplitude-modulated noise (rain/storm effect)."""
        noise = self._generate_noise(duration, color=noise_color)
        n = len(noise)
        t = np.linspace(0.0, duration, n, endpoint=False)

        # Amplitude modulation.
        modulator = 1.0 - mod_depth + mod_depth * np.sin(2.0 * np.pi * mod_freq * t)
        return noise * modulator * 0.4

    # ═══════════════════════════════════════════════════════════════════════
    # Utilities
    # ═══════════════════════════════════════════════════════════════════════

    def _apply_fade(
        self,
        signal: np.ndarray,
        fade_in_secs: float,
        fade_out_secs: float,
    ) -> np.ndarray:
        """Apply linear fade-in and fade-out to a signal."""
        n = len(signal)
        result = np.copy(signal)

        fade_in_samples = min(int(fade_in_secs * self.sample_rate), n)
        fade_out_samples = min(int(fade_out_secs * self.sample_rate), n)

        if fade_in_samples > 0:
            result[:fade_in_samples] *= np.linspace(0.0, 1.0, fade_in_samples)

        if fade_out_samples > 0:
            result[-fade_out_samples:] *= np.linspace(1.0, 0.0, fade_out_samples)

        return result

    def _save_wav(self, signal: np.ndarray, output_path: str) -> None:
        """Save a float64 signal as a 16-bit PCM WAV file.

        Parameters
        ----------
        signal:
            1-D float64 array with values in [-1, 1].
        output_path:
            Destination file path.
        """
        # Ensure parent directory exists.
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Convert to 16-bit PCM.
        pcm = np.clip(signal, -1.0, 1.0)
        pcm_int16 = (pcm * 32767).astype(np.int16)

        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)  # mono
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_int16.tobytes())
