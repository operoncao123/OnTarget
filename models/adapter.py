#!/usr/bin/env python3
"""
数据库适配器 - 让simple_db兼容SQLAlchemy风格API
"""

import json
from datetime import datetime, timedelta
from models.simple_db import get_db

class QueryWrapper:
    """查询包装器，模拟SQLAlchemy查询"""
    
    def __init__(self, table_name):
        self.table_name = table_name
        self.db = get_db()
        self.filters = []
        self._limit = None
        self._order_by = None
    
    def _dict_to_object(self, data):
        """将字典转换为模型对象"""
        if data is None:
            return None
        
        # 表名到模型类的映射（延迟导入避免循环依赖）
        model_map = {
            'users': User,
            'sessions': Session,
            'keyword_groups': KeywordGroup,
            'papers': Paper,
            'search_cache': SearchCache,
            'analysis_cache': AnalysisCache,
            'keyword_index': KeywordIndex,
            'group_saved_papers': GroupSavedPaper,
            'group_viewed_papers': GroupViewedPaper,
            'user_papers': UserPaper,
        }
        
        model_class = model_map.get(self.table_name)
        if model_class:
            # 处理特殊字段
            if 'preferences' in data and isinstance(data['preferences'], str):
                try:
                    data['preferences'] = json.loads(data['preferences'])
                except:
                    data['preferences'] = {}
            if 'keywords' in data and isinstance(data['keywords'], str):
                try:
                    data['keywords'] = json.loads(data['keywords'])
                except:
                    data['keywords'] = []
            if 'authors' in data and isinstance(data['authors'], str):
                try:
                    data['authors'] = json.loads(data['authors'])
                except:
                    data['authors'] = []
            # 处理布尔值
            for field in ['is_active', 'is_admin', 'is_analyzed', 'is_saved', 'is_viewed']:
                if field in data:
                    data[field] = bool(data[field])
            return model_class(**data)
        return data
    
    def filter(self, condition):
        """添加过滤条件"""
        self.filters.append(condition)
        return self
    
    def filter_by(self, **kwargs):
        """通过关键字过滤"""
        # 累积过滤条件，而不是覆盖
        if not hasattr(self, '_where_clauses'):
            self._where_clauses = []
            self._where_params = []
        
        for key, value in kwargs.items():
            self._where_clauses.append(f"{key} = ?")
            self._where_params.append(value)
        
        # 构建完整查询
        query = f"SELECT * FROM {self.table_name}"
        if self._where_clauses:
            query += " WHERE " + " AND ".join(self._where_clauses)
        
        self._query = query
        self._params = self._where_params
        return self
    
    def first(self):
        """获取第一条记录"""
        if hasattr(self, '_query'):
            result = self.db.fetchone(self._query, self._params)
            return self._dict_to_object(result)
        return None
    
    def all(self):
        """获取所有记录"""
        if hasattr(self, '_query'):
            results = self.db.fetchall(self._query, self._params)
        else:
            results = self.db.fetchall(f"SELECT * FROM {self.table_name}")
        return [self._dict_to_object(r) for r in results]
    
    def count(self):
        """获取记录数"""
        if hasattr(self, '_where_clauses') and self._where_clauses:
            # 使用过滤条件
            query = f"SELECT COUNT(*) as count FROM {self.table_name} WHERE " + " AND ".join(self._where_clauses)
            result = self.db.fetchone(query, self._where_params)
        else:
            # 无过滤条件
            result = self.db.fetchone(f"SELECT COUNT(*) as count FROM {self.table_name}")
        return result['count'] if result else 0
    
    def order_by(self, column):
        """排序"""
        self._order_by = column
        return self
    
    def limit(self, n):
        """限制结果数"""
        self._limit = n
        return self

def get_db_session(db_path=None):
    """获取数据库会话（兼容函数）"""
    return DBSession()

class DBSession:
    """数据库会话类，模拟SQLAlchemy Session"""
    
    def __init__(self):
        self.db = get_db()
        self._pending = []
    
    def query(self, model_class):
        """创建查询"""
        if isinstance(model_class, str):
            table_name = model_class
        elif hasattr(model_class, '__tablename__'):
            table_name = model_class.__tablename__
        elif model_class.__name__ == 'User':
            table_name = 'users'
        elif model_class.__name__ == 'Session':
            table_name = 'sessions'
        elif model_class.__name__ == 'KeywordGroup':
            table_name = 'keyword_groups'
        elif model_class.__name__ == 'Paper':
            table_name = 'papers'
        elif model_class.__name__ == 'SearchCache':
            table_name = 'search_cache'
        elif model_class.__name__ == 'AnalysisCache':
            table_name = 'analysis_cache'
        elif model_class.__name__ == 'KeywordIndex':
            table_name = 'keyword_index'
        elif model_class.__name__ == 'GroupSavedPaper':
            table_name = 'group_saved_papers'
        elif model_class.__name__ == 'GroupViewedPaper':
            table_name = 'group_viewed_papers'
        elif model_class.__name__ == 'UserPaper':
            table_name = 'user_papers'
        else:
            table_name = model_class.__name__.lower() + 's'
        
        return QueryWrapper(table_name)
    
    def add(self, obj):
        """添加对象"""
        self._pending.append(obj)
    
    def commit(self):
        """提交事务"""
        # 保存待处理的对象
        for obj in self._pending:
            if hasattr(obj, 'save'):
                obj.save()
        self._pending = []
    
    def flush(self):
        """刷新会话（立即保存所有修改）"""
        self.commit()
    
    def rollback(self):
        """回滚事务"""
        self._pending = []
    
    def close(self):
        """关闭会话"""
        self._pending = []
    
    def delete(self, obj):
        """删除对象"""
        from models.simple_db import get_db
        db = get_db()
        
        # 根据对象类型确定表名和ID字段
        if hasattr(obj, '__tablename__'):
            table_name = obj.__tablename__
        elif obj.__class__.__name__ == 'User':
            table_name = 'users'
        elif obj.__class__.__name__ == 'Session':
            table_name = 'sessions'
        elif obj.__class__.__name__ == 'KeywordGroup':
            table_name = 'keyword_groups'
        elif obj.__class__.__name__ == 'Paper':
            table_name = 'papers'
        elif obj.__class__.__name__ == 'SearchCache':
            table_name = 'search_cache'
        elif obj.__class__.__name__ == 'AnalysisCache':
            table_name = 'analysis_cache'
        elif obj.__class__.__name__ == 'KeywordIndex':
            table_name = 'keyword_index'
        elif obj.__class__.__name__ == 'GroupSavedPaper':
            table_name = 'group_saved_papers'
        elif obj.__class__.__name__ == 'GroupViewedPaper':
            table_name = 'group_viewed_papers'
        elif obj.__class__.__name__ == 'UserPaper':
            table_name = 'user_papers'
        else:
            table_name = obj.__class__.__name__.lower() + 's'
        
        # 执行删除
        obj_id = getattr(obj, 'id', None)
        if obj_id:
            db.execute(f"DELETE FROM {table_name} WHERE id = ?", (obj_id,))

# 模型类定义（简化版）
class User:
    __tablename__ = 'users'
    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.username = kwargs.get('username')
        self.email = kwargs.get('email')
        self.password_hash = kwargs.get('password_hash')
        self.password_salt = kwargs.get('password_salt')
        self.security_question = kwargs.get('security_question', '')
        self.security_answer_hash = kwargs.get('security_answer_hash', '')
        self.security_answer_salt = kwargs.get('security_answer_salt', '')
        self.is_active = kwargs.get('is_active', True)
        self.is_admin = kwargs.get('is_admin', False)
        self.created_at = kwargs.get('created_at')
        self.last_login = kwargs.get('last_login')
        self.preferences = kwargs.get('preferences', {})
        self.avatar = kwargs.get('avatar', '')
    
    def save(self):
        """保存到数据库"""
        db = get_db()
        preferences_json = json.dumps(self.preferences) if isinstance(self.preferences, dict) else self.preferences
        
        # 处理 last_login 字段
        last_login_val = self.last_login
        if isinstance(last_login_val, str):
            last_login_val = last_login_val
        elif hasattr(last_login_val, 'isoformat'):
            last_login_val = last_login_val.isoformat()
        else:
            last_login_val = None
        
        # 处理 created_at 字段
        created_at_val = self.created_at
        if isinstance(created_at_val, str):
            created_at_val = created_at_val
        elif hasattr(created_at_val, 'isoformat'):
            created_at_val = created_at_val.isoformat()
        else:
            created_at_val = datetime.now().isoformat()
        
        # 检查是否存在
        existing = db.fetchone("SELECT id FROM users WHERE id = ?", (self.id,))
        
        if existing:
            # 更新
            db.execute('''
                UPDATE users SET 
                    username = ?, email = ?, password_hash = ?, password_salt = ?,
                    security_question = ?, security_answer_hash = ?, security_answer_salt = ?,
                    is_active = ?, is_admin = ?, last_login = ?, preferences = ?, avatar = ?
                WHERE id = ?
            ''', (self.username, self.email, self.password_hash, self.password_salt,
                  self.security_question, self.security_answer_hash, self.security_answer_salt,
                  int(self.is_active), int(self.is_admin), 
                  last_login_val,
                  preferences_json, self.avatar or '', self.id))
        else:
            # 插入
            db.execute('''
                INSERT INTO users (id, username, email, password_hash, password_salt,
                    security_question, security_answer_hash, security_answer_salt,
                    is_active, is_admin, created_at, last_login, preferences, avatar)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (self.id, self.username, self.email, self.password_hash, self.password_salt,
                  self.security_question, self.security_answer_hash, self.security_answer_salt,
                  int(self.is_active), int(self.is_admin),
                  created_at_val,
                  last_login_val,
                  preferences_json, self.avatar or ''))

class Session:
    __tablename__ = 'sessions'
    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.user_id = kwargs.get('user_id')
        self.created_at = kwargs.get('created_at')
        self.expires_at = kwargs.get('expires_at')
        self.ip_address = kwargs.get('ip_address')
        self.user_agent = kwargs.get('user_agent')

class KeywordGroup:
    __tablename__ = 'keyword_groups'
    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.user_id = kwargs.get('user_id')
        self.name = kwargs.get('name')
        self.description = kwargs.get('description', '')
        self.icon = kwargs.get('icon', '🔬')
        self.color = kwargs.get('color', '#5a9a8f')
        self.keywords = kwargs.get('keywords', [])
        self.match_mode = kwargs.get('match_mode', 'any')
        self.min_match_score = kwargs.get('min_match_score', 0.3)
        self.is_active = kwargs.get('is_active', True)
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')
    
    def save(self):
        """保存到数据库"""
        from models.simple_db import get_db
        import json
        db = get_db()
        
        keywords_json = json.dumps(self.keywords) if isinstance(self.keywords, list) else self.keywords
        
        existing = db.fetchone("SELECT id FROM keyword_groups WHERE id = ?", (self.id,))
        
        if existing:
            # 更新
            db.execute('''
                UPDATE keyword_groups SET
                    name = ?, description = ?, icon = ?, color = ?, keywords = ?,
                    match_mode = ?, min_match_score = ?, is_active = ?, updated_at = ?
                WHERE id = ?
            ''', (self.name, self.description, self.icon, self.color, keywords_json,
                  self.match_mode, self.min_match_score, int(self.is_active),
                  self.updated_at.isoformat() if self.updated_at else datetime.now().isoformat(),
                  self.id))
        else:
            # 插入
            db.execute('''
                INSERT INTO keyword_groups (id, user_id, name, description, icon, color, keywords,
                    match_mode, min_match_score, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (self.id, self.user_id, self.name, self.description, self.icon, self.color, keywords_json,
                  self.match_mode, self.min_match_score, int(self.is_active),
                  self.created_at.isoformat() if self.created_at else datetime.now().isoformat(),
                  self.updated_at.isoformat() if self.updated_at else datetime.now().isoformat()))

class Paper:
    __tablename__ = 'papers'
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

class SearchCache:
    __tablename__ = 'search_cache'
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

class AnalysisCache:
    __tablename__ = 'analysis_cache'
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

class KeywordIndex:
    __tablename__ = 'keyword_index'
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

class GroupSavedPaper:
    __tablename__ = 'group_saved_papers'
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def save(self):
        """保存到数据库"""
        from models.simple_db import get_db
        db = get_db()
        
        # 获取数据并确保 saved_at 是字符串
        group_id = getattr(self, 'group_id', None)
        paper_id = getattr(self, 'paper_id', None)
        saved_at = getattr(self, 'saved_at', None)
        
        # 转换 datetime 对象为字符串
        if hasattr(saved_at, 'isoformat'):
            saved_at = saved_at.isoformat()
        
        # 检查是否已存在
        check = db.fetchone(
            'SELECT id FROM group_saved_papers WHERE group_id = ? AND paper_id = ?',
            (group_id, paper_id)
        )
        if not check:
            db.execute(
                'INSERT INTO group_saved_papers (group_id, paper_id, saved_at) VALUES (?, ?, ?)',
                (group_id, paper_id, saved_at)
            )

class GroupViewedPaper:
    __tablename__ = 'group_viewed_papers'
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def save(self):
        """保存到数据库"""
        from models.simple_db import get_db
        db = get_db()
        data = {
            'group_id': getattr(self, 'group_id', None),
            'paper_id': getattr(self, 'paper_id', None),
            'viewed_at': getattr(self, 'viewed_at', None)
        }
        # 检查是否已存在
        check = db.fetchone(
            'SELECT id FROM group_viewed_papers WHERE group_id = ? AND paper_id = ?',
            (data['group_id'], data['paper_id'])
        )
        if not check:
            db.execute(
                'INSERT INTO group_viewed_papers (group_id, paper_id, viewed_at) VALUES (?, ?, ?)',
                (data['group_id'], data['paper_id'], data['viewed_at'])
            )

class UserPaper:
    __tablename__ = 'user_papers'
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

# 兼容函数
def get_db_manager(db_path=None):
    """获取数据库管理器（兼容函数）"""
    return get_db()
