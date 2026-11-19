import json
import os
import re
import time
import unicodedata
from pathlib import Path

import httpx
import jiwer

from app.config import settings
from app.transcribe import get_model, transcribe_whisper

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"
REFS = Path(__file__).with_name("references.json")
OUT = ROOT / "docs" / "benchmark.md"

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
SCRIBE_MODEL = os.getenv("SCRIBE_MODEL", "scribe_v1")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def wer(ref: str, hyp: str) -> float:
    return round(jiwer.wer(normalize(ref), normalize(hyp)), 3)


def run_scribe(path: Path, key: str) -> str:
    with open(path, "rb") as f:
        res = httpx.post(
            SCRIBE_URL,
            headers={"xi-api-key": key},
            data={"model_id": SCRIBE_MODEL},
            files={"file": (path.name, f)},
            timeout=120,
        )
    res.raise_for_status()
    return res.json()["text"]


def main() -> None:
    refs = json.loads(REFS.read_text(encoding="utf-8"))
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("ELEVENLABS_API_KEY missing in backend/.env, Scribe will be skipped.")

    print(f"Loading Whisper model: {settings.model_name}")
    get_model()  # load once so timings measure transcription only

    rows = []
    for name, ref in refs.items():
        path = SAMPLES / name
        if not path.exists():
            print(f"Missing sample: {path}")
            continue

        t0 = time.perf_counter()
        w_text = transcribe_whisper(str(path), ref["language"])["text"]
        w_time = round(time.perf_counter() - t0, 2)

        s_text, s_time = "", None
        if key:
            t0 = time.perf_counter()
            s_text = run_scribe(path, key)
            s_time = round(time.perf_counter() - t0, 2)

        rows.append({
            "clip": name,
            "language": ref["language"],
            "reference": ref["text"],
            "whisper": w_text,
            "whisper_wer": wer(ref["text"], w_text),
            "whisper_time": w_time,
            "scribe": s_text,
            "scribe_wer": wer(ref["text"], s_text) if key else None,
            "scribe_time": s_time,
        })
        print(f"Done: {name}")

    lines = [
        "# Speech to text benchmark",
        "",
        f"Whisper: `{settings.model_name}` ({settings.device}, {settings.compute_type}). "
        f"Scribe: `{SCRIBE_MODEL}`.",
        "",
        "WER = word error rate after lowercasing and removing punctuation. Lower is better.",
        "",
        "| Clip | Language | Whisper WER | Scribe WER | Whisper time (s) | Scribe time (s) |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['clip']} | {r['language']} | {r['whisper_wer']} | "
            f"{r['scribe_wer'] if r['scribe_wer'] is not None else 'n/a'} | "
            f"{r['whisper_time']} | {r['scribe_time'] if r['scribe_time'] is not None else 'n/a'} |"
        )

    lines += ["", "## Transcripts", ""]
    for r in rows:
        lines += [
            f"### {r['clip']}",
            "",
            f"- Reference: {r['reference']}",
            f"- Whisper: {r['whisper']}",
            f"- Scribe: {r['scribe'] or 'n/a'}",
            "",
        ]
    lines += [
        "Note: numbers written as digits (1,500) vs words (one thousand five hundred) "
        "count as errors here. Amounts are normalised later, in the extraction step.",
        "",
    ]

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print()
    print("\n".join(lines[6:6 + 2 + len(rows)]))
    print(f"\nSaved: {OUT}")


if __name__ == "__main__":
    main()
