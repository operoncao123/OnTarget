#!/usr/bin/env python3
"""
用户管理系统 - SQLite版本 (V2.3)
使用SQLAlchemy ORM替代JSON文件存储
"""

import hashlib
import secrets
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from models.adapter import get_db_session, User, Session
from utils.encryption import get_encryption_manager

AVATAR_EMOJIS = ['🐶', '🐱', '🐭', '🐹', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯', '🦁', '🐮', '🐷', '🐸', '🐵', '🐔', '🐧', '🐦', '🐤', '🦆', '🦅', '🦉', '🦇', '🐺', '🐗', '🐴', '🦄', '🐝', '🐛', '🦋', '🐌', '🐞', '🐜', '🦟', '🦗', '🕷', '🦂', '🐢', '🐍', '🦎', '🦖', '🦕', '🐙', '🦑', '🦐', '🦞', '🦀', '🐡', '🐠', '🐟', '🐬', '🐳', '🦈', '🐊', '🐅', '🐆', '🦓', '🦍', '🦧', '🐘', '🦛', '🦏', '🐪', '🐫', '🦒', '🦘', '🦬', '🐃', '🐂', '🐄', '🐎', '🐖', '🐏', '🐑', '🦙', '🐐', '🦌', '🐕', '🐩', '🦮', '🐕‍🦺', '🐈', '🐓', '🦃', '🦚', '🦜', '🦢', '🦩', '🕊', '🐇', '🦝', '🦨', '🦡', '🦫', '🦦', '🦥', '🐁', '🐀', '🐿', '🦔']

def generate_avatar(username: str) -> str:
    """生成用户头像 - 使用Emoji（本地，无需网络）"""
    # 根据用户名hash选择固定的emoji，保证同一用户名显示相同头像
    hash_val = int(hashlib.md5(username.encode()).hexdigest(), 16)
    emoji = AVATAR_EMOJIS[hash_val % len(AVATAR_EMOJIS)]
    # 返回特殊格式，前端渲染为emoji
    return f"emoji:{emoji}"

class UserManager:
    """用户管理器 - 处理用户注册、登录和个性化设置"""
    
    def __init__(self, db_path='data/literature.db'):
        self.db_path = db_path
    
    def _get_session(self):
        """获取数据库会话"""
        return get_db_session(self.db_path)
    
    def _hash_password(self, password: str, salt: str = None) -> tuple:
        """哈希密码"""
        if salt is None:
            salt = secrets.token_hex(16)
        pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return pwdhash.hex(), salt
    
    def _verify_password(self, password: str, hashed: str, salt: str) -> bool:
        """验证密码"""
        pwdhash, _ = self._hash_password(password, salt)
        return pwdhash == hashed
    
    def register_user(self, username: str, email: str, password: str, 
                     keywords: List[str] = None) -> Dict:
        """
        注册用户（兼容旧版，不带安全问题）
        """
        return self.register_user_with_security(username, email, password, keywords, None, None)
    
    def register_user_with_security(self, username: str, email: str, password: str, 
                     keywords: List[str] = None, security_question: str = None, 
                     security_answer: str = None) -> Dict:
        """
        注册用户（带安全问题）
        """
        db = self._get_session()
        try:
            # 检查用户名是否已存在
            existing_user = db.query(User).filter_by(username=username.lower()).first()
            if not existing_user:
                existing_user = db.query(User).filter_by(email=email.lower()).first()
            
            if existing_user:
                if existing_user.username.lower() == username.lower():
                    return {'success': False, 'error': '用户名已存在'}
                else:
                    return {'success': False, 'error': '邮箱已被注册'}
            
            # 创建新用户
            user_id = f"user_{int(datetime.now().timestamp())}_{secrets.token_hex(4)}"
            pwd_hash, salt = self._hash_password(password)
            avatar_url = generate_avatar(username)
            
            # 处理安全问题
            security_answer_hash = None
            security_answer_salt = None
            if security_question and security_answer:
                security_answer_hash, security_answer_salt = self._hash_password(security_answer)
            
            new_user = User(
                id=user_id,
                username=username,
                email=email,
                password_hash=pwd_hash,
                password_salt=salt,
                security_question=security_question,
                security_answer_hash=security_answer_hash,
                security_answer_salt=security_answer_salt,
                is_active=True,
                is_admin=False,
                created_at=datetime.now(),
                last_login=None,
                preferences={
                    'min_score_threshold': 0.3,
                    'paper_types': ['research', 'review'],
                    'sources': ['pubmed', 'biorxiv', 'medrxiv'],
                    'daily_limit': 20,
                    'email_notifications': True,
                    'keywords': keywords or []  # 存储在preferences中
                },
                avatar=avatar_url
            )
            
            db.add(new_user)
            db.commit()
            
            return {
                'success': True,
                'user_id': user_id,
                'username': username,
                'message': '注册成功'
            }
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'注册失败: {str(e)}'}
        finally:
            db.close()
    
    def get_security_question(self, username_or_email: str) -> Dict:
        """获取用户的安全问题"""
        db = self._get_session()
        try:
            # 查找用户
            user = db.query(User).filter_by(username=username_or_email).first()
            if not user:
                user = db.query(User).filter_by(email=username_or_email).first()
            
            if not user:
                return {'success': False, 'error': '用户不存在'}
            
            if not user.security_question:
                return {'success': False, 'error': '该用户未设置安全问题'}
            
            return {
                'success': True,
                'question': user.security_question,
                'username': user.username
            }
        finally:
            db.close()
    
    def verify_security_answer(self, username_or_email: str, answer: str) -> Dict:
        """验证安全问题答案"""
        db = self._get_session()
        try:
            # 查找用户
            user = db.query(User).filter_by(username=username_or_email).first()
            if not user:
                user = db.query(User).filter_by(email=username_or_email).first()
            
            if not user:
                return {'success': False, 'error': '用户不存在'}
            
            if not user.security_answer_hash:
                return {'success': False, 'error': '该用户未设置安全问题'}
            
            # 验证答案
            if self._verify_password(answer, user.security_answer_hash, user.security_answer_salt):
                return {
                    'success': True,
                    'user_id': user.id,
                    'username': user.username
                }
            else:
                return {'success': False, 'error': '答案不正确'}
        finally:
            db.close()
    
    def reset_password(self, user_id: str, new_password: str) -> Dict:
        """重置用户密码"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return {'success': False, 'error': '用户不存在'}
            
            # 生成新密码哈希
            pwd_hash, salt = self._hash_password(new_password)
            user.password_hash = pwd_hash
            user.password_salt = salt
            
            db.commit()
            return {'success': True, 'message': '密码重置成功'}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'重置失败: {str(e)}'}
        finally:
            db.close()
    
    def login(self, username_or_email: str, password: str, ip_address: str = None, 
              user_agent: str = None) -> Dict:
        """
        用户登录
        """
        db = self._get_session()
        try:
            # 查找用户（支持用户名或邮箱）
            # 先尝试用用户名查找
            user = db.query(User).filter_by(username=username_or_email).first()
            # 如果没找到，再用邮箱查找
            if not user:
                user = db.query(User).filter_by(email=username_or_email).first()
            
            if not user:
                return {'success': False, 'error': '用户不存在'}
            
            if not user.is_active:
                return {'success': False, 'error': '账号已被禁用'}
            
            # 验证密码
            if not self._verify_password(password, user.password_hash, user.password_salt):
                return {'success': False, 'error': '密码错误'}
            
            # 更新最后登录时间
            user.last_login = datetime.now()
            
            # 创建会话
            session_token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(days=7)
            
            new_session = Session(
                id=session_token,
                user_id=user.id,
                created_at=datetime.now(),
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            db.add(new_session)
            db.commit()
            
            # 获取关键词（从preferences中）
            keywords = user.preferences.get('keywords', [])
            
            return {
                'success': True,
                'session_token': session_token,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'keywords': keywords,
                    'is_admin': user.is_admin
                }
            }
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'登录失败: {str(e)}'}
        finally:
            db.close()
    
    def logout(self, session_token: str) -> bool:
        """登出用户"""
        if not session_token:
            return False
            
        db = self._get_session()
        try:
            session = db.query(Session).filter(Session.id == session_token).first()
            if session:
                db.delete(session)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            return False
        finally:
            db.close()
    
    def validate_session(self, session_token: str) -> Optional[Dict]:
        """
        验证会话是否有效
        """
        if not session_token:
            return None
            
        db = self._get_session()
        try:
            session = db.query(Session).filter(Session.id == session_token).first()
            
            if not session:
                return None
            
            # 检查是否过期
            if datetime.now() > session.expires_at:
                db.delete(session)
                db.commit()
                return None
            
            user = session.user
            if not user or not user.is_active:
                return None
            
            # 获取关键词
            keywords = user.preferences.get('keywords', [])
            
            return {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'keywords': keywords,
                'preferences': user.preferences,
                'is_admin': user.is_admin
            }
            
        finally:
            db.close()
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        """获取用户信息"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return None
            
            keywords = user.preferences.get('keywords', []) if isinstance(user.preferences, dict) else []
            
            return {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'keywords': keywords,
                'preferences': user.preferences,
                'avatar': user.avatar or '',
                'is_admin': user.is_admin,
                'created_at': user.created_at.isoformat() if hasattr(user.created_at, 'isoformat') else user.created_at,
                'last_login': user.last_login.isoformat() if hasattr(user.last_login, 'isoformat') else user.last_login
            }
        finally:
            db.close()

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """通过用户名获取用户信息"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(username=username).first()
            if not user:
                return None
            keywords = user.preferences.get('keywords', []) if isinstance(user.preferences, dict) else []
            return {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'keywords': keywords,
                'preferences': user.preferences,
                'avatar': user.avatar or '',
                'is_admin': user.is_admin,
                'created_at': user.created_at.isoformat() if hasattr(user.created_at, 'isoformat') else user.created_at,
                'last_login': user.last_login.isoformat() if hasattr(user.last_login, 'isoformat') else user.last_login
            }
        finally:
            db.close()

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """通过邮箱获取用户信息"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(email=email).first()
            if not user:
                return None
            keywords = user.preferences.get('keywords', []) if isinstance(user.preferences, dict) else []
            return {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'keywords': keywords,
                'preferences': user.preferences,
                'avatar': user.avatar or '',
                'is_admin': user.is_admin,
                'created_at': user.created_at.isoformat() if hasattr(user.created_at, 'isoformat') else user.created_at,
                'last_login': user.last_login.isoformat() if hasattr(user.last_login, 'isoformat') else user.last_login
            }
        finally:
            db.close()

    def update_keywords(self, user_id: str, keywords: List[str]) -> Dict:
        """更新用户关键词"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return {'success': False, 'error': '用户不存在'}
            
            # 更新preferences中的keywords
            prefs = user.preferences or {}
            prefs['keywords'] = keywords
            user.preferences = prefs
            
            db.commit()
            return {'success': True, 'message': '关键词已更新'}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'更新失败: {str(e)}'}
        finally:
            db.close()
    
    def update_preferences(self, user_id: str, preferences: Dict) -> Dict:
        """更新用户偏好设置"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return {'success': False, 'error': '用户不存在'}
            
            # 合并偏好设置
            current_prefs = user.preferences or {}
            current_prefs.update(preferences)
            user.preferences = current_prefs
            
            # 添加到待保存列表并提交
            db.add(user)
            db.commit()
            return {'success': True, 'message': '偏好设置已更新'}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'更新失败: {str(e)}'}
        finally:
            db.close()
    
    def get_all_users(self) -> List[Dict]:
        """获取所有用户（管理员用）"""
        db = self._get_session()
        try:
            users = db.query(User).all()
            return [
                {
                    'id': u.id,
                    'username': u.username,
                    'email': u.email,
                    'keywords': u.preferences.get('keywords', []) if hasattr(u, 'preferences') and u.preferences else [],
                    'created_at': u.created_at.isoformat() if hasattr(u.created_at, 'isoformat') else u.created_at,
                    'last_login': u.last_login.isoformat() if hasattr(u.last_login, 'isoformat') else u.last_login,
                    'is_active': u.is_active,
                    'is_admin': u.is_admin,
                    'avatar': u.avatar or ''
                }
                for u in users
            ]
        finally:
            db.close()
    
    def get_keyword_distribution(self) -> Dict:
        """获取所有用户的关键词分布"""
        db = self._get_session()
        try:
            users = db.query(User).all()
            keyword_count = {}
            
            for user in users:
                keywords = user.preferences.get('keywords', [])
                for keyword in keywords:
                    kw_lower = keyword.lower()
                    if kw_lower not in keyword_count:
                        keyword_count[kw_lower] = {
                            'count': 0,
                            'original': keyword,
                            'users': []
                        }
                    keyword_count[kw_lower]['count'] += 1
                    keyword_count[kw_lower]['users'].append(user.id)
            
            return keyword_count
        finally:
            db.close()
    
    def cleanup_expired_sessions(self) -> int:
        """清理过期会话"""
        db = self._get_session()
        try:
            expired = db.query(Session).filter(Session.expires_at < datetime.now()).all()
            count = len(expired)
            
            for session in expired:
                db.delete(session)
            
            db.commit()
            return count
        except Exception as e:
            db.rollback()
            return 0
        finally:
            db.close()
    
    def set_admin(self, user_id: str, is_admin: bool = True) -> bool:
        """设置用户管理员权限"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return False
            
            user.is_admin = is_admin
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            return False
        finally:
            db.close()
    
    def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return False
            
            db.delete(user)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            return False
        finally:
            db.close()
    
    def get_user_settings(self, user_id: str) -> Optional[Dict]:
        """获取用户设置（不含敏感信息）"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return None
            
            prefs = user.preferences or {}
            return {
                'api_provider': prefs.get('api_provider', 'deepseek'),
                'api_base_url': prefs.get('api_base_url', ''),
                'update_frequency_days': prefs.get('update_frequency_days', 7),
                'max_auto_analyze': prefs.get('max_auto_analyze', 20),
                'has_custom_api': bool(prefs.get('api_key')),
                'model': prefs.get('model', 'deepseek-chat'),
                'sources': prefs.get('sources', ['pubmed', 'biorxiv', 'medrxiv'])
            }
        finally:
            db.close()
    
    def save_user_api_settings(self, user_id: str, api_settings: Dict) -> Dict:
        """保存用户API设置（API Key会被加密存储）"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return {'success': False, 'error': '用户不存在'}
            
            # 解析 preferences 为字典
            prefs = user.preferences
            if isinstance(prefs, str):
                prefs = json.loads(prefs) if prefs else {}
            elif not prefs:
                prefs = {}
            
            # 获取加密管理器
            encryption = get_encryption_manager()
            
            # 更新API相关设置
            if 'api_provider' in api_settings:
                prefs['api_provider'] = api_settings['api_provider']
            if 'api_key' in api_settings and api_settings['api_key']:
                # 加密存储API Key
                prefs['api_key'] = encryption.encrypt(api_settings['api_key'])
            if 'api_base_url' in api_settings:
                prefs['api_base_url'] = api_settings['api_base_url']
            if 'model' in api_settings:
                prefs['model'] = api_settings['model']
            
            # 先添加到 pending 列表，这样 commit 才会保存
            db.add(user)
            user.preferences = prefs
            db.commit()
            
            return {'success': True, 'message': 'API设置已保存（已加密）'}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'保存失败: {str(e)}'}
        finally:
            db.close()
    
    def get_user_api_key(self, user_id: str) -> Optional[str]:
        """获取用户加密的API Key（自动解密）"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return None
            
            encrypted_key = None
            if isinstance(user.preferences, dict):
                encrypted_key = user.preferences.get('api_key')
            elif user.preferences:
                # 尝试解析JSON
                try:
                    prefs = json.loads(user.preferences) if isinstance(user.preferences, str) else user.preferences
                    encrypted_key = prefs.get('api_key')
                except:
                    pass
            
            if not encrypted_key:
                return None
            
            # 解密API Key
            encryption = get_encryption_manager()
            return encryption.decrypt(encrypted_key)
        finally:
            db.close()
    
    def save_user_update_settings(self, user_id: str, settings: Dict) -> Dict:
        """保存用户更新频率设置"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return {'success': False, 'error': '用户不存在'}
            
            prefs = user.preferences or {}
            
            if 'update_frequency_days' in settings:
                prefs['update_frequency_days'] = max(1, min(30, int(settings['update_frequency_days'])))
            if 'max_auto_analyze' in settings:
                prefs['max_auto_analyze'] = max(1, min(50, int(settings['max_auto_analyze'])))
            
            user.preferences = prefs
            db.commit()
            
            return {'success': True, 'message': '更新设置已保存'}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'保存失败: {str(e)}'}
        finally:
            db.close()
    
    def get_user_sources(self, user_id: str) -> List[str]:
        """获取用户选择的文献源"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return ['pubmed', 'biorxiv', 'medrxiv']
            
            prefs = user.preferences or {}
            return prefs.get('sources', ['pubmed', 'biorxiv', 'medrxiv'])
        finally:
            db.close()
    
    def save_user_sources(self, user_id: str, sources: List[str]) -> Dict:
        """保存用户选择的文献源"""
        db = self._get_session()
        try:
            user = db.query(User).filter_by(id=user_id).first()
            if not user:
                return {'success': False, 'error': '用户不存在'}
            
            # 验证源
            from v1.fetcher import PaperFetcher
            available = list(PaperFetcher.PAPER_SOURCES.keys())
            valid_sources = [s for s in sources if s in available]
            
            # 至少选择一个源
            if not valid_sources:
                valid_sources = ['pubmed']
            
            prefs = user.preferences or {}
            prefs['sources'] = valid_sources
            user.preferences = prefs
            db.commit()
            
            return {'success': True, 'message': '文献源设置已保存'}
            
        except Exception as e:
            db.rollback()
            return {'success': False, 'error': f'保存失败: {str(e)}'}
        finally:
            db.close()

    @property
    def users(self) -> Dict:
        """兼容属性 - 返回所有用户的字典格式"""
        users_list = self.get_all_users()
        return {user['id']: user for user in users_list}


# 预设的关键词分类
PREDEFINED_KEYWORDS = {
    '靶向蛋白降解': {
        'icon': '🎯',
        'keywords': [
            'targeted protein degradation',
            'PROTAC',
            'molecular glue',
            'degrader',
            'ubiquitin-proteasome',
            'E3 ligase'
        ]
    },
    '免疫治疗': {
        'icon': '🛡️',
        'keywords': [
            'immunotherapy',
            'CAR-T',
            'checkpoint inhibitor',
            'PD-1',
            'PD-L1',
            'immune checkpoint'
        ]
    },
    '基因治疗': {
        'icon': '🧬',
        'keywords': [
            'gene therapy',
            'CRISPR',
            'gene editing',
            'AAV',
            'viral vector'
        ]
    },
    '肿瘤学': {
        'icon': '🔬',
        'keywords': [
            'oncology',
            'cancer',
            'tumor',
            'metastasis',
            'chemotherapy',
            'targeted therapy'
        ]
    },
    '神经科学': {
        'icon': '🧠',
        'keywords': [
            'neuroscience',
            'neurodegenerative',
            "Alzheimer's",
            "Parkinson's",
            'neural'
        ]
    },
    '代谢疾病': {
        'icon': '⚡',
        'keywords': [
            'metabolic disease',
            'diabetes',
            'obesity',
            'insulin',
            'glucose'
        ]
    }
}


def get_predefined_categories() -> Dict:
    """获取预设的关键词分类"""
    return PREDEFINED_KEYWORDS


def expand_keywords(selected_categories: List[str]) -> List[str]:
    """
    根据选择的分类展开关键词列表
    """
    keywords = []
    for category in selected_categories:
        if category in PREDEFINED_KEYWORDS:
            keywords.extend(PREDEFINED_KEYWORDS[category]['keywords'])
    return list(set(keywords))  # 去重
