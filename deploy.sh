#!/usr/bin/env bash
# deploy.sh — Mac 侧一键推代码到新 Vast 实例
# 用法： ./deploy.sh <HOST> <PORT>
#   例： ./deploy.sh ssh8.vast.ai 12301
# 之后 SSH 上去跑：bash ~/AvatarForcing/provision.sh
set -euo pipefail

HOST="${1:?用法: ./deploy.sh <HOST> <PORT>}"
PORT="${2:?用法: ./deploy.sh <HOST> <PORT>}"
SSH="ssh -p $PORT -o StrictHostKeyChecking=accept-new"
DST="root@$HOST:~/AvatarForcing"
ENGINE=~/Downloads/AvatarForcing-main
BOT=~/Downloads/Avatar

echo "==== [1/3] 引擎 + 权重脚本 + provision + data（AvatarForcing-main）→ $HOST ===="
rsync -avz -e "$SSH" \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude 'pretrained_dir' --exclude 'results' \
  "$ENGINE/" "$DST/"

echo "==== [2/3] bot 文件（Avatar 项目）→ $HOST ===="
rsync -avz -e "$SSH" \
  "$BOT/patient_jordan.py" "$BOT/patient_candice.py" "$BOT/patient_savannah.py" \
  "$BOT/avatarforcing_service.py" \
  "$BOT/session_log.py" "$BOT/vision.py" "$BOT/ser.py" "$BOT/.env" \
  "$DST/"

echo "==== [3/3] web 前端 → $HOST ===="
rsync -avz -e "$SSH" "$BOT/web" "$DST/"

echo
echo "✅ 推送完成。下一步（一条命令配环境）："
echo "   ssh -p $PORT root@$HOST 'bash ~/AvatarForcing/provision.sh'"
echo "然后跑 bot："
echo "   ssh -p $PORT root@$HOST"
echo "   conda activate afp && cd ~/AvatarForcing && AVATAR=avatarforcing python patient_jordan.py -t daily"
