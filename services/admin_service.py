#!/usr/bin/env python3
"""
后台管理系统 - 提供管理员功能
包括：用户管理、系统监控、文献管理、系统配置
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

class AdminManager:
    """后台管理器 - 处理管理员功能"""
    
    def __init__(self, data_dir='data', cache=None, user_manager=None, analyzer=None):
        self.data_dir = data_dir
        self.cache = cache
        self.user_manager = user_manager
        self.analyzer = analyzer
        self.logs_file = os.path.join(data_dir, 'admin_logs.json')
        self.config_file = os.path.join(data_dir, 'admin_config.json')
        self._ensure_data_dir()
        self.config = self._load_config()
    
    def _ensure_data_dir(self):
        """确保数据目录存在"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def _load_config(self) -> Dict:
        """加载管理员配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return self._default_config()
        return self._default_config()
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            'update_interval_days': 2,
            'max_papers_per_user': 100,
            'allow_registration': True,
            'maintenance_mode': False,
            'last_updated': datetime.now().isoformat()
        }
    
    def save_config(self, config: Dict):
        """保存配置"""
        config['last_updated'] = datetime.now().isoformat()
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        self.config = config
    
    def get_config(self) -> Dict:
        """获取当前配置"""
        return self.config
    
    def is_admin(self, user_id: str) -> bool:
        """检查用户是否为管理员"""
        if not user_id or not self.user_manager:
            return False
        
        user = self.user_manager.users.get(user_id)
        if not user:
            return False
        
        # 检查是否为管理员（通过邮箱或特殊标记）
        admin_emails = ['admin@example.com', 'caolongzhi@example.com']
        return user.get('email') in admin_emails or user.get('is_admin', False)
    
    def get_all_users(self) -> List[Dict]:
        """获取所有用户信息（管理员用）"""
        if not self.user_manager:
            return []
        
        # 从数据库获取所有用户
        db = self.user_manager._get_session()
        try:
            from models.adapter import User
            users = db.query(User).all()
            
            users_list = []
            for user in users:
                keywords = user.preferences.get('keywords', []) if isinstance(user.preferences, dict) else []
                sources = user.preferences.get('sources', []) if isinstance(user.preferences, dict) else []
                custom_sources = user.preferences.get('custom_sources', '') if isinstance(user.preferences, dict) else ''
                user_info = {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'created_at': user.created_at.isoformat() if hasattr(user.created_at, 'isoformat') else user.created_at,
                    'last_login': user.last_login.isoformat() if hasattr(user.last_login, 'isoformat') else user.last_login,
                    'keywords_count': len(keywords),
                    'sources': sources,
                    'custom_sources': custom_sources,
                    'is_admin': user.is_admin,
                    'avatar': user.avatar or ''
                }
                users_list.append(user_info)
            
            # 按创建时间排序
            users_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            return users_list
        finally:
            db.close()
    
    def get_user_details(self, user_id: str) -> Optional[Dict]:
        """获取用户详细信息"""
        if not self.user_manager:
            return None
        
        user_data = self.user_manager.users.get(user_id)
        if not user_data:
            return None
        
        prefs = user_data.get('preferences', {})
        if isinstance(prefs, str):
            try:
                prefs = json.loads(prefs)
            except:
                prefs = {}
        
        return {
            'id': user_id,
            'username': user_data.get('username', ''),
            'email': user_data.get('email', ''),
            'keywords': user_data.get('keywords', []),
            'sources': prefs.get('sources', []),
            'custom_sources': prefs.get('custom_sources', ''),
            'created_at': user_data.get('created_at', ''),
            'last_login': user_data.get('last_login', ''),
            'is_admin': user_data.get('is_admin', False)
        }
    
    def update_user(self, user_id: str, updates: Dict) -> bool:
        """更新用户信息"""
        if not self.user_manager:
            return False
        
        if user_id not in self.user_manager.users:
            return False
        
        user = self.user_manager.users[user_id]
        
        # 允许更新的字段
        allowed_fields = ['username', 'email', 'keywords', 'is_admin']
        for field in allowed_fields:
            if field in updates:
                user[field] = updates[field]
        
        user['updated_at'] = datetime.now().isoformat()
        self.user_manager._save_users()
        
        # 记录日志
        self._log_action('update_user', {'user_id': user_id, 'updates': updates})
        return True
    
    def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        if not self.user_manager:
            return False
        
        if user_id not in self.user_manager.users:
            return False
        
        # 删除用户数据
        del self.user_manager.users[user_id]
        self.user_manager._save_users()
        
        # 清理用户相关数据
        self._cleanup_user_data(user_id)
        
        # 记录日志
        self._log_action('delete_user', {'user_id': user_id})
        return True
    
    def reset_user_password(self, user_id: str, new_password: str) -> bool:
        """重置用户密码"""
        if not self.user_manager:
            return False
        
        if user_id not in self.user_manager.users:
            return False
        
        # 使用UserManager的密码重置功能
        return self.user_manager.reset_password(user_id, new_password)
    
    def _cleanup_user_data(self, user_id: str):
        """清理用户相关数据"""
        # 清理用户会话
        sessions_to_remove = []
        for sid, session in self.user_manager.sessions.items():
            if session.get('user_id') == user_id:
                sessions_to_remove.append(sid)
        
        for sid in sessions_to_remove:
            del self.user_manager.sessions[sid]
        
        self.user_manager._save_sessions()
        
        # 清理用户文献数据
        user_papers_file = os.path.join(self.data_dir, 'user_papers.json')
        if os.path.exists(user_papers_file):
            try:
                with open(user_papers_file, 'r', encoding='utf-8') as f:
                    user_papers = json.load(f)
                
                if user_id in user_papers:
                    del user_papers[user_id]
                
                with open(user_papers_file, 'w', encoding='utf-8') as f:
                    json.dump(user_papers, f, ensure_ascii=False, indent=2)
            except:
                pass
    
    def get_system_stats(self) -> Dict:
        """获取系统统计信息"""
        stats = {
            'users': self._get_user_stats(),
            'cache': self._get_cache_stats(),
            'api': self._get_api_stats(),
            'system': self._get_system_info()
        }
        return stats
    
    def _get_user_stats(self) -> Dict:
        """获取用户统计"""
        if not self.user_manager:
            return {}
        
        users = self.user_manager.users
        today_str = datetime.now().strftime('%Y-%m-%d')
        week_ago = (datetime.now() - __import__('datetime').timedelta(days=7)).isoformat()
        
        return {
            'total_users': len(users),
            'total_admins': sum(1 for u in users.values() if u.get('is_admin', False)),
            'active_today': sum(1 for u in users.values() 
                              if (u.get('last_login') or '').startswith(today_str)),
            'active_this_week': sum(1 for u in users.values() 
                                   if (u.get('last_login') or '') >= week_ago)
        }
    
    def _get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        if not self.cache:
            return {}
        
        return self.cache.get_cache_stats()
    
    def _get_api_stats(self) -> Dict:
        """获取API调用统计"""
        if not self.analyzer:
            return {}
        
        return self.analyzer.get_stats()
    
    def _get_system_info(self) -> Dict:
        """获取系统信息"""
        import psutil
        
        return {
            'disk_usage': {
                'total_gb': round(psutil.disk_usage('/').total / (1024**3), 2),
                'used_gb': round(psutil.disk_usage('/').used / (1024**3), 2),
                'free_gb': round(psutil.disk_usage('/').free / (1024**3), 2),
                'percent': psutil.disk_usage('/').percent
            },
            'memory_usage': {
                'total_gb': round(psutil.virtual_memory().total / (1024**3), 2),
                'used_gb': round(psutil.virtual_memory().used / (1024**3), 2),
                'percent': psutil.virtual_memory().percent
            },
            'cpu_percent': psutil.cpu_percent(interval=1),
            'uptime': self._get_uptime()
        }
    
    def _get_uptime(self) -> str:
        """获取系统运行时间"""
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                hours = int(uptime_seconds // 3600)
                minutes = int((uptime_seconds % 3600) // 60)
                return f"{hours}小时{minutes}分钟"
        except:
            return "未知"
    
    def get_all_papers(self, limit: int = 100, offset: int = 0) -> Dict:
        """获取所有文献（管理员用）"""
        if not self.cache:
            return {'papers': [], 'total': 0}
        
        all_papers = []
        for paper_hash, paper in self.cache.papers_cache.items():
            paper_info = {
                'hash': paper_hash,
                'title': paper.get('title', '')[:100] + '...' if len(paper.get('title', '')) > 100 else paper.get('title', ''),
                'source': paper.get('source', 'unknown'),
                'journal': paper.get('journal', ''),
                'publication_date': paper.get('publication_date', ''),
                'is_analyzed': paper.get('is_analyzed', False),
                'keywords_score': paper.get('keywords_score', 0),
                'impact_factor': paper.get('impact_factor', 0)
            }
            all_papers.append(paper_info)
        
        # 按日期排序
        all_papers.sort(key=lambda x: x.get('publication_date', ''), reverse=True)
        
        total = len(all_papers)
        
        # 分页
        papers_page = all_papers[offset:offset+limit]
        
        return {
            'papers': papers_page,
            'total': total,
            'limit': limit,
            'offset': offset
        }
    
    def delete_paper(self, paper_hash: str) -> bool:
        """删除文献"""
        if not self.cache:
            return False
        
        if paper_hash not in self.cache.papers_cache:
            return False
        
        # 删除文献
        del self.cache.papers_cache[paper_hash]
        
        # 更新缓存文件
        self.cache._save_cache(
            self.cache.papers_cache_file, 
            self.cache.papers_cache
        )
        
        # 从关键词索引中移除
        for keyword_data in self.cache.keywords_index.values():
            if paper_hash in keyword_data.get('papers', []):
                keyword_data['papers'].remove(paper_hash)
        
        self.cache._save_cache(
            self.cache.keywords_index_file,
            self.cache.keywords_index
        )
        
        # 记录日志
        self._log_action('delete_paper', {'paper_hash': paper_hash})
        return True
    
    def _log_action(self, action: str, details: Dict):
        """记录管理员操作日志"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'details': details
        }
        
        logs = []
        if os.path.exists(self.logs_file):
            try:
                with open(self.logs_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            except:
                logs = []
        
        logs.append(log_entry)
        
        # 只保留最近1000条日志
        if len(logs) > 1000:
            logs = logs[-1000:]
        
        with open(self.logs_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    
    def get_logs(self, limit: int = 100) -> List[Dict]:
        """获取操作日志"""
        if not os.path.exists(self.logs_file):
            return []
        
        try:
            with open(self.logs_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            return logs[-limit:]
        except:
            return []
    
    def clear_cache(self, cache_type: str = 'all') -> bool:
        """清理缓存"""
        if not self.cache:
            return False
        
        if cache_type == 'all':
            self.cache.papers_cache = {}
            self.cache.analysis_cache = {}
            self.cache.search_cache = {}
            self.cache.keywords_index = {}
        elif cache_type == 'papers':
            self.cache.papers_cache = {}
        elif cache_type == 'analysis':
            self.cache.analysis_cache = {}
        elif cache_type == 'search':
            self.cache.search_cache = {}
        
        # 保存空缓存
        self.cache._save_cache(self.cache.papers_cache_file, self.cache.papers_cache)
        self.cache._save_cache(self.cache.analysis_cache_file, self.cache.analysis_cache)
        self.cache._save_cache(self.cache.search_cache_file, self.cache.search_cache)
        self.cache._save_cache(self.cache.keywords_index_file, self.cache.keywords_index)
        
        # 记录日志
        self._log_action('clear_cache', {'cache_type': cache_type})
        return True
