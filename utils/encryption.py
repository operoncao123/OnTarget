#!/usr/bin/env python3
"""
加密工具模块 - 用于API密钥加密存储
使用简单对称加密（AES）或Base64 fallback
"""

import os
import base64
import hashlib
from typing import Optional

# Try to import cryptography, fallback to simple base64 if not available
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    print("Warning: cryptography module not available, using simple base64 encoding")

class EncryptionManager:
    """
    加密管理器
    使用系统密钥对所有用户数据进行对称加密
    """
    
    def __init__(self, master_key: Optional[str] = None):
        """
        初始化加密管理器
        
        Args:
            master_key: 主密钥，优先从环境变量 ENCRYPTION_KEY 获取
        """
        self.master_key = master_key or os.getenv('ENCRYPTION_KEY')
        if not self.master_key:
            # 如果没有设置主密钥，使用默认密钥（仅用于开发环境）
            self.master_key = 'default-dev-key-please-change-in-production'
        
        self._fernet = self._create_fernet()
    
    def _create_fernet(self):
        """创建Fernet实例（如果cryptography可用）"""
        if not CRYPTO_AVAILABLE:
            return None
        
        # 使用主密钥派生加密密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'fixed_salt_for_deterministic_encryption',
            iterations=100000,
            backend=default_backend()
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key.encode()))
        return Fernet(key)
    
    def encrypt(self, plaintext: str) -> str:
        """
        加密字符串
        
        Args:
            plaintext: 明文
            
        Returns:
            加密后的base64字符串
        """
        if not plaintext:
            return ""
        
        try:
            if CRYPTO_AVAILABLE and self._fernet:
                encrypted = self._fernet.encrypt(plaintext.encode())
                return base64.urlsafe_b64encode(encrypted).decode()
            else:
                # Fallback: simple base64 encoding
                combined = f"{self.master_key}:{plaintext}"
                return base64.urlsafe_b64encode(combined.encode()).decode()
        except Exception as e:
            print(f"Encryption error: {e}")
            return ""
    
    def decrypt(self, ciphertext: str) -> str:
        """
        解密字符串
        
        Args:
            ciphertext: 密文（base64编码）
            
        Returns:
            解密后的明文
        """
        if not ciphertext:
            return ""
        
        try:
            if CRYPTO_AVAILABLE and self._fernet:
                # 解码base64
                encrypted = base64.urlsafe_b64decode(ciphertext.encode())
                decrypted = self._fernet.decrypt(encrypted)
                return decrypted.decode()
            else:
                # Fallback: simple base64 decoding
                combined = base64.urlsafe_b64decode(ciphertext.encode()).decode()
                if ':' in combined:
                    key, plaintext = combined.split(':', 1)
                    if key == self.master_key:
                        return plaintext
                return combined
        except Exception as e:
            print(f"Decryption error: {e}")
            return ""
    
    def encrypt_dict(self, data: dict, fields: list) -> dict:
        """
        加密字典中的指定字段
        
        Args:
            data: 原始字典
            fields: 需要加密的字段列表
            
        Returns:
            加密后的字典
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                result[field] = self.encrypt(result[field])
        return result
    
    def decrypt_dict(self, data: dict, fields: list) -> dict:
        """
        解密字典中的指定字段
        
        Args:
            data: 加密后的字典
            fields: 需要解密的字段列表
            
        Returns:
            解密后的字典
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                result[field] = self.decrypt(result[field])
        return result

# 全局加密管理器实例
_encryption_manager = None

def get_encryption_manager() -> EncryptionManager:
    """获取全局加密管理器实例（单例模式）"""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager()
    return _encryption_manager
