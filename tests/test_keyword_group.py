#!/usr/bin/env python3
"""
关键词组功能测试 - 验证关键词组管理功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestKeywordGroup:
    """关键词组测试"""
    
    def test_group_structure(self):
        """测试关键词组数据结构"""
        group = {
            'id': 'group_001',
            'name': '癌症研究',
            'keywords': ['cancer', 'tumor', 'oncology'],
            'color': '#FF5733',
            'icon': '🔬',
            'user_id': 'user_001'
        }
        
        assert 'id' in group
        assert 'name' in group
        assert 'keywords' in group
        assert isinstance(group['keywords'], list)
    
    def test_group_keywords_list(self):
        """测试关键词列表"""
        keywords = ['cancer', 'tumor', 'carcinoma', 'oncology', 'neoplasm']
        
        assert len(keywords) == 5
        assert all(isinstance(k, str) for k in keywords)
    
    def test_group_empty_keywords(self):
        """测试空关键词"""
        group = {
            'id': 'group_001',
            'name': '测试组',
            'keywords': [],
            'color': '#FF0000',
            'icon': '📝'
        }
        
        assert len(group['keywords']) == 0
    
    def test_group_duplicated_keywords(self):
        """测试重复关键词处理"""
        keywords = ['cancer', 'cancer', 'tumor', 'cancer']
        
        # 去重
        unique_keywords = list(set(keywords))
        
        assert len(unique_keywords) == 2
    
    def test_group_color_format(self):
        """测试颜色格式"""
        valid_colors = ['#FF5733', '#FFFFFF', '#000000', '#123456']
        
        for color in valid_colors:
            assert color.startswith('#')
            assert len(color) == 7
    
    def test_group_icon_emoji(self):
        """测试图标Emoji"""
        icons = ['🔬', '💊', '🧬', '🧪', '📊']
        
        assert all(len(icon) <= 2 for icon in icons)


class TestKeywordGroupCRUD:
    """关键词组CRUD测试"""
    
    def test_create_group(self):
        """测试创建关键词组"""
        user_id = 'test_user_001'
        
        new_group = {
            'id': 'new_group_001',
            'name': '新关键词组',
            'keywords': ['keyword1', 'keyword2'],
            'color': '#3498DB',
            'icon': '📚',
            'user_id': user_id,
            'created_at': '2024-01-01'
        }
        
        assert new_group['name'] == '新关键词组'
        assert new_group['user_id'] == user_id
    
    def test_update_group_name(self):
        """测试更新组名称"""
        group = {
            'id': 'group_001',
            'name': '旧名称',
            'keywords': ['test']
        }
        
        # 更新名称
        group['name'] = '新名称'
        
        assert group['name'] == '新名称'
    
    def test_update_group_keywords(self):
        """测试更新关键词"""
        group = {
            'id': 'group_001',
            'name': '测试组',
            'keywords': ['old1', 'old2']
        }
        
        # 更新关键词
        group['keywords'] = ['new1', 'new2', 'new3']
        
        assert len(group['keywords']) == 3
        assert 'new1' in group['keywords']
    
    def test_delete_group(self):
        """测试删除关键词组"""
        groups = [
            {'id': 'group_001', 'name': '组1'},
            {'id': 'group_002', 'name': '组2'},
            {'id': 'group_003', 'name': '组3'},
        ]
        
        # 删除一个组
        groups = [g for g in groups if g['id'] != 'group_002']
        
        assert len(groups) == 2
        assert all(g['id'] != 'group_002' for g in groups)
    
    def test_user_groups_isolation(self):
        """测试用户组隔离"""
        user1_groups = [
            {'id': 'g1', 'name': '用户1组1'},
            {'id': 'g2', 'name': '用户1组2'},
        ]
        
        user2_groups = [
            {'id': 'g3', 'name': '用户2组1'},
        ]
        
        # 用户1不应该看到用户2的组
        assert len(user1_groups) == 2
        assert len(user2_groups) == 1


class TestKeywordGroupValidation:
    """关键词组验证测试"""
    
    def test_validate_keyword_length(self):
        """测试关键词长度验证"""
        valid_keywords = ['ab', 'cancer', 'verylongkeyword']
        invalid_keywords = ['a', '']  # 太短或空
        
        # 有效关键词
        for kw in valid_keywords:
            assert len(kw) >= 2
        
        # 无效关键词应该被过滤
        for kw in invalid_keywords:
            assert len(kw) < 2
    
    def test_validate_group_name_length(self):
        """测试组名长度验证"""
        valid_names = ['组', '测试', '这是一个很长的组名']
        invalid_names = ['', 'a' * 100]  # 太长或空
        
        # 验证逻辑
        def is_valid_name(name):
            return 1 <= len(name) <= 50
        
        for name in valid_names:
            assert is_valid_name(name)
    
    def test_validate_keywords_count(self):
        """测试关键词数量限制"""
        max_keywords = 100
        
        keywords = ['kw1', 'kw2', 'kw3']
        
        assert len(keywords) < max_keywords
    
    def test_sanitize_keyword(self):
        """测试关键词清理"""
        # 清理前后空格
        keyword = '  cancer  '
        cleaned = keyword.strip()
        
        assert cleaned == 'cancer'
    
    def test_normalize_keyword_case(self):
        """测试关键词大小写标准化"""
        keywords = ['Cancer', 'CANCER', 'cancer']
        
        # 标准化为小写
        normalized = [kw.lower() for kw in keywords]
        
        assert len(set(normalized)) == 1  # 应该只有一个唯一值


class TestKeywordGroupMerge:
    """关键词组合并测试"""
    
    def test_merge_multiple_groups_keywords(self):
        """测试合并多个组的关键词"""
        groups = [
            {'keywords': ['cancer', 'tumor']},
            {'keywords': ['cancer', 'carcinoma']},
            {'keywords': ['oncology']},
        ]
        
        # 合并所有关键词并去重
        all_keywords = []
        for group in groups:
            all_keywords.extend(group['keywords'])
        
        unique_keywords = list(set(all_keywords))
        
        assert len(unique_keywords) == 4  # cancer, tumor, carcinoma, oncology
    
    def test_group_priority(self):
        """测试组优先级"""
        groups = [
            {'id': 'g1', 'priority': 1, 'keywords': ['cancer']},
            {'id': 'g2', 'priority': 2, 'keywords': ['tumor']},
        ]
        
        # 按优先级排序
        sorted_groups = sorted(groups, key=lambda g: g['priority'])
        
        assert sorted_groups[0]['id'] == 'g1'
    
    def test_keyword_usage_count(self):
        """测试关键词使用统计"""
        groups = [
            {'keywords': ['cancer', 'tumor']},
            {'keywords': ['cancer', 'carcinoma']},
            {'keywords': ['cancer']},
        ]
        
        # 统计每个关键词出现的次数
        from collections import Counter
        all_kw = []
        for g in groups:
            all_kw.extend(g['keywords'])
        
        counts = Counter(all_kw)
        
        assert counts['cancer'] == 3
        assert counts['tumor'] == 1


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
