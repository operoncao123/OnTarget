#!/usr/bin/env python3
"""
V2 Web应用 - 带用户系统的文献推送Web界面
"""

import os
import sys
import threading
import time
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from functools import wraps

from flask import Flask, render_template, jsonify, request, session, redirect, url_for

# 加载环境变量（使用绝对路径）
env_file = os.path.join(base_dir, '.env')
if os.path.exists(env_file):
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# 导入模块（新目录结构）
from models.user_manager import UserManager, get_predefined_categories, expand_keywords
from core.cache_manager import SmartCache
from services.push_service import PersonalizedPushEngine, PushScheduler
from core.analyzer import OptimizedAnalyzer, AnalysisQueue
from core.system import LiteraturePushSystemV2
#from services.admin_service import AdminManager  # 开源版不需要
from models.keyword_group_manager import KeywordGroupManager
from utils.encryption import get_encryption_manager

app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# 初始化系统 - 使用相对于当前文件的路径
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, 'data')
system = LiteraturePushSystemV2(data_dir)

## 初始化管理员管理器
##admin_manager = AdminManager  # 开源版不需要(
#data_dir=data_dir,
#    cache=system.cache,
#    user_manager=system.user_manager,
#    analyzer=system.analyzer
#)

# 初始化关键词组管理器 - V2.3使用SQLite数据库
keyword_group_manager = KeywordGroupManager(db_path=os.path.join(data_dir, 'literature.db'))

# 初始化加密管理器
encryption_manager = get_encryption_manager()


# ============ 开源版单用户模式 ============
SINGLE_USER_ID = "default_user"
# ============ 单用户模式结束 ============

# ============ API限流配置 (V2.6) ============
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def get_limit_auth():
    """获取当前用户的ID用于限流"""
    return session.get('user_id', get_remote_address())

limiter = Limiter(
    app=app,
    key_func=get_limit_auth,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://"
)

# 公开限流（登录、注册等）
public_limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["10 per minute", "5 per minute"]
)
# ============ 限流配置结束 ============

# 初始化自动更新服务
from services.auto_update_service import AutoUpdateService
auto_update_service = AutoUpdateService(system, keyword_group_manager)

# ============ 限流错误处理 ============
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        'success': False,
        'error': '请求过于频繁，请稍后再试',
        'retry_after': e.description
    }), 429
# ============ 限流错误处理结束 ============

# ============ HTTP安全头 ============
@app.after_request
def add_security_headers(response):
    """添加HTTP安全头"""
    # 防止点击劫持
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # 防止MIME类型嗅探
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # XSS保护
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # 引用策略
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # 禁用缓存敏感页面
    if request.path.startswith('/api/') or request.path in ['/login', '/register', '/forgot-password']:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
    return response
# ============ HTTP安全头结束 ============

# ============ 异步更新任务管理 ============
# 存储更新任务状态: {user_id: {'status': 'running'|'completed'|'failed', 'result': {...}, 'started_at': ..., 'completed_at': ...}}
update_tasks = {}
update_tasks_lock = threading.Lock()

def run_update_task(user_id):
    """在后台线程运行更新任务"""
    try:
        with update_tasks_lock:
            update_tasks[user_id] = {
                'status': 'running',
                'result': None,
                'started_at': datetime.now(),
                'completed_at': None,
                'message': '正在获取文献...'
            }
        
        print(f"[后台任务] 开始为用户 {user_id} 更新文献")
        
        # 执行更新
        result = system.run_for_user(user_id)
        
        # 保存最后更新时间到用户偏好
        try:
            system.user_manager.update_preferences(user_id, {
                'last_manual_update_at': datetime.now().isoformat(),
                'last_manual_update_result': {
                    'fetched': result.get('fetched', 0),
                    'from_cache': result.get('from_cache', 0),
                    'new_analysis': result.get('new_analysis', 0)
                }
            })
        except Exception as e:
            print(f"[后台任务] 保存更新时间失败: {e}")
        
        with update_tasks_lock:
            update_tasks[user_id] = {
                'status': 'completed',
                'result': result,
                'started_at': update_tasks[user_id]['started_at'],
                'completed_at': datetime.now(),
                'message': f"获取完成: {result.get('fetched', 0)} 篇新文献"
            }
        
        print(f"[后台任务] 用户 {user_id} 更新完成: {result}")
        
    except Exception as e:
        print(f"[后台任务] 用户 {user_id} 更新失败: {e}")
        import traceback
        traceback.print_exc()
        
        with update_tasks_lock:
            update_tasks[user_id] = {
                'status': 'failed',
                'result': {'error': str(e)},
                'started_at': update_tasks[user_id].get('started_at', datetime.now()),
                'completed_at': datetime.now(),
                'message': f'更新失败: {str(e)}'
            }

def cleanup_old_tasks():
    """清理超过1小时的旧任务记录"""
    with update_tasks_lock:
        now = datetime.now()
        expired_users = []
        for user_id, task in update_tasks.items():
            if task.get('completed_at') and (now - task['completed_at']).total_seconds() > 3600:
                expired_users.append(user_id)
        for user_id in expired_users:
            del update_tasks[user_id]
            print(f"[清理] 已删除用户 {user_id} 的旧任务记录")

# 定期清理旧任务
def start_cleanup_timer():
    def cleanup_loop():
        while True:
            time.sleep(1800)  # 每30分钟清理一次
            cleanup_old_tasks()
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    print("[系统] 后台清理任务已启动")

start_cleanup_timer()
# ============ 异步更新任务管理结束 ============

# 初始化数据库（确保表已创建）
from models.simple_db import get_db
_db = get_db()
print("✅ 数据库初始化完成")

# 启动自动更新服务（如果不在调试模式的重新加载进程中）
if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    try:
        auto_update_service.start()
        print("✅ 自动更新服务已启动")
    except Exception as e:
        print(f"⚠️ 自动更新服务启动失败: {e}")

# 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '请先登录', 'redirect': '/login'}), 401
        return f(*args, **kwargs)
    return decorated_function

# 管理员权限验证装饰器
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '请先登录', 'redirect': '/login'}), 401
        
        # 检查用户是否是管理员
        user_id = SINGLE_USER_ID
        user = system.user_manager.get_user(user_id)
        
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404
        
        # 检查is_admin字段或邮箱白名单
        is_admin = user.get('is_admin', False)
        admin_emails = ['admin@example.com', 'caolongzhi@example.com']
        user_email = user.get('email', '').lower()
        
        if not is_admin and user_email not in [e.lower() for e in admin_emails]:
            return jsonify({'success': False, 'error': '需要管理员权限'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

# 主页 - 展示页面
@app.route('/')
def index():
    """主页 - 如果未登录显示展示页，否则显示文献列表"""
    if True:  # 单用户模式
        return render_template('v2_dashboard.html')
    return render_template('v2_landing.html')

# 关键词设置页面
@app.route('/keywords')
def keywords_page():
    return render_template('v2_keywords.html')

# 登录页面
# 已移除：@app.route('/login')
def login_page():
    if True:  # 单用户模式
        return redirect('/')
    return render_template('v2_login.html')

# 注册页面
# 已移除：@app.route('/register')
def register_page():
    if True:  # 单用户模式
        return redirect('/')
    return render_template('v2_register.html')
    
# API: 用户注册
# 已移除：@app.route('/api/auth/register', methods=['POST'])
def api_register():
    """用户注册API"""
    data = request.json
    
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400
    
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    selected_categories = data.get('categories', [])
    custom_keywords = data.get('custom_keywords', '')
    
    # 验证输入
    if not username or not email or not password:
        return jsonify({'success': False, 'error': '请填写所有必填项'}), 400
    
    if len(password) < 6:
        return jsonify({'success': False, 'error': '密码至少6位'}), 400
    
    # 展开关键词
    keywords = expand_keywords(selected_categories)
    if custom_keywords:
        custom_list = [k.strip() for k in custom_keywords.split(',') if k.strip()]
        keywords.extend(custom_list)
    
    # 去重
    keywords = list(set(keywords))
    
    # 获取安全问题
    security_question = data.get('security_question', '')
    security_answer = data.get('security_answer', '')
    
    # 获取文献源
    selected_sources = data.get('sources', ['pubmed', 'biorxiv', 'medrxiv', 'arxiv'])
    custom_sources = data.get('custom_sources', '')
    
    # 注册用户
    result = system.user_manager.register_user_with_security(
        username, email, password, keywords, 
        security_question if security_question else None,
        security_answer if security_answer else None
    )
    
    if result['success']:
        # 自动登录
        SINGLE_USER_ID = result['user_id']
        session['username'] = result['username']
        
        # 保存文献源偏好
        try:
            prefs = {
                'sources': selected_sources,
                'custom_sources': custom_sources  # 记录但不立即使用
            }
            system.user_manager.update_preferences(result['user_id'], prefs)
        except Exception as e:
            print(f"保存文献源偏好失败: {e}")
        
        # 自动为用户创建默认关键词组
        try:
            if keywords:  # 只有在有关键词时才创建组
                # 获取分类信息以确定图标和颜色
                categories_dict = get_predefined_categories()
                group_icon = '📚'
                group_color = '#5a9a8f'
                group_name = '我的文献'
                
                # 如果有选择分类，使用第一个分类的信息
                if selected_categories and len(selected_categories) > 0:
                    first_category = selected_categories[0]
                    if first_category in categories_dict:
                        group_icon = categories_dict[first_category].get('icon', '📚')
                        group_name = first_category
                    else:
                        group_name = first_category
                
                # 创建关键词组
                keyword_group_manager.create_group(
                    user_id=result['user_id'],
                    name=group_name,
                    keywords=keywords,
                    icon=group_icon,
                    color=group_color,
                    description=f'{group_name} - 注册时自动创建',
                    match_mode='any',
                    min_match_score=0.3
                )
        except Exception as e:
            print(f"创建默认关键词组失败: {e}")
            # 创建组失败不影响注册流程
        
        return jsonify({
            'success': True,
            'user_id': result['user_id'],
            'username': result['username'],
            'keywords': keywords,
            'redirect': '/keywords'
        })
    else:
        return jsonify({'success': False, 'error': result['error']}), 400

# API: 用户登录
# 已移除：@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """用户登录API"""
    data = request.json
    
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400
    
    username_or_email = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username_or_email or not password:
        return jsonify({'success': False, 'error': '请输入用户名/邮箱和密码'}), 400
    
    result = system.user_manager.login(username_or_email, password)
    
    if result['success']:
        SINGLE_USER_ID = result['user']['id']
        session['username'] = result['user']['username']
        
        return jsonify({
            'success': True,
            'user': result['user'],
            'redirect': '/keywords'
        })
    else:
        return jsonify({'success': False, 'error': result['error']}), 401

# API: 根据用户名获取用户公开信息（头像）
@app.route('/api/user/public/<username>')
def api_get_user_public(username):
    """获取用户公开信息（用于登录页面显示头像）"""
    if not username:
        return jsonify({'success': False, 'error': '用户名不能为空'}), 400
    
    # 尝试通过用户名或邮箱查找用户
    user = system.user_manager.get_user_by_username(username)
    if not user:
        user = system.user_manager.get_user_by_email(username)
    
    if user:
        return jsonify({
            'success': True,
            'username': user.get('username'),
            'avatar': user.get('avatar', '')
        })
    else:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

# API: 用户登出
# 已移除：@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """用户登出API"""
    system.user_manager.logout(session.get('session_token', ''))
    session.clear()
    return jsonify({'success': True, 'message': '已登出'})

# 忘记密码页面
# 已移除：@app.route('/forgot-password')
def forgot_password_page():
    """忘记密码页面"""
    if True:  # 单用户模式
        return redirect('/')
    return render_template('v2_forgot_password.html')

# API: 获取安全问题
# 已移除：@app.route('/api/auth/forgot-password', methods=['POST'])
def api_forgot_password():
    """忘记密码 - 获取安全问题"""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400
    
    username = data.get('username', '').strip()
    if not username:
        return jsonify({'success': False, 'error': '请输入用户名或邮箱'}), 400
    
    result = system.user_manager.get_security_question(username)
    return jsonify(result)

# API: 验证安全问题答案
@app.route('/api/auth/verify-security', methods=['POST'])
def api_verify_security():
    """验证安全问题答案"""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400
    
    username = data.get('username', '').strip()
    answer = data.get('answer', '').strip()
    
    if not username or not answer:
        return jsonify({'success': False, 'error': '请填写所有必填项'}), 400
    
    result = system.user_manager.verify_security_answer(username, answer)
    return jsonify(result)

# API: 重置密码
# 已移除：@app.route('/api/auth/reset-password', methods=['POST'])
def api_reset_password():
    """重置密码"""
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400
    
    user_id = data.get('user_id', '')
    new_password = data.get('new_password', '')
    
    if not user_id or not new_password:
        return jsonify({'success': False, 'error': '缺少必要参数'}), 400
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'error': '密码至少6位'}), 400
    
    result = system.user_manager.reset_password(user_id, new_password)
    return jsonify(result)

# API: 获取当前用户信息
@app.route('/api/user/me')
def api_get_user():
    """获取当前用户信息"""
    user_id = SINGLE_USER_ID
    
    # 从数据库获取用户信息（包括头像）
    user = system.user_manager.get_user(user_id)
    if user:
        return jsonify({
            'success': True,
            'user': {
                'id': user_id,
                'username': user.get('username', ''),
                'email': user.get('email', ''),
                'keywords': user.get('keywords', []),
                'preferences': user.get('preferences', {}),
                'avatar': user.get('avatar', ''),
                'stats': system.push_engine.get_user_stats(user_id)
            }
        })
    
    return jsonify({'success': False, 'error': '用户不存在'}), 404

# API: 更新用户关键词
@app.route('/api/user/keywords', methods=['POST'])
def api_update_keywords():
    """更新用户关键词"""
    data = request.json
    user_id = SINGLE_USER_ID
    
    selected_categories = data.get('categories', [])
    custom_keywords = data.get('custom_keywords', '')
    
    # 展开关键词
    keywords = expand_keywords(selected_categories)
    if custom_keywords:
        custom_list = [k.strip() for k in custom_keywords.split(',') if k.strip()]
        keywords.extend(custom_list)
    
    keywords = list(set(keywords))
    
    result = system.user_manager.update_keywords(user_id, keywords)
    
    if result['success']:
        return jsonify({
            'success': True,
            'keywords': keywords,
            'message': '关键词已更新'
        })
    else:
        return jsonify({'success': False, 'error': result['error']}), 400

# ==================== 关键词组管理 API ====================

# API: 获取用户的关键词组列表
@app.route('/api/user/keyword-groups')
def api_get_keyword_groups():
    """获取用户的所有关键词组"""
    user_id = SINGLE_USER_ID
    
    # 检查是否包含已禁用的组
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
    
    # 获取用户的所有组
    groups = keyword_group_manager.get_user_groups(user_id, include_inactive=include_inactive)
    
    return jsonify({
        'success': True,
        'groups': groups
    })

# API: 获取用户关键词组汇总（用于Dashboard）
@app.route('/api/user/keyword-groups/summary')
def api_get_keyword_groups_summary():
    """获取用户关键词组的汇总信息"""
    user_id = SINGLE_USER_ID
    
    summary = keyword_group_manager.get_user_groups_summary(user_id)
    
    return jsonify({
        'success': True,
        'summary': summary
    })

# API: 创建关键词组
@app.route('/api/user/keyword-groups', methods=['POST'])
def api_create_keyword_group():
    """创建新的关键词组"""
    user_id = SINGLE_USER_ID
    data = request.json
    
    # 验证必填字段
    name = data.get('name', '').strip()
    keywords = data.get('keywords', [])
    
    if not name:
        return jsonify({'success': False, 'error': '组名称不能为空'}), 400
    
    if not keywords or len(keywords) == 0:
        return jsonify({'success': False, 'error': '关键词不能为空'}), 400
    
    # 创建组
    result = keyword_group_manager.create_group(
        user_id=user_id,
        name=name,
        keywords=keywords,
        icon=data.get('icon', '🔬'),
        color=data.get('color', '#5a9a8f'),
        description=data.get('description', ''),
        match_mode=data.get('match_mode', 'any'),
        min_match_score=data.get('min_match_score', 0.3)
    )
    
    if result['success']:
        return jsonify({
            'success': True,
            'group_id': result['group_id'],
            'group': result['group'],
            'message': '关键词组创建成功'
        })
    else:
        return jsonify({'success': False, 'error': result['error']}), 400

# API: 更新关键词组
@app.route('/api/user/keyword-groups/<group_id>', methods=['PUT'])
def api_update_keyword_group(group_id):
    """更新关键词组"""
    user_id = SINGLE_USER_ID
    data = request.json
    
    # 检查组是否存在
    group = keyword_group_manager.get_group(user_id, group_id)
    if not group:
        return jsonify({'success': False, 'error': '关键词组不存在'}), 404
    
    # 更新组
    result = keyword_group_manager.update_group(user_id, group_id, data)
    
    if result['success']:
        return jsonify({
            'success': True,
            'group': result['group'],
            'message': '关键词组更新成功'
        })
    else:
        return jsonify({'success': False, 'error': result['error']}), 400

# API: 删除关键词组
@app.route('/api/user/keyword-groups/<group_id>', methods=['DELETE'])
def api_delete_keyword_group(group_id):
    """删除关键词组"""
    user_id = SINGLE_USER_ID
    
    result = keyword_group_manager.delete_group(user_id, group_id)
    
    if result['success']:
        return jsonify({
            'success': True,
            'message': '关键词组已删除'
        })
    else:
        return jsonify({'success': False, 'error': result['error']}), 400

# API: 重新排序关键词组
@app.route('/api/user/keyword-groups/reorder', methods=['PUT'])
def api_reorder_keyword_groups():
    """重新排序关键词组"""
    user_id = SINGLE_USER_ID
    data = request.json
    group_order = data.get('group_order', [])
    
    if not group_order:
        return jsonify({'success': False, 'error': '排序列表不能为空'}), 400
    
    result = keyword_group_manager.reorder_groups(user_id, group_order)
    
    if result['success']:
        return jsonify({
            'success': True,
            'message': '排序已更新'
        })
    else:
        return jsonify({'success': False, 'error': result['error']}), 400

# API: 获取特定关键词组的文献
@app.route('/api/user/keyword-groups/<group_id>/papers')
def api_get_group_papers(group_id):
    """获取特定关键词组的个性化文献"""
    user_id = SINGLE_USER_ID
    
    # 获取组信息
    group = keyword_group_manager.get_group(user_id, group_id)
    if not group:
        return jsonify({'success': False, 'error': '关键词组不存在'}), 404
    
    # 检查组是否激活
    if not group.get('is_active', True):
        return jsonify({
            'success': True,
            'papers': [],
            'message': '该关键词组已禁用'
        })
    
    # 从缓存获取所有文献
    all_papers = list(system.cache.papers_cache.values())
    
    # 获取该组的个性化文献
    papers = system.push_engine.get_personalized_papers_for_group(
        user_id=user_id,
        group=group,
        available_papers=all_papers,
        limit=50
    )
    
    # 获取该组收藏的文献
    saved_hashes = keyword_group_manager.get_saved_papers_in_group(user_id, group_id)
    saved_papers = []
    for h in saved_hashes:
        if h in system.cache.papers_cache:
            saved_papers.append(system.cache.papers_cache[h])
    
    # 更新访问时间
    keyword_group_manager.update_group_access_time(user_id, group_id)
    
    # 标记文献为已浏览（关键词组）
    paper_hashes = [p['hash'] for p in papers]
    for ph in paper_hashes:
        keyword_group_manager.mark_paper_viewed_in_group(user_id, group_id, ph)
    
    return jsonify({
        'success': True,
        'papers': papers,
        'saved_papers': saved_hashes,
        'group': {
            'id': group['id'],
            'name': group['name'],
            'icon': group.get('icon', '🔬'),
            'color': group.get('color', '#5a9a8f')
        }
    })

# API: 在特定组中收藏文献
@app.route('/api/user/keyword-groups/<group_id>/papers/<paper_hash>/save', methods=['POST'])
def api_save_paper_to_group(group_id, paper_hash):
    """在特定关键词组中收藏文献"""
    user_id = SINGLE_USER_ID
    
    # 检查组是否存在
    group = keyword_group_manager.get_group(user_id, group_id)
    if not group:
        return jsonify({'success': False, 'error': '关键词组不存在'}), 404
    
    # 收藏文献
    result = keyword_group_manager.save_paper_to_group(user_id, group_id, paper_hash)
    
    if result['success']:
        return jsonify({
            'success': True,
            'message': '文献已收藏到该组'
        })
    else:
        return jsonify({'success': False, 'error': result['error']}), 400

# API: 在特定组中取消收藏文献
@app.route('/api/user/keyword-groups/<group_id>/papers/<paper_hash>/save', methods=['DELETE'])
def api_unsave_paper_from_group(group_id, paper_hash):
    """在特定关键词组中取消收藏文献"""
    user_id = SINGLE_USER_ID
    
    # 检查组是否存在
    group = keyword_group_manager.get_group(user_id, group_id)
    if not group:
        return jsonify({'success': False, 'error': '关键词组不存在'}), 404
    
    # 取消收藏
    result = keyword_group_manager.unsave_paper_from_group(user_id, group_id, paper_hash)
    
    if result['success']:
        return jsonify({
            'success': True,
            'message': '文献已取消收藏'
        })
    else:
        return jsonify({'success': False, 'error': result['error']}), 400

# API: 获取预设关键词分类
@app.route('/api/keywords/categories')
def api_get_categories():
    """获取预设关键词分类"""
    categories_dict = get_predefined_categories()
    # 将字典转换为数组格式，方便前端使用
    categories_list = []
    for name, data in categories_dict.items():
        categories_list.append({
            'name': name,
            'icon': data.get('icon', '📚'),
            'keywords': data.get('keywords', [])
        })
    return jsonify({
        'success': True,
        'categories': categories_list
    })

# ==================== 用户设置 API ====================

# API: 获取用户设置
@app.route('/api/user/settings')
def api_get_user_settings():
    """获取用户设置"""
    user_id = SINGLE_USER_ID
    
    settings = system.user_manager.get_user_settings(user_id)
    
    if settings is None:
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    
    return jsonify({
        'success': True,
        'settings': settings
    })

# API: 更新用户设置
@app.route('/api/user/settings', methods=['PUT'])
def api_update_user_settings():
    """更新用户设置"""
    user_id = SINGLE_USER_ID
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'})
    
    # 处理API设置
    if 'api_provider' in data or 'api_key' in data or 'api_base_url' in data or 'model' in data:
        api_settings = {
            'api_provider': data.get('api_provider'),
            'api_key': data.get('api_key'),
            'api_base_url': data.get('api_base_url'),
            'model': data.get('model')
        }
        result = system.user_manager.save_user_api_settings(user_id, api_settings)
        if not result['success']:
            return jsonify(result), 400
    
    # 处理更新频率设置
    if 'update_frequency_days' in data or 'max_auto_analyze' in data:
        update_settings = {
            'update_frequency_days': data.get('update_frequency_days'),
            'max_auto_analyze': data.get('max_auto_analyze')
        }
        result = system.user_manager.save_user_update_settings(user_id, update_settings)
        if not result['success']:
            return jsonify(result), 400
    
    # 处理文献源设置
    if 'sources' in data:
        sources = data.get('sources', [])
        if isinstance(sources, list):
            result = system.user_manager.save_user_sources(user_id, sources)
            if not result['success']:
                return jsonify(result), 400
    
    return jsonify({
        'success': True,
        'message': '设置已保存'
    })

# API: 获取系统默认API配置（不包含密钥）
@app.route('/api/user/system-api-info')
def api_get_system_api_info():
    """获取系统默认API配置信息"""
    return jsonify({
        'success': True,
        'has_system_api': bool(os.getenv('DEEPSEEK_API_KEY')),
        'default_provider': 'deepseek',
        'default_model': 'deepseek-chat'
    })

# API: 修改密码
# 已移除：@app.route('/api/user/change-password', methods=['POST'])
def api_change_password():
    """修改用户密码"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400
    
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    if not current_password or not new_password:
        return jsonify({'success': False, 'error': '请提供当前密码和新密码'}), 400
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'error': '新密码至少6位'}), 400
    
    user_id = SINGLE_USER_ID
    
    # 验证当前密码
    user = system.user_manager.get_user(user_id)
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    
    # 检查当前密码是否正确
    from models.user_manager import UserManager
    user_manager = UserManager()
    login_result = user_manager.login(user['username'], current_password)
    
    if not login_result['success']:
        return jsonify({'success': False, 'error': '当前密码不正确'}), 401
    
    # 更新密码
    try:
        result = system.user_manager.reset_password(user_id, new_password)
        if result['success']:
            return jsonify({'success': True, 'message': '密码修改成功'})
        else:
            return jsonify({'success': False, 'error': result.get('error', '修改失败')}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# API: 获取可用的文献源
@app.route('/api/sources/available')
def api_get_available_sources():
    """获取所有可用的文献源"""
    from v1.fetcher import PaperFetcher
    sources = PaperFetcher.get_available_sources()
    return jsonify({
        'success': True,
        'sources': sources
    })

        # API: 获取个性化文献推送
@app.route('/api/papers/personalized')
def api_get_personalized_papers():
    """获取个性化文献列表（V2.6 支持分页）"""
    user_id = SINGLE_USER_ID

    if not user_id:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    # 获取用户信息
    if user_id not in system.user_manager.users:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    user = system.user_manager.users[user_id]
    user_keywords = user.get('keywords', [])

    if not user_keywords:
        return jsonify({
            'success': True,
            'papers': [],
            'saved_papers': [],
            'total': 0,
            'message': '请先设置关键词'
        })

    # V2.6 优化：获取分页参数
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
    except (ValueError, TypeError):
        page = 1
        per_page = 20

    # 限制每页最大数量，防止内存溢出
    per_page = min(per_page, 50)
    page = max(page, 1)

    # 检查是否指定了关键词组
    group_id = request.args.get('group_id')

    if group_id:
        # 使用特定关键词组
        group = keyword_group_manager.get_group(user_id, group_id)
        if not group:
            return jsonify({'success': False, 'error': '关键词组不存在'}), 404

        if not group.get('is_active', True):
            return jsonify({
                'success': True,
                'papers': [],
                'saved_papers': [],
                'total': 0,
                'message': '该关键词组已禁用'
            })

        # 获取该组的关键词
        user_keywords = group.get('keywords', [])

        # 获取该组收藏的文献（只查询一次）
        saved_papers = keyword_group_manager.get_saved_papers_in_group(user_id, group_id)
        saved_set = set(saved_papers)

        # 获取用户的所有收藏（用于"仅收藏"筛选）- 批量获取，减少请求次数
        global_saved_papers = keyword_group_manager.get_all_saved_papers_for_user(user_id)
        global_saved_set = set(global_saved_papers)

        # 从缓存获取所有文献并筛选
        all_papers = list(system.cache.papers_cache.values())
        scored_papers = system.push_engine.get_personalized_papers_for_group(
            user_id=user_id,
            group=group,
            available_papers=all_papers,
            limit=100  # 内部限制最多返回100篇，避免内存溢出
        )

        # 标记是否已在当前组收藏
        for paper in scored_papers:
            paper['is_saved'] = paper['hash'] in saved_set

        # V2.6 优化：服务端分页
        total = len(scored_papers)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_papers = scored_papers[start_idx:end_idx]

        # 只有第一页才标记为已浏览（避免重复标记）
        if page == 1:
            # 标记文献为已浏览（全局）
            paper_hashes = [p['hash'] for p in paginated_papers]
            system.push_engine.mark_papers_as_seen(user_id, paper_hashes)

            # 标记文献为已浏览（关键词组）
            for ph in paper_hashes:
                keyword_group_manager.mark_paper_viewed_in_group(user_id, group_id, ph)

        # 更新访问时间
        keyword_group_manager.update_group_access_time(user_id, group_id)

        # 返回结果（包含分页信息）
        return jsonify({
            'success': True,
            'papers': paginated_papers,
            'saved_papers': saved_papers,
            'global_saved_papers': global_saved_papers,
            'total': total,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'group': {
                'id': group['id'],
                'name': group['name'],
                'icon': group.get('icon', '🔬'),
                'color': group.get('color', '#5a9a8f'),
                'keywords': group.get('keywords', [])
            }
        })
    
    # 如果没有指定组，使用所有激活组的关键词（或向后兼容）
    # 从缓存获取文献
    paper_hashes = system.cache.find_papers_by_keywords(user_keywords)
    papers = system.cache.batch_get_papers(paper_hashes)
    
    # 获取用户收藏的文献（全局）
    saved_papers = []
    if user_id in system.push_engine.user_papers:
        saved_papers = system.push_engine.user_papers[user_id].get('saved_papers', [])
    
    # 为每篇文献计算个性化分数
    scored_papers = []
    for paper in papers:
        paper_copy = paper.copy()
        score = system.push_engine._calculate_paper_score(paper, user_keywords)
        paper_copy['personalized_score'] = score
        paper_copy['hash'] = paper.get('hash', system.cache._get_paper_hash(paper))
        paper_copy['is_saved'] = paper_copy['hash'] in saved_papers
        scored_papers.append(paper_copy)
    
    # 按分数排序
    scored_papers.sort(key=lambda x: x.get('personalized_score', 0), reverse=True)
    
    # 获取分页参数
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
    except:
        page = 1
        per_page = 50
    
    # 分页
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paged_papers = scored_papers[start_idx:end_idx]
    
    # V2.6 优化：服务端分页，只标记当前页的文献为已浏览
    if page == 1:
        paper_hashes = [p['hash'] for p in paged_papers]
        system.push_engine.mark_papers_as_seen(user_id, paper_hashes)

    # V2.6 优化：返回分页后的文献，包含完整分页信息
    total = len(scored_papers)
    return jsonify({
        'success': True,
        'papers': paged_papers,  # V2.6 修复：返回分页后的文献
        'saved_papers': saved_papers,
        'total': total,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page,
            'has_next': end_idx < total,
            'has_prev': page > 1
        }
    })

# API: 保存/取消保存文献
@app.route('/api/papers/save', methods=['POST'])
def api_save_paper():
    """保存文献到关键词组"""
    data = request.json
    user_id = SINGLE_USER_ID
    paper_hash = data.get('paper_hash')
    group_id = data.get('group_id')
    
    if not paper_hash:
        return jsonify({'success': False, 'error': '缺少文献标识'}), 400
    
    if not group_id:
        return jsonify({'success': False, 'error': '缺少关键词组ID'}), 400
    
    # 保存到指定组
    result = keyword_group_manager.save_paper_to_group(user_id, group_id, paper_hash)
    
    if result['success']:
        return jsonify({
            'success': True,
            'message': '文献已收藏到该组'
        })
    else:
        return jsonify(result), 400

@app.route('/api/papers/unsave', methods=['POST'])
def api_unsave_paper():
    """从关键词组取消保存文献"""
    data = request.json
    user_id = SINGLE_USER_ID
    paper_hash = data.get('paper_hash')
    group_id = data.get('group_id')
    
    if not paper_hash:
        return jsonify({'success': False, 'error': '缺少文献标识'}), 400
    
    if not group_id:
        return jsonify({'success': False, 'error': '缺少关键词组ID'}), 400
    
    # 从指定组移除收藏
    result = keyword_group_manager.unsave_paper_from_group(user_id, group_id, paper_hash)
    
    if result['success']:
        return jsonify({
            'success': True,
            'message': '文献已从该组取消收藏'
        })
    else:
        return jsonify(result), 400

# API: 获取文献在哪些组被收藏
@app.route('/api/papers/<paper_hash>/saved-groups', methods=['GET'])
def api_get_paper_saved_groups(paper_hash):
    """获取文献收藏的所有组"""
    user_id = SINGLE_USER_ID
    
    # 获取用户的所有组
    groups = keyword_group_manager.get_user_groups(user_id, include_inactive=False)
    
    # 检查每个组是否收藏了该文献
    saved_groups = []
    for group in groups:
        is_saved = keyword_group_manager.is_paper_saved_in_group(user_id, group['id'], paper_hash)
        if is_saved:
            saved_groups.append({
                'id': group['id'],
                'name': group['name'],
                'icon': group.get('icon', '🔬'),
                'color': group.get('color', '#5a9a8f')
            })
    
    return jsonify({
        'success': True,
        'paper_hash': paper_hash,
        'saved_groups': saved_groups,
        'count': len(saved_groups)
    })

# API: 触发更新
@app.route('/api/trigger-update', methods=['POST'])
@limiter.limit("3 per minute")
def api_trigger_update():
    """手动触发文献更新 - 异步版本"""
    user_id = SINGLE_USER_ID
    
    # 清理旧任务记录
    cleanup_old_tasks()
    
    with update_tasks_lock:
        # 检查是否已有正在运行的任务
        if user_id in update_tasks:
            task = update_tasks[user_id]
            if task['status'] == 'running':
                return jsonify({
                    'success': False,
                    'error': '更新正在进行中，请稍后再试',
                    'status': 'running'
                }), 429
    
    try:
        # 启动后台线程执行更新
        thread = threading.Thread(target=run_update_task, args=(user_id,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': '更新任务已启动，正在后台运行中',
            'status': 'started'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 查询更新状态
@app.route('/api/update-status', methods=['GET'])
def api_get_update_status():
    """获取当前更新任务状态"""
    user_id = SINGLE_USER_ID
    
    with update_tasks_lock:
        if user_id not in update_tasks:
            return jsonify({
                'success': True,
                'status': 'idle',
                'message': '没有正在进行的更新任务'
            })
        
        task = update_tasks[user_id]
        response = {
            'success': True,
            'status': task['status'],
            'message': task.get('message', ''),
            'started_at': task.get('started_at').isoformat() if task.get('started_at') else None,
        }
        
        if task['status'] == 'completed':
            response['result'] = task.get('result', {})
            response['completed_at'] = task.get('completed_at').isoformat() if task.get('completed_at') else None
        elif task['status'] == 'failed':
            response['error'] = task.get('result', {}).get('error', '未知错误')
            response['completed_at'] = task.get('completed_at').isoformat() if task.get('completed_at') else None
        
        return jsonify(response)

# API: 批量更新（管理员用）
# 已移除：@app.route('/api/admin/batch-update', methods=['POST'])
def api_batch_update():
    """批量更新所有用户"""
    # 这里可以添加管理员权限检查
    
    try:
        result = system.run_batch_for_all_users()
        return jsonify({
            'success': True,
            'result': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 获取系统统计
@app.route('/api/stats')
def api_get_stats():
    """获取系统统计"""
    user_id = SINGLE_USER_ID
    
    # 获取该用户所有关键词组的文献总数
    user_groups = keyword_group_manager.get_user_groups(user_id)
    user_keywords = []
    for group in user_groups:
        user_keywords.extend(group.get('keywords', []))
    
    # 如果没有关键词组，从用户 preferences 中获取关键词（向后兼容）
    if not user_keywords:
        user = system.user_manager.get_user(user_id)
        if user and user.get('preferences'):
            user_keywords = user['preferences'].get('keywords', [])
    
    user_keywords = list(set(user_keywords))
    
    # 计算匹配的文献数量
    # 从数据库获取所有文献并实时筛选
    all_papers = system.cache.get_all_papers()
    scored_papers = []
    for paper in all_papers:
        score = system.push_engine._calculate_paper_score(paper, user_keywords)
        if score > 0:
            scored_papers.append(paper)
    user_total_papers = len(scored_papers)
    
    # 添加用户个人统计
    user_stats = system.push_engine.get_user_stats(user_id)
    
    return jsonify({
        'success': True,
        'total_papers': user_total_papers,
        'user': user_stats
    })

# API: 分析待处理文献
@app.route('/api/analyze-pending', methods=['POST'])
def api_analyze_pending():
    """分析待处理的文献"""
    user_id = SINGLE_USER_ID
    
    # 获取用户关键词
    if user_id not in system.user_manager.users:
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    
    user = system.user_manager.users[user_id]
    user_keywords = user.get('keywords', [])
    
    if not user_keywords:
        return jsonify({'success': False, 'error': '用户未设置关键词'})
    
    try:
        # 获取用户专属分析器
        user_analyzer = system.get_user_analyzer(user_id)
        
        # 从缓存获取文献
        paper_hashes = system.cache.find_papers_by_keywords(user_keywords)
        papers = system.cache.batch_get_papers(paper_hashes)
        
        # 分析未分析的文献
        analyzed_count = 0
        for paper in papers:
            if not paper.get('is_analyzed', False):
                # 调用用户专属分析器
                analysis = user_analyzer.analyze_paper(
                    paper.get('title', ''),
                    paper.get('abstract', '')
                )
                
                if analysis and not analysis.get('error'):
                    # 翻译摘要（使用用户专属分析器）
                    abstract = paper.get('abstract', '')
                    abstract_cn = ''
                    if abstract and len(abstract) > 50:
                        abstract_cn = user_analyzer.translate_abstract(abstract)
                    
                    # 确保所有值为字符串（处理元组和嵌套结构）
                    def to_str(v):
                        if v is None:
                            return ''
                        if isinstance(v, (tuple, list)):
                            if len(v) == 0:
                                return ''
                            return to_str(v[0])
                        if isinstance(v, dict):
                            for k in ['main_findings', 'innovations', 'limitations', 'future_directions', 'abstract_cn']:
                                if k in v and v[k]:
                                    return to_str(v[k])
                            return str(v)
                        return str(v) if v else ''
                    
                    # 缓存分析结果
                    paper_hash = paper.get('hash')
                    if paper_hash:
                        system.cache.cache_analysis(
                            paper.get('title', ''),
                            abstract,
                            {
                                'main_findings': to_str(analysis.get('main_findings', '')),
                                'innovations': to_str(analysis.get('innovations', '')),
                                'limitations': to_str(analysis.get('limitations', '')),
                                'future_directions': to_str(analysis.get('future_directions', '')),
                                'abstract_cn': to_str(abstract_cn)
                            },
                            paper_hash=paper_hash
                        )
                    
                    # 同时更新文献缓存中的分析结果
                    paper_hash = paper.get('hash')
                    if paper_hash and paper_hash in system.cache.papers_cache:
                        system.cache.papers_cache[paper_hash]['is_analyzed'] = True
                        system.cache.papers_cache[paper_hash]['main_findings'] = to_str(analysis.get('main_findings', ''))
                        system.cache.papers_cache[paper_hash]['innovations'] = to_str(analysis.get('innovations', ''))
                        system.cache.papers_cache[paper_hash]['limitations'] = to_str(analysis.get('limitations', ''))
                        system.cache.papers_cache[paper_hash]['future_directions'] = to_str(analysis.get('future_directions', ''))
                        system.cache.papers_cache[paper_hash]['abstract_cn'] = to_str(abstract_cn)
                    
                    analyzed_count += 1
        
        return jsonify({
            'success': True,
            'analyzed_count': analyzed_count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 分析单篇文献 (V2.6 异步版本)
@app.route('/api/analyze-paper', methods=['POST'])
@limiter.limit("10 per minute")
def api_analyze_paper():
    """分析单篇文献 - V2.6 支持异步队列"""
    user_id = SINGLE_USER_ID
    data = request.get_json()
    paper_hash = data.get('paper_hash')
    # V2.6: 新增 async 参数，支持同步或异步模式
    async_mode = data.get('async', True)  # 默认异步模式

    if not paper_hash:
        return jsonify({'success': False, 'error': '缺少paper_hash参数'})

    try:
        # 获取文献
        paper = system.cache.get_paper(paper_hash)
        if not paper:
            return jsonify({'success': False, 'error': '文献不存在'})

        title = paper.get('title', '')
        abstract = paper.get('abstract', '')

        if not title or not abstract:
            return jsonify({'success': False, 'error': '文献标题或摘要为空'})

        # 检查是否已有缓存分析
        cached = system.cache.get_cached_analysis(title, abstract)
        if cached:
            # 更新paper表
            paper.update(cached)
            paper['is_analyzed'] = True

            # 保存到数据库
            system.cache.cache_analysis(title, abstract, cached, paper_hash=paper_hash)

            return jsonify({
                'success': True,
                'analyzed': False,
                'message': '已有缓存分析结果',
                'analysis': cached
            })

        # V2.6: 异步分析模式
        if async_mode:
            # 导入异步队列
            from core.async_queue import get_analysis_queue

            task_id = f"analyze_{user_id}_{paper_hash}"

            # 检查是否已在队列中
            queue = get_analysis_queue(max_workers=2)
            status = queue.get_status(task_id)

            if status and status['status'] in ['pending', 'running']:
                return jsonify({
                    'success': True,
                    'async': True,
                    'task_id': task_id,
                    'status': status['status'],
                    'message': '分析任务已在队列中'
                })

            # 获取用户分析器配置
            user_analyzer = system.get_user_analyzer(user_id)

            # 定义分析任务函数
            def do_analysis(analyzer, title, abstract, paper_hash):
                try:
                    # 分析文献
                    analysis = analyzer.analyze_paper(title, abstract)

                    if not analysis or analysis.get('error'):
                        return {'error': analysis.get('error', '分析失败')}

                    # 翻译摘要
                    abstract_cn = ''
                    if abstract and len(abstract) > 50:
                        abstract_cn = analyzer.translate_abstract(abstract)

                    # 确保值为字符串
                    def to_str(v):
                        if v is None:
                            return ''
                        if isinstance(v, (tuple, list)):
                            if len(v) == 0:
                                return ''
                            return to_str(v[0])
                        if isinstance(v, dict):
                            for k in ['main_findings', 'innovations', 'limitations', 'future_directions', 'abstract_cn']:
                                if k in v and v[k]:
                                    return to_str(v[k])
                            return str(v)
                        return str(v) if v else ''

                    result = {
                        'main_findings': to_str(analysis.get('main_findings', '')),
                        'innovations': to_str(analysis.get('innovations', '')),
                        'limitations': to_str(analysis.get('limitations', '')),
                        'future_directions': to_str(analysis.get('future_directions', '')),
                        'abstract_cn': to_str(abstract_cn) if not abstract_cn.startswith('翻译失败') else ''
                    }

                    # 保存到缓存
                    from core.cache_manager import SmartCache
                    cache = SmartCache()
                    cache.cache_analysis(title, abstract, result, paper_hash=paper_hash)

                    return result
                except Exception as e:
                    return {'error': str(e)}

            # 提交异步任务
            result = queue.submit(
                task_id=task_id,
                func=do_analysis,
                args=(user_analyzer, title, abstract, paper_hash),
                priority=5
            )

            if result['success']:
                return jsonify({
                    'success': True,
                    'async': True,
                    'task_id': task_id,
                    'status': 'submitted',
                    'message': '分析任务已提交，请稍后查询结果'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': result.get('error', '提交任务失败')
                })

        else:
            # 同步模式（兼容旧版本）
            user_analyzer = system.get_user_analyzer(user_id)
            analysis = user_analyzer.analyze_paper(title, abstract)

            if not analysis or analysis.get('error'):
                return jsonify({'success': False, 'error': analysis.get('error', '分析失败')})

            # 翻译摘要
            abstract_cn = ''
            if abstract and len(abstract) > 50:
                abstract_cn = user_analyzer.translate_abstract(abstract)

            # 确保值为字符串
            def to_str(v):
                if v is None:
                    return ''
                if isinstance(v, (tuple, list)):
                    if len(v) == 0:
                        return ''
                    return to_str(v[0])
                if isinstance(v, dict):
                    for k in ['main_findings', 'innovations', 'limitations', 'future_directions', 'abstract_cn']:
                        if k in v and v[k]:
                            return to_str(v[k])
                    return str(v)
                return str(v) if v else ''

            result = {
                'main_findings': to_str(analysis.get('main_findings', '')),
                'innovations': to_str(analysis.get('innovations', '')),
                'limitations': to_str(analysis.get('limitations', '')),
                'future_directions': to_str(analysis.get('future_directions', '')),
                'abstract_cn': to_str(abstract_cn) if not abstract_cn.startswith('翻译失败') else ''
            }

            # 保存到缓存和数据库
            system.cache.cache_analysis(title, abstract, result, paper_hash=paper_hash)

            return jsonify({
                'success': True,
                'analyzed': True,
                'analysis': result
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 查询分析任务状态 (V2.6 新增)
@app.route('/api/analyze-status/<task_id>')
def api_analyze_status(task_id):
    """查询异步分析任务状态"""
    try:
        from core.async_queue import get_analysis_queue
        queue = get_analysis_queue()
        status = queue.get_status(task_id)

        if not status:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        return jsonify({
            'success': True,
            'task_id': task_id,
            'status': status['status'],
            'result': status.get('result'),
            'error': status.get('error')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 获取缓存统计 (V2.6 增强版)
# 已移除：@app.route('/api/admin/cache-stats')
def api_get_cache_stats():
    """获取缓存统计（管理员用）- V2.6 包含内存缓存统计"""
    cache_stats = system.cache.get_cache_stats()

    # V2.6: 添加内存缓存统计
    memory_stats = {}
    try:
        from core.memory_cache import get_memory_cache
        memory_stats = get_memory_cache().get_stats()
    except Exception as e:
        memory_stats = {'error': str(e)}

    # V2.6: 添加异步队列统计
    queue_stats = {}
    try:
        from core.async_queue import get_analysis_queue
        queue_stats = get_analysis_queue().get_stats()
    except Exception as e:
        queue_stats = {'error': str(e)}

    return jsonify({
        'success': True,
        'v2_6_optimizations': {
            'sqlite_wal_mode': True,
            'memory_cache': True,
            'pagination': True,
            'async_analysis': True
        },
        'cache': cache_stats,
        'memory_cache': memory_stats,
        'async_queue': queue_stats,
        'analyzer': system.analyzer.get_stats()
    })

# API: 执行系统清理
# 已移除：@app.route('/api/admin/cleanup', methods=['POST'])
def api_cleanup():
    """执行系统清理"""
    try:
        result = system.cleanup()
        return jsonify({
            'success': True,
            'result': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# 管理员验证装饰器
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': '请先登录', 'redirect': '/login'}), 401
        
        user_id = SINGLE_USER_ID
        if not admin_manager.is_admin(user_id):
            return jsonify({'success': False, 'error': '需要管理员权限'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

# 后台管理页面
@app.route('/admin')
def admin_dashboard():
    """后台管理页面"""
    user_id = SINGLE_USER_ID
    if not admin_manager.is_admin(user_id):
        return redirect('/')
    return render_template('v2_admin.html')

# API: 获取管理员面板数据
@app.route('/api/admin/dashboard')
def api_admin_dashboard():
    """获取管理员面板概览数据"""
    try:
        stats = admin_manager.get_system_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 获取所有用户
@app.route('/api/admin/users')
def api_admin_users():
    """获取所有用户列表"""
    try:
        users = admin_manager.get_all_users()
        return jsonify({
            'success': True,
            'users': users
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 获取用户详情
@app.route('/api/admin/users/<user_id>')
def api_admin_user_detail(user_id):
    """获取用户详细信息"""
    try:
        user = admin_manager.get_user_details(user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': '用户不存在'
            }), 404
        
        return jsonify({
            'success': True,
            'user': user
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 更新用户信息
@app.route('/api/admin/users/<user_id>', methods=['PUT'])
def api_admin_update_user(user_id):
    """更新用户信息"""
    try:
        data = request.get_json()
        success = admin_manager.update_user(user_id, data)
        
        if success:
            return jsonify({
                'success': True,
                'message': '用户更新成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '用户更新失败'
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 删除用户
@app.route('/api/admin/users/<user_id>', methods=['DELETE'])
def api_admin_delete_user(user_id):
    """删除用户"""
    try:
        success = admin_manager.delete_user(user_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': '用户已删除'
            })
        else:
            return jsonify({
                'success': False,
                'error': '用户删除失败'
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 重置用户密码
@app.route('/api/admin/users/<user_id>/reset-password', methods=['POST'])
def api_admin_reset_password(user_id):
    """重置用户密码"""
    try:
        data = request.get_json()
        new_password = data.get('new_password')
        
        if not new_password:
            return jsonify({
                'success': False,
                'error': '请提供新密码'
            }), 400
        
        success = admin_manager.reset_user_password(user_id, new_password)
        
        if success:
            return jsonify({
                'success': True,
                'message': '密码重置成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '密码重置失败'
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 获取所有文献
@app.route('/api/admin/papers')
def api_admin_papers():
    """获取所有文献列表"""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        result = admin_manager.get_all_papers(limit=limit, offset=offset)
        return jsonify({
            'success': True,
            **result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 删除文献
@app.route('/api/admin/papers/<paper_hash>', methods=['DELETE'])
def api_admin_delete_paper(paper_hash):
    """删除文献"""
    try:
        success = admin_manager.delete_paper(paper_hash)
        
        if success:
            return jsonify({
                'success': True,
                'message': '文献已删除'
            })
        else:
            return jsonify({
                'success': False,
                'error': '文献删除失败'
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 获取系统配置
@app.route('/api/admin/config')
def api_admin_config():
    """获取系统配置"""
    try:
        config = admin_manager.get_config()
        return jsonify({
            'success': True,
            'config': config
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 更新系统配置
@app.route('/api/admin/config', methods=['PUT'])
def api_admin_update_config():
    """更新系统配置"""
    try:
        data = request.get_json()
        admin_manager.save_config(data)
        
        return jsonify({
            'success': True,
            'message': '配置已更新'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 获取操作日志
@app.route('/api/admin/logs')
def api_admin_logs():
    """获取管理员操作日志"""
    try:
        limit = request.args.get('limit', 100, type=int)
        logs = admin_manager.get_logs(limit=limit)
        
        return jsonify({
            'success': True,
            'logs': logs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# API: 清理缓存
@app.route('/api/admin/clear-cache', methods=['POST'])
def api_admin_clear_cache():
    """清理系统缓存"""
    try:
        data = request.get_json() or {}
        cache_type = data.get('type', 'all')
        
        success = admin_manager.clear_cache(cache_type)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'{cache_type} 缓存已清理'
            })
        else:
            return jsonify({
                'success': False,
                'error': '缓存清理失败'
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============ 自动更新相关 API ============

@app.route('/api/user/auto-update-settings', methods=['GET'])
def api_get_auto_update_settings():
    """获取用户自动更新设置"""
    user_id = SINGLE_USER_ID
    
    try:
        settings = auto_update_service.get_user_schedule_info(user_id)
        settings['recommended_intervals'] = auto_update_service.get_recommended_intervals()
        
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/user/auto-update-settings', methods=['PUT'])
def api_save_auto_update_settings():
    """保存用户自动更新设置"""
    user_id = SINGLE_USER_ID
    data = request.get_json()
    
    if data is None:
        return jsonify({
            'success': False,
            'error': '缺少请求数据'
        }), 400
    
    enabled = data.get('enabled', False)
    interval_days = data.get('interval_days', 2)
    
    try:
        # 更新调度
        auto_update_service.update_user_schedule(user_id, enabled, interval_days)
        
        # 保存到用户 preferences
        system.user_manager.update_preferences(user_id, {
            'auto_update_enabled': enabled,
            'auto_update_interval_days': interval_days
        })
        
        return jsonify({
            'success': True,
            'message': '自动更新设置已保存'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/user/last-update-info')
def api_get_last_update_info():
    """获取用户最后更新信息"""
    user_id = SINGLE_USER_ID
    
    try:
        info = auto_update_service.get_user_schedule_info(user_id)
        
        return jsonify({
            'success': True,
            'last_update_at': info.get('last_update_at'),
            'last_update_result': info.get('last_update_result'),
            'auto_update_enabled': info.get('enabled', False)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/user/all-saved-papers')
def api_get_all_saved_papers():
    """获取用户所有收藏的文献（跨所有组）"""
    user_id = SINGLE_USER_ID
    
    try:
        # 获取所有收藏的文献哈希
        saved_hashes = keyword_group_manager.get_all_saved_papers_for_user(user_id)
        
        if not saved_hashes:
            return jsonify({
                'success': True,
                'papers': [],
                'saved_hashes': [],
                'total': 0
            })
        
        # 从缓存获取文献详情
        papers = []
        missing_hashes = []
        for paper_hash in saved_hashes:
            paper = system.cache.get_cached_paper(paper_hash)
            if paper:
                # 标记为已收藏
                paper_copy = paper.copy()
                paper_copy['is_saved'] = True
                papers.append(paper_copy)
            else:
                # 记录缺失的文献
                missing_hashes.append(paper_hash)
        
        return jsonify({
            'success': True,
            'papers': papers,
            'saved_hashes': saved_hashes,
            'missing_hashes': missing_hashes,
            'total': len(saved_hashes)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# 健康检查
@app.route('/api/health')
def api_health():
    """健康检查"""
    return jsonify({
        'status': 'healthy',
        'version': '2.0',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    host = os.getenv('WEB_HOST', '0.0.0.0')
    port = int(os.getenv('WEB_PORT', '5001'))
    debug = os.getenv('WEB_DEBUG', 'True').lower() == 'true'
    
    print(f"\n{'='*60}")
    print(f"V2 文献推送系统启动")
    print(f"访问地址: http://localhost:{port}")
    print(f"{'='*60}\n")
    
    app.run(host=host, port=port, debug=debug)
