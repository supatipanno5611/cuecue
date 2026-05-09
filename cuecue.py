#!/usr/bin/env python3

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import gc
import json
import math
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AUDIO_LIBRARY_DIR = Path(r"여기에 음성 파일들이 들어 있는 폴더 경로를 넣어주세요")
OUTPUT_DIR = Path(r"여기에 전사된 파일들이 출력될 폴더 경로를 넣어주세요")
TEMP_CHUNKS_DIR = Path(__file__).resolve().parent / "temp_chunks"
AUDIO_EXTENSIONS = (".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".wma")
DEFAULT_CHUNK_MINUTES = 15
MODEL_SIZE = "small"
LANGUAGE = "en"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
CUE_MARKER = "▶"
MANIFEST_VERSION = 1

_MODEL = None
_MODEL_WORKERS = 0
_MODEL_LOCK = threading.Lock()


@dataclass(frozen=True)
class Chunk:
    index: int
    path: Path
    start: float
    duration: float


@dataclass(frozen=True)
class ProcessingOptions:
    workers: int
    chunk_limit: int | None


def audio_files() -> list[Path]:
    if not AUDIO_LIBRARY_DIR.is_dir():
        raise SystemExit(f"Audio folder not found: {AUDIO_LIBRARY_DIR}")
    return sorted(
        path for path in AUDIO_LIBRARY_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )


def parse_selection(raw: str, count: int) -> list[int]:
    selected: set[int] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_raw, end_raw = token.split("-", 1)
            start = int(start_raw)
            end = int(end_raw)
            if start > end:
                start, end = end, start
            selected.update(range(start, end + 1))
        else:
            selected.add(int(token))

    invalid = [n for n in selected if n < 1 or n > count]
    if invalid:
        raise ValueError(f"Selection out of range: {', '.join(map(str, sorted(invalid)))}")
    return sorted(selected)


def parse_chunk_numbers(raw: str, allowed: set[int]) -> set[int]:
    selected: set[int] = set()
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_raw, end_raw = token.split("-", 1)
            start = int(start_raw)
            end = int(end_raw)
            if start > end:
                start, end = end, start
            selected.update(range(start, end + 1))
        else:
            selected.add(int(token))

    invalid = sorted(selected - allowed)
    if invalid:
        raise ValueError(f"Invalid chunk number: {', '.join(map(str, invalid))}")
    return selected


def choose_audio_files() -> list[Path]:
    files = audio_files()
    if not files:
        raise SystemExit(f"No audio files found in {AUDIO_LIBRARY_DIR}")

    print(f"Audio folder: {AUDIO_LIBRARY_DIR}")
    for i, path in enumerate(files, start=1):
        print(f"[{i}] {path.name}")

    while True:
        try:
            raw = input("Select files (1,3, 1-4, all, q): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("Cancelled.")
        if raw in {"q", "quit", "exit"}:
            raise SystemExit("Cancelled.")
        if not raw:
            print("Please enter a selection, all, or q.")
            continue
        if raw == "all":
            return files
        try:
            indexes = parse_selection(raw, len(files))
        except ValueError as exc:
            print(exc)
            continue
        if indexes:
            return [files[i - 1] for i in indexes]


def ask_yes_no(prompt: str) -> bool:
    while True:
        try:
            raw = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("Cancelled.")
        if raw == "y":
            return True
        if raw == "n":
            return False
        print("Please enter y or n.")


def ask_processing_options(pending_count: int) -> ProcessingOptions:
    use_two_workers = ask_yes_no("Use two workers for faster processing? This may increase heat and fan noise. (y/n): ")
    workers = 2 if use_two_workers else 1
    while True:
        try:
            raw = input("Limit chunks per worker for this run? Type a number, or all to process all remaining chunks: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("Cancelled.")
        if raw == "all":
            return ProcessingOptions(workers=workers, chunk_limit=None)
        try:
            chunks_per_worker = int(raw)
        except ValueError:
            print("Please enter a positive number or all.")
            continue
        if chunks_per_worker <= 0:
            print("Please enter a positive number or all.")
            continue
        return ProcessingOptions(workers=workers, chunk_limit=min(pending_count, workers * chunks_per_worker))


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def require_tool(name: str) -> None:
    try:
        run([name, "-version"])
    except FileNotFoundError:
        raise SystemExit(f"Missing required tool: {name}. Install ffmpeg and ensure it is on PATH.")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Could not run {name}: {exc.stderr.strip()}")


def audio_duration(path: Path) -> float:
    try:
        result = run([
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ])
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"ffprobe failed for {path}: {exc.stderr.strip()}")

    try:
        return float(result.stdout.strip())
    except ValueError:
        raise SystemExit(f"Could not read audio duration for {path}")


def split_audio(input_path: Path, work_dir: Path, duration: float, chunk_seconds: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    count = math.ceil(duration / chunk_seconds)
    suffix = input_path.suffix or ".wav"
    work_dir.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        start = i * chunk_seconds
        length = min(chunk_seconds, duration - start)
        chunk_path = work_dir / f"chunk_{i + 1:03d}{suffix}"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(start),
            "-t", str(length),
            "-i", str(input_path),
            "-vn",
            "-acodec", "copy",
            str(chunk_path),
        ]
        try:
            run(cmd)
        except subprocess.CalledProcessError:
            chunk_path = work_dir / f"chunk_{i + 1:03d}.wav"
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(start),
                "-t", str(length),
                "-i", str(input_path),
                "-vn",
                "-ac", "1",
                "-ar", "16000",
                str(chunk_path),
            ]
            try:
                run(cmd)
            except subprocess.CalledProcessError as exc:
                raise SystemExit(f"ffmpeg failed while creating chunk {i + 1}: {exc.stderr.strip()}")
        chunks.append(Chunk(i + 1, chunk_path, start, length))

    return chunks


def format_time(seconds: float) -> str:
    whole = int(seconds)
    h = whole // 3600
    m = (whole % 3600) // 60
    s = whole % 60

    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_elapsed(seconds: float) -> str:
    whole = int(seconds)
    h = whole // 3600
    m = (whole % 3600) // 60
    s = whole % 60
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def format_clock(value: dt.datetime) -> str:
    return value.strftime("%H:%M:%S")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug[:60] or "audio"


def unique_job_dir(input_path: Path) -> Path:
    TEMP_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = TEMP_CHUNKS_DIR / f"{stamp}-{safe_slug(input_path.stem)}"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = TEMP_CHUNKS_DIR / f"{base.name}-{suffix}"
        suffix += 1
    return candidate


def unique_output_path(output_dir: Path, stem: str) -> Path:
    candidate = output_dir / f"{stem}.md"
    suffix = 1
    while candidate.exists():
        candidate = output_dir / f"{stem} ({suffix}).md"
        suffix += 1
    return candidate


def manifest_path(job_dir: Path) -> Path:
    return job_dir / "manifest.json"


def write_manifest(job_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    path = manifest_path(job_dir)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def load_manifest(job_dir: Path) -> dict[str, Any]:
    return json.loads(manifest_path(job_dir).read_text(encoding="utf-8"))


def chunk_from_item(item: dict[str, Any]) -> Chunk:
    return Chunk(
        index=int(item["index"]),
        path=Path(str(item["audio_path"])),
        start=float(item["start"]),
        duration=float(item["duration"]),
    )


def completed_count(manifest: dict[str, Any]) -> int:
    return sum(1 for item in manifest["chunks"] if item.get("status") == "done")


def pending_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in manifest["chunks"] if item.get("status") != "done"]


def all_chunks_done(manifest: dict[str, Any]) -> bool:
    return completed_count(manifest) == len(manifest["chunks"])


def create_job(input_path: Path, args: argparse.Namespace) -> Path:
    output_dir = (args.output_dir or OUTPUT_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    chunk_seconds = int(args.chunk_minutes * 60)
    if chunk_seconds <= 0:
        raise SystemExit("--chunk-minutes must be greater than 0")

    duration = audio_duration(input_path)
    job_dir = unique_job_dir(input_path)
    chunks_dir = job_dir / "chunks"
    partial_dir = job_dir / "partial"
    partial_dir.mkdir(parents=True, exist_ok=True)

    if duration >= chunk_seconds:
        chunks = split_audio(input_path, chunks_dir, duration, chunk_seconds)
    else:
        chunks = [Chunk(1, input_path, 0, duration)]

    now = dt.datetime.now().isoformat(timespec="seconds")
    manifest: dict[str, Any] = {
        "version": MANIFEST_VERSION,
        "status": "active",
        "source_path": str(input_path),
        "source_name": input_path.name,
        "source_stem": input_path.stem,
        "output_dir": str(output_dir),
        "created_at": now,
        "updated_at": now,
        "chunk_minutes": args.chunk_minutes,
        "duration": duration,
        "model": MODEL_SIZE,
        "language": LANGUAGE,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
        "merged_output": None,
        "chunks": [
            {
                "index": chunk.index,
                "audio_path": str(chunk.path),
                "partial_path": str(partial_dir / f"chunk_{chunk.index:03d}.md"),
                "start": chunk.start,
                "duration": chunk.duration,
                "status": "pending",
            }
            for chunk in chunks
        ],
    }
    write_manifest(job_dir, manifest)
    return job_dir


def get_model(workers: int = 1):
    global _MODEL, _MODEL_WORKERS
    workers = max(1, min(2, workers))
    if _MODEL is None or _MODEL_WORKERS != workers:
        with _MODEL_LOCK:
            if _MODEL is None or _MODEL_WORKERS != workers:
                _MODEL = None
                gc.collect()
                from faster_whisper import WhisperModel
                _MODEL_WORKERS = workers
                _MODEL = WhisperModel(
                    MODEL_SIZE,
                    device=DEVICE,
                    compute_type=COMPUTE_TYPE,
                    cpu_threads=1,
                    num_workers=_MODEL_WORKERS,
                )
    return _MODEL


def transcribe_chunk(chunk: Chunk, output_path: Path, workers: int) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    segments, _info = get_model(workers).transcribe(str(chunk.path), language=LANGUAGE)

    lines: list[str] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        lines.append(f"{CUE_MARKER} {format_time(chunk.start + segment.start)} {text}")
        lines.append("")

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def transcribe_item(item: dict[str, Any], workers: int) -> tuple[Path, dt.datetime, dt.datetime, float]:
    started_at = dt.datetime.now()
    started_perf = time.perf_counter()
    path = transcribe_chunk(chunk_from_item(item), Path(str(item["partial_path"])), workers)
    finished_at = dt.datetime.now()
    return path, started_at, finished_at, time.perf_counter() - started_perf


def mark_chunk_done(job_dir: Path, manifest: dict[str, Any], item: dict[str, Any]) -> None:
    item["status"] = "done"
    item["completed_at"] = dt.datetime.now().isoformat(timespec="seconds")
    write_manifest(job_dir, manifest)


def print_chunk_progress(
    manifest: dict[str, Any],
    item: dict[str, Any],
    started_at: dt.datetime,
    finished_at: dt.datetime,
    chunk_elapsed: float,
    file_started_perf: float,
) -> None:
    done = completed_count(manifest)
    total = len(manifest["chunks"])
    file_elapsed = time.perf_counter() - file_started_perf
    print()
    print(f"Chunk {item['index']} completed ({done}/{total} done)")
    print(f"Started: {format_clock(started_at)}")
    print(f"Completed: {format_clock(finished_at)}")
    print(f"Chunk elapsed: {format_elapsed(chunk_elapsed)}")
    print(f"File elapsed: {format_elapsed(file_elapsed)}")


def handle_ambiguous_partials(job_dir: Path, manifest: dict[str, Any]) -> None:
    ambiguous = [
        item for item in manifest["chunks"]
        if item.get("status") != "done" and Path(str(item["partial_path"])).is_file()
    ]
    if not ambiguous:
        return

    allowed = {int(item["index"]) for item in ambiguous}
    print()
    print("Some partial results exist but are not marked complete.")
    print("These files may be incomplete if the previous run stopped while writing.")
    print()
    for item in ambiguous:
        path = Path(str(item["partial_path"]))
        stat = path.stat()
        modified = dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        size_kb = max(1, math.ceil(stat.st_size / 1024))
        print(f"[{item['index']}] {path.name}  {size_kb} KB  modified {modified}")

    while True:
        try:
            raw = input("Select chunks to keep as completed. Use numbers like 3,5 or 3-5; none = reprocess all; all = keep all: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("Cancelled.")
        if raw == "none":
            return
        if raw == "all":
            keep = allowed
            break
        try:
            keep = parse_chunk_numbers(raw, allowed)
        except ValueError as exc:
            print(exc)
            continue
        if keep:
            break
        print("Please enter chunk numbers, none, or all.")

    for item in ambiguous:
        if int(item["index"]) in keep:
            item["status"] = "done"
            item["completed_at"] = dt.datetime.now().isoformat(timespec="seconds")
    write_manifest(job_dir, manifest)


def process_job(job_dir: Path) -> None:
    manifest = load_manifest(job_dir)
    handle_ambiguous_partials(job_dir, manifest)
    manifest = load_manifest(job_dir)
    pending = pending_items(manifest)

    print()
    print(f"Input: {manifest['source_path']}")
    print(f"Duration: {format_time(float(manifest['duration']))}")
    print(f"Chunks: {len(manifest['chunks'])}")
    print(f"Completed: {completed_count(manifest)}/{len(manifest['chunks'])}")
    print(f"Model: {MODEL_SIZE}, language: {LANGUAGE}, device: {DEVICE}, compute_type: {COMPUTE_TYPE}")

    file_started_perf = time.perf_counter()
    if pending:
        options = ask_processing_options(len(pending))
        run_items = pending if options.chunk_limit is None else pending[:options.chunk_limit]
        workers = min(options.workers, len(run_items))
        print(f"Workers: {workers}")
        print(f"Chunks this run: {len(run_items)}")

        if workers <= 1:
            for item in run_items:
                try:
                    _path, started_at, finished_at, elapsed = transcribe_item(item, workers)
                    mark_chunk_done(job_dir, manifest, item)
                    print_chunk_progress(manifest, item, started_at, finished_at, elapsed, file_started_perf)
                except Exception as exc:
                    print(f"Transcription failed for chunk {item['index']}: {exc}", file=sys.stderr)
        else:
            failed: list[dict[str, Any]] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                future_map = {executor.submit(transcribe_item, item, workers): item for item in run_items}
                for future in concurrent.futures.as_completed(future_map):
                    item = future_map[future]
                    try:
                        _path, started_at, finished_at, elapsed = future.result()
                    except Exception as exc:
                        print(f"Parallel transcription failed for chunk {item['index']}; retrying serially: {exc}", file=sys.stderr)
                        failed.append(item)
                        continue
                    mark_chunk_done(job_dir, manifest, item)
                    print_chunk_progress(manifest, item, started_at, finished_at, elapsed, file_started_perf)

            for item in failed:
                try:
                    _path, started_at, finished_at, elapsed = transcribe_item(item, 1)
                    mark_chunk_done(job_dir, manifest, item)
                    print_chunk_progress(manifest, item, started_at, finished_at, elapsed, file_started_perf)
                except Exception as exc:
                    print(f"Serial retry failed for chunk {item['index']}: {exc}", file=sys.stderr)

        manifest = load_manifest(job_dir)

    if all_chunks_done(manifest):
        maybe_merge_job(job_dir, manifest)
    else:
        print()
        print(f"Job remains incomplete: {completed_count(manifest)}/{len(manifest['chunks'])} chunks done.")
        print(f"Temp job: {job_dir}")


def maybe_merge_job(job_dir: Path, manifest: dict[str, Any]) -> None:
    print()
    print("All chunks are complete.")
    if not ask_yes_no("Merge them into one Markdown file now? (y/n): "):
        print(f"Merge skipped. Temp job remains: {job_dir}")
        return

    output_dir = Path(str(manifest["output_dir"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    merged_path = unique_output_path(output_dir, str(manifest["source_stem"]))
    parts: list[str] = []
    for item in sorted(manifest["chunks"], key=lambda value: int(value["index"])):
        partial_path = Path(str(item["partial_path"]))
        parts.append(partial_path.read_text(encoding="utf-8").strip())
    merged_path.write_text("\n\n".join(part for part in parts if part).rstrip() + "\n", encoding="utf-8")

    manifest["status"] = "merged"
    manifest["merged_output"] = str(merged_path)
    manifest["merged_at"] = dt.datetime.now().isoformat(timespec="seconds")
    write_manifest(job_dir, manifest)

    print(f"Merged output: {merged_path}")
    if ask_yes_no("Keep temporary chunks and partial results? (y/n): "):
        print(f"Temp job kept: {job_dir}")
    else:
        shutil.rmtree(job_dir)
        print("Temporary chunks and partial results removed.")


def load_resumable_jobs() -> list[tuple[Path, dict[str, Any]]]:
    if not TEMP_CHUNKS_DIR.is_dir():
        return []

    jobs: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(TEMP_CHUNKS_DIR.iterdir()):
        if not path.is_dir() or not manifest_path(path).is_file():
            continue
        try:
            manifest = load_manifest(path)
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("status") == "merged":
            continue
        jobs.append((path, manifest))
    return jobs


def choose_resume_job() -> Path | None:
    jobs = load_resumable_jobs()
    if not jobs:
        return None

    print("Unfinished jobs:")
    for i, (_job_dir, manifest) in enumerate(jobs, start=1):
        done = completed_count(manifest)
        total = len(manifest["chunks"])
        suffix = "not merged" if done == total else "incomplete"
        print(f"[{i}] {manifest['source_name']} ({done}/{total} done, {suffix}, created {manifest['created_at']})")
    print("[n] New transcription")
    print("[q] Quit")

    while True:
        try:
            raw = input("Select: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("Cancelled.")
        if raw in {"q", "quit", "exit"}:
            raise SystemExit("Cancelled.")
        if raw == "n":
            return None
        try:
            index = int(raw)
        except ValueError:
            print("Please enter a job number, n, or q.")
            continue
        if 1 <= index <= len(jobs):
            return jobs[index - 1][0]
        print("Selection out of range.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe audio into Sakko cue Markdown with faster-whisper.")
    parser.add_argument("-o", "--output-dir", type=Path, default=None, help="Directory for final Markdown output")
    parser.add_argument("--chunk-minutes", type=float, default=DEFAULT_CHUNK_MINUTES, help="Split threshold and chunk size in minutes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    require_tool("ffprobe")
    require_tool("ffmpeg")

    resume_job = choose_resume_job()
    if resume_job is not None:
        process_job(resume_job)
        return 0

    selected_files = choose_audio_files()
    for i, input_path in enumerate(selected_files, start=1):
        print(f"\nFile {i}/{len(selected_files)}")
        job_dir = create_job(input_path, args)
        process_job(job_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
