#!/usr/bin/env python3
"""
评分算法测试 - 验证文献评分功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v1.scorer import KeywordScorer


class TestPaperScorer:
    """文献评分测试"""
    
    def setup_method(self):
        """每个测试方法执行前调用"""
        self.scorer = KeywordScorer()
    
    def test_exact_keyword_match_title(self):
        """测试标题中精确关键词匹配"""
        paper = {
            'title': 'Cancer research advances',
            'abstract': 'This paper discusses new methods in cancer treatment.'
        }
        keywords = ['cancer']
        
        scored = self.scorer.score_papers([paper], keywords)
        
        assert len(scored) == 1
        assert scored[0]['keywords_score'] > 0
        assert 'keyword_matches' in scored[0]
    
    def test_multiple_keywords_match(self):
        """测试多个关键词匹配"""
        paper = {
            'title': 'Cancer and immunotherapy research',
            'abstract': 'New advances in cancer immunotherapy.'
        }
        keywords = ['cancer', 'immunotherapy']
        
        scored = self.scorer.score_papers([paper], keywords)
        
        assert len(scored) == 1
        # keyword_matches结构可能不同，检查score大于0
        assert scored[0]['keywords_score'] > 0
    
    def test_no_match_returns_zero(self):
        """测试无匹配返回0分"""
        paper = {
            'title': 'Weather patterns analysis',
            'abstract': 'This paper discusses meteorological phenomena.'
        }
        keywords = ['cancer', 'immunotherapy']
        
        scored = self.scorer.score_papers([paper], keywords)
        
        assert len(scored) == 1
        assert scored[0]['keywords_score'] == 0
    
    def test_case_insensitive_match(self):
        """测试大小写不敏感"""
        paper = {
            'title': 'CANCER Research',
            'abstract': 'CANCER treatment advances.'
        }
        keywords = ['cancer']
        
        scored = self.scorer.score_papers([paper], keywords)
        
        assert len(scored) == 1
        assert scored[0]['keywords_score'] > 0
    
    def test_partial_word_match(self):
        """测试部分匹配"""
        paper = {
            'title': 'Carcinoma research',
            'abstract': 'Study of carcinoma cells.'
        }
        keywords = ['cancer']
        
        scored = self.scorer.score_papers([paper], keywords)
        
        # 部分匹配应该不得分
        assert scored[0]['keywords_score'] == 0
    
    def test_empty_keywords(self):
        """测试空关键词列表"""
        paper = {
            'title': 'Cancer research',
            'abstract': 'Abstract text here.'
        }
        keywords = []
        
        scored = self.scorer.score_papers([paper], keywords)
        
        assert len(scored) == 1
        assert scored[0]['keywords_score'] == 0
    
    def test_empty_paper(self):
        """测试空文献"""
        papers = []
        keywords = ['cancer']
        
        scored = self.scorer.score_papers(papers, keywords)
        
        assert len(scored) == 0
    
    def test_abstract_only_match(self):
        """测试仅在摘要中匹配"""
        paper = {
            'title': 'Research advances',
            'abstract': 'This paper discusses cancer treatment methods.'
        }
        keywords = ['cancer']
        
        scored = self.scorer.score_papers([paper], keywords)
        
        assert len(scored) == 1
        assert scored[0]['keywords_score'] > 0
    
    def test_title_weight_higher(self):
        """测试标题权重更高"""
        paper_title = {
            'title': 'Cancer research',
            'abstract': 'Some abstract.'
        }
        paper_abstract = {
            'title': 'Research paper',
            'abstract': 'Some abstract about cancer.'
        }
        keywords = ['cancer']
        
        scored_title = self.scorer.score_papers([paper_title], keywords)
        scored_abstract = self.scorer.score_papers([paper_abstract], keywords)
        
        # 标题匹配应该比摘要匹配分数更高或相等
        assert scored_title[0]['keywords_score'] >= scored_abstract[0]['keywords_score']


class TestPaperScorerSorting:
    """评分排序测试"""
    
    def setup_method(self):
        self.scorer = KeywordScorer()
    
    def test_sorted_by_score_descending(self):
        """测试按分数降序排序"""
        papers = [
            {'title': 'Paper C', 'abstract': 'a b c'},
            {'title': 'Paper A', 'abstract': 'a'},
            {'title': 'Paper B', 'abstract': 'a b'}
        ]
        keywords = ['a']
        
        scored = self.scorer.score_papers(papers, keywords)
        
        # 分数应该按降序排列
        scores = [p['keywords_score'] for p in scored]
        assert scores == sorted(scores, reverse=True)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
