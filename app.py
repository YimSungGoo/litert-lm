import logging
import os
import sys
from pathlib import Path

# 캐시된 모델만 사용 — HuggingFace 네트워크 요청 차단
# 폐쇄망 환경에서 필수. 인터넷 있는 개발 환경에서 처음 1회는 주석 처리 후 다운로드
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import gradio as gr

import config
import pipeline
import search

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

cfg = config.ensure_default()


# ── 검색 탭 ──────────────────────────────────────────────────────────────────

_last_results: list = []


def do_search(query: str):
    global _last_results
    if not query.strip():
        return "", "검색어를 입력해주세요."

    try:
        results = search.search(query, cfg)
        _last_results = results

        if not results:
            return "", "관련 영상을 찾지 못했습니다."

        rows = []
        for r in results:
            rows.append(f"| {r.filename} | {r.timestamp} | {round(r.score * 100, 1)}% | {r.caption} |")

        table = (
            "| 파일명 | 시각 | 유사도 | 장면 설명 |\n"
            "|--------|------|--------|----------|\n"
            + "\n".join(rows)
        )
        return table, ""

    except Exception as e:
        logger.error(f"검색 오류: {e}")
        return "", f"오류: {e}"


def do_summarize(query: str):
    if not _last_results:
        return "먼저 검색을 실행해주세요."
    try:
        return search.summarize(query, _last_results, cfg)
    except Exception as e:
        logger.error(f"요약 오류: {e}")
        return f"오류: {e}"


# ── 파이프라인 탭 ──────────────────────────────────────────────────────────────

def pipeline_start():
    if pipeline.get_status()["running"]:
        return "이미 실행 중입니다."
    if not Path(cfg.model_path).exists():
        return f"모델 파일을 찾을 수 없습니다: {cfg.model_path}\n설정 탭에서 경로를 확인해주세요."
    pipeline.start(cfg)
    return "파이프라인 시작됨"


def pipeline_stop():
    pipeline.stop()
    return "파이프라인 중지 요청됨"


def _fmt_seconds(sec: float) -> str:
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    if h:
        return f"{h}시간 {m}분 {s}초"
    if m:
        return f"{m}분 {s}초"
    return f"{s}초"


def pipeline_status():
    import time as t
    s = pipeline.get_status()

    lines = [f"**상태**: {'실행 중 🟢' if s['running'] else '중지 🔴'}"]

    # 경과 시간
    if s["running"] and s["started_at"]:
        elapsed = t.monotonic() - s["started_at"]
        lines.append(f"**경과 시간**: {_fmt_seconds(elapsed)}")

    # 파일 진행
    lines.append(
        f"**파일**: {s['processed']} / {s['total']} 완료"
        + (f" — 현재 {s['current_file_idx']}번째" if s['current_file'] else "")
    )

    all_done = s["total"] > 0 and s["processed"] >= s["total"]

    if s["current_file"]:
        lines.append(f"**현재 파일**: `{s['current_file']}`")

        # 영상 시각 기반 진행 바
        dur = s.get("current_duration_sec", 0)
        pos = s.get("current_pos_sec", 0)
        if dur > 0:
            pct = min(100, int(pos / dur * 100))
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            dur_str = _fmt_seconds(dur)
            pos_str = _fmt_seconds(pos)
            lines.append(
                f"**영상 진행**: {pos_str} / {dur_str} [{bar}] {pct}% "
                f"({s['current_frame']}장 처리)"
            )

        # ETA: 남은 영상 시간 / 프레임 간격 * 프레임당 평균 소요 시간
        frame_times = s.get("frame_times", [])
        if frame_times and dur > 0 and not all_done:
            avg_sec = sum(frame_times) / len(frame_times)
            interval = cfg.frame_interval or 5
            remaining_video_sec = max(0, dur - pos)
            remaining_frames_cur = remaining_video_sec / interval
            remaining_files = max(0, s["total"] - s["current_file_idx"])
            eta_sec = avg_sec * (remaining_frames_cur + remaining_files * (dur / interval))
            lines.append(
                f"**프레임당 평균**: {avg_sec:.1f}초 | "
                f"**예상 남은 시간**: {_fmt_seconds(max(0, eta_sec))}"
            )

        if s["current_caption"]:
            lines.append(f"**마지막 캡션**: {s['current_caption']}")

    if all_done and s["running"]:
        lines.append("**✅ 전체 처리 완료 — 신규 파일 대기 중**")

    count = search.db_count(cfg)
    lines.append(f"**DB 저장 장면**: {count:,}개")

    if s["errors"]:
        lines.append(f"\n**오류** ({len(s['errors'])}건):")
        for e in s["errors"][-3:]:
            lines.append(f"- {e}")

    return "\n\n".join(lines)


# ── 설정 탭 ──────────────────────────────────────────────────────────────────

_HF_CACHE = Path.home() / ".cache/huggingface/hub"
_MODEL_PRESETS = {
    # Gemma 4 — litert-community (멀티모달 지원)
    "Gemma 4 E2B (2B, 빠름)": "models--litert-community--gemma-4-E2B-it-litert-lm",
    "Gemma 4 E4B (4B, 균형)": "models--litert-community--gemma-4-E4B-it-litert-lm",
    # Gemma 3n — google 공식 (멀티모달 지원)
    "Gemma 3n E2B (2B, 빠름)": "models--google--gemma-3n-E2B-it-litert-lm",
    "Gemma 3n E4B (4B, 균형)": "models--google--gemma-3n-E4B-it-litert-lm",
}


def _find_model_in_cache(hf_repo_dir: str) -> str:
    base = _HF_CACHE / hf_repo_dir / "snapshots"
    if not base.exists():
        return ""
    for snapshot in sorted(base.iterdir()):
        for f in snapshot.glob("*.litertlm"):
            return str(f)
    return ""


def on_preset_select(preset_name: str):
    if preset_name not in _MODEL_PRESETS:
        return gr.update(), gr.update(visible=False)
    path = _find_model_in_cache(_MODEL_PRESETS[preset_name])
    if path:
        return gr.update(value=path), gr.update(value="", visible=False)
    repo_id = _MODEL_PRESETS[preset_name].replace("models--", "").replace("--", "/", 1)
    msg = f"⚠️ 모델 미다운로드. 터미널에서 실행:\n```\nlitert-lm import --from-huggingface-repo {repo_id} $(basename $(ls ~/.cache/huggingface/hub/{_MODEL_PRESETS[preset_name]}/snapshots/*/*.litertlm 2>/dev/null || echo 'gemma-4.litertlm'))\n```\n또는:\n```\nuv tool run litert-lm import --from-huggingface-repo {repo_id} gemma-4-E4B-it.litertlm\n```"
    return gr.update(value=""), gr.update(value=msg, visible=True)


_RESOLUTION_PRESETS = {
    "320px — 빠름 (~5초/장, 낮은 정확도)": 320,
    "640px — 균형 (~15초/장, 권장)": 640,
    "1280px — 정확 (~45초/장, 고해상도)": 1280,
}


def load_settings():
    c = config.load()
    res_label = next(
        (k for k, v in _RESOLUTION_PRESETS.items() if v == c.frame_width),
        list(_RESOLUTION_PRESETS.keys())[0],
    )
    return (
        c.model_path,
        c.recording_dir,
        c.db_path,
        c.embedding_model_path,
        c.backend,
        c.frame_interval,
        res_label,
        c.top_k,
        c.caption_prompt,
    )


def save_settings(model_path, recording_dir, db_path, emb_path, backend, frame_interval, res_label, top_k, caption_prompt):
    global cfg
    cfg = config.Config(
        model_path=model_path,
        recording_dir=recording_dir,
        db_path=db_path,
        embedding_model_path=emb_path,
        backend=backend,
        frame_interval=int(frame_interval),
        frame_width=_RESOLUTION_PRESETS.get(res_label, 320),
        top_k=int(top_k),
        caption_prompt=caption_prompt,
    )
    config.save(cfg)
    return "✅ 설정이 저장되었습니다."


# ── UI 구성 ──────────────────────────────────────────────────────────────────

with gr.Blocks(title="NVR 영상 검색") as app:
    gr.Markdown("# 📹 NVR 영상 자연어 검색 시스템")
    gr.Markdown("Gemma 4 VLM으로 캡셔닝된 영상을 자연어로 검색합니다.")

    with gr.Tab("🔍 영상 검색"):
        with gr.Row():
            query_box = gr.Textbox(
                label="검색어",
                placeholder="예: 주차장에서 빨간 차가 이동하는 장면",
                scale=4,
            )
            search_btn = gr.Button("검색", variant="primary", scale=1)

        results_out = gr.Markdown(label="검색 결과")
        error_out = gr.Markdown()

        summarize_btn = gr.Button("🤖 AI 요약 (느림 ~30초)", variant="secondary")
        summary_out = gr.Markdown(label="AI 요약")

        search_btn.click(
            fn=do_search,
            inputs=[query_box],
            outputs=[results_out, error_out],
        )
        query_box.submit(
            fn=do_search,
            inputs=[query_box],
            outputs=[results_out, error_out],
        )
        summarize_btn.click(
            fn=do_summarize,
            inputs=[query_box],
            outputs=[summary_out],
        )

    with gr.Tab("⚙️ 파이프라인"):
        gr.Markdown("### 영상 처리 파이프라인")
        gr.Markdown("녹화 디렉토리의 영상을 자동으로 처리하여 DB에 저장합니다.")

        with gr.Row():
            start_btn = gr.Button("▶ 시작", variant="primary")
            stop_btn = gr.Button("⏹ 중지", variant="stop")

        log_out = gr.Markdown()
        status_out = gr.Markdown()

        start_btn.click(fn=pipeline_start, outputs=[log_out])
        stop_btn.click(fn=pipeline_stop, outputs=[log_out])

        timer = gr.Timer(value=2)
        timer.tick(fn=pipeline_status, outputs=[status_out])
        app.load(fn=pipeline_status, outputs=[status_out])

    with gr.Tab("🛠️ 설정"):
        gr.Markdown("### 시스템 설정")
        gr.Markdown("변경 후 **저장** 버튼을 누르면 즉시 적용됩니다.")

        with gr.Row():
            model_preset_in = gr.Dropdown(
                choices=list(_MODEL_PRESETS.keys()),
                label="모델 프리셋 선택",
                value=None,
                scale=2,
            )
            preset_status = gr.Markdown(visible=False)

        model_path_in = gr.Textbox(label="모델 경로 (.litertlm) — 프리셋 선택 또는 직접 입력")

        model_preset_in.change(
            fn=on_preset_select,
            inputs=[model_preset_in],
            outputs=[model_path_in, preset_status],
        )
        recording_dir_in = gr.Textbox(label="NVR 녹화 디렉토리")
        db_path_in = gr.Textbox(label="벡터 DB 저장 경로")
        emb_path_in = gr.Textbox(label="임베딩 모델 경로")

        with gr.Row():
            backend_in = gr.Radio(
                choices=["cpu", "gpu"],
                label="추론 백엔드",
                value="cpu",
            )
            frame_interval_in = gr.Slider(
                minimum=1, maximum=60, step=1,
                label="프레임 추출 간격 (초)",
                value=5,
            )
            res_label_in = gr.Radio(
                choices=list(_RESOLUTION_PRESETS.keys()),
                label="프레임 해상도",
                value=list(_RESOLUTION_PRESETS.keys())[0],
            )
            top_k_in = gr.Slider(
                minimum=1, maximum=50, step=1,
                label="최대 검색 결과 수",
                value=10,
            )

        caption_prompt_in = gr.Textbox(
            label="캡셔닝 프롬프트",
            lines=3,
        )

        with gr.Row():
            load_btn = gr.Button("↺ 불러오기")
            save_btn = gr.Button("💾 저장", variant="primary")

        settings_msg = gr.Markdown()

        load_btn.click(
            fn=load_settings,
            outputs=[model_path_in, recording_dir_in, db_path_in,
                     emb_path_in, backend_in, frame_interval_in,
                     res_label_in, top_k_in, caption_prompt_in],
        )
        save_btn.click(
            fn=save_settings,
            inputs=[model_path_in, recording_dir_in, db_path_in,
                    emb_path_in, backend_in, frame_interval_in,
                    res_label_in, top_k_in, caption_prompt_in],
            outputs=[settings_msg],
        )

        app.load(
            fn=load_settings,
            outputs=[model_path_in, recording_dir_in, db_path_in,
                     emb_path_in, backend_in, frame_interval_in,
                     res_label_in, top_k_in, caption_prompt_in],
        )


if __name__ == "__main__":
    app.launch(
        server_name=cfg.host,
        server_port=cfg.port,
        show_error=True,
        theme=gr.themes.Soft(),
    )
