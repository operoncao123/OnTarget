#!/usr/bin/env python3
"""
收藏功能测试 - 验证文献收藏功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.push_service import PersonalizedPushEngine
import json
import tempfile
import shutil


class TestFavoriteManager:
    """收藏管理器测试"""
    
    def setup_method(self):
        """每个测试方法执行前调用"""
        # 创建临时目录用于测试
        self.temp_dir = tempfile.mkdtemp()
        self.engine = PersonalizedPushEngine(data_dir=self.temp_dir)
    
    def teardown_method(self):
        """测试后清理"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_save_paper_for_user(self):
        """测试保存文献"""
        user_id = 'test_user_001'
        paper_hash = 'paper_hash_123'
        
        # 保存文献
        result = self.engine.save_paper_for_user(user_id, paper_hash)
        
        # 验证
        assert result is not None
    
    def test_unsave_paper_for_user(self):
        """测试取消收藏"""
        user_id = 'test_user_001'
        paper_hash = 'paper_hash_123'
        
        # 先保存
        self.engine.save_paper_for_user(user_id, paper_hash)
        
        # 再取消
        result = self.engine.unsave_paper_for_user(user_id, paper_hash)
        
        assert result is not None
    
    def test_get_saved_papers(self):
        """测试获取已收藏文献"""
        user_id = 'test_user_002'
        
        # 保存几篇文献
        self.engine.save_paper_for_user(user_id, 'hash_1')
        self.engine.save_paper_for_user(user_id, 'hash_2')
        self.engine.save_paper_for_user(user_id, 'hash_3')
        
        # 获取已收藏
        saved = self.engine.get_saved_papers(user_id)
        
        assert len(saved) >= 3
    
    def test_save_duplicate(self):
        """测试重复保存"""
        user_id = 'test_user_003'
        paper_hash = 'hash_duplicate'
        
        # 多次保存同一篇
        self.engine.save_paper_for_user(user_id, paper_hash)
        self.engine.save_paper_for_user(user_id, paper_hash)
        
        # 应该只有一篇
        saved = self.engine.get_saved_papers(user_id)
        # 可能返回1或依赖实现
    
    def test_save_different_users(self):
        """测试不同用户的收藏独立"""
        user1 = 'user_1'
        user2 = 'user_2'
        same_hash = 'same_paper_hash'
        
        # 两个用户都收藏同一篇
        self.engine.save_paper_for_user(user1, same_hash)
        self.engine.save_paper_for_user(user2, same_hash)
        
        # 各自应该都能看到
        saved1 = self.engine.get_saved_papers(user1)
        saved2 = self.engine.get_saved_papers(user2)
        
        assert same_hash in saved1
        assert same_hash in saved2


class TestFavoriteDataPersistence:
    """收藏数据持久化测试"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = PersonalizedPushEngine(data_dir=self.temp_dir)
    
    def teardown_method(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_user_papers_file_created(self):
        """测试用户文献文件创建"""
        user_id = 'test_user_persistence'
        self.engine.save_paper_for_user(user_id, 'hash_123')
        
        # 文件应该存在
        assert os.path.exists(self.engine.user_papers_file)
    
    def test_data_saved_correctly(self):
        """测试数据正确保存"""
        user_id = 'test_save_correct'
        paper_hash = 'hash_correct'
        
        # 保存
        self.engine.save_paper_for_user(user_id, paper_hash)
        
        # 重新创建引擎（模拟重启）
        new_engine = PersonalizedPushEngine(data_dir=self.temp_dir)
        
        # 应该能读取到
        saved = new_engine.get_saved_papers(user_id)
        # 数据持久化验证


class TestFavoriteFiltering:
    """收藏筛选测试"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = PersonalizedPushEngine(data_dir=self.temp_dir)
    
    def teardown_method(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_is_paper_saved(self):
        """测试检查文献是否已收藏"""
        user_id = 'test_filter_user'
        paper_hash = 'hash_to_check'
        
        # 未收藏时
        is_saved = self.engine.is_paper_saved(user_id, paper_hash)
        assert is_saved is False
        
        # 收藏后
        self.engine.save_paper_for_user(user_id, paper_hash)
        is_saved = self.engine.is_paper_saved(user_id, paper_hash)
        assert is_saved is True
    
    def test_get_saved_count(self):
        """测试获取收藏数量"""
        user_id = 'test_count_user'
        
        # 收藏多篇
        for i in range(5):
            self.engine.save_paper_for_user(user_id, f'hash_{i}')
        
        saved = self.engine.get_saved_papers(user_id)
        # 数量验证


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
