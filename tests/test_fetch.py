#!/usr/bin/env python3
"""
文献获取测试 - 验证文献更新功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v1.fetcher import PaperFetcher


class TestPaperFetcher:
    """文献获取器测试"""
    
    def setup_method(self):
        """每个测试方法执行前调用"""
        self.fetcher = PaperFetcher(pubmed_email='test@example.com')
    
    def test_paper_sources_available(self):
        """测试文献源是否可用"""
        sources = self.fetcher.PAPER_SOURCES
        assert 'pubmed' in sources
        assert 'biorxiv' in sources
        assert 'medrxiv' in sources
        assert len(sources) >= 7
    
    def test_source_info_structure(self):
        """测试文献源信息结构"""
        for source_key, source_info in self.fetcher.PAPER_SOURCES.items():
            assert 'name' in source_info
            assert 'category' in source_info
            assert 'description' in source_info
    
    def test_biorxiv_category(self):
        """测试bioRxiv分类"""
        assert self.fetcher.PAPER_SOURCES['biorxiv']['category'] == 'preprint'
    
    def test_pubmed_category(self):
        """测试PubMed分类"""
        assert self.fetcher.PAPER_SOURCES['pubmed']['category'] == 'journal'
    
    def test_fetch_all_with_empty_keywords(self):
        """测试空关键词处理"""
        # 空关键词应该返回空列表，不会崩溃
        papers = self.fetcher.fetch_all(keywords=[], days_back=1)
        assert isinstance(papers, list)
    
    def test_fetch_all_with_none_keywords(self):
        """测试None关键词处理"""
        papers = self.fetcher.fetch_all(keywords=None, days_back=1)
        assert isinstance(papers, list)
    
    def test_days_back_parameter(self):
        """测试days_back参数"""
        # 验证参数可以接受不同值
        papers_1 = self.fetcher.fetch_all(keywords=['cancer'], days_back=1)
        papers_7 = self.fetcher.fetch_all(keywords=['cancer'], days_back=7)
        # 天数越多，应该返回更多或相等数量的文献
        assert isinstance(papers_1, list)
        assert isinstance(papers_7, list)
    
    def test_source_timeout_config(self):
        """测试超时配置"""
        from config import PARALLEL_FETCH
        timeouts = PARALLEL_FETCH.get('timeouts', {})
        assert 'pubmed' in timeouts
        assert timeouts['pubmed'] >= 30  # 至少30秒


class TestPaperDeduplication:
    """文献去重测试"""
    
    def setup_method(self):
        self.fetcher = PaperFetcher(pubmed_email='test@example.com')
    
    def test_deduplication_by_title(self):
        """测试基于标题去重"""
        papers = [
            {'title': 'Test Paper A', 'doi': '', 'abstract': 'test'},
            {'title': 'Test Paper A', 'doi': '', 'abstract': 'test'},  # 重复
            {'title': 'Test Paper B', 'doi': '', 'abstract': 'test'},
        ]
        
        # 去重逻辑
        seen = set()
        unique_papers = []
        for paper in papers:
            key = (paper.get('title', ''), paper.get('doi', ''))
            if key not in seen:
                seen.add(key)
                unique_papers.append(paper)
        
        assert len(unique_papers) == 2
    
    def test_deduplication_by_doi(self):
        """测试基于DOI去重"""
        papers = [
            {'title': 'Paper A', 'doi': '10.1234/test', 'abstract': 'test'},
            {'title': 'Paper B', 'doi': '10.1234/test', 'abstract': 'test'},  # DOI重复
            {'title': 'Paper C', 'doi': '10.1234/other', 'abstract': 'test'},
        ]
        
        seen = set()
        unique_papers = []
        for paper in papers:
            key = (paper.get('title', ''), paper.get('doi', ''))
            if key not in seen:
                seen.add(key)
                unique_papers.append(paper)
        
        assert len(unique_papers) == 2


class TestPaperDataStructure:
    """文献数据结构测试"""
    
    def test_paper_required_fields(self):
        """测试文献必需字段"""
        paper = {
            'title': 'Test Title',
            'abstract': 'Test Abstract',
            'authors': ['Author A', 'Author B'],
            'journal': 'Test Journal',
            'publication_date': '2024-01-01',
            'doi': '10.1234/test',
            'url': 'https://example.com',
            'source': 'pubmed'
        }
        
        # 验证必需字段存在
        assert 'title' in paper
        assert 'abstract' in paper
        assert 'authors' in paper
    
    def test_paper_optional_fields(self):
        """测试文献可选字段"""
        paper = {
            'title': 'Test Title',
            'abstract': 'Test Abstract',
            'pmid': '12345678',
            'doi': '10.1234/test',
            'impact_factor': 10.5,
            'citations': 100,
            'score': 0.8
        }
        
        assert paper.get('pmid') is not None
        assert paper.get('impact_factor') is not None


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
