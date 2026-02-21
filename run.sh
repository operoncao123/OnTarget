#!/bin/bash
# OnTarget 开源版启动脚本

# 切换到脚本所在目录
cd "$(dirname "$0")" || exit 1

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}  OnTarget 开源版启动中...  ${NC}"
echo -e "${GREEN}================================${NC}"

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}警告：未找到 .env 文件${NC}"
    echo -e "${YELLOW}请复制 .env.example 为 .env 并配置${NC}"
    echo ""
    echo "执行以下命令："
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo ""
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}未找到虚拟环境，正在创建...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ 虚拟环境创建完成${NC}"
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo -e "${YELLOW}检查依赖...${NC}"
pip install -q -r requirements.txt
echo -e "${GREEN}✓ 依赖检查完成${NC}"

# 创建必要的目录
mkdir -p data logs

# 检查 API Key 配置
if grep -q "your-api-key-here" .env 2>/dev/null; then
    echo -e "${YELLOW}=====================================${NC}"
    echo -e "${YELLOW}  警告：API Key 尚未配置！${NC}"
    echo -e "${YELLOW}=====================================${NC}"
    echo ""
    echo "AI 分析功能需要配置 API Key。"
    echo "请编辑 .env 文件，设置您的 API Key："
    echo ""
    echo "  API_KEY=your-actual-api-key"
    echo ""
    echo "支持的服务商："
    echo "  - DeepSeek (推荐): https://platform.deepseek.com"
    echo "  - OpenAI: https://platform.openai.com"
    echo "  - Anthropic: https://www.anthropic.com"
    echo ""
    read -p "按回车继续启动（AI 分析功能将不可用）..."
fi

# 设置环境变量
export PYTHONPATH="$(pwd):$PYTHONPATH"
export FLASK_APP=app.py

# 启动服务
echo ""
echo -e "${GREEN}启动服务...${NC}"
echo -e "${GREEN}访问地址: http://localhost:5000${NC}"
echo -e "${YELLOW}按 Ctrl+C 停止服务${NC}"
echo ""

# 使用 gunicorn 启动（如果虚拟环境中有）
if venv/bin/gunicorn &> /dev/null || [ -f "venv/bin/gunicorn" ]; then
    WORKERS=${WORKERS:-4}
    ./venv/bin/gunicorn \
        -w $WORKERS \
        -b 0.0.0.0:5000 \
        --timeout 120 \
        --access-logfile - \
        --error-logfile - \
        app:app
else
    # 使用 Flask 开发服务器
    python3 app.py
fi
