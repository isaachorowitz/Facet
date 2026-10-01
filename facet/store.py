"""Local SQLite history: numbers and transcripts only, never images or audio."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections import Counter
from datetime import datetime, timedelta

import numpy as np

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS face_windows (ts REAL NOT NULL, neutral INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS verdicts (ts REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS speech (ts REAL NOT NULL, text TEXT NOT NULL, prosody TEXT NOT NULL, emotion TEXT NOT NULL, verdict TEXT);
CREATE TABLE IF NOT EXISTS events (ts REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS face_ts ON face_windows(ts);
CREATE INDEX IF NOT EXISTS verdict_ts ON verdicts(kind, ts);
CREATE INDEX IF NOT EXISTS speech_ts ON speech(ts);
"""

BASELINE_KEYS = ("neck", "shoulder_y", "shoulder_width", "shoulder_tilt", "smile", "brow_furrow", "eye_squint", "lip_press", "jaw_forward", "tension", "frown", "eye_openness", "blink_rate", "movement", "face_size", "pitch")


def day_bounds(date: str | None) -> tuple[float, float]:
    day = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


class Store:
    def __init__(self) -> None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.baseline: dict[str, dict[str, float]] = {}
        self.posture_ref: dict[str, float] | None = None
        self.posture_learned: dict[str, float] | None = None
        self.refresh_baseline()

    def _exec(self, sql: str, args: tuple = ()) -> None:
        with self.lock:
            self.db.execute(sql, args)
            self.db.commit()

    def _query(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    # -- writes -----------------------------------------------------------
    def add_face_window(self, data: dict, neutral: bool = False) -> None:
        self._exec("INSERT INTO face_windows VALUES (?,?,?)", (time.time(), int(neutral), json.dumps(data)))

    def add_verdict(self, kind: str, data: dict) -> None:
        self._exec("INSERT INTO verdicts VALUES (?,?,?)", (time.time(), kind, json.dumps(data)))

    def add_speech(self, seg: dict, verdict: dict | None, store_text: bool) -> None:
        self._exec(
            "INSERT INTO speech VALUES (?,?,?,?,?)",
            (seg["ts"], seg["text"] if store_text else "", json.dumps(seg["prosody"]), json.dumps(seg["emotion"]), json.dumps(verdict)),
        )

    def add_event(self, kind: str, data: dict) -> None:
        self._exec("INSERT INTO events VALUES (?,?,?)", (time.time(), kind, json.dumps(data)))

    def get_setting(self, key: str, default):
        rows = self._query("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(rows[0][0]) if rows else default

    def set_setting(self, key: str, value) -> None:
        self._exec("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    # -- baseline ---------------------------------------------------------
    def refresh_baseline(self) -> None:
        """Your normal face: the last 14 days of windows where you were present.

        Neutral calibration windows, when they exist, set the center; the spread
        comes from all windows so day-to-day variation is respected.
        """
        since = time.time() - 14 * 86400
        rows = self._query("SELECT neutral, data FROM face_windows WHERE ts > ?", (since,))
        all_rows = [json.loads(d) for n, d in rows]
        all_rows = [r for r in all_rows if r.get("present", 0) > 0.5 and "smile" in r]
        neutral_rows = [json.loads(d) for n, d in rows if n]
        neutral_rows = [r for r in neutral_rows if "smile" in r]
        with_neck = [r for r in all_rows if "neck" in r and "shoulder_y" in r]
        if len(with_neck) >= 60:
            cut = float(np.percentile([r["neck"] for r in with_neck], 70))
            best = [r for r in with_neck if r["neck"] >= cut]
            self.posture_learned = {k: float(np.median([r[k] for r in best])) for k in ("neck", "shoulder_y", "shoulder_width")}
        upright = [r for r in neutral_rows if "neck" in r]
        self.posture_ref = (
            {k: float(np.median([r[k] for r in upright])) for k in ("neck", "shoulder_y", "shoulder_width")}
            if len(upright) >= 3 else None
        )
        if len(all_rows) < 60 and len(neutral_rows) < 3:
            self.baseline = {}
            return
        base: dict[str, dict[str, float]] = {}
        for k in BASELINE_KEYS:
            vals = np.array([r[k] for r in all_rows if k in r]) if all_rows else np.array([])
            center_vals = np.array([r[k] for r in neutral_rows if k in r]) if neutral_rows else vals
            if len(center_vals) == 0:
                continue
            spread = float(vals.std()) if len(vals) > 20 else float(center_vals.std())
            base[k] = {"mean": float(np.median(center_vals)), "std": max(spread, 0.02 if k not in ("blink_rate", "pitch") else 1.0)}
        base["_samples"] = {"mean": float(len(all_rows)), "std": float(len(neutral_rows))}
        self.baseline = base

    def zscores(self, metrics: dict[str, float]) -> dict[str, float]:
        out = {}
        for k, b in self.baseline.items():
            if k.startswith("_") or k not in metrics:
                continue
            out[k] = round((metrics[k] - b["mean"]) / b["std"], 2)
        return out

    # -- reads ------------------------------------------------------------
    def recent_verdicts(self, kind: str, seconds: float) -> list[tuple[float, dict]]:
        rows = self._query("SELECT ts, data FROM verdicts WHERE kind=? AND ts>? ORDER BY ts", (kind, time.time() - seconds))
        return [(ts, json.loads(d)) for ts, d in rows]

    def recent_speech(self, seconds: float) -> list[dict]:
        rows = self._query("SELECT ts, text, prosody, emotion, verdict FROM speech WHERE ts>? ORDER BY ts", (time.time() - seconds,))
        return [{"ts": r[0], "text": r[1], "prosody": json.loads(r[2]), "emotion": json.loads(r[3]), "verdict": json.loads(r[4] or "null")} for r in rows]

    def timeline(self, date: str | None, bucket_minutes: int = 5) -> dict:
        start, end = day_bounds(date)
        size = bucket_minutes * 60
        buckets: dict[int, dict[str, list]] = {}

        def put(ts: float, key: str, value) -> None:
            b = buckets.setdefault(int((ts - start) // size), {})
            b.setdefault(key, []).append(value)

        for ts, d in self._query("SELECT ts, data FROM verdicts WHERE kind='face' AND ts BETWEEN ? AND ?", (start, end)):
            v = json.loads(d)
            for k in ("stress", "fatigue", "focus", "energy", "positivity", "tension"):
                put(ts, k, v[k])
            put(ts, "expression", v["expression"]["choice"])
        for ts, d in self._query("SELECT ts, data FROM face_windows WHERE ts BETWEEN ? AND ? AND neutral=0", (start, end)):
            v = json.loads(d)
            put(ts, "present", v.get("present", 0))
            if "posture_score" in v:
                put(ts, "posture", v["posture_score"] / 25.0)
            if "tension" in v:
                put(ts, "measured_tension", v["tension"])
                put(ts, "smile", v["smile"])
                put(ts, "blink_rate", v.get("blink_rate", 0))
        for ts, d in self._query("SELECT ts, prosody FROM speech WHERE ts BETWEEN ? AND ?", (start, end)):
            put(ts, "speech_s", json.loads(d)["duration_s"])
        points = []
        for i in sorted(buckets):
            b = buckets[i]
            p: dict = {"t": start + i * size}
            for k, vals in b.items():
                if k == "expression":
                    p[k] = Counter(vals).most_common(1)[0][0]
                elif k == "speech_s":
                    p[k] = round(sum(vals), 1)
                else:
                    p[k] = round(float(np.mean(vals)), 3)
            points.append(p)
        return {"start": start, "bucket_minutes": bucket_minutes, "points": points}

    def summary(self, date: str | None) -> dict:
        start, end = day_bounds(date)
        face = [(ts, json.loads(d)) for ts, d in self._query("SELECT ts, data FROM verdicts WHERE kind='face' AND ts BETWEEN ? AND ? ORDER BY ts", (start, end))]
        windows = [(ts, json.loads(d)) for ts, d in self._query("SELECT ts, data FROM face_windows WHERE ts BETWEEN ? AND ? AND neutral=0 ORDER BY ts", (start, end))]
        speech = self._query("SELECT ts, prosody, verdict FROM speech WHERE ts BETWEEN ? AND ?", (start, end))
        events = self._query("SELECT ts, kind, data FROM events WHERE ts BETWEEN ? AND ? ORDER BY ts", (start, end))
        present_ts = [ts for ts, w in windows if w.get("present", 0) > 0.5]
        out: dict = {
            "date": datetime.fromtimestamp(start).strftime("%Y-%m-%d"),
            "minutes_present": round(len(present_ts) * config.FACE_WINDOW_SECONDS / 60, 1),
            "first_seen": present_ts[0] if present_ts else None,
            "last_seen": present_ts[-1] if present_ts else None,
            "verdicts": len(face),
            "minutes_talking": round(sum(json.loads(p)["duration_s"] for _, p, _ in speech) / 60, 1),
            "notifications": [{"ts": ts, **json.loads(d)} for ts, k, d in events if k == "notification"],
        }
        scores = [w["posture_score"] for _, w in windows if "posture_score" in w]
        if scores:
            out["avg_posture"] = round(float(np.mean(scores)), 1)
            out["minutes_poor_posture"] = round(sum(1 for x in scores if x < 55) * config.FACE_WINDOW_SECONDS / 60, 1)
            out["minutes_good_posture"] = round(sum(1 for x in scores if x >= 75) * config.FACE_WINDOW_SECONDS / 60, 1)
        if not face:
            return out
        exp = Counter(v["expression"]["choice"] for _, v in face)
        out["expressions"] = {k: round(c / len(face), 3) for k, c in exp.most_common()}
        for k in ("stress", "fatigue", "focus", "energy", "positivity", "tension"):
            vals = [v[k] for _, v in face]
            out[f"avg_{k}"] = round(float(np.mean(vals)), 2)
        out["smiling_share"] = round(float(np.mean([v["smiling"] > 0.5 for _, v in face])), 3)
        out["posture"] = dict(Counter(v["posture"]["choice"] for _, v in face).most_common())
        out["activity"] = dict(Counter(v["activity"]["choice"] for _, v in face).most_common())

        # Stress peaks: highest one-minute averages, at least ten minutes apart.
        minutes: dict[int, list[float]] = {}
        for ts, v in face:
            minutes.setdefault(int(ts // 60), []).append(v["stress"])
        ranked = sorted(((float(np.mean(s)), m * 60) for m, s in minutes.items() if len(s) >= 3), reverse=True)
        peaks: list[dict] = []
        for score, ts in ranked:
            if score < 1.5:
                break
            if all(abs(ts - p["ts"]) > 600 for p in peaks):
                peaks.append({"ts": ts, "stress": round(score, 2)})
            if len(peaks) == 5:
                break
        out["stress_peaks"] = peaks

        # Focus streaks: runs where focus stays at or above 2.5 with gaps under 30 s.
        streaks, run_start, last = [], None, None
        for ts, v in face:
            if v["focus"] >= 2.5 and (last is None or ts - last < 30):
                run_start = run_start or ts
            elif v["focus"] >= 2.5:
                run_start = ts
            else:
                if run_start and last and last - run_start > 300:
                    streaks.append((run_start, last))
                run_start = None
            last = ts
        if run_start and last and last - run_start > 300:
            streaks.append((run_start, last))
        streaks.sort(key=lambda s: s[1] - s[0], reverse=True)
        out["focus_streaks"] = [{"start": s, "minutes": round((e - s) / 60, 1)} for s, e in streaks[:5]]

        # Breaks: gaps in presence longer than BREAK_GAP_SECONDS.
        breaks = []
        for a, b in zip(present_ts, present_ts[1:]):
            if b - a > config.BREAK_GAP_SECONDS:
                breaks.append({"start": a, "minutes": round((b - a) / 60, 1)})
        out["breaks"] = breaks

        hours: dict[int, list[dict]] = {}
        for ts, v in face:
            hours.setdefault(datetime.fromtimestamp(ts).hour, []).append(v)
        out["by_hour"] = [
            {
                "hour": h,
                "stress": round(float(np.mean([v["stress"] for v in vs])), 2),
                "focus": round(float(np.mean([v["focus"] for v in vs])), 2),
                "fatigue": round(float(np.mean([v["fatigue"] for v in vs])), 2),
                "positivity": round(float(np.mean([v["positivity"] for v in vs])), 2),
                "top_expression": Counter(v["expression"]["choice"] for v in vs).most_common(1)[0][0],
            }
            for h, vs in sorted(hours.items())
        ]
        tones = [json.loads(v)["tone"]["choice"] for _, _, v in speech if v and json.loads(v)]
        if tones:
            out["voice_tones"] = dict(Counter(tones).most_common())
        return out
