#!/bin/bash
# OnTarget 开源版后台启动脚本

cd "$(dirname "$0")" || exit 1

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}  OnTarget 开源版后台启动  ${NC}"
echo -e "${GREEN}================================${NC}"

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}警告：未找到 .env 文件${NC}"
    echo "请先运行: cp .env.example .env && nano .env"
    exit 1
fi

# 创建必要的目录
mkdir -p data logs

# 激活虚拟环境
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo -e "${YELLOW}正在创建虚拟环境...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    pip install -q -r requirements.txt
fi

# 检查是否已在运行
if [ -f "ontarget.pid" ] && kill -0 $(cat ontarget.pid) 2>/dev/null; then
    echo -e "${YELLOW}服务已在运行中，PID: $(cat ontarget.pid)${NC}"
    exit 0
fi

# 设置环境变量
export PYTHONPATH="$(pwd):$PYTHONPATH"
export FLASK_APP=app.py

echo ""
echo -e "${GREEN}启动后台服务...${NC}"

# 使用 nohup 后台运行 gunicorn
WORKERS=${WORKERS:-4}
nohup ./venv/bin/gunicorn \
    -w $WORKERS \
    -b 0.0.0.0:5500 \
    --timeout 120 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log \
    --pid ontarget.pid \
    --daemon \
    app:app

sleep 2

if [ -f "ontarget.pid" ] && kill -0 $(cat ontarget.pid) 2>/dev/null; then
    echo ""
    echo -e "${GREEN}✅ 服务已启动 (PID: $(cat ontarget.pid))${NC}"
    echo -e "${GREEN}访问地址: http://localhost:5500${NC}"
    echo ""
    echo "日志文件:"
    echo "  - logs/access.log"
    echo "  - logs/error.log"
    echo ""
    echo "停止服务: ./stop.sh"
else
    echo -e "${YELLOW}⚠️ 服务启动失败，请查看 logs/error.log${NC}"
    exit 1
fi
