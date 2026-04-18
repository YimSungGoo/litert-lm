from __future__ import annotations

import sys
import os
import time
import threading
import tempfile
import logging
from pathlib import Path
from typing import Callable

import time as _time

import cv2

import config
import db as db_module

logger = logging.getLogger(__name__)

# LiteRT-LM은 uv tool 환경에서 로드
_LITERT_SITE = "/home/yimstar9/.local/share/uv/tools/litert-lm/lib/python3.12/site-packages"
if _LITERT_SITE not in sys.path:
    sys.path.insert(0, _LITERT_SITE)

import litert_lm


VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".ts", ".m4v"}
_engine: litert_lm.Engine | None = None
_embedder = None
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None

status = {
    "running": False,
    "processed": 0,
    "total": 0,
    "current_file": "",
    "current_file_idx": 0,
    "current_frame": 0,          # 처리한 프레임 수
    "current_pos_sec": 0.0,      # 현재 처리 중인 영상 위치 (초)
    "current_duration_sec": 0.0, # 현재 영상 전체 길이 (초)
    "current_caption": "",
    "started_at": 0.0,
    "frame_times": [],            # 최근 프레임 소요 시간 (이동 평균용)
    "errors": [],
}


def _load_engine(cfg: config.Config):
    global _engine
    backend = litert_lm.Backend.GPU if cfg.backend == "gpu" else litert_lm.Backend.CPU
    _engine = litert_lm.Engine(
        cfg.model_path,
        backend=backend,
        vision_backend=litert_lm.Backend.CPU,
    )
    _engine.__enter__()
    logger.info("LiteRT-LM Engine 로드 완료")


def _load_embedder(cfg: config.Config):
    global _embedder
    if _embedder is not None:
        return
    from sentence_transformers import SentenceTransformer
    model_name_or_path = cfg.embedding_model_path
    cache_dir = None
    # 경로가 존재하는 디렉토리면 로컬 캐시로 사용, 아니면 모델명으로 다운로드
    if Path(model_name_or_path).exists():
        cache_dir = str(Path(model_name_or_path).parent)
    _embedder = SentenceTransformer(model_name_or_path, cache_folder=cache_dir)
    logger.info("임베딩 모델 로드 완료")



def _caption_frame(frame_path: str, cfg: config.Config) -> str:
    with _engine.create_conversation() as conv:
        response = conv.send_message({
            "role": "user",
            "content": [
                {"type": "image", "path": frame_path},
                {"type": "text", "text": cfg.caption_prompt},
            ],
        })
    texts = [p["text"] for p in response.get("content", []) if p.get("type") == "text"]
    return " ".join(texts).strip()


def _process_video(video_path: str, cfg: config.Config) -> int:
    global status
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_step = max(1, int(fps * cfg.frame_interval))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps
    filename = Path(video_path).name

    status["current_frame"] = 0
    status["current_pos_sec"] = 0.0
    status["current_duration_sec"] = duration_sec
    status["current_caption"] = ""

    logger.info(
        f"[{filename}] 시작 — 길이: {_fmt_timestamp(duration_sec)}, "
        f"FPS: {fps:.1f}, 추출 간격: {cfg.frame_interval}초"
    )
    count = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_step == 0:
                frame_path = os.path.join(tmpdir, f"frame_{frame_idx:08d}.jpg")
                h, w = frame.shape[:2]
                if w > cfg.frame_width:
                    scale = cfg.frame_width / w
                    frame = cv2.resize(frame, (cfg.frame_width, int(h * scale)), interpolation=cv2.INTER_AREA)
                cv2.imwrite(frame_path, frame)

                timestamp_sec = frame_idx / fps
                timestamp_str = _fmt_timestamp(timestamp_sec)

                status["current_pos_sec"] = timestamp_sec
                logger.info(f"[{filename}] [{timestamp_str}] 캡셔닝 중... ({count+1}번째)")

                t0 = _time.monotonic()
                caption = _caption_frame(frame_path, cfg)
                elapsed = _time.monotonic() - t0

                if not caption:
                    frame_idx += 1
                    continue

                embedding = _embedder.encode(caption).tolist()
                doc_id = f"{filename}_{frame_idx:08d}"

                db_module.get_collection(cfg).upsert(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[caption],
                    metadatas=[{
                        "filename": filename,
                        "filepath": video_path,
                        "frame_idx": frame_idx,
                        "timestamp_sec": timestamp_sec,
                        "timestamp": timestamp_str,
                    }],
                )
                count += 1
                status["current_frame"] = count
                status["current_caption"] = caption[:80]
                status["frame_times"] = (status["frame_times"] + [elapsed])[-5:]
                logger.info(f"[{filename}] ✓ [{timestamp_str}] {elapsed:.1f}초 → {caption[:80]}")
            frame_idx += 1

    cap.release()
    logger.info(f"[{filename}] 완료 — {count}개 프레임 저장")
    return count


def _fmt_timestamp(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _already_processed(video_path: str, cfg: config.Config) -> bool:
    filename = Path(video_path).name
    results = db_module.get_collection(cfg).get(where={"filename": filename}, limit=1)
    return len(results["ids"]) > 0


def _collect_videos(recording_dir: str) -> list[str]:
    videos = []
    for root, _, files in os.walk(recording_dir):
        for f in sorted(files):
            if Path(f).suffix.lower() in VIDEO_EXTENSIONS:
                videos.append(os.path.join(root, f))
    return videos


def _worker(cfg: config.Config, on_progress: Callable | None):
    global status
    try:
        _load_engine(cfg)
        _load_embedder(cfg)
        db_module.get_collection(cfg)
        logger.info(f"ChromaDB 로드 완료: {cfg.db_path}")
    except Exception as e:
        status["errors"].append(f"초기화 실패: {e}")
        status["running"] = False
        logger.error(f"초기화 실패: {e}")
        return

    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class NewVideoHandler(FileSystemEventHandler):
        def __init__(self, queue):
            self.queue = queue

        def on_created(self, event):
            if not event.is_directory and Path(event.src_path).suffix.lower() in VIDEO_EXTENSIONS:
                self.queue.append(event.src_path)

    queue = []
    observer = Observer()
    observer.schedule(NewVideoHandler(queue), cfg.recording_dir, recursive=True)
    observer.start()

    existing = _collect_videos(cfg.recording_dir)
    status["total"] = len(existing)
    logger.info(f"녹화 폴더 스캔 완료 — 총 {len(existing)}개 파일")

    for file_idx, vpath in enumerate(existing, 1):
        if _stop_event.is_set():
            break
        if _already_processed(vpath, cfg):
            status["processed"] += 1
            logger.info(f"[{file_idx}/{len(existing)}] 스킵 (이미 처리됨): {Path(vpath).name}")
            continue
        status["current_file"] = Path(vpath).name
        status["current_file_idx"] = file_idx
        logger.info(f"[{file_idx}/{len(existing)}] 처리 시작: {Path(vpath).name}")
        try:
            n = _process_video(vpath, cfg)
            status["current_pos_sec"] = status["current_duration_sec"]  # 100% 표시
            status["processed"] += 1
            if on_progress:
                on_progress(status.copy())
        except Exception as e:
            status["errors"].append(f"{Path(vpath).name}: {e}")
            logger.error(f"처리 실패 {vpath}: {e}")

    while not _stop_event.is_set():
        if queue:
            vpath = queue.pop(0)
            status["current_file"] = Path(vpath).name
            status["total"] += 1
            try:
                time.sleep(2)  # 녹화 완료 대기
                _process_video(vpath, cfg)
                status["processed"] += 1
            except Exception as e:
                status["errors"].append(f"{Path(vpath).name}: {e}")
        else:
            time.sleep(1)

    observer.stop()
    observer.join()
    status["running"] = False
    status["current_file"] = ""
    logger.info("파이프라인 중지")


def start(cfg: config.Config, on_progress: Callable | None = None):
    global _worker_thread, status
    if status["running"]:
        return
    _stop_event.clear()
    status.update({
        "running": True, "processed": 0, "total": 0,
        "current_file": "", "current_file_idx": 0,
        "current_frame": 0, "current_frame_total": 0,
        "current_caption": "", "started_at": _time.monotonic(),
        "frame_times": [], "errors": [],
    })
    _worker_thread = threading.Thread(target=_worker, args=(cfg, on_progress), daemon=True)
    _worker_thread.start()
    logger.info("파이프라인 시작")


def stop():
    global status
    _stop_event.set()
    status["running"] = False
    if _engine:
        try:
            _engine.__exit__(None, None, None)
        except Exception:
            pass
    logger.info("파이프라인 중지 요청")


def get_status() -> dict:
    return status.copy()
