import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field, asdict

_IS_INSTALLED = Path("/opt/nvr-search").exists()
_DEFAULT_CONFIG = "/opt/nvr-search/config.yaml" if _IS_INSTALLED else "./config.yaml"
CONFIG_PATH = Path(os.environ.get("NVR_CONFIG", _DEFAULT_CONFIG))

DEFAULT_DB_PATH = "/opt/nvr-search/db" if _IS_INSTALLED else "./dev-db"
DEFAULT_EMBEDDING_MODEL = "/opt/nvr-search/models/embedding" if _IS_INSTALLED else "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_MODEL_PATH = "/opt/nvr-search/models/gemma-4.litertlm" if _IS_INSTALLED else ""


@dataclass
class Config:
    model_path: str = DEFAULT_MODEL_PATH
    recording_dir: str = "/mnt/recordings"
    db_path: str = DEFAULT_DB_PATH
    embedding_model_path: str = DEFAULT_EMBEDDING_MODEL
    backend: str = "cpu"
    frame_interval: int = 5
    caption_prompt: str = "보안 카메라 프레임을 1~2문장으로 간결하게 설명해. 사람·차량·행동·장소만 포함해."
    frame_width: int = 320  # VLM 입력 해상도 (320/640/1280)
    top_k: int = 10
    host: str = "0.0.0.0"
    port: int = 7860


def _resolve(path: str) -> str:
    return str(Path(path).resolve())


def load() -> Config:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        cfg = Config(**{k: v for k, v in data.items() if k in Config.__dataclass_fields__})
    else:
        cfg = Config()
    cfg.db_path = _resolve(cfg.db_path)
    return cfg


def save(cfg: Config) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(asdict(cfg), f, allow_unicode=True, default_flow_style=False)


def ensure_default() -> Config:
    cfg = load()
    if not CONFIG_PATH.exists():
        save(cfg)
    return cfg
