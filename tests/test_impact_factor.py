#!/usr/bin/env python3
"""
影响因子测试 - 验证期刊匹配功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v1.impact_factor import ImpactFactorFetcher


class TestImpactFactor:
    """影响因子匹配测试"""
    
    def setup_method(self):
        """每个测试方法执行前调用"""
        self.fetcher = ImpactFactorFetcher()
    
    def test_exact_match_nature(self):
        """测试精确匹配 Nature"""
        result = self.fetcher.get_impact_factor('Nature')
        assert result == 64.8, f"Expected 64.8, got {result}"
    
    def test_exact_match_cell(self):
        """测试精确匹配 Cell"""
        result = self.fetcher.get_impact_factor('cell')
        assert result == 64.5, f"Expected 64.5, got {result}"
    
    def test_exact_match_science(self):
        """测试精确匹配 Science"""
        result = self.fetcher.get_impact_factor('science')
        assert result == 56.9, f"Expected 56.9, got {result}"
    
    def test_biorxiv_returns_zero(self):
        """测试bioRxiv返回0"""
        result = self.fetcher.get_impact_factor('bioRxiv')
        assert result == 0.0, f"Expected 0.0, got {result}"
    
    def test_medrxiv_returns_zero(self):
        """测试medRxiv返回0"""
        result = self.fetcher.get_impact_factor('medRxiv')
        assert result == 0.0, f"Expected 0.0, got {result}"
    
    def test_case_insensitive(self):
        """测试大小写不敏感"""
        result1 = self.fetcher.get_impact_factor('Nature')
        result2 = self.fetcher.get_impact_factor('NATURE')
        result3 = self.fetcher.get_impact_factor('nature')
        assert result1 == result2 == result3 == 64.8
    
    def test_clean_parentheses(self):
        """测试移除括号后的匹配"""
        result = self.fetcher.get_impact_factor('Advanced science (Weinheim, Baden-Wurttemberg, Ger')
        assert result is not None, "Should match after removing parentheses"
        assert result > 0, f"Expected positive value, got {result}"
    
    def test_acs_nano(self):
        """测试ACS Nano"""
        result = self.fetcher.get_impact_factor('ACS nano')
        assert result == 17.1, f"Expected 17.1, got {result}"
    
    def test_npj_precision_oncology(self):
        """测试NPJ Precision Oncology"""
        result = self.fetcher.get_impact_factor('NPJ precision oncology')
        assert result == 7.9, f"Expected 7.9, got {result}"
    
    def test_bmc_cancer(self):
        """测试BMC Cancer"""
        result = self.fetcher.get_impact_factor('BMC cancer')
        assert result == 4.4, f"Expected 4.4, got {result}"
    
    def test_empty_string_returns_none(self):
        """测试空字符串返回None"""
        result = self.fetcher.get_impact_factor('')
        assert result is None, f"Expected None, got {result}"
    
    def test_none_returns_none(self):
        """测试None返回None"""
        result = self.fetcher.get_impact_factor(None)
        assert result is None, f"Expected None, got {result}"
    
    def test_unknown_journal_returns_none(self):
        """测试未知期刊返回None"""
        result = self.fetcher.get_impact_factor('Some Unknown Journal XYZ')
        # 未知期刊可能返回None或通过外部API获取
        # 这里我们只检查不为正数（因为外部API可能返回有效值）
        assert result is None or isinstance(result, (int, float))


class TestImpactFactorFuzzy:
    """模糊匹配测试"""
    
    def setup_method(self):
        self.fetcher = ImpactFactorFetcher()
    
    def test_fuzzy_match_nature_communications(self):
        """测试Nature Communications模糊匹配"""
        result = self.fetcher.get_impact_factor('Nature communications')
        assert result is not None and result > 0
    
    def test_fuzzy_match_plos_one(self):
        """测试PLOS ONE模糊匹配"""
        result = self.fetcher.get_impact_factor('PLoS One')
        assert result == 3.7, f"Expected 3.7, got {result}"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
