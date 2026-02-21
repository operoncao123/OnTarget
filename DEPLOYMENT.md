# OnTarget 开源版部署指南

## 快速部署

### 1. 环境要求

- Python 3.9+
- SQLite 3
- 2GB+ 内存
- 现代浏览器

### 2. 下载代码

```bash
git clone https://github.com/yourusername/OnTarget-open.git
cd OnTarget-open
```

### 3. 配置环境

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
nano .env
```

**必须配置的项：**
- `API_KEY` - 你的 AI API Key
- `SECRET_KEY` - 随机生成的密钥
- `PUBMED_EMAIL` - 你的邮箱

### 4. 启动服务

```bash
chmod +x run.sh
./run.sh
```

### 5. 访问系统

打开浏览器访问：http://localhost:5000

## 生产环境部署

### 使用 Gunicorn

```bash
# 安装 Gunicorn
pip install gunicorn

# 启动服务（4个worker）
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### 使用 Systemd

创建服务文件 `/etc/systemd/system/ontarget.service`:

```ini
[Unit]
Description=OnTarget Service
After=network.target

[Service]
Type=exec
User=www-data
WorkingDirectory=/path/to/OnTarget-open
Environment="PATH=/path/to/OnTarget-open/venv/bin"
ExecStart=/path/to/OnTarget-open/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 app:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl start ontarget
sudo systemctl enable ontarget
```

### 使用 Nginx 反向代理

Nginx 配置示例：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /path/to/OnTarget-open/static;
    }
}
```

### 使用 HTTPS (Let's Encrypt)

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

## 性能优化

### 1. 调整 Worker 数量

根据 CPU 核心数调整：

```bash
# 4核CPU建议
WORKERS=8
```

### 2. 启用缓存

编辑 `core/memory_cache.py`，调整缓存大小。

### 3. 数据库优化

SQLite 已配置 WAL 模式，无需额外优化。

## 数据备份

### 手动备份

```bash
# 备份数据库
cp data/literature.db backups/literature-$(date +%Y%m%d).db

# 备份配置
cp .env backups/.env-$(date +%Y%m%d)
```

### 自动备份（Cron）

```bash
# 编辑 crontab
crontab -e

# 每天凌晨2点备份
0 2 * * * cd /path/to/OnTarget-open && cp data/literature.db backups/literature-$(date +\%Y\%m\%d).db
```

## 故障排查

### 查看日志

```bash
# 查看错误日志
tail -f logs/error.log

# 查看访问日志
tail -f logs/access.log
```

### 常见问题

**问题 1：端口被占用**
```bash
# 查找占用端口的进程
lsof -i :5000

# 杀掉进程
kill -9 <PID>
```

**问题 2：API Key 无效**
- 检查 `.env` 文件中的 `API_KEY` 是否正确
- 确认 API Key 是否有效
- 检查 API 配额是否用完

**问题 3：无法获取文献**
- 检查网络连接
- 确认 `PUBMED_EMAIL` 已配置
- 查看日志了解详细错误

## 更新升级

```bash
# 拉取最新代码
git pull origin main

# 更新依赖
pip install -r requirements.txt

# 重启服务
sudo systemctl restart ontarget
```

## 技术支持

- **在线服务**: [ontarget.chat](https://ontarget.chat)
- **问题反馈**: [GitHub Issues](https://github.com/yourusername/OnTarget-open/issues)
- **文档**: [GitHub Wiki](https://github.com/yourusername/OnTarget-open/wiki)
