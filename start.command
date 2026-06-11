#!/bin/bash
# 一键启动:清理旧进程 → 起网页服务器(8000)→ 开浏览器 → 跑 bot(7860)
# 用法:双击本文件,或在终端 ./start.command
# 退出:在终端按 Ctrl+C(会自动关掉后台网页服务器)

cd "$(dirname "$0")"                       # 切到本脚本所在目录(Avatar/)
PY=/opt/anaconda3/envs/csl/bin/python      # csl 环境的 python(装了 pipecat 的那个)

echo "==> 清理可能残留的旧进程(端口 7860 / 8000)..."
lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null
lsof -ti:7860 2>/dev/null | xargs kill -9 2>/dev/null

echo "==> 启动网页服务器(http://localhost:8000)..."
( cd web && "$PY" -m http.server 8000 >/dev/null 2>&1 ) &
WEB_PID=$!

# 退出时(Ctrl+C / 关窗)自动关掉网页服务器
trap 'echo "==> 关闭网页服务器..."; kill $WEB_PID 2>/dev/null' EXIT

sleep 1
echo "==> 打开浏览器..."
open http://localhost:8000

echo "==> 启动 bot(Ctrl+C 停止)..."
"$PY" patient_jordan.py
