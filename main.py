
import time
import threading
import platform
import subprocess
import io
import wave
import struct
import math
import tempfile
import os
import tkinter as tk
from tkinter import ttk
from math import isfinite

# Try to import simpleaudio but DO NOT use it unless user selects it.
try:
    import simpleaudio as sa  # optional
except Exception:
    sa = None

APP_TITLE = "BPM Calculator (Safe Metronome + Visual)"
APP_MIN_WIDTH = 820
APP_MIN_HEIGHT = 760
SR = 44100  # sample rate
BYTES_PER_SAMPLE = 2
NUM_CH = 1

def clamp_bpm(value):
    try:
        v = float(value)
    except (ValueError, TypeError):
        return 0.0
    if v < 0:
        v = 0.0
    if v > 500:
        v = 500.0
    return v

# ---------- Click synthesis ----------
def synth_click_pcm(f_hz=2000.0, ms=20, gain=0.3, samplerate=SR):
    n = int(samplerate * (ms / 1000.0))
    buf = bytearray()
    for i in range(n):
        t = i / samplerate
        env = math.exp(-t * 60)  # very fast decay
        sample = math.sin(2 * math.pi * f_hz * t) * env * gain
        if sample > 1.0: sample = 1.0
        if sample < -1.0: sample = -1.0
        s = int(sample * 32767.0)
        buf += struct.pack('<h', s)
    return bytes(buf)

def wrap_wav(pcm_bytes, samplerate=SR, num_ch=NUM_CH, bytes_per_sample=BYTES_PER_SAMPLE):
    with io.BytesIO() as bio:
        with wave.open(bio, 'wb') as wf:
            wf.setnchannels(num_ch)
            wf.setsampwidth(bytes_per_sample)
            wf.setframerate(samplerate)
            wf.writeframes(pcm_bytes)
        return bio.getvalue()

ACCENT_PCM = synth_click_pcm(f_hz=2200.0, ms=25, gain=0.5)
TICK_PCM   = synth_click_pcm(f_hz=1500.0, ms=20, gain=0.35)
ACCENT_WAV = wrap_wav(ACCENT_PCM)
TICK_WAV   = wrap_wav(TICK_PCM)

class AudioEngine:
    def __init__(self, mode='System'):
        self.mode = mode  # 'System' | 'SimpleAudio'
        self._prepare_backend()

    def _prepare_backend(self):
        self.system = platform.system()
        self._sa_accent = None
        self._sa_tick = None
        self._tmp_accent = None
        self._tmp_tick = None

        if self.mode == 'SimpleAudio' and sa is not None:
            try:
                self._sa_accent = sa.WaveObject(ACCENT_PCM, num_channels=NUM_CH, bytes_per_sample=BYTES_PER_SAMPLE, sample_rate=SR)
                self._sa_tick   = sa.WaveObject(TICK_PCM,   num_channels=NUM_CH, bytes_per_sample=BYTES_PER_SAMPLE, sample_rate=SR)
            except Exception as e:
                print("[AudioEngine] Failed to init simpleaudio, falling back to System:", e)
                self.mode = 'System'

        if self.mode == 'System':
            try:
                ta = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                ta.write(ACCENT_WAV); ta.flush(); ta.close()
                self._tmp_accent = ta.name
                tt = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                tt.write(TICK_WAV); tt.flush(); tt.close()
                self._tmp_tick = tt.name
            except Exception as e:
                print("[AudioEngine] Failed to create temp wavs:", e)

    def cleanup(self):
        for p in (self._tmp_accent, self._tmp_tick):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def play(self, accent=False):
        if self.mode == 'SimpleAudio' and self._sa_accent and self._sa_tick:
            try:
                (self._sa_accent if accent else self._sa_tick).play()
                return
            except Exception as e:
                print("[AudioEngine] SimpleAudio play failed; switching to System:", e)
                self.mode = 'System'

        # System mode
        if self.system == 'Darwin':
            path = self._tmp_accent if accent else self._tmp_tick
            if path:
                try:
                    subprocess.Popen(['afplay', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception as e:
                    print("[AudioEngine] afplay failed:", e)
        elif self.system == 'Windows':
            try:
                import winsound
                data = ACCENT_WAV if accent else TICK_WAV
                winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
            except Exception as e:
                print("[AudioEngine] winsound failed:", e)
        else:
            path = self._tmp_accent if accent else self._tmp_tick
            if path:
                for cmd in (['paplay', path], ['aplay', path]):
                    try:
                        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        break
                    except Exception:
                        continue

class BpmCalculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(APP_MIN_WIDTH, APP_MIN_HEIGHT)

        # Tap-tempo state
        self.tap_times = []
        self.tap_timeout_s = 2.0
        self.max_taps = 8

        # Metronome state
        self.metro_thread = None
        self.metro_stop = threading.Event()
        self.metro_running_var = tk.BooleanVar(value=False)
        self.metro_subdiv_var = tk.StringVar(value="Quarter")
        self.metro_accent_every_var = tk.IntVar(value=4)
        self.audio_mode_var = tk.StringVar(value="System")
        self.audio_engine = AudioEngine(mode=self.audio_mode_var.get())
        self.audio_enabled_var = tk.BooleanVar(value=True)
        self.visual_enabled_var = tk.BooleanVar(value=True)

        # Vars
        self.bpm_var = tk.DoubleVar(value=120.0)
        self.ms_per_beat_var = tk.StringVar(value="500.00 ms")
        self.hz_var = tk.StringVar(value="2.000 Hz")
        self.half_bpm_var = tk.StringVar(value="60.00")
        self.double_bpm_var = tk.StringVar(value="240.00")
        self.third_bpm_var = tk.StringVar(value="40.00")
        self.quad_bpm_var = tk.StringVar(value="480.00")

        self.tap_bpm_var = tk.StringVar(value="—")
        self.tap_count_var = tk.StringVar(value="0")

        # Swing percentage var
        self.swing_pct_var = tk.DoubleVar(value=50.0)
        self.swing_first_ms_var = tk.StringVar(value="—")
        self.swing_second_ms_var = tk.StringVar(value="—")

        self._build_ui()
        self._wire_events()
        self.update_calculations()

    def _build_ui(self):
        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        # === Input row ===
        input_frame = ttk.LabelFrame(main, text="Input")
        input_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(input_frame, text="BPM (0–500):").grid(row=0, column=0, padx=(12, 8), pady=12, sticky="w")
        vcmd = (self.register(self._validate_bpm_entry), "%P")
        self.bpm_entry = ttk.Entry(input_frame, textvariable=self.bpm_var, width=10, validate="key", validatecommand=vcmd)
        self.bpm_entry.grid(row=0, column=1, pady=12, sticky="w")

        # Scale for BPM
        self.scale = ttk.Scale(input_frame, from_=0, to=500, orient="horizontal")
        self.scale.set(self.bpm_var.get())
        self.scale.grid(row=0, column=2, padx=(16, 12), pady=12, sticky="ew")
        input_frame.columnconfigure(2, weight=1)

        # Quick set buttons
        quick = ttk.Frame(input_frame)
        quick.grid(row=0, column=3, sticky="e", padx=(8, 12))
        for val in (60, 90, 100, 120, 140, 160):
            ttk.Button(quick, text=str(val), width=4, command=lambda v=val: self.set_bpm(v)).pack(side="left", padx=2)

        # === Tap-tempo & Swing row ===
        ts = ttk.LabelFrame(main, text="Tap Tempo & Swing")
        ts.pack(fill="x", pady=(0, 12))

        # Tap controls
        tap_frame = ttk.Frame(ts)
        tap_frame.grid(row=0, column=0, sticky="w", padx=12, pady=8)

        ttk.Button(tap_frame, text="Tap (Space)", command=self.tap).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(tap_frame, text="Reset Taps", command=self.reset_taps).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(tap_frame, text="Use Tap BPM", command=self.use_tap_bpm).grid(row=0, column=2, padx=(0, 8))

        ttk.Label(tap_frame, text="Tap BPM:").grid(row=1, column=0, sticky="e", pady=(8, 0))
        ttk.Label(tap_frame, textvariable=self.tap_bpm_var, font=("", 10, "bold")).grid(row=1, column=1, sticky="w", pady=(8,0))
        ttk.Label(tap_frame, text="taps:").grid(row=1, column=2, sticky="e", pady=(8,0))
        ttk.Label(tap_frame, textvariable=self.tap_count_var).grid(row=1, column=3, sticky="w", pady=(8,0))

        # Swing controls
        swing_frame = ttk.Frame(ts)
        swing_frame.grid(row=0, column=1, sticky="e", padx=12, pady=8)
        ttk.Label(swing_frame, text="Swing % (first of pair):").grid(row=0, column=0, sticky="w")
        self.swing_scale = ttk.Scale(swing_frame, from_=50, to=80, orient="horizontal", variable=self.swing_pct_var)
        self.swing_scale.grid(row=0, column=1, padx=8, sticky="ew")
        swing_frame.columnconfigure(1, weight=1)
        self.swing_spin = ttk.Spinbox(swing_frame, from_=50, to=80, increment=0.1, textvariable=self.swing_pct_var, width=6)
        self.swing_spin.grid(row=0, column=2, padx=(8,0))

        ttk.Label(swing_frame, text="Swung 8ths (pair):").grid(row=1, column=0, sticky="w", pady=(8,0))
        ttk.Label(swing_frame, textvariable=self.swing_first_ms_var, font=("", 10, "bold")).grid(row=1, column=1, sticky="w", pady=(8,0))
        ttk.Label(swing_frame, text=" + ").grid(row=1, column=2, sticky="w", pady=(8,0))
        ttk.Label(swing_frame, textvariable=self.swing_second_ms_var, font=("", 10, "bold")).grid(row=1, column=3, sticky="w", pady=(8,0))

        # === Metronome row ===
        metro = ttk.LabelFrame(main, text="Metronome")
        metro.pack(fill="x", pady=(0, 12))

        self.metro_btn = ttk.Checkbutton(metro, text="Start / Stop", variable=self.metro_running_var, command=self.toggle_metronome)
        self.metro_btn.grid(row=0, column=0, padx=12, pady=8, sticky="w")

        ttk.Label(metro, text="Subdivision:").grid(row=0, column=1, sticky="e")
        self.metro_subdiv = ttk.Combobox(metro, textvariable=self.metro_subdiv_var, width=16, state="readonly",
                                         values=["Quarter", "Eighth", "Sixteenth", "Quarter Triplets"])
        self.metro_subdiv.grid(row=0, column=2, padx=8, sticky="w")

        ttk.Label(metro, text="Accent every").grid(row=0, column=3, sticky="e")
        self.metro_accent_spin = ttk.Spinbox(metro, from_=1, to=16, textvariable=self.metro_accent_every_var, width=4)
        self.metro_accent_spin.grid(row=0, column=4, padx=(6, 12), sticky="w")

        ttk.Label(metro, text="Audio Engine:").grid(row=0, column=5, sticky="e")
        self.audio_mode_combo = ttk.Combobox(metro, textvariable=self.audio_mode_var, width=12, state="readonly",
                                             values=["System"] + (["SimpleAudio"] if sa is not None else []))
        self.audio_mode_combo.grid(row=0, column=6, padx=8, sticky="w")

        ttk.Checkbutton(metro, text="Audio On", variable=self.audio_enabled_var).grid(row=1, column=0, padx=12, sticky="w")
        ttk.Checkbutton(metro, text="Visual On", variable=self.visual_enabled_var).grid(row=1, column=1, sticky="w")

        # === Visual Beat Indicator ===
        visual = ttk.LabelFrame(main, text="Visual Beat")
        visual.pack(fill="x", pady=(0, 12))
        self.canvas = tk.Canvas(visual, width=140, height=140, highlightthickness=0)
        self.canvas.grid(row=0, column=0, padx=12, pady=8, sticky="w")
        self._circle = self.canvas.create_oval(10, 10, 130, 130, fill="#1f2937", outline="")
        # Label for beat count / subdivision
        self.beat_label_var = tk.StringVar(value="Ready")
        ttk.Label(visual, textvariable=self.beat_label_var, font=("", 12, "bold")).grid(row=0, column=1, padx=12, sticky="w")
        ttk.Label(visual, text="Accent flashes brighter; normal beats flash dimmer.").grid(row=0, column=2, padx=12, sticky="w")

        # === Summary row ===
        summary = ttk.LabelFrame(main, text="Summary")
        summary.pack(fill="x", pady=(0, 12))

        ttk.Label(summary, text="ms per beat:").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        ttk.Label(summary, textvariable=self.ms_per_beat_var, font=("", 10, "bold")).grid(row=0, column=1, pady=8, sticky="w")

        ttk.Label(summary, text="Frequency (Hz):").grid(row=0, column=2, padx=(24, 8), pady=8, sticky="w")
        ttk.Label(summary, textvariable=self.hz_var, font=("", 10, "bold")).grid(row=0, column=3, pady=8, sticky="w")

        grid = [
            ("Half-time BPM", self.half_bpm_var),
            ("Double-time BPM", self.double_bpm_var),
            ("Third-time BPM (÷3)", self.third_bpm_var),
            ("Quad-time BPM (×4)", self.quad_bpm_var),
        ]
        for i, (label, var) in enumerate(grid, start=1):
            ttk.Label(summary, text=label + ":").grid(row=i, column=0 if i < 3 else 2, padx=12 if i < 3 else (24, 8), pady=4, sticky="w")
            ttk.Label(summary, textvariable=var, font=("", 10, "bold")).grid(row=i, column=1 if i < 3 else 3, pady=4, sticky="w")

        # === Note durations table ===
        table_frame = ttk.LabelFrame(main, text="Note Durations (based on current BPM)")
        table_frame.pack(fill="both", expand=True)

        cols = ("note", "beats", "millis")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=12)
        self.tree.heading("note", text="Note")
        self.tree.heading("beats", text="Beats")
        self.tree.heading("millis", text="Milliseconds")
        self.tree.column("note", width=300, anchor="w")
        self.tree.column("beats", width=80, anchor="center")
        self.tree.column("millis", width=160, anchor="e")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        hint = ttk.Label(main, text="Safe Mode audio by default. Switch to 'SimpleAudio' if desired. Visual indicator flashes on each tick.", foreground="#666")
        hint.pack(anchor="w", padx=4, pady=(0, 4))

        # Attach callback for BPM slider after widgets exist
        self.scale.configure(command=self._on_bpm_scale)

    def _wire_events(self):
        self.bpm_entry.bind("<KeyRelease>", lambda e: self.update_calculations())
        self.bind("<Return>", lambda e: self.update_calculations())
        self.bind("<space>", lambda e: self.tap())
        self.swing_pct_var.trace_add("write", lambda *args: self._on_swing_change())
        self.audio_mode_var.trace_add("write", lambda *args: self._on_audio_mode_change())

    def _on_audio_mode_change(self):
        self.stop_metronome()
        if self.audio_engine:
            self.audio_engine.cleanup()
        self.audio_engine = AudioEngine(mode=self.audio_mode_var.get())

    def _on_bpm_scale(self, _):
        self.bpm_var.set(round(self.scale.get(), 2))
        self.update_calculations()

    def _on_swing_change(self):
        try:
            value = float(self.swing_pct_var.get())
        except Exception:
            return
        if value < 50.0: value = 50.0
        if value > 80.0: value = 80.0
        if value != self.swing_pct_var.get():
            self.swing_pct_var.set(value)
            return
        self.update_calculations()

    def _validate_bpm_entry(self, proposed: str):
        if proposed == "":
            return True
        try:
            float(proposed)
            return True
        except ValueError:
            return False

    def set_bpm(self, value: float):
        self.bpm_var.set(float(value))
        self.scale.set(float(value))
        self.update_calculations()

    # --- Tap tempo ---
    def tap(self):
        now = time.monotonic()
        if self.tap_times and (now - self.tap_times[-1] > self.tap_timeout_s):
            self.tap_times = []
        self.tap_times.append(now)
        if len(self.tap_times) > self.max_taps:
            self.tap_times = self.tap_times[-self.max_taps:]
        self._update_tap_readout()

    def reset_taps(self):
        self.tap_times = []
        self.tap_bpm_var.set("—")
        self.tap_count_var.set("0")

    def use_tap_bpm(self):
        try:
            bpm = float(self.tap_bpm_var.get())
        except ValueError:
            return
        self.set_bpm(bpm)

    def _update_tap_readout(self):
        n = len(self.tap_times)
        self.tap_count_var.set(str(n))
        if n < 2:
            self.tap_bpm_var.set("—")
            return
        intervals = [self.tap_times[i] - self.tap_times[i-1] for i in range(1, n)]
        avg = sum(intervals) / len(intervals)
        if avg <= 0:
            return
        bpm = 60.0 / avg
        bpm = clamp_bpm(bpm)
        self.tap_bpm_var.set(f"{bpm:.2f}")
        self.set_bpm(bpm)

    # --- Metronome ---
    def toggle_metronome(self):
        if self.metro_running_var.get():
            self.start_metronome()
        else:
            self.stop_metronome()

    def start_metronome(self):
        if self.metro_thread and self.metro_thread.is_alive():
            return
        self.metro_stop.clear()
        self.metro_thread = threading.Thread(target=self._metronome_loop, daemon=True)
        self.metro_thread.start()

    def stop_metronome(self):
        self.metro_stop.set()

    def _subdiv_multiplier(self):
        mode = self.metro_subdiv_var.get()
        if mode == "Quarter":
            return 1.0
        if mode == "Eighth":
            return 2.0
        if mode == "Sixteenth":
            return 4.0
        if mode == "Quarter Triplets":
            return 1.5
        return 1.0

    def _flash_visual(self, accent=False, count=0):
        # Accent bright (e.g., orange/red); normal dim (e.g., teal/blue)
        fill = "#ef4444" if accent else "#06b6d4"
        base = "#1f2937"
        self.canvas.itemconfig(self._circle, fill=fill)
        self.beat_label_var.set(f"Beat {count + 1}" if accent else f"tick {count + 1}")
        # revert after 120ms
        self.after(120, lambda: self.canvas.itemconfig(self._circle, fill=base))

    def _metronome_loop(self):
        count = 0
        next_time = time.perf_counter()
        while not self.metro_stop.is_set():
            bpm = clamp_bpm(self.bpm_var.get())
            if bpm <= 0:
                time.sleep(0.05)
                next_time = time.perf_counter() + 0.2
                continue

            subdiv = self._subdiv_multiplier()
            beat_sec = 60.0 / bpm
            period = beat_sec / subdiv

            accent_every = max(1, int(self.metro_accent_every_var.get()))
            is_accent = (count % accent_every == 0)

            # Schedule UI flash safely from thread
            if self.visual_enabled_var.get():
                self.after(0, self._flash_visual, is_accent, count % accent_every)

            # Play audio
            if self.audio_enabled_var.get():
                try:
                    self.audio_engine.play(accent=is_accent)
                except Exception as e:
                    print("[Metronome] Audio play error:", e)

            count = (count + 1) % 1000000

            next_time += period
            now = time.perf_counter()
            delay = next_time - now
            if delay < 0:
                next_time = now
                delay = 0
            end = now + delay
            while not self.metro_stop.is_set():
                remaining = end - time.perf_counter()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 0.01))

    def update_calculations(self):
        bpm = clamp_bpm(self.bpm_var.get())
        if bpm != self.bpm_var.get():
            self.bpm_var.set(bpm)
            self.scale.set(bpm)

        ms_per_beat = (60000.0 / bpm) if bpm > 0 else float("inf")
        hz = (bpm / 60.0)

        self.ms_per_beat_var.set("—" if ms_per_beat == float("inf") else f"{ms_per_beat:.2f} ms")
        self.hz_var.set(f"{hz:.3f} Hz" if isfinite(hz) else "—")

        self.half_bpm_var.set(f"{bpm/2:.2f}")
        self.double_bpm_var.set(f"{bpm*2:.2f}")
        self.third_bpm_var.set(f"{bpm/3:.2f}")
        self.quad_bpm_var.set(f"{bpm*4:.2f}")

        if bpm > 0:
            pair_ms = 60000.0 / bpm
            try:
                swing_pct = float(self.swing_pct_var.get())
            except Exception:
                swing_pct = 50.0
            swing_pct = 50.0 if swing_pct < 50.0 else 80.0 if swing_pct > 80.0 else swing_pct
            first_ms = pair_ms * (swing_pct / 100.0)
            second_ms = pair_ms - first_ms
            self.swing_first_ms_var.set(f"{first_ms:.2f} ms")
            self.swing_second_ms_var.set(f"{second_ms:.2f} ms")
        else:
            self.swing_first_ms_var.set("—")
            self.swing_second_ms_var.set("—")

        if hasattr(self, "tree"):
            for row in self.tree.get_children():
                self.tree.delete(row)

            notes = [
                ("1 bar (4/4)", 4.0),
                ("Dotted half", 3.0),
                ("Half", 2.0),
                ("Dotted quarter", 1.5),
                ("Quarter", 1.0),
                ("Triplet quarter", 2.0/3.0),
                ("Eighth", 0.5),
                ("Triplet eighth", 1.0/3.0),
                ("Sixteenth", 0.25),
                ("Triplet sixteenth", 1.0/6.0),
                ("Thirty-second", 0.125),
                ("— Swung Eighths (pair) —", None),
            ]

            for name, beats in notes:
                if beats is None:
                    self.tree.insert("", "end", values=(name, "", ""))
                    if bpm > 0:
                        swing_pct = float(self.swing_pct_var.get())
                        swing_pct = 50.0 if swing_pct < 50.0 else 80.0 if swing_pct > 80.0 else swing_pct
                        pair_ms = 60000.0 / bpm
                        first_ms = pair_ms * (swing_pct / 100.0)
                        second_ms = pair_ms - first_ms
                        self.tree.insert("", "end", values=(f"   First 8th ({swing_pct:.1f}%)", "—", f"{first_ms:.2f}"))
                        self.tree.insert("", "end", values=(f"   Second 8th ({100.0 - swing_pct:.1f}%)", "—", f"{second_ms:.2f}"))
                    else:
                        self.tree.insert("", "end", values=("   First 8th", "—", "—"))
                        self.tree.insert("", "end", values=("   Second 8th", "—", "—"))
                    continue

                if bpm <= 0:
                    ms = "—"
                else:
                    ms = 60000.0 * beats / bpm
                    ms = f"{ms:.2f}"
                self.tree.insert("", "end", values=(name, f"{beats:g}", ms))

    def destroy(self):
        self.stop_metronome()
        if self.audio_engine:
            self.audio_engine.cleanup()
        super().destroy()

if __name__ == "__main__":
    try:
        root = BpmCalculator()
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        root.mainloop()
    except Exception as e:
        import sys, traceback
        traceback.print_exc()
        sys.exit(1)
