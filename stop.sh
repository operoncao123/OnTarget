#!/bin/bash
# OnTarget 开源版停止脚本

cd "$(dirname "$0")" || exit 1

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}停止 OnTarget 服务...${NC}"

if [ -f "ontarget.pid" ]; then
    PID=$(cat ontarget.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        sleep 2
        if kill -0 $PID 2>/dev/null; then
            kill -9 $PID
        fi
        echo -e "${GREEN}✅ 服务已停止${NC}"
    else
        echo -e "${YELLOW}服务未运行${NC}"
    fi
    rm -f ontarget.pid
else
    echo -e "${YELLOW}未找到 PID 文件，尝试通过端口查找...${NC}"
    PID=$(lsof -ti:5500 2>/dev/null)
    if [ -n "$PID" ]; then
        kill $PID
        echo -e "${GREEN}✅ 服务已停止 (PID: $PID)${NC}"
    else
        echo -e "${YELLOW}未找到运行中的服务${NC}"
    fi
fi
