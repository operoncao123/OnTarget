#!/bin/bash
# OnTarget 开源版状态检查脚本

cd "$(dirname "$0")" || exit 1

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "OnTarget 服务状态:"
echo "=================="

if [ -f "ontarget.pid" ]; then
    PID=$(cat ontarget.pid)
    if kill -0 $PID 2>/dev/null; then
        echo -e "状态: ${GREEN}运行中${NC}"
        echo "PID: $PID"
        echo "端口: 5500"
        echo ""
        echo "进程信息:"
        ps -p $PID -o pid,ppid,%cpu,%mem,etime,command 2>/dev/null
    else
        echo -e "状态: ${RED}已停止${NC} (PID 文件存在但进程不存在)"
        rm -f ontarget.pid
    fi
else
    # 尝试通过端口检查
    PID=$(lsof -ti:5500 2>/dev/null)
    if [ -n "$PID" ]; then
        echo -e "状态: ${GREEN}运行中${NC} (通过端口检测)"
        echo "PID: $PID"
        echo "端口: 5500"
    else
        echo -e "状态: ${YELLOW}未运行${NC}"
    fi
fi
