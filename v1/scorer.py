import re
from typing import Dict, List, Tuple
from collections import Counter

class KeywordScorer:
    """关键词评分系统 - 根据关键词匹配度为文献评分"""
    
    def __init__(self):
        # 定义核心关键词及其权重
        self.keywords_config = {
            # 核心关键词 - 高权重
            'targeted protein degradation': {
                'weight': 3.0,
                'aliases': ['tpd', 'targeted degradation', 'protein degradation', 'degrader'],
                'category': 'core'
            },
            'protac': {
                'weight': 3.0,
                'aliases': ['protacs', 'proteolysis targeting chimera'],
                'category': 'core'
            },
            'molecular glue': {
                'weight': 3.0,
                'aliases': ['molecular glues', 'glue degrader', 'molecular glue degrader'],
                'category': 'core'
            },
            
            # 重要相关词 - 中等权重
            'ubiquitin': {
                'weight': 2.0,
                'aliases': ['ubiquitylation', 'ubiquitination', 'ubiquitin-proteasome'],
                'category': 'important'
            },
            'proteasome': {
                'weight': 2.0,
                'aliases': ['26s proteasome', 'proteasomal'],
                'category': 'important'
            },
            'e3 ligase': {
                'weight': 2.0,
                'aliases': ['ubiquitin ligase', 'e3 ubiquitin ligase', 'e3 ligases'],
                'category': 'important'
            },
            'von hippel-lindau': {
                'weight': 2.0,
                'aliases': ['vhl', 'vhl ligase'],
                'category': 'important'
            },
            'cereblon': {
                'weight': 2.0,
                'aliases': ['crbn', 'cr4bn'],
                'category': 'important'
            },
            
            # 相关技术词 - 较低权重
            'degron': {
                'weight': 1.5,
                'aliases': ['degrons', 'degron-tag'],
                'category': 'related'
            },
            'induced proximity': {
                'weight': 1.5,
                'aliases': ['proximity-induced'],
                'category': 'related'
            },
            'arvinas': {
                'weight': 1.0,
                'aliases': [],
                'category': 'related'
            },
            'lenalidomide': {
                'weight': 1.0,
                'aliases': ['pomalidomide', 'thalidomide', 'imids'],
                'category': 'related'
            },
            'lethal': {
                'weight': 1.0,
                'aliases': ['lethality'],
                'category': 'related'
            }
        }
        
        # 编译正则表达式以提高性能
        self._compile_patterns()
    
    def _compile_patterns(self):
        """编译关键词匹配模式"""
        self.patterns = {}
        
        for keyword, config in self.keywords_config.items():
            # 主关键词模式
            escaped_kw = re.escape(keyword.lower())
            self.patterns[keyword] = re.compile(r'\b' + escaped_kw + r'\b', re.IGNORECASE)
            
            # 别名模式
            for alias in config.get('aliases', []):
                escaped_alias = re.escape(alias.lower())
                self.patterns[alias] = re.compile(r'\b' + escaped_alias + r'\b', re.IGNORECASE)
    
    def score_paper(self, title: str, abstract: str, user_keywords: List[str] = None) -> Tuple[float, Dict]:
        """
        为单篇文献评分
        
        Args:
            title: 文献标题
            abstract: 文献摘要
            user_keywords: 用户自定义关键词列表（可选）
        
        Returns:
            tuple: (总分, 匹配详情)
        """
        text = f"{title} {abstract}".lower()
        total_score = 0.0
        matches = {
            'core': [],
            'important': [],
            'related': []
        }
        
        matched_keywords = set()  # 避免重复计算
        
        # 如果提供了用户关键词，优先使用用户关键词进行评分
        if user_keywords:
            for keyword in user_keywords:
                keyword_lower = keyword.lower()
                # 检查关键词出现次数
                count = text.count(keyword_lower)
                if count > 0:
                    # 标题匹配权重更高
                    weight = 3.0 if keyword_lower in title.lower() else 1.5
                    score = weight * count
                    total_score += score
                    matches['core'].append({
                        'keyword': keyword,
                        'count': count,
                        'score': score
                    })
                    matched_keywords.add(keyword)
        
        # 也检查预设关键词配置
        for keyword, config in self.keywords_config.items():
            weight = config['weight']
            category = config['category']
            aliases = config.get('aliases', [])
            
            # 检查主关键词
            main_matches = len(self.patterns[keyword].findall(text))
            if main_matches > 0 and keyword not in matched_keywords:
                score = weight * main_matches
                total_score += score
                matches[category].append({
                    'keyword': keyword,
                    'count': main_matches,
                    'score': score
                })
                matched_keywords.add(keyword)
            
            # 检查别名
            for alias in aliases:
                alias_matches = len(self.patterns[alias].findall(text))
                if alias_matches > 0 and keyword not in matched_keywords:
                    score = weight * alias_matches * 0.8  # 别名权重略低
                    total_score += score
                    matches[category].append({
                        'keyword': alias,
                        'count': alias_matches,
                        'score': score,
                        'is_alias': True
                    })
                    matched_keywords.add(keyword)
        
        # 标题加分（标题中出现核心词权重更高）
        title_bonus = self._calculate_title_bonus(title.lower())
        total_score += title_bonus
        
        # 归一化到0-1范围
        normalized_score = min(total_score / 10.0, 1.0)
        
        return normalized_score, {
            'total_score': normalized_score,
            'raw_score': total_score,
            'matches': matches,
            'title_bonus': title_bonus
        }
    
    def _calculate_title_bonus(self, title: str) -> float:
        """计算标题匹配加分"""
        bonus = 0.0
        
        for keyword, config in self.keywords_config.items():
            if config['category'] == 'core' and keyword in title:
                bonus += 0.5
            elif config['category'] == 'important' and keyword in title:
                bonus += 0.3
        
        return bonus
    
    def score_papers(self, papers: List[Dict], user_keywords: List[str] = None) -> List[Dict]:
        """
        为多篇文献评分
        
        Args:
            papers: 文献列表，每项为包含title和abstract的字典
            user_keywords: 用户自定义关键词列表（可选）
            
        Returns:
            添加了score和keyword_matches字段的文献列表
        """
        scored_papers = []
        
        for paper in papers:
            title = paper.get('title', '')
            abstract = paper.get('abstract', '')
            
            score, details = self.score_paper(title, abstract, user_keywords)
            
            paper_copy = paper.copy()
            paper_copy['keywords_score'] = score
            paper_copy['keyword_matches'] = details['matches']
            
            scored_papers.append(paper_copy)
        
        # 按评分排序
        scored_papers.sort(key=lambda x: x['keywords_score'], reverse=True)
        
        return scored_papers
    
    def filter_by_threshold(self, papers: List[Dict], threshold: float = 0.3) -> List[Dict]:
        """
        根据阈值过滤低分文献
        
        Args:
            papers: 文献列表
            threshold: 评分阈值（0-1）
            
        Returns:
            评分高于阈值的文献列表
        """
        return [p for p in papers if p.get('keywords_score', 0) >= threshold]
    
    def get_score_breakdown(self, paper: Dict) -> str:
        """获取评分详细说明"""
        matches = paper.get('keyword_matches', {})
        score = paper.get('keywords_score', 0)
        
        breakdown = f"关键词评分: {score:.2f}\n\n"
        
        if matches.get('core'):
            breakdown += "核心匹配:\n"
            for m in matches['core']:
                breakdown += f"  - {m['keyword']}: {m['count']}次 (得分: {m['score']:.2f})\n"
        
        if matches.get('important'):
            breakdown += "\n重要匹配:\n"
            for m in matches['important']:
                breakdown += f"  - {m['keyword']}: {m['count']}次 (得分: {m['score']:.2f})\n"
        
        if matches.get('related'):
            breakdown += "\n相关匹配:\n"
            for m in matches['related']:
                breakdown += f"  - {m['keyword']}: {m['count']}次 (得分: {m['score']:.2f})\n"
        
        return breakdown

# 创建全局实例
scorer = KeywordScorer()
