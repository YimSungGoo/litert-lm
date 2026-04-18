# NVR 영상 자연어 검색 시스템 — 계획서

## 1. 프로젝트 개요

### 목적
NVR(Network Video Recorder) 시스템에 저장된 보안 카메라 녹화 영상을 AI로 분석하여, 관리자가 자연어로 원하는 장면을 빠르게 찾을 수 있게 한다.

### 배경
- 기존 NVR 시스템은 시각(날짜/시간) 기반 탐색만 가능
- 특정 사건(인물, 차량, 행동)을 찾으려면 수동으로 영상을 돌려봐야 함
- VLM(Vision Language Model)과 벡터 검색을 결합해 자연어 검색을 구현

### 제약 조건
| 항목 | 조건 |
|------|------|
| 네트워크 | 폐쇄망 (인터넷 없음) |
| 사용자 | 비개발자, CLI 미사용 |
| 배포 | 단일 설치 파일 (바이너리) |
| 운영체제 | Arch Linux |
| 하드웨어 | Intel Core Ultra 5 255H, 16GB RAM, Intel Arc iGPU, Intel NPU |

---

## 2. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────┐
│                  NVR 녹화 파일                       │
│          /mnt/recordings/*.mp4, *.ts, ...           │
└────────────────────┬────────────────────────────────┘
                     │ watchdog 감시 (신규 파일 자동 감지)
                     ▼
┌─────────────────────────────────────────────────────┐
│              파이프라인 (pipeline.py)                 │
│                                                     │
│  OpenCV → 프레임 추출 (N초 간격)                     │
│       ↓                                             │
│  LiteRT-LM + Gemma 4 VLM → 이미지 캡셔닝            │
│       ↓                                             │
│  sentence-transformers → 텍스트 임베딩              │
│       ↓                                             │
│  ChromaDB → 벡터 저장                               │
└─────────────────────────────────────────────────────┘
                     │
                     │ 검색 요청
                     ▼
┌─────────────────────────────────────────────────────┐
│              검색 엔진 (search.py)                   │
│                                                     │
│  사용자 쿼리 → 임베딩 → ChromaDB 유사도 검색         │
│       ↓                                             │
│  LiteRT-LM LLM → 결과 요약 및 설명                  │
└─────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│              웹 UI (app.py / Gradio)                 │
│                                                     │
│  [검색 탭]      [파이프라인 탭]      [설정 탭]       │
│  자연어 검색    처리 시작/중지       경로/옵션 변경   │
└─────────────────────────────────────────────────────┘
```

---

## 3. 기술 스택

| 역할 | 라이브러리/도구 | 선택 이유 |
|------|---------------|----------|
| VLM 추론 | LiteRT-LM + Gemma 4 | 온디바이스, 폐쇄망 가능 |
| 프레임 추출 | OpenCV | 경량, 다양한 코덱 지원 |
| 텍스트 임베딩 | sentence-transformers | 한국어 지원, CPU 동작 |
| 벡터 DB | ChromaDB | 서버리스 로컬 DB, 설치 간단 |
| 파일 감시 | watchdog | 신규 녹화 자동 처리 |
| 웹 UI | Gradio | Python 직접 연동, 빠른 구현 |
| 패키징 | PyInstaller | 단일 바이너리, Python 불필요 |
| 의존성 관리 | uv | 빠른 설치, 재현 가능 환경 |

---

## 4. 파일 구성

```
liteRT-lm/
├── app.py              # Gradio 웹 UI 메인
├── pipeline.py         # 영상 처리 파이프라인
├── search.py           # 벡터 검색 + LLM 요약
├── config.py           # 설정 읽기/쓰기 (config.yaml)
├── pyproject.toml      # Python 의존성
├── build/
│   ├── build.sh        # 배포 패키지 빌드 스크립트
│   └── nvr-search.spec # PyInstaller 번들 설정
├── install.sh          # NVR 시스템 설치 스크립트
├── README.md           # 사용자 설명서
└── PLAN.md             # 이 계획서
```

---

## 5. 핵심 데이터 흐름

### 5-1. 영상 처리 (Ingestion)

```python
# 1. 프레임 추출
cap = cv2.VideoCapture("recording.mp4")
frame_step = fps * frame_interval  # 기본 5초

# 2. VLM 캡셔닝
message = {
    "role": "user",
    "content": [
        {"type": "image", "path": "/tmp/frame.jpg"},
        {"type": "text", "text": "이 보안 카메라 프레임을 설명해줘"},
    ]
}
response = conversation.send_message(message)

# 3. ChromaDB 저장
db.upsert(
    ids=["recording_000012345"],
    embeddings=[embedding_vector],
    documents=["주차장에서 빨간 차가 이동 중..."],
    metadatas=[{"filename": "recording.mp4", "timestamp": "00:02:03"}]
)
```

### 5-2. 검색 (Search)

```python
# 1. 쿼리 임베딩
query_vec = embedder.encode("빨간 차 주차장")

# 2. 유사도 검색
results = db.query(query_embeddings=[query_vec], n_results=10)

# 3. LLM 요약
summary = llm.send_message(f"검색 결과: {results}\n질문: 빨간 차 어디 있어?")
```

---

## 6. 하드웨어 활용 전략

| 컴포넌트 | 사용 칩 | 비고 |
|---------|---------|------|
| Gemma 4 VLM 추론 | Intel Arc iGPU | `backend=gpu` 설정 시 |
| Gemma 4 VLM 추론 | CPU (기본값) | 안정성 우선, 기본값 |
| 이미지 인코딩 | CPU | `vision_backend=CPU` |
| 임베딩 모델 | CPU | sentence-transformers |
| Intel NPU | **미사용** | LiteRT-LM 미지원 (OpenVINO 별도 필요) |

> **GPU 사용 권장 조건**: RAM 여유가 8GB 이상 있을 때 `backend: gpu`로 변경

---

## 7. 배포 전략

### 7-1. 빌드 단계 (개발자 머신, 인터넷 필요)

```
[개발자 머신]
uv sync
임베딩 모델 다운로드 (~400MB)
PyInstaller 번들링
→ nvr-search-v1.0.tar.gz 생성
```

### 7-2. 배포 단계 (NVR, 폐쇄망)

```
[USB / 내부망 전달]
nvr-search-v1.0.tar.gz   (앱 + 임베딩 모델 포함)
gemma-4.litertlm          (별도, 수 GB)

[NVR에서 설치]
sudo ./install.sh
→ /opt/nvr-search/ 에 설치
→ systemd 서비스 자동 등록
→ 부팅 시 자동 시작
```

### 7-3. 배포 패키지 내용물

```
nvr-search-v1.0.tar.gz
└── nvr-search/
    ├── nvr-search           # 실행 바이너리
    ├── _internal/           # .so 파일, Gradio 에셋 등
    │   ├── litert_lm/       # LiteRT-LM 네이티브 라이브러리
    │   └── gradio/          # Gradio 웹 에셋
    ├── nvr_embedding_model/ # 임베딩 모델 (오프라인 번들)
    ├── config.yaml          # 기본 설정 템플릿
    └── install.sh           # 설치 스크립트
```

---

## 8. 성능 예상

| 작업 | 예상 시간 | 비고 |
|------|----------|------|
| 프레임 캡셔닝 (CPU) | 3~8초/장 | Gemma 4 E2B 모델 기준 |
| 프레임 캡셔닝 (iGPU) | 1~3초/장 | GPU 백엔드 |
| 임베딩 생성 | ~0.1초/건 | CPU |
| 벡터 검색 | <0.5초 | ChromaDB HNSW |
| LLM 요약 | 3~10초 | |
| 1시간 영상 처리 | 약 36~120분 | 5초 간격, CPU 기준 |

> 처음 처리 시 시간이 걸리지만 이후 검색은 즉시 응답

---

## 9. 향후 개선 사항

- [ ] Intel NPU 지원 (OpenVINO 연동)
- [ ] 얼굴/번호판 인식 특화 캡셔닝
- [ ] 타임라인 기반 영상 클립 직접 재생 UI
- [ ] 다중 NVR 채널 동시 처리
- [ ] 알림 기능 (특정 장면 감지 시 알림)
- [ ] 검색 결과에서 영상 직접 재생

---

## 10. 개발 진행 상황

| 단계 | 상태 | 비고 |
|------|------|------|
| config.py | ✅ 완료 | |
| pipeline.py | ✅ 완료 | vision_backend 동작 여부 현장 테스트 필요 |
| search.py | ✅ 완료 | |
| app.py | ✅ 완료 | |
| build/build.sh | ✅ 완료 | |
| build/nvr-search.spec | ✅ 완료 | |
| install.sh | ✅ 완료 | |
| 실제 영상 테스트 | ⬜ 미완 | Gemma 4 모델 파일 필요 |
| PyInstaller 빌드 테스트 | ⬜ 미완 | |
| NVR 현장 배포 테스트 | ⬜ 미완 | |
