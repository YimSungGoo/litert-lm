#!/usr/bin/env bash
# NVR Search 설치 스크립트
# sudo ./install.sh

set -euo pipefail

INSTALL_DIR="/opt/nvr-search"
SERVICE_NAME="nvr-search"
WEB_PORT=7860

if [ "$EUID" -ne 0 ]; then
    echo "오류: 관리자 권한이 필요합니다. sudo ./install.sh 로 실행해주세요."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==================================="
echo "  NVR Search 시스템 설치"
echo "==================================="

# 1. 설치 디렉토리 생성
echo "[1/5] 설치 디렉토리 생성..."
mkdir -p "$INSTALL_DIR/models"
mkdir -p "$INSTALL_DIR/db"

# 2. 파일 복사
echo "[2/5] 파일 복사..."
cp -r "$SCRIPT_DIR"/. "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/nvr-search"

# 3. 설정 파일 처리
echo "[3/5] 설정 파일 준비..."
CONFIG="$INSTALL_DIR/config.yaml"

if [ ! -f "$CONFIG" ]; then
    cp "$SCRIPT_DIR/config.yaml" "$CONFIG"
fi

# 임베딩 모델 경로 자동 설정
if [ -d "$INSTALL_DIR/nvr_embedding_model" ]; then
    sed -i "s|embedding_model_path:.*|embedding_model_path: $INSTALL_DIR/nvr_embedding_model|" "$CONFIG"
fi

echo ""
echo "  📁 모델 파일 위치를 설정합니다."
echo "  Gemma 4 모델(.litertlm) 파일 경로를 입력해주세요."
echo "  (예: /mnt/usb/gemma-4.litertlm)"
read -rp "  모델 경로: " MODEL_PATH

if [ -f "$MODEL_PATH" ]; then
    sed -i "s|model_path:.*|model_path: $MODEL_PATH|" "$CONFIG"
    echo "  ✅ 모델 경로 설정 완료"
else
    echo "  ⚠️  파일을 찾을 수 없습니다. 나중에 웹 설정 화면에서 변경 가능합니다."
fi

echo ""
echo "  NVR 녹화 파일 디렉토리를 입력해주세요."
echo "  (예: /mnt/recordings 또는 /var/nvr/videos)"
read -rp "  녹화 디렉토리: " REC_DIR

if [ -d "$REC_DIR" ]; then
    sed -i "s|recording_dir:.*|recording_dir: $REC_DIR|" "$CONFIG"
    echo "  ✅ 녹화 디렉토리 설정 완료"
else
    echo "  ⚠️  디렉토리를 찾을 수 없습니다. 나중에 웹 설정 화면에서 변경 가능합니다."
fi

# 4. systemd 서비스 등록
echo "[4/5] 자동 시작 서비스 등록..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=NVR 영상 자연어 검색 시스템
After=network.target

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/nvr-search
WorkingDirectory=${INSTALL_DIR}
Environment=NVR_CONFIG=${CONFIG}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# 5. 방화벽 포트 안내
echo "[5/5] 설치 완료"

# IP 주소 확인
IP=$(hostname -I | awk '{print $1}')

echo ""
echo "==================================="
echo "  ✅ 설치 완료!"
echo "==================================="
echo ""
echo "  웹 브라우저에서 아래 주소로 접속하세요:"
echo "  → http://localhost:${WEB_PORT}"
echo "  → http://${IP}:${WEB_PORT}  (다른 PC에서 접속)"
echo ""
echo "  서비스 관리 명령어:"
echo "  systemctl status $SERVICE_NAME   # 상태 확인"
echo "  systemctl stop $SERVICE_NAME     # 중지"
echo "  systemctl start $SERVICE_NAME    # 시작"
echo "  journalctl -u $SERVICE_NAME -f   # 로그 보기"
echo ""
echo "  설정은 웹 UI의 [설정] 탭에서 변경 가능합니다."
echo ""
