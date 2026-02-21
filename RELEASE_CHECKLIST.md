# OnTarget 开源版发布检查清单

## ✅ 已完成

### 核心文件
- [x] app.py - 主应用（已转换为单用户模式）
- [x] config.py - 配置文件
- [x] requirements.txt - 依赖列表
- [x] run.sh - 启动脚本（已添加权限）

### 核心模块
- [x] core/ - 核心模块（analyzer, cache_manager, system等）
- [x] models/ - 数据模型（database, user_manager, keyword_group_manager等）
- [x] services/ - 服务模块（push_service, auto_update_service等）
- [x] v1/ - 文献获取（fetcher, impact_factor, scorer）
- [x] utils/ - 工具（encryption）
- [x] tests/ - 单元测试

### 前端文件
- [x] templates/v2_dashboard.html - 主页面（已移除登录相关）
- [x] templates/v2_keywords.html - 关键词管理页面
- [x] templates/v2_landing.html - 首页（已移除注册按钮）
- [x] static/ - 静态资源（CSS, JS, 图片）

### 配置文件
- [x] .gitignore - Git 忽略规则
- [x] .env.example - 环境变量模板
- [x] LICENSE - AGPL 3.0 许可证
- [x] README.md - 项目说明（突出 ontarget.chat）
- [x] CONTRIBUTING.md - 贡献指南
- [x] DEPLOYMENT.md - 部署指南

### 功能特性
- [x] 单用户模式（无需登录注册）
- [x] 多源文献获取（PubMed, bioRxiv, medRxiv, arXiv等）
- [x] 关键词组管理
- [x] AI智能分析（需用户配置API Key）
- [x] 智能收藏
- [x] 个性化评分
- [x] 影响因子显示
- [x] 自动更新服务
- [x] HTTP安全头
- [x] API限流保护

### 移除的功能（仅在线版提供）
- [x] 用户注册系统
- [x] 用户登录系统
- [x] 找回密码功能
- [x] 管理员后台
- [x] 多用户管理

## 📋 发布前检查

### 1. 代码质量
```bash
# 检查语法错误
python3 -m py_compile app.py
python3 -m py_compile core/*.py
python3 -m py_compile models/*.py

# 运行测试
pytest tests/
```

### 2. 安全检查
- [ ] 确认 .env 文件不在仓库中
- [ ] 确认无硬编码的 API Key
- [ ] 确认 SECRET_KEY 使用占位符
- [ ] 确认数据库文件已排除
- [ ] 确认日志文件已排除

### 3. 文档检查
- [ ] README.md 中的链接有效
- [ ] 服务网址正确：ontarget.chat
- [ ] LICENSE 文件完整
- [ ] .env.example 配置说明清晰

### 4. 功能测试
- [ ] 可以正常启动
- [ ] 首页可以访问
- [ ] 可以创建关键词组
- [ ] 可以更新文献
- [ ] 可以收藏文献
- [ ] AI分析功能正常（配置API Key后）

### 5. 性能测试
- [ ] 页面加载速度正常
- [ ] 文献获取速度正常
- [ ] 数据库查询速度正常
- [ ] 内存占用合理

## 🚀 发布步骤

### 1. 创建 GitHub 仓库
```bash
# 在 GitHub 上创建新仓库：OnTarget-open
```

### 2. 初始化 Git
```bash
cd /www/OnTarget-open
git init
git add .
git commit -m "Initial commit: OnTarget open source version"
git branch -M main
git remote add origin https://github.com/yourusername/OnTarget-open.git
git push -u origin main
```

### 3. 添加 Topics
在 GitHub 仓库设置中添加 topics：
- literature-management
- academic-research
- paper-recommendation
- python
- flask
- ai
- open-source

### 4. 创建 Release
```bash
# 创建标签
git tag -a v1.0.0 -m "OnTarget Open Source v1.0.0"
git push origin v1.0.0

# 在 GitHub 上创建 Release
```

### 5. 宣传
- [ ] 在社交媒体发布
- [ ] 在学术论坛分享
- [ ] 联系相关研究者
- [ ] 添加到学术工具列表

## 📊 发布后维护

### 定期检查
- [ ] 每周查看 Issues
- [ ] 每月查看 Pull Requests
- [ ] 每季度更新依赖
- [ ] 每年更新许可证

### 社区互动
- [ ] 及时回复 Issues
- [ ] 审核 Pull Requests
- [ ] 更新文档
- [ ] 收集反馈

## 🎯 目标

- [ ] GitHub Stars > 100
- [ ] 活跃贡献者 > 5
- [ ] 月活跃用户 > 100
- [ ] 社区反馈 > 50

## 📝 备注

发布日期：2026-02-21
版本：v1.0.0
许可证：AGPL 3.0

---

祝发布顺利！🎉
