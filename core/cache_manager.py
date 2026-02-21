#!/usr/bin/env python3
"""
智能缓存系统 - V2.6 混合缓存版本
- 第一层：内存缓存（高速，TTL/LRU）
- 第二层：SQLite（持久化，WAL模式）
- 大幅降低磁盘I/O，提升并发性能
"""

import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from models.database import get_db_session, Paper, SearchCache, AnalysisCache, KeywordIndex
# V2.6 新增：内存缓存
from core.memory_cache import get_memory_cache

import os

class SmartCache:
    """
    智能缓存管理器 - V2.6 混合缓存版本
    - 内存缓存优先（微秒级响应）
    - SQLite 持久化（防止数据丢失）
    - 自动同步两层缓存
    """
    
    def __init__(self, db_path='data/literature.db'):
        # 使用项目根目录的绝对路径（core的上级目录）
        if not os.path.isabs(db_path):
            # 获取项目根目录（core的上级目录）
            core_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(core_dir)
            self.db_path = os.path.join(project_root, db_path)
        else:
            self.db_path = db_path
        
        # 确保目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        # V2.6 新增：内存缓存实例
        self.memory_cache = get_memory_cache()
    
    def _get_session(self):
        """获取数据库会话"""
        return get_db_session(self.db_path)
    
    def _get_paper_hash(self, paper: Dict) -> str:
        """
        生成文献的唯一哈希值
        基于DOI、PMID或标题
        """
        doi = paper.get('doi', '')
        pmid = paper.get('pmid', '')
        title = paper.get('title', '').lower().strip()
        
        # 优先使用DOI，其次是PMID，最后是标题
        if doi:
            return hashlib.md5(f"doi:{doi}".encode()).hexdigest()
        elif pmid:
            return hashlib.md5(f"pmid:{pmid}".encode()).hexdigest()
        else:
            return hashlib.md5(f"title:{title}".encode()).hexdigest()
    
    def _get_search_hash(self, keywords: List[str], days_back: int) -> str:
        """生成搜索请求的哈希值"""
        search_str = f"{sorted([k.lower() for k in keywords])}:{days_back}"
        return hashlib.md5(search_str.encode()).hexdigest()
    
    def _get_analysis_hash(self, title: str, abstract: str) -> str:
        """生成分析请求的哈希值"""
        text = f"{title.lower().strip()}:{abstract.lower().strip()[:500]}"
        return hashlib.md5(text.encode()).hexdigest()
    
    def get_cached_paper(self, paper_hash: str) -> Optional[Dict]:
        """
        获取缓存的文献 - V2.6 优先查内存缓存
        
        Returns:
            文献数据或None
        """
        # V2.6 优化：先查内存缓存（微秒级）
        cached = self.memory_cache.get('paper', paper_hash)
        if cached is not None:
            return cached
        
        # 内存未命中，查数据库
        db = self._get_session()
        try:
            paper = db.query(Paper).filter(Paper.id == paper_hash).first()
            
            if paper:
                # 检查缓存是否过期（30天）
                if paper.created_at and (datetime.now() - paper.created_at) < timedelta(days=30):
                    paper_dict = self._paper_to_dict(paper)
                    # V2.6 优化：写入内存缓存
                    self.memory_cache.set('paper', paper_hash, paper_dict)
                    return paper_dict
                else:
                    # 过期，删除
                    db.delete(paper)
                    db.commit()
            
            return None
        finally:
            db.close()
    
    def cache_paper(self, paper: Dict) -> str:
        """
        缓存文献 - V2.6 同时写入内存和数据库
        
        Returns:
            文献的哈希值
        """
        paper_hash = self._get_paper_hash(paper)
        
        # V2.6 优化：先写入内存缓存（微秒级）
        self.memory_cache.set('paper', paper_hash, paper)
        
        # 再写入数据库（持久化）
        db = self._get_session()
        try:
            # 检查是否已存在
            existing = db.query(Paper).filter(Paper.id == paper_hash).first()
            
            if not existing:
                new_paper = Paper(
                    id=paper_hash,
                    title=paper.get('title', ''),
                    abstract=paper.get('abstract', ''),
                    abstract_cn=paper.get('abstract_cn', ''),
                    authors=paper.get('authors', []),
                    journal=paper.get('journal', ''),
                    pub_date=paper.get('publication_date', '') or paper.get('pub_date', ''),
                    doi=paper.get('doi', ''),
                    pmid=paper.get('pmid', ''),
                    url=paper.get('url', ''),
                    source=paper.get('source', ''),
                    main_findings=paper.get('main_findings', ''),
                    innovations=paper.get('innovations', ''),
                    limitations=paper.get('limitations', ''),
                    future_directions=paper.get('future_directions', ''),
                    is_analyzed=paper.get('is_analyzed', False),
                    impact_factor=paper.get('impact_factor'),
                    citations=paper.get('citations', 0),
                    score=paper.get('score', 0.0),
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                db.add(new_paper)
                db.commit()
            
            return paper_hash
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def get_cached_search(self, keywords: List[str], days_back: int) -> Optional[List[str]]:
        """
        获取缓存的搜索结果 - V2.6 优先查内存缓存
        
        Returns:
            文献哈希值列表或None
        """
        search_hash = self._get_search_hash(keywords, days_back)
        
        # V2.6 优化：先查内存缓存（微秒级）
        cached = self.memory_cache.get('search', search_hash)
        if cached is not None:
            return cached
        
        # 内存未命中，查数据库
        db = self._get_session()
        try:
            cache_entry = db.query(SearchCache).filter(SearchCache.id == search_hash).first()
            
            if cache_entry:
                # 搜索缓存48小时有效（2天）
                if cache_entry.created_at and (datetime.now() - cache_entry.created_at) < timedelta(hours=48):
                    paper_ids = cache_entry.paper_ids
                    # V2.6 优化：写入内存缓存
                    self.memory_cache.set('search', search_hash, paper_ids)
                    return paper_ids
                else:
                    # 过期，删除
                    db.delete(cache_entry)
                    db.commit()
            
            return None
        finally:
            db.close()
    
    def cache_search_results(self, keywords: List[str], days_back: int,
                           paper_hashes: List[str]):
        """缓存搜索结果 - V2.6 同时写入内存和数据库"""
        search_hash = self._get_search_hash(keywords, days_back)

        # V2.6 优化：先写入内存缓存（微秒级）
        self.memory_cache.set('search', search_hash, paper_hashes)

        # 再写入数据库（持久化）
        db = self._get_session()
        try:
            # 检查是否已存在
            existing = db.query(SearchCache).filter(SearchCache.id == search_hash).first()

            if existing:
                existing.paper_ids = paper_hashes
                existing.created_at = datetime.now()
                existing.expires_at = datetime.now() + timedelta(hours=48)  # 48小时过期
            else:
                new_cache = SearchCache(
                    id=search_hash,
                    keywords=keywords,
                    days_back=days_back,
                    paper_ids=paper_hashes,
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=48)  # 48小时过期
                )
                db.add(new_cache)

            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def get_cached_analysis(self, title: str, abstract: str) -> Optional[Dict]:
        """
        获取缓存的AI分析结果 - V2.6 优先查内存缓存

        Returns:
            分析结果或None
        """
        analysis_hash = self._get_analysis_hash(title, abstract)

        # V2.6 优化：先查内存缓存（微秒级）
        cached = self.memory_cache.get('analysis', analysis_hash)
        if cached is not None:
            return cached

        # 内存未命中，查数据库
        db = self._get_session()
        try:
            cache_entry = db.query(AnalysisCache).filter(AnalysisCache.id == analysis_hash).first()

            if cache_entry:
                # 分析结果90天有效
                if cache_entry.created_at and (datetime.now() - cache_entry.created_at) < timedelta(days=90):
                    result = {
                        'main_findings': cache_entry.main_findings,
                        'innovations': cache_entry.innovations,
                        'limitations': cache_entry.limitations,
                        'future_directions': cache_entry.future_directions,
                        'abstract_cn': cache_entry.abstract_cn
                    }
                    # V2.6 优化：写入内存缓存
                    self.memory_cache.set('analysis', analysis_hash, result)
                    return result

            return None
        finally:
            db.close()
    
    def cache_analysis(self, title: str, abstract: str, analysis: Dict, paper_hash: str = None):
        """缓存AI分析结果 - V2.6 同时写入内存和数据库"""
        analysis_hash = self._get_analysis_hash(title, abstract)

        # 如果没有传入 paper_hash，尝试使用 analysis_hash（兼容旧逻辑）
        if not paper_hash:
            paper_hash = analysis_hash

        # 辅助函数：确保值为字符串
        def to_str(value):
            if value is None:
                return ''
            # 处理元组和列表
            if isinstance(value, (tuple, list)):
                if len(value) == 0:
                    return ''
                # 递归处理元素（可能是嵌套结构）
                return to_str(value[0])
            # 处理字典（JSON解析可能产生）
            if isinstance(value, dict):
                # 尝试获取字符串值
                for k in ['main_findings', 'innovations', 'limitations', 'future_directions', 'abstract_cn']:
                    if k in value and value[k]:
                        return to_str(value[k])
                return str(value)
            return str(value) if value else ''

        # 提取并转换分析结果
        main_findings = to_str(analysis.get('main_findings', ''))
        innovations = to_str(analysis.get('innovations', ''))
        limitations = to_str(analysis.get('limitations', ''))
        future_directions = to_str(analysis.get('future_directions', ''))
        abstract_cn = to_str(analysis.get('abstract_cn', ''))

        # V2.6 优化：先写入内存缓存（微秒级）
        cache_data = {
            'main_findings': main_findings,
            'innovations': innovations,
            'limitations': limitations,
            'future_directions': future_directions,
            'abstract_cn': abstract_cn
        }
        self.memory_cache.set('analysis', analysis_hash, cache_data)

        # 再写入数据库（持久化）
        db = self._get_session()
        try:
            # 1. 保存到 analysis_cache 表
            existing = db.query(AnalysisCache).filter(AnalysisCache.id == analysis_hash).first()
            
            if existing:
                existing.main_findings = main_findings
                existing.innovations = innovations
                existing.limitations = limitations
                existing.future_directions = future_directions
                existing.abstract_cn = abstract_cn
            else:
                new_cache = AnalysisCache(
                    id=analysis_hash,
                    title=title[:100],
                    abstract=abstract[:500] if abstract else '',
                    main_findings=main_findings,
                    innovations=innovations,
                    limitations=limitations,
                    future_directions=future_directions,
                    abstract_cn=abstract_cn,
                    created_at=datetime.now()
                )
                db.add(new_cache)
            
            # 2. 同时更新 papers 表（使用传入的 paper_hash）
            if paper_hash:
                paper = db.query(Paper).filter(Paper.id == paper_hash).first()
                if paper:
                    paper.is_analyzed = True
                    paper.main_findings = main_findings
                    paper.innovations = innovations
                    paper.limitations = limitations
                    paper.future_directions = future_directions
                    paper.abstract_cn = abstract_cn
            
            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def index_paper_keywords(self, paper_hash: str, keywords: List[str]):
        """
        索引文献的关键词
        用于快速检索匹配用户的文献
        """
        db = self._get_session()
        try:
            for keyword in keywords:
                kw_lower = keyword.lower()
                
                # 检查是否已存在
                existing = db.query(KeywordIndex).filter(
                    KeywordIndex.keyword == kw_lower,
                    KeywordIndex.paper_id == paper_hash
                ).first()
                
                if not existing:
                    new_index = KeywordIndex(
                        keyword=kw_lower,
                        paper_id=paper_hash
                    )
                    db.add(new_index)
            
            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def find_papers_by_keywords(self, user_keywords: List[str], limit: int = None) -> List[str]:
        """
        根据用户关键词查找匹配的文献 - 智能匹配算法 V2.5
        
        改进点:
        1. 相关性评分: 精确匹配 > 部分匹配 > 相关词匹配
        2. 多关键词组合: 匹配关键词越多的文献排名越高
        3. 跨用户共享: 利用所有已索引的文献
        
        Args:
            user_keywords: 用户的关键词列表
            limit: 返回的最大文献数量(可选)
        
        Returns:
            按相关性排序的文献哈希值列表
        """
        if not user_keywords:
            return []
        
        db = self._get_session()
        try:
            # 相关性评分字典: {paper_hash: score}
            paper_scores = {}
            
            # 记录每篇文献匹配到的关键词
            paper_matched_keywords = {}
            
            for keyword in user_keywords:
                kw_lower = keyword.lower().strip()
                if not kw_lower:
                    continue
                
                # 1. 精确匹配 (权重: 10分)
                exact_matches = db.query(KeywordIndex).filter(
                    KeywordIndex.keyword == kw_lower
                ).all()
                
                for match in exact_matches:
                    paper_id = match.paper_id
                    paper_scores[paper_id] = paper_scores.get(paper_id, 0) + 10
                    if paper_id not in paper_matched_keywords:
                        paper_matched_keywords[paper_id] = set()
                    paper_matched_keywords[paper_id].add(keyword)
                
                # 2. 部分匹配 - 开头匹配 (权重: 5分)
                # 如搜索 "cancer" 匹配 "cancer therapy"
                prefix_matches = db.query(KeywordIndex).filter(
                    KeywordIndex.keyword.like(f'{kw_lower} %')
                ).all()
                
                for match in prefix_matches:
                    paper_id = match.paper_id
                    paper_scores[paper_id] = paper_scores.get(paper_id, 0) + 5
                    if paper_id not in paper_matched_keywords:
                        paper_matched_keywords[paper_id] = set()
                    paper_matched_keywords[paper_id].add(keyword)
                
                # 3. 部分匹配 - 包含匹配 (权重: 3分)
                # 如搜索 "therapy" 匹配 "cancer therapy"
                contains_matches = db.query(KeywordIndex).filter(
                    KeywordIndex.keyword.like(f'% {kw_lower} %')
                ).all()
                
                for match in contains_matches:
                    paper_id = match.paper_id
                    paper_scores[paper_id] = paper_scores.get(paper_id, 0) + 3
                    if paper_id not in paper_matched_keywords:
                        paper_matched_keywords[paper_id] = set()
                    paper_matched_keywords[paper_id].add(keyword)
            
            # 4. 多关键词匹配奖励
            # 匹配的关键词越多,额外加分越多 (鼓励多关键词匹配)
            for paper_id, matched_kws in paper_matched_keywords.items():
                match_count = len(matched_kws)
                if match_count >= 2:
                    # 匹配2个关键词: +5分, 3个: +10分, 4个: +15分...
                    bonus = (match_count - 1) * 5
                    paper_scores[paper_id] = paper_scores.get(paper_id, 0) + bonus
            
            # 5. 按相关性评分排序
            sorted_papers = sorted(
                paper_scores.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            # 只返回paper_hash列表
            result = [paper_id for paper_id, score in sorted_papers]
            
            # 如果指定了limit,只返回前N个
            if limit and limit > 0:
                result = result[:limit]
            
            print(f"[智能匹配] 找到 {len(result)} 篇相关文献, 关键词: {user_keywords}")
            
            return result
            
        finally:
            db.close()
    
    def get_cache_stats(self) -> Dict:
        """获取缓存统计信息"""
        db = self._get_session()
        try:
            total_papers = db.query(Paper).count()
            total_analysis = db.query(AnalysisCache).count()
            total_searches = db.query(SearchCache).count()
            # 使用 group_by 代替 distinct
            from sqlalchemy import func
            total_keywords = db.query(KeywordIndex.keyword).group_by(KeywordIndex.keyword).count()
            
            # 计算节省的API调用次数
            api_calls_saved = total_analysis
            
            # 估算节省的费用（DeepSeek API大约每1000tokens $0.001）
            # 假设平均每篇文献分析使用2000 tokens
            estimated_savings = total_analysis * 2000 * 0.001 / 1000
            
            return {
                'cached_papers': total_papers,
                'cached_analysis': total_analysis,
                'cached_searches': total_searches,
                'api_calls_saved': api_calls_saved,
                'estimated_cost_savings_usd': round(estimated_savings, 4),
                'keywords_indexed': total_keywords
            }
        finally:
            db.close()
    
    def get_total_papers_count(self) -> int:
        """获取系统中所有文献的总数量"""
        db = self._get_session()
        try:
            return db.query(Paper).count()
        finally:
            db.close()
    
    def cleanup_old_cache(self, days: int = 30):
        """
        清理旧缓存
        
        Args:
            days: 清理超过多少天的缓存
        """
        db = self._get_session()
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            analysis_cutoff = datetime.now() - timedelta(days=90)
            
            # 清理文献缓存
            papers_to_remove = db.query(Paper).filter(Paper.created_at < cutoff_date).all()
            papers_count = len(papers_to_remove)
            for paper in papers_to_remove:
                db.delete(paper)
            
            # 清理搜索缓存
            searches_to_remove = db.query(SearchCache).filter(SearchCache.created_at < cutoff_date).all()
            searches_count = len(searches_to_remove)
            for search in searches_to_remove:
                db.delete(search)
            
            # 清理分析缓存（保留更长时间）
            analysis_to_remove = db.query(AnalysisCache).filter(AnalysisCache.created_at < analysis_cutoff).all()
            analysis_count = len(analysis_to_remove)
            for analysis in analysis_to_remove:
                db.delete(analysis)
            
            db.commit()
            
            return {
                'removed_papers': papers_count,
                'removed_searches': searches_count,
                'removed_analysis': analysis_count
            }
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def get_paper(self, paper_hash: str) -> Optional[Dict]:
        """获取单篇文献"""
        db = self._get_session()
        try:
            paper = db.query(Paper).filter(Paper.id == paper_hash).first()
            if paper:
                return self._paper_to_dict(paper)
            return None
        finally:
            db.close()
    
    def batch_get_papers(self, paper_hashes: List[str]) -> List[Dict]:
        """批量获取缓存的文献"""
        db = self._get_session()
        try:
            papers = []
            for paper_hash in paper_hashes:
                paper = db.query(Paper).filter(Paper.id == paper_hash).first()
                if paper:
                    papers.append(self._paper_to_dict(paper))
            return papers
        finally:
            db.close()
    
    def get_all_papers(self, limit: int = None) -> List[Dict]:
        """获取所有缓存的文献"""
        db = self._get_session()
        try:
            query = db.query(Paper)
            if limit:
                query = query.limit(limit)
            papers = query.all()
            return [self._paper_to_dict(paper) for paper in papers]
        finally:
            db.close()
    
    @property
    def papers_cache(self) -> Dict[str, Dict]:
        """兼容属性 - 返回所有文献的字典格式"""
        papers = self.get_all_papers()
        return {paper['hash']: paper for paper in papers}
    
    def get_popular_keywords(self, limit: int = 20) -> List[Dict]:
        """
        获取最热门的关键词
        用于优化搜索策略
        """
        db = self._get_session()
        try:
            from sqlalchemy import func
            
            # 按关键词分组统计
            keyword_stats = db.query(
                KeywordIndex.keyword,
                func.count(KeywordIndex.paper_id).label('paper_count')
            ).group_by(KeywordIndex.keyword).order_by(func.count(KeywordIndex.paper_id).desc()).limit(limit).all()
            
            return [
                {
                    'keyword': kw.keyword,
                    'paper_count': kw.paper_count
                }
                for kw in keyword_stats
            ]
        finally:
            db.close()
    
    def _paper_to_dict(self, paper: Paper) -> Dict:
        """将Paper对象转换为字典"""
        # 处理created_at字段（可能是datetime对象或字符串）
        cached_at = None
        if paper.created_at:
            if hasattr(paper.created_at, 'isoformat'):
                cached_at = paper.created_at.isoformat()
            else:
                cached_at = str(paper.created_at)
        
        return {
            'id': paper.id,
            'title': paper.title,
            'abstract': paper.abstract,
            'abstract_cn': paper.abstract_cn,
            'authors': paper.authors,
            'journal': paper.journal,
            'pub_date': paper.pub_date,
            'publication_date': paper.pub_date,
            'doi': paper.doi,
            'pmid': paper.pmid,
            'url': paper.url,
            'source': paper.source,
            'main_findings': paper.main_findings,
            'innovations': paper.innovations,
            'limitations': paper.limitations,
            'future_directions': paper.future_directions,
            'is_analyzed': paper.is_analyzed,
            'impact_factor': paper.impact_factor,
            'citations': paper.citations,
            'score': paper.score,
            'paper_type': getattr(paper, 'paper_type', 'research'),
            'hash': paper.id,
            'cached_at': cached_at
        }


class CacheOptimizer:
    """
    缓存优化器
    用于智能合并和优化缓存
    """
    
    def __init__(self, cache: SmartCache):
        self.cache = cache
    
    def merge_similar_keywords(self, similarity_threshold: float = 0.8) -> int:
        """
        合并相似的关键词
        减少重复索引
        """
        # 在SQLite版本中，这个功能可以通过SQL查询实现
        # 暂时返回0，表示未执行
        return 0
    
    def deduplicate_papers(self) -> int:
        """
        去重文献缓存
        基于标题相似度
        """
        # 基于哈希去重（已在缓存时处理）
        return 0
    
    def optimize_storage(self):
        """优化存储空间"""
        stats_before = self.cache.get_cache_stats()
        
        # 清理旧缓存
        cleanup_result = self.cache.cleanup_old_cache(days=30)
        
        # 合并相似关键词
        merged_keywords = self.merge_similar_keywords()
        
        stats_after = self.cache.get_cache_stats()
        
        return {
            'before': stats_before,
            'after': stats_after,
            'cleanup': cleanup_result,
            'merged_keywords': merged_keywords
        }
