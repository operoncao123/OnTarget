#!/usr/bin/env python3
"""
加密工具测试 - 验证加解密功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.encryption import EncryptionManager


class TestEncryption:
    """加密解密测试"""
    
    def setup_method(self):
        """每个测试方法执行前调用"""
        self.encryption = EncryptionManager(master_key='test-key-123')
    
    def test_encrypt_decrypt_simple(self):
        """测试简单字符串加密解密"""
        original = 'Hello World!'
        encrypted = self.encryption.encrypt(original)
        decrypted = self.encryption.decrypt(encrypted)
        
        assert encrypted != original, "加密后应该与原文本不同"
        assert decrypted == original, f"解密后应该等于原文本: {original} != {decrypted}"
    
    def test_encrypt_decrypt_api_key(self):
        """测试API Key加密解密"""
        original = 'sk-abcdefghijklmnopqrstuvwxyz1234567890'
        encrypted = self.encryption.encrypt(original)
        decrypted = self.encryption.decrypt(encrypted)
        
        assert encrypted != original
        assert decrypted == original
    
    def test_encrypt_empty_string(self):
        """测试空字符串加密"""
        result = self.encryption.encrypt('')
        assert result == '', "空字符串加密后应返回空字符串"
    
    def test_decrypt_empty_string(self):
        """测试空字符串解密"""
        result = self.encryption.decrypt('')
        assert result == '', "空字符串解密后应返回空字符串"
    
    def test_encrypt_chinese(self):
        """测试中文加密"""
        original = '这是一段中文测试文本'
        encrypted = self.encryption.encrypt(original)
        decrypted = self.encryption.decrypt(encrypted)
        
        assert decrypted == original
    
    def test_encrypt_special_chars(self):
        """测试特殊字符加密"""
        original = '!@#$%^&*()_+-=[]{}|;:,.<>?`~'
        encrypted = self.encryption.encrypt(original)
        decrypted = self.encryption.decrypt(encrypted)
        
        assert decrypted == original
    
    def test_encrypt_long_text(self):
        """测试长文本加密"""
        original = 'A' * 10000  # 10KB 文本
        encrypted = self.encryption.encrypt(original)
        decrypted = self.encryption.decrypt(encrypted)
        
        assert decrypted == original
    
    def test_different_keys_produce_different(self):
        """测试不同密钥产生不同加密结果"""
        enc1 = EncryptionManager(master_key='key1')
        enc2 = EncryptionManager(master_key='key2')
        
        original = 'test message'
        encrypted1 = enc1.encrypt(original)
        encrypted2 = enc2.encrypt(original)
        
        assert encrypted1 != encrypted2, "不同密钥加密结果应该不同"
    
    def test_encrypt_dict(self):
        """测试字典加密"""
        data = {
            'api_key': 'sk-test123',
            'username': 'testuser',
            'count': 123
        }
        
        encrypted = self.encryption.encrypt_dict(data, ['api_key'])
        
        assert encrypted['api_key'] != data['api_key'], "api_key应该被加密"
        assert encrypted['username'] == data['username'], "username不应该被加密"
        assert encrypted['count'] == data['count'], "count不应该被加密"
    
    def test_decrypt_dict(self):
        """测试字典解密"""
        data = {
            'api_key': 'sk-test123',
            'username': 'testuser'
        }
        encrypted = self.encryption.encrypt_dict(data, ['api_key'])
        decrypted = self.encryption.decrypt_dict(encrypted, ['api_key'])
        
        assert decrypted['api_key'] == 'sk-test123', "api_key应该被解密"
        assert decrypted['username'] == 'testuser', "username应该保持不变"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
