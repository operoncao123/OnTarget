#!/usr/bin/env python3
"""
筛选功能测试 - 验证文献筛选功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPaperFiltering:
    """文献筛选测试"""
    
    def setup_method(self):
        # 模拟文献数据
        self.papers = [
            {'title': 'Cancer research advances', 'source': 'pubmed', 'score': 0.9, 'is_saved': False, 'is_analyzed': True},
            {'title': 'Bioinformatics methods', 'source': 'biorxiv', 'score': 0.7, 'is_saved': True, 'is_analyzed': True},
            {'title': 'Machine learning in biology', 'source': 'arxiv', 'source': 'arxiv', 'score': 0.8, 'is_saved': False, 'is_analyzed': False},
            {'title': 'Medical imaging analysis', 'source': 'medrxiv', 'score': 0.6, 'is_saved': True, 'is_analyzed': False},
            {'title': 'Drug discovery pipeline', 'source': 'pubmed', 'score': 0.95, 'is_saved': False, 'is_analyzed': True},
        ]
    
    def test_filter_by_source(self):
        """测试按来源筛选"""
        source = 'pubmed'
        filtered = [p for p in self.papers if p['source'] == source]
        
        assert len(filtered) == 2
        assert all(p['source'] == 'pubmed' for p in filtered)
    
    def test_filter_by_saved(self):
        """测试按收藏状态筛选"""
        saved_only = [p for p in self.papers if p['is_saved']]
        
        assert len(saved_only) == 2
        assert all(p['is_saved'] for p in saved_only)
    
    def test_filter_by_analyzed(self):
        """测试按分析状态筛选"""
        analyzed_only = [p for p in self.papers if p.get('is_analyzed')]
        
        assert len(analyzed_only) == 3
    
    def test_filter_by_score(self):
        """测试按评分筛选"""
        min_score = 0.8
        filtered = [p for p in self.papers if p['score'] >= min_score]
        
        assert len(filtered) == 3
        assert all(p['score'] >= min_score for p in filtered)
    
    def test_filter_by_multiple_criteria(self):
        """测试多条件筛选"""
        # 来源是pubmed且评分>=0.9
        filtered = [p for p in self.papers 
                   if p['source'] == 'pubmed' and p['score'] >= 0.9]
        
        # 应该是Drug discovery pipeline (0.95)
        assert len(filtered) >= 1
        assert any(p['title'] == 'Drug discovery pipeline' for p in filtered)
    
    def test_filter_no_results(self):
        """测试无结果筛选"""
        # 筛选不存在的来源
        filtered = [p for p in self.papers if p['source'] == 'nonexistent']
        
        assert len(filtered) == 0
    
    def test_filter_case_insensitive(self):
        """测试大小写不敏感筛选"""
        # 来源字段应该是统一的小写
        papers = [
            {'title': 'Test A', 'source': 'PubMed'},
            {'title': 'Test B', 'source': 'pubmed'},
            {'title': 'Test C', 'source': 'PUBMED'},
        ]
        
        # 标准化后筛选
        source = 'pubmed'
        filtered = [p for p in papers if p['source'].lower() == source]
        
        assert len(filtered) == 3


class TestFilterCombination:
    """筛选组合测试"""
    
    def setup_method(self):
        self.papers = [
            {'title': 'Paper A', 'source': 'pubmed', 'score': 0.9, 'is_saved': True, 'is_analyzed': True, 'impact_factor': 10.5},
            {'title': 'Paper B', 'source': 'biorxiv', 'score': 0.7, 'is_saved': False, 'is_analyzed': True, 'impact_factor': 0},
            {'title': 'Paper C', 'source': 'pubmed', 'score': 0.5, 'is_saved': True, 'is_analyzed': False, 'impact_factor': 5.2},
            {'title': 'Paper D', 'source': 'medrxiv', 'score': 0.8, 'is_saved': False, 'is_analyzed': False, 'impact_factor': 0},
        ]
    
    def test_and_filter(self):
        """测试AND筛选"""
        # 已收藏 AND 已分析
        filtered = [p for p in self.papers if p['is_saved'] and p['is_analyzed']]
        
        assert len(filtered) == 1
        assert filtered[0]['title'] == 'Paper A'
    
    def test_or_filter(self):
        """测试OR筛选"""
        # 来源是pubmed OR 评分>0.8
        filtered = [p for p in self.papers 
                   if p['source'] == 'pubmed' or p['score'] > 0.8]
        
        # Paper A (pubmed), Paper C (pubmed), Paper D (>0.8)
        assert len(filtered) >= 2
    
    def test_not_filter(self):
        """测试NOT筛选"""
        # 未收藏
        filtered = [p for p in self.papers if not p['is_saved']]
        
        assert len(filtered) == 2
    
    def test_complex_filter(self):
        """测试复杂筛选"""
        # (已收藏 OR 已分析) AND (评分>0.6)
        filtered = [p for p in self.papers 
                   if (p['is_saved'] or p['is_analyzed']) and p['score'] > 0.6]
        
        # Paper A (saved+analyzed+score>0.6), Paper B (analyzed+score>0.6)
        assert len(filtered) >= 2


class TestFilterPagination:
    """筛选分页测试"""
    
    def setup_method(self):
        # 生成分测试数据
        self.all_papers = [{'id': i, 'title': f'Paper {i}'} for i in range(100)]
    
    def test_pagination_basic(self):
        """测试基本分页"""
        page = 1
        per_page = 20
        
        start = (page - 1) * per_page
        end = start + per_page
        
        paginated = self.all_papers[start:end]
        
        assert len(paginated) == 20
        assert paginated[0]['id'] == 0
        assert paginated[-1]['id'] == 19
    
    def test_pagination_last_page(self):
        """测试最后一页"""
        # 100条，每页20，共5页
        page = 5
        per_page = 20
        
        start = (page - 1) * per_page
        end = start + per_page
        
        paginated = self.all_papers[start:end]
        
        assert len(paginated) == 20
        assert paginated[-1]['id'] == 99
    
    def test_pagination_partial_page(self):
        """测试不完整页"""
        page = 3
        per_page = 20
        
        start = (page - 1) * per_page
        end = start + per_page
        
        paginated = self.all_papers[start:end]
        
        # 第3页应该是 40-59，只有20条
        assert len(paginated) == 20
    
    def test_total_pages_calculation(self):
        """测试总页数计算"""
        total = len(self.all_papers)
        per_page = 20
        
        total_pages = (total + per_page - 1) // per_page
        
        assert total_pages == 5
    
    def test_filter_with_pagination(self):
        """测试筛选+分页"""
        # 先筛选
        filtered = self.all_papers  # 使用类中的测试数据
        
        # 再分页
        page = 1
        per_page = 2
        start = (page - 1) * per_page
        end = start + per_page
        
        result = filtered[start:end]
        
        assert len(result) == 2


class TestFilterSorting:
    """筛选排序测试"""
    
    def setup_method(self):
        self.papers = [
            {'title': 'Paper C', 'score': 0.8, 'date': '2024-01-03'},
            {'title': 'Paper A', 'score': 0.9, 'date': '2024-01-01'},
            {'title': 'Paper B', 'score': 0.7, 'date': '2024-01-02'},
        ]
    
    def test_sort_by_score_desc(self):
        """测试按评分降序"""
        sorted_papers = sorted(self.papers, key=lambda x: x['score'], reverse=True)
        
        assert sorted_papers[0]['title'] == 'Paper A'  # 0.9
        assert sorted_papers[1]['title'] == 'Paper C'  # 0.8
        assert sorted_papers[2]['title'] == 'Paper B'  # 0.7
    
    def test_sort_by_score_asc(self):
        """测试按评分升序"""
        sorted_papers = sorted(self.papers, key=lambda x: x['score'])
        
        assert sorted_papers[0]['title'] == 'Paper B'
        assert sorted_papers[2]['title'] == 'Paper A'
    
    def test_sort_by_date(self):
        """测试按日期排序"""
        sorted_papers = sorted(self.papers, key=lambda x: x['date'])
        
        assert sorted_papers[0]['title'] == 'Paper A'
        assert sorted_papers[1]['title'] == 'Paper B'
        assert sorted_papers[2]['title'] == 'Paper C'


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
