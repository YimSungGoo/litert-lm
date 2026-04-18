#!/usr/bin/env bash
# NVR Search 빌드 스크립트
# 개발자 머신 (인터넷 연결 환경)에서 실행

set -euo pipefail
cd "$(dirname "$0")/.."

DIST_DIR="dist/nvr-search"
VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')
OUTPUT="nvr-search-v${VERSION}.tar.gz"

echo "=== NVR Search v${VERSION} 빌드 ==="

# 1. 의존성 설치
echo "[1/4] 의존성 설치 중..."
uv sync
uv pip install pyinstaller

# 2. 임베딩 모델 미리 다운로드 (오프라인 배포용)
echo "[2/4] 임베딩 모델 다운로드 중..."
CACHE_DIR="$HOME/.cache/nvr-search-embedding"
if [ ! -d "$CACHE_DIR" ]; then
    uv run python3 - <<'EOF'
import os
from sentence_transformers import SentenceTransformer
cache = os.path.expanduser("~/.cache/nvr-search-embedding")
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", cache_folder=cache)
print(f"임베딩 모델 저장 완료: {cache}")
EOF
fi

# 3. PyInstaller 빌드
echo "[3/4] PyInstaller 빌드 중..."
rm -rf dist/ build/__pycache__
uv run pyinstaller build/nvr-search.spec --distpath dist --workpath /tmp/nvr-search-build

# 임베딩 모델을 dist 폴더에 복사
if [ -d "$CACHE_DIR" ]; then
    cp -r "$CACHE_DIR" "$DIST_DIR/nvr_embedding_model"
fi

# 4. 배포 패키지 생성
echo "[4/4] 배포 패키지 생성 중..."
cp install.sh "$DIST_DIR/"
chmod +x "$DIST_DIR/nvr-search"
chmod +x "$DIST_DIR/install.sh"

# 설정 템플릿 포함
cat > "$DIST_DIR/config.yaml" <<'YAML'
model_path: /opt/nvr-search/models/gemma-4.litertlm
recording_dir: /mnt/recordings
db_path: /opt/nvr-search/db
embedding_model_path: /opt/nvr-search/models/embedding
backend: cpu
frame_interval: 5
caption_prompt: "이 보안 카메라 영상 프레임을 상세히 설명해줘. 사람, 차량, 물체, 행동, 장소 특징을 포함해."
top_k: 10
host: 0.0.0.0
port: 7860
YAML

tar czf "$OUTPUT" -C dist nvr-search/

echo ""
echo "✅ 빌드 완료: $OUTPUT"
echo ""
echo "배포 방법:"
echo "  1. $OUTPUT 을 NVR 시스템으로 복사"
echo "  2. Gemma 4 모델 파일을 /opt/nvr-search/models/ 에 복사"
echo "  3. NVR 시스템에서: sudo ./nvr-search/install.sh"
