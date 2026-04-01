#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
PY="$WORKSPACE/.venv-flow/bin/python"
RUNNER="$WORKSPACE/scripts/flow_batch_runner.py"

if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi

if [ ! -f "$RUNNER" ]; then
  echo "[error] missing runner: $RUNNER"
  exit 2
fi

echo "=== Flow Image Wizard ==="
read -r -p "Nhập đường dẫn thư mục ảnh: " IMAGES_DIR
if [ -z "$IMAGES_DIR" ] || [ ! -d "$IMAGES_DIR" ]; then
  echo "[error] thư mục không hợp lệ"
  exit 2
fi

# kiểm tra ảnh đánh số 1.*,2.*,3.*...
count=0
for ext in jpg jpeg png webp; do
  if [ -f "$IMAGES_DIR/1.$ext" ]; then
    break
  fi
done

n=1
while true; do
  found=0
  for ext in jpg jpeg png webp; do
    if [ -f "$IMAGES_DIR/$n.$ext" ]; then
      found=1
      break
    fi
  done
  if [ "$found" -eq 1 ]; then
    count=$n
    n=$((n+1))
  else
    break
  fi
done

if [ "$count" -eq 0 ]; then
  echo "[error] không thấy ảnh đánh số kiểu 1.jpg / 1.png ..."
  exit 2
fi

echo "[ok] phát hiện $count ảnh đánh số liên tiếp (1..$count)"

read -r -p "Mỗi ảnh tạo mấy video? (mặc định 1): " VPI
VPI="${VPI:-1}"

read -r -p "Tỷ lệ video (16:9 hoặc 9:16, mặc định 16:9): " ASPECT
ASPECT="${ASPECT:-16:9}"
if [ "$ASPECT" != "16:9" ] && [ "$ASPECT" != "9:16" ]; then
  echo "[error] tỷ lệ chỉ nhận 16:9 hoặc 9:16"
  exit 2
fi

read -r -p "Chế độ chọn cảnh: (1) từ cảnh đầu đến cuối, (2) cảnh đơn lẻ [1/2]: " MODE
MODE="${MODE:-1}"

ARGS=(
  --input-mode image
  --images-dir "$IMAGES_DIR"
  --videos-per-image "$VPI"
  --aspect-ratio "$ASPECT"
)

if [ "$MODE" = "2" ]; then
  read -r -p "Nhập số cảnh đơn lẻ (1..$count): " SINGLE
  ARGS+=(--image-single "$SINGLE")
else
  read -r -p "Cảnh bắt đầu (mặc định 1): " START
  START="${START:-1}"
  read -r -p "Cảnh kết thúc (mặc định $count): " END
  END="${END:-$count}"
  ARGS+=(--image-start "$START" --image-end "$END")
fi

echo "[run] $PY $RUNNER ${ARGS[*]}"
"$PY" "$RUNNER" "${ARGS[@]}"
