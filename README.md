# NVR 영상 자연어 검색 시스템

Gemma 4 VLM으로 NVR 녹화 영상을 자동 캡셔닝하고, 자연어로 영상을 검색하는 로컬 AI 시스템입니다.

---

## 시스템 요구사항

| 항목 | 최소 사양 |
|------|----------|
| OS | Linux (Arch Linux 권장) |
| CPU | Intel Core Ultra 5 이상 |
| RAM | 16GB 이상 |
| 저장소 | 50GB 이상 (DB + 모델) |
| GPU | Intel Arc iGPU (선택, CPU도 동작) |

> **폐쇄망 환경**: 설치 후 인터넷 연결 불필요

---

## 설치 방법 (NVR 시스템)

### 사전 준비

배포 패키지와 Gemma 4 모델 파일을 USB 또는 내부망으로 NVR 시스템에 복사합니다.

```
전달할 파일:
├── nvr-search-v1.0.tar.gz   ← 배포 패키지
└── gemma-4.litertlm          ← Gemma 4 모델 파일 (별도)
```

### 설치

```bash
# 1. 패키지 압축 해제
tar xzf nvr-search-v1.0.tar.gz

# 2. 설치 스크립트 실행 (관리자 권한 필요)
sudo ./nvr-search/install.sh
```

설치 중 아래 두 가지를 입력합니다:
- Gemma 4 모델 파일 경로 (예: `/mnt/usb/gemma-4.litertlm`)
- NVR 녹화 디렉토리 경로 (예: `/mnt/recordings`)

### 설치 결과

```
/opt/nvr-search/
├── nvr-search          ← 실행 바이너리
├── config.yaml         ← 설정 파일
├── models/             ← 모델 파일 위치
├── db/                 ← 벡터 DB 저장소
└── nvr_embedding_model/ ← 임베딩 모델 (번들됨)
```

설치 완료 후 시스템이 부팅될 때마다 자동으로 시작됩니다.

---

## 사용 방법

### 웹 UI 접속

설치 완료 후 브라우저에서 접속:

```
http://localhost:7860        (NVR 본체에서)
http://[NVR-IP주소]:7860    (같은 네트워크의 다른 PC에서)
```

### 탭 구성

#### 🔍 영상 검색
자연어로 원하는 장면을 검색합니다.

```
검색 예시:
- "주차장에서 빨간 차가 이동하는 장면"
- "밤에 사람이 건물 입구에 접근하는 영상"
- "오후에 화물차가 하역하는 모습"
```

검색 결과로 관련 영상 파일명, 시각, 장면 설명, 유사도를 보여줍니다.

#### ⚙️ 파이프라인
녹화 영상 처리를 시작/중지하고 진행 상황을 확인합니다.

- **시작**: 녹화 폴더의 영상을 분석하여 DB에 저장
- **중지**: 분석 중단 (이어서 시작 가능)
- **상태 갱신**: 처리 진행률 및 저장된 장면 수 확인

#### 🛠️ 설정
시스템 설정을 변경합니다. 변경 후 **저장** 버튼을 누르면 즉시 적용됩니다.

| 설정 항목 | 설명 | 기본값 |
|----------|------|--------|
| 모델 경로 | Gemma 4 `.litertlm` 파일 위치 | `/opt/nvr-search/models/gemma-4.litertlm` |
| 녹화 디렉토리 | NVR 녹화 파일 폴더 | `/mnt/recordings` |
| 추론 백엔드 | `cpu` 또는 `gpu` (Intel Arc) | `cpu` |
| 프레임 추출 간격 | N초마다 프레임 1장 분석 | `5`초 |
| 최대 검색 결과 | 검색 시 반환할 최대 결과 수 | `10` |
| 캡셔닝 프롬프트 | VLM에 전달하는 분석 지시문 | (한국어 기본값) |

---

## 서비스 관리

```bash
# 상태 확인
systemctl status nvr-search

# 시작 / 중지 / 재시작
systemctl start nvr-search
systemctl stop nvr-search
systemctl restart nvr-search

# 실시간 로그 보기
journalctl -u nvr-search -f

# 부팅 자동 시작 비활성화
systemctl disable nvr-search
```

---

## 설정 파일 직접 편집

`/opt/nvr-search/config.yaml`을 직접 편집할 수 있습니다.

```yaml
model_path: /opt/nvr-search/models/gemma-4.litertlm
recording_dir: /mnt/recordings
db_path: /opt/nvr-search/db
embedding_model_path: /opt/nvr-search/models/embedding
backend: cpu          # cpu 또는 gpu
frame_interval: 5     # 프레임 추출 간격 (초)
top_k: 10             # 최대 검색 결과 수
host: 0.0.0.0
port: 7860
```

편집 후 서비스를 재시작합니다:
```bash
systemctl restart nvr-search
```

---

## 지원 영상 형식

`.mp4` `.avi` `.mkv` `.mov` `.ts` `.m4v`

---

## 문제 해결

### 웹 페이지가 열리지 않는 경우
```bash
systemctl status nvr-search
journalctl -u nvr-search -f
```

### 모델을 찾을 수 없다는 오류
웹 UI → 설정 탭에서 모델 경로를 확인하거나 config.yaml을 직접 수정합니다.

### 검색 결과가 없는 경우
파이프라인 탭에서 처리가 완료됐는지 확인합니다. DB에 저장된 장면 수가 0이면 파이프라인을 먼저 실행해야 합니다.

### GPU 사용 시 오류
설정에서 백엔드를 `cpu`로 변경합니다.

---

## 개발자 가이드

### 환경 설정

```bash
# 저장소 클론 후 의존성 설치
cd liteRT-lm
uv sync

# LiteRT-LM은 uv tool로 별도 설치 (이미 설치된 경우 생략)
uv tool install litert-lm
```

### 로컬 실행

```bash
# 기본 실행 (config.yaml 자동 생성)
uv run python app.py

# 설정 파일 경로 지정
NVR_CONFIG=./my-config.yaml uv run python app.py

# 접속: http://localhost:7860
```

### 개발용 config.yaml 예시

프로젝트 루트에 `config.yaml`을 생성합니다:

```yaml
model_path: /path/to/gemma-4.litertlm
recording_dir: /path/to/test-videos
db_path: ./dev-db
embedding_model_path: ~/.cache/nvr-search-embedding
backend: cpu
frame_interval: 10
top_k: 5
host: 127.0.0.1
port: 7860
```

### 각 모듈 단독 테스트

```bash
# 파이프라인만 테스트 (영상 1개 처리)
uv run python - <<'EOF'
import config, pipeline
cfg = config.load()
pipeline._load_engine(cfg)
pipeline._load_embedder(cfg)
pipeline._load_db(cfg)
n = pipeline._process_video("/path/to/test.mp4", cfg)
print(f"처리된 프레임: {n}개")
EOF

# 검색만 테스트
uv run python - <<'EOF'
import config, search
cfg = config.load()
results = search.search("빨간 차", cfg)
for r in results:
    print(f"{r.filename} [{r.timestamp}] {r.score:.2%} — {r.caption[:60]}")
EOF

# 임베딩 모델 다운로드 (최초 1회)
uv run python - <<'EOF'
from sentence_transformers import SentenceTransformer
model = SentenceTransformer(
    "paraphrase-multilingual-MiniLM-L12-v2",
    cache_folder="~/.cache/nvr-search-embedding"
)
print("다운로드 완료")
EOF
```

### 프로젝트 구조

```
liteRT-lm/
├── app.py          # Gradio UI — 탭 레이아웃, 이벤트 핸들러
├── pipeline.py     # 영상 처리 — 프레임 추출, VLM 캡셔닝, DB 저장
├── search.py       # 검색 엔진 — 벡터 검색, LLM 요약
├── config.py       # 설정 관리 — config.yaml 읽기/쓰기
├── pyproject.toml  # 의존성
├── build/
│   ├── build.sh        # 배포 패키지 빌드 (인터넷 환경에서 실행)
│   └── nvr-search.spec # PyInstaller 번들 설정
└── install.sh      # NVR 배포용 설치 스크립트
```

### 배포 패키지 빌드

인터넷이 연결된 개발자 머신에서 실행합니다:

```bash
bash build/build.sh
# → nvr-search-v1.0.tar.gz 생성
```

빌드 내부 과정:
1. `uv sync` — 의존성 설치
2. 임베딩 모델 다운로드 (`~/.cache/nvr-search-embedding`)
3. `pyinstaller build/nvr-search.spec` — 바이너리 번들링
4. `tar czf` — 배포 패키지 압축

### LiteRT-LM Python 경로

`uv tool install litert-lm`으로 설치된 모듈 위치:

```
~/.local/share/uv/tools/litert-lm/lib/python3.12/site-packages/litert_lm/
```

`pipeline.py`, `search.py`에서 `sys.path`에 자동으로 추가됩니다.
PyInstaller 빌드 시 `nvr-search.spec`의 `--collect-all litert_lm`으로 번들됩니다.

### 캡셔닝 프롬프트 수정

`config.yaml`의 `caption_prompt`를 수정하거나 웹 UI 설정 탭에서 변경합니다:

```yaml
# 번호판 인식에 특화
caption_prompt: "이 보안 카메라 프레임에서 차량 번호판, 차종, 색상을 정확히 읽어줘."

# 사람 행동 분석에 특화
caption_prompt: "이 프레임에 있는 사람의 외모, 복장, 행동을 상세히 설명해줘."
```

### 주의사항

- `vision_backend` 파라미터는 Gemma 4 멀티모달 모델에서만 동작합니다
- Intel iGPU GPU 백엔드(`backend: gpu`)는 실제 NVR 하드웨어에서 테스트 필요합니다
- Intel NPU는 LiteRT-LM 미지원으로 현재 사용하지 않습니다
- ChromaDB는 단일 프로세스만 접근 가능하므로 앱 인스턴스를 하나만 실행하세요
