import tkinter as tk
from tkinter import ttk
from math import isfinite

APP_TITLE = "BPM Calculator"
APP_MIN_WIDTH = 620
APP_MIN_HEIGHT = 520

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

class BpmCalculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(APP_MIN_WIDTH, APP_MIN_HEIGHT)

        # Vars
        self.bpm_var = tk.DoubleVar(value=120.0)
        self.ms_per_beat_var = tk.StringVar(value="500.00 ms")
        self.hz_var = tk.StringVar(value="2.000 Hz")
        self.half_bpm_var = tk.StringVar(value="60.00")
        self.double_bpm_var = tk.StringVar(value="240.00")
        self.third_bpm_var = tk.StringVar(value="40.00")
        self.quad_bpm_var = tk.StringVar(value="480.00")

        self._build_ui()
        self._wire_events()
        self.update_calculations()

    def _build_ui(self):
        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        # === Input row ===
        input_frame = ttk.LabelFrame(main, text="Input")
        input_frame.pack(fill="x", pady=(0, 12))

        # BPM entry
        ttk.Label(input_frame, text="BPM (0–500):").grid(row=0, column=0, padx=(12, 8), pady=12, sticky="w")
        vcmd = (self.register(self._validate_bpm_entry), "%P")
        self.bpm_entry = ttk.Entry(input_frame, textvariable=self.bpm_var, width=10, validate="key", validatecommand=vcmd)
        self.bpm_entry.grid(row=0, column=1, pady=12, sticky="w")

        # Scale
        self.scale = ttk.Scale(input_frame, from_=0, to=500, orient="horizontal", command=self._on_scale)
        self.scale.set(self.bpm_var.get())
        self.scale.grid(row=0, column=2, padx=(16, 12), pady=12, sticky="ew")
        input_frame.columnconfigure(2, weight=1)

        # Quick set buttons
        quick = ttk.Frame(input_frame)
        quick.grid(row=0, column=3, sticky="e", padx=(8, 12))
        for val in (60, 90, 100, 120, 140, 160):
            b = ttk.Button(quick, text=str(val), width=4, command=lambda v=val: self.set_bpm(v))
            b.pack(side="left", padx=2)

        # === Summary row ===
        summary = ttk.LabelFrame(main, text="Summary")
        summary.pack(fill="x", pady=(0, 12))

        ttk.Label(summary, text="ms per beat:").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        ttk.Label(summary, textvariable=self.ms_per_beat_var, font=("", 10, "bold")).grid(row=0, column=1, pady=8, sticky="w")

        ttk.Label(summary, text="Frequency (Hz):").grid(row=0, column=2, padx=(24, 8), pady=8, sticky="w")
        ttk.Label(summary, textvariable=self.hz_var, font=("", 10, "bold")).grid(row=0, column=3, pady=8, sticky="w")

        # Half / Double, etc.
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
        self.tree.column("note", width=220, anchor="w")
        self.tree.column("beats", width=80, anchor="center")
        self.tree.column("millis", width=140, anchor="e")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        # Footer hint
        hint = ttk.Label(main, text="Tip: Drag the slider or type a BPM to see values update live. Values are rounded to 2 decimals.", foreground="#666")
        hint.pack(anchor="w", padx=4, pady=(0, 4))

    def _wire_events(self):
        self.bpm_entry.bind("<KeyRelease>", lambda e: self.update_calculations())
        self.bind("<Return>", lambda e: self.update_calculations())

    def _on_scale(self, _):
        # Keep entry in sync with slider
        self.bpm_var.set(round(self.scale.get(), 2))
        self.update_calculations()

    def _validate_bpm_entry(self, proposed: str):
        # Allow empty while typing
        if proposed == "":
            return True
        # Allow numeric (float)
        try:
            float(proposed)
            return True
        except ValueError:
            return False

    def set_bpm(self, value: float):
        self.bpm_var.set(float(value))
        self.scale.set(float(value))
        self.update_calculations()

    def update_calculations(self):
        bpm = clamp_bpm(self.bpm_var.get())
        # Clamp state
        if bpm != self.bpm_var.get():
            self.bpm_var.set(bpm)
            self.scale.set(bpm)

        # Core conversions
        ms_per_beat = (60000.0 / bpm) if bpm > 0 else float("inf")
        hz = (bpm / 60.0)

        # Update summary labels
        if ms_per_beat == float("inf"):
            self.ms_per_beat_var.set("—")
        else:
            self.ms_per_beat_var.set(f"{ms_per_beat:.2f} ms")
        self.hz_var.set(f"{hz:.3f} Hz" if isfinite(hz) else "—")

        self.half_bpm_var.set(f"{bpm/2:.2f}")
        self.double_bpm_var.set(f"{bpm*2:.2f}")
        self.third_bpm_var.set(f"{bpm/3:.2f}")
        self.quad_bpm_var.set(f"{bpm*4:.2f}")

        # Rebuild table
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
        ]

        for name, beats in notes:
            if bpm <= 0:
                ms = "—"
            else:
                ms = 60000.0 * beats / bpm
                ms = f"{ms:.2f}"
            self.tree.insert("", "end", values=(name, f"{beats:g}", ms))

if __name__ == "__main__":
    try:
        # Use ttk theme if available
        root = BpmCalculator()
        # Apply padding to all ttk widgets for a cleaner look
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
