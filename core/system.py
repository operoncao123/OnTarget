#!/usr/bin/env python3
"""
V2主应用 - 带用户系统的文献推送系统
"""

import os
import sys

# 首先添加项目根目录到Python路径
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 添加项目祖父目录（包含v1模块）
grandparent_dir = os.path.dirname(parent_dir)
if grandparent_dir not in sys.path:
    sys.path.insert(0, grandparent_dir)

from datetime import datetime
from typing import Dict, List

# 加载环境变量（使用绝对路径）
_current_dir = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(_current_dir, '.env')
if os.path.exists(env_file):
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# 导入本地模块（新目录结构）
from models.user_manager import UserManager, get_predefined_categories, expand_keywords
from core.cache_manager import SmartCache, CacheOptimizer
from services.push_service import PersonalizedPushEngine, PushScheduler
from core.analyzer import OptimizedAnalyzer, AnalysisQueue
from models.keyword_group_manager import KeywordGroupManager

# 导入v1模块（复用fetcher和scorer）- 从项目根目录
from v1.fetcher import PaperFetcher
from v1.scorer import scorer
from v1.impact_factor import ImpactFactorFetcher

class LiteraturePushSystemV2:
    """
    V2文献推送系统
    新特性：
    - 用户注册和管理
    - 关键词选择和分类
    - 智能缓存避免重复分析
    - 个性化推送
    - API消耗优化
    """
    
    def __init__(self, data_dir='v2/data'):
        self.data_dir = data_dir
        
        # 初始化各模块
        self.user_manager = UserManager(data_dir)
        self.cache = SmartCache(os.path.join(data_dir, 'literature.db'))
        self.push_engine = PersonalizedPushEngine(data_dir)
        self.analyzer = OptimizedAnalyzer(
            api_key=os.getenv('DEEPSEEK_API_KEY'),
            base_url=os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
            cache=self.cache
        )
        self.analysis_queue = AnalysisQueue(
            os.path.join(data_dir, 'analysis_queue.json')
        )
        self.cache_optimizer = CacheOptimizer(self.cache)
        self.push_scheduler = PushScheduler(self.push_engine)
        
        # 初始化Fetcher（复用v1）
        pubmed_email = os.getenv('PUBMED_EMAIL', 'ontarget@example.com')
        self.fetcher = PaperFetcher(pubmed_email)
        self.impact_factor_fetcher = ImpactFactorFetcher()
        
        # 系统配置
        self.default_days_back = int(os.getenv('UPDATE_INTERVAL_DAYS', '7'))
        self.default_score_threshold = float(os.getenv('SCORE_THRESHOLD', '0.3'))
    
    def get_user_analyzer(self, user_id: str) -> OptimizedAnalyzer:
        """获取用户专属的分析器（使用用户的API配置，自动解密）"""
        user = self.user_manager.get_user(user_id)
        if not user:
            return self.analyzer
        
        prefs = user.get('preferences', {})
        
        # 检查用户是否有自定义API配置（使用解密后的API Key）
        decrypted_api_key = self.user_manager.get_user_api_key(user_id)
        if decrypted_api_key:
            user_api_config = {
                'provider': prefs.get('api_provider', 'deepseek'),
                'api_key': decrypted_api_key,
                'base_url': prefs.get('api_base_url'),
                'model': prefs.get('model', 'deepseek-chat')
            }
            return OptimizedAnalyzer(
                api_key=decrypted_api_key,
                base_url=prefs.get('api_base_url'),
                cache=self.cache,
                user_api_config=user_api_config
            )
        
        return self.analyzer
    
    def get_user_settings(self, user_id: str) -> Dict:
        """获取用户的更新设置"""
        user = self.user_manager.get_user(user_id)
        if not user:
            return {
                'update_frequency_days': 7,
                'max_auto_analyze': 20
            }
        
        prefs = user.get('preferences', {})
        return {
            'update_frequency_days': prefs.get('update_frequency_days', 7),
            'max_auto_analyze': prefs.get('max_auto_analyze', 20)
        }
    
    def run_for_user(self, user_id: str, days_back: int = None) -> Dict:
        """
        为特定用户运行文献获取和推送
        
        Args:
            user_id: 用户ID
            days_back: 获取多少天内的文献
        
        Returns:
            运行结果统计
        """
        # 如果未指定天数，使用用户设置或系统默认
        if days_back is None:
            user_settings = self.get_user_settings(user_id)
            days_back = user_settings.get('update_frequency_days', self.default_days_back)
        
        # 获取用户信息
        user = self.user_manager.get_user(user_id)
        if not user:
            return {'success': False, 'error': '用户不存在'}
        
        # 获取用户选择的文献源
        user_sources = self.user_manager.get_user_sources(user_id)
        
        # 使用关键词组系统获取所有关键词
        kg_manager = KeywordGroupManager()
        user_groups = kg_manager.get_user_groups(user_id)
        
        if not user_groups:
            # 如果没有关键词组，尝试使用旧版关键词
            user_keywords = user.get('keywords', [])
            if not user_keywords:
                return {'success': False, 'error': '用户未设置关键词'}
        else:
            # 合并所有关键词组的关键词
            user_keywords = []
            for group in user_groups:
                user_keywords.extend(group.get('keywords', []))
            user_keywords = list(set(user_keywords))  # 去重
        
        if not user_keywords:
            return {'success': False, 'error': '用户未设置关键词'}
        
        print(f"\n{'='*60}")
        print(f"为用户 {user['username']} 获取文献")
        print(f"关键词组数量: {len(user_groups) if user_groups else 0}")
        print(f"合并关键词: {', '.join(user_keywords)}")
        print(f"{'='*60}\n")
        
        result = {
            'fetched': 0,
            'from_cache': 0,
            'new_analysis': 0,
            'cached_analysis': 0,
            'pushed': 0,
            'errors': []
        }
        
        try:
            # 1. 检查搜索缓存
            print("[1/5] 检查搜索缓存...")
            cached_hashes = self.cache.get_cached_search(user_keywords, days_back)
            
            papers = []
            if cached_hashes:
                print(f"✓ 从缓存获取 {len(cached_hashes)} 篇文献")
                papers = self.cache.batch_get_papers(cached_hashes)
                result['from_cache'] = len(papers)
            else:
                # 2. 从各源获取文献
                print("[2/5] 从各源获取文献...")
                print(f"   - 文献源: {', '.join(user_sources)}")
                papers = self.fetcher.fetch_all(user_keywords, days_back, sources=user_sources)
                result['fetched'] = len(papers)
                print(f"✓ 获取到 {len(papers)} 篇文献")
                
                # 将 datetime 对象转换为字符串以便 JSON 序列化
                for paper in papers:
                    if 'publication_date' in paper and hasattr(paper['publication_date'], 'isoformat'):
                        paper['publication_date'] = paper['publication_date'].isoformat()
                
                # 缓存搜索结果 - 批量缓存到SQLite数据库
                paper_hashes = []
                current_time = datetime.now().isoformat()
                for paper in papers:
                    paper_hash = self.cache._get_paper_hash(paper)
                    paper_hashes.append(paper_hash)
                    
                    # 添加到数据库缓存
                    paper['cached_at'] = current_time
                    paper['hash'] = paper_hash
                    self.cache.cache_paper(paper)
                    
                    # 索引关键词
                    matched_keywords = self._extract_matched_keywords(paper, user_keywords)
                    self.cache.index_paper_keywords(paper_hash, matched_keywords)
                
                # 保存搜索结果到数据库
                self.cache.cache_search_results(user_keywords, days_back, paper_hashes)
            
            # 3. 关键词评分
            print("\n[3/5] 关键词评分...")
            scored_papers = scorer.score_papers(papers, user_keywords)
            print(f"  评分完成: {len(scored_papers)} 篇")
            
            # 显示评分分布
            scores = [p['keywords_score'] for p in scored_papers]
            if scores:
                print(f"  评分范围: {min(scores):.2f} - {max(scores):.2f}")
                print(f"  平均分: {sum(scores)/len(scores):.2f}")
            
            # 将评分结果保存回数据库
            print("  更新缓存中的评分数据...")
            db = self.cache._get_session()
            try:
                from models.database import Paper
                for paper in scored_papers:
                    paper_hash = paper.get('hash')
                    if paper_hash:
                        db_paper = db.query(Paper).filter(Paper.id == paper_hash).first()
                        if db_paper:
                            db_paper.score = paper['keywords_score']
                            db_paper.updated_at = datetime.now()
                db.commit()
            finally:
                db.close()
            print(f"  ✓ 已更新 {len(scored_papers)} 篇文献的评分")
            
            # 暂时不过滤，让所有文献都通过（后续个性化推送会再筛选）
            filtered_papers = scored_papers
            print(f"✓ 保留所有文献: {len(filtered_papers)} 篇")
            
            # 4. 获取影响因子
            print("\n[4/5] 获取影响因子...")
            papers_with_if = self.impact_factor_fetcher.batch_get_impact_factors(
                filtered_papers
            )
            
            # 将影响因子保存到数据库
            print("  保存影响因子到缓存...")
            db = self.cache._get_session()
            try:
                from models.database import Paper
                for paper in papers_with_if:
                    paper_hash = paper.get('hash')
                    if paper_hash:
                        db_paper = db.query(Paper).filter(Paper.id == paper_hash).first()
                        if db_paper:
                            db_paper.impact_factor = paper.get('impact_factor')
                            db_paper.journal = paper.get('journal', db_paper.journal)
                            db_paper.updated_at = datetime.now()
                db.commit()
            finally:
                db.close()
            print(f"  ✓ 已保存影响因子")
            
            # 5. 智能分析（自动分析未缓存的文献）
            print("\n[5/5] AI分析未缓存的文献...")
            
            # 获取用户设置
            user_settings = self.get_user_settings(user_id)
            max_auto_analyze = user_settings.get('max_auto_analyze', 20)
            
            # 获取用户专属的分析器
            user_analyzer = self.get_user_analyzer(user_id)
            
            all_papers = []
            cached_count = 0
            new_analysis_count = 0
            
            papers_to_analyze = []
            
            for paper in papers_with_if:
                cached_analysis = self.cache.get_cached_analysis(
                    paper.get('title', ''),
                    paper.get('abstract', '')
                )
                
                if cached_analysis:
                    paper.update(cached_analysis)
                    paper['is_analyzed'] = True
                    cached_count += 1
                else:
                    # 新文献加入待分析列表
                    papers_to_analyze.append(paper)
                    paper['is_analyzed'] = False
                    paper['main_findings'] = ''
                    paper['innovations'] = ''
                    paper['limitations'] = ''
                    paper['future_directions'] = ''
                    paper['abstract_cn'] = ''
                
                all_papers.append(paper)
            
            # 自动分析未缓存的文献
            if papers_to_analyze and user_analyzer:
                analyze_count = 0
                for paper in papers_to_analyze:
                    if analyze_count >= max_auto_analyze:
                        print(f"  - 已自动分析 {analyze_count} 篇，更多文献可手动分析")
                        break
                    
                    title = paper.get('title', '')
                    abstract = paper.get('abstract', '')
                    
                    if title and abstract and len(abstract) > 50:
                        # 调用用户专属AI分析
                        analysis = user_analyzer.analyze_paper(title, abstract)
                        
                        if analysis and not analysis.get('error'):
                            # 翻译摘要（使用用户专属分析器）
                            abstract_cn = user_analyzer.translate_abstract(abstract) if len(abstract) > 50 else ''
                            
                            # 确保值为字符串
                            def to_str(v):
                                if v is None:
                                    return ''
                                if isinstance(v, (tuple, list)):
                                    return to_str(v[0]) if v else ''
                                if isinstance(v, dict):
                                    for k in ['main_findings', 'innovations', 'limitations', 'future_directions']:
                                        if k in v and v[k]:
                                            return to_str(v[k])
                                    return str(v)
                                return str(v) if v else ''
                            
                            # 更新paper对象
                            paper['main_findings'] = to_str(analysis.get('main_findings', ''))
                            paper['innovations'] = to_str(analysis.get('innovations', ''))
                            paper['limitations'] = to_str(analysis.get('limitations', ''))
                            paper['future_directions'] = to_str(analysis.get('future_directions', ''))
                            paper['abstract_cn'] = to_str(abstract_cn) if not abstract_cn.startswith('翻译失败') else ''
                            paper['is_analyzed'] = True
                            
                            # 缓存分析结果
                            self.cache.cache_analysis(title, abstract, {
                                'main_findings': paper['main_findings'],
                                'innovations': paper['innovations'],
                                'limitations': paper['limitations'],
                                'future_directions': paper['future_directions'],
                                'abstract_cn': paper['abstract_cn']
                            }, paper_hash=paper.get('hash'))
                            
                            new_analysis_count += 1
                            analyze_count += 1
                            
                            if analyze_count % 5 == 0:
                                print(f"  - 已分析 {analyze_count}/{min(len(papers_to_analyze), max_auto_analyze)} 篇...")
            
            print(f"  - 已缓存分析: {cached_count} 篇")
            print(f"  - 新增分析: {new_analysis_count} 篇")
            if len(papers_to_analyze) > max_auto_analyze:
                print(f"  - 还有 {len(papers_to_analyze) - max_auto_analyze} 篇待分析（可手动点击AI分析）")
            
            result['cached_analysis'] = cached_count
            result['new_analysis'] = new_analysis_count
            
            # 6. 生成个性化推送
            print("\n[6/6] 生成个性化推送...")
            print(f"  - 用户ID: {user_id}")
            print(f"  - 用户关键词: {user_keywords}")
            print(f"  - 可用文献数: {len(all_papers)}")
            

            
            personalized = self.push_engine.get_personalized_papers(
                user_id, user_keywords, all_papers, limit=20
            )
            result['pushed'] = len(personalized)
            print(f"\n✓ 推送 {len(personalized)} 篇个性化文献")
            

            
            # 记录推送历史
            if personalized:
                paper_hashes = [p.get('hash', '') for p in personalized]
                self.push_engine.record_push(user_id, paper_hashes, 'manual')
            
            # 更新用户统计
            self.user_manager.update_user_stats(user_id, {
                'last_paper_fetch': datetime.now().isoformat()
            })
            
        except Exception as e:
            error_msg = f"系统错误: {str(e)}"
            result['errors'].append(error_msg)
            print(f"✗ {error_msg}")
        
        # 打印统计
        print("\n" + "="*60)
        print(f"获取: {result['fetched']} | 缓存: {result['from_cache']} | "
              f"新分析: {result['new_analysis']} | 缓存分析: {result['cached_analysis']} | "
              f"推送: {result['pushed']}")
        print("="*60)
        
        # 打印API使用统计
        stats = self.analyzer.get_stats()
        print(f"\nAPI使用统计:")
        print(f"  - 总调用: {stats['total_calls']} 次")
        print(f"  - 缓存命中: {stats['cache_hits']} 次")
        print(f"  - Token使用: {stats['tokens_used']}")
        print(f"  - 预估费用: ${stats['cost_estimate_usd']:.4f}")
        
        return result
    
    def _extract_matched_keywords(self, paper: Dict, user_keywords: List[str]) -> List[str]:
        """提取文献匹配的关键词"""
        text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
        matched = []
        for kw in user_keywords:
            if kw.lower() in text:
                matched.append(kw)
        return matched
    
    def run_batch_for_all_users(self, days_back: int = None) -> Dict:
        """
        为所有用户批量运行
        
        优化策略：
        1. 先收集所有用户的关键词
        2. 去重后统一搜索（减少API调用）
        3. 缓存分析结果（所有用户共享）
        """
        days_back = days_back or self.default_days_back
        
        print(f"\n{'='*60}")
        print("批量获取 - 优化模式")
        print(f"{'='*60}\n")
        
        # 1. 收集所有唯一关键词
        all_keywords = set()
        keyword_to_users = {}  # 关键词 -> 用户列表映射
        
        for user_id, user in self.user_manager.users.items():
            if not user.get('is_active', True):
                continue
            
            user_keywords = user.get('keywords', [])
            for kw in user_keywords:
                kw_lower = kw.lower()
                all_keywords.add(kw_lower)
                
                if kw_lower not in keyword_to_users:
                    keyword_to_users[kw_lower] = []
                keyword_to_users[kw_lower].append(user_id)
        
        if not all_keywords:
            print("没有活跃用户或关键词")
            return {'success': False, 'error': '没有活跃用户'}
        
        print(f"共 {len(self.user_manager.users)} 个用户")
        print(f"合并后关键词: {len(all_keywords)} 个")
        print(f"关键词: {', '.join(list(all_keywords)[:10])}...")
        
        # 2. 统一搜索（使用合并后的关键词）
        print("\n执行统一搜索...")
        all_papers = []
        
        # 检查缓存
        cached_hashes = self.cache.get_cached_search(list(all_keywords), days_back)
        
        if cached_hashes:
            print(f"✓ 使用缓存的搜索结果 ({len(cached_hashes)} 篇)")
            all_papers = self.cache.batch_get_papers(cached_hashes)
        else:
            if not self.fetcher:
                return {'success': False, 'error': 'PubMed邮箱未配置'}
            
            # 分批搜索避免请求过大
            keyword_list = list(all_keywords)
            batch_size = 10
            
            for i in range(0, len(keyword_list), batch_size):
                batch = keyword_list[i:i+batch_size]
                print(f"搜索批次 {i//batch_size + 1}: {batch}")
                
                papers = self.fetcher.fetch_all(batch, days_back)
                all_papers.extend(papers)
            
            # 去重
            seen = set()
            unique_papers = []
            for paper in all_papers:
                key = paper.get('doi') or paper.get('title', '').lower()
                if key and key not in seen:
                    seen.add(key)
                    unique_papers.append(paper)
            
            all_papers = unique_papers
            print(f"✓ 共获取 {len(all_papers)} 篇唯一文献")
            
            # 缓存所有文献
            paper_hashes = []
            for paper in all_papers:
                paper_hash = self.cache.cache_paper(paper)
                paper_hashes.append(paper_hash)
                
                # 索引关键词
                matched_keywords = self._extract_matched_keywords(
                    paper, list(all_keywords)
                )
                self.cache.index_paper_keywords(paper_hash, matched_keywords)
            
            # 缓存搜索结果
            self.cache.cache_search_results(
                list(all_keywords), days_back, paper_hashes
            )
        
        # 3. 统一分析（所有用户共享分析结果）
        print("\n执行统一分析...")
        papers_to_analyze = []
        already_analyzed = []
        
        for paper in all_papers:
            cached = self.cache.get_cached_analysis(
                paper.get('title', ''),
                paper.get('abstract', '')
            )
            
            if cached:
                paper.update(cached)
                paper['is_analyzed'] = True
                already_analyzed.append(paper)
            else:
                papers_to_analyze.append(paper)
        
        print(f"  - 已缓存: {len(already_analyzed)} 篇")
        print(f"  - 待分析: {len(papers_to_analyze)} 篇")
        
        if papers_to_analyze:
            # 评分筛选，只分析高分文献
            scored = scorer.score_papers(papers_to_analyze)
            high_score_papers = scorer.filter_by_threshold(scored, 0.4)
            
            print(f"  - 高分文献（>0.4）: {len(high_score_papers)} 篇")
            
            if high_score_papers:
                # 获取影响因子
                papers_with_if = self.impact_factor_fetcher.batch_get_impact_factors(
                    high_score_papers
                )
                
                # 批量分析
                analyzed = self.analyzer.batch_analyze(
                    papers_with_if,
                    batch_size=5,
                    delay=1.0
                )
                
                # 缓存结果
                for paper in analyzed:
                    if paper.get('is_analyzed'):
                        self.cache.cache_analysis(
                            paper.get('title', ''),
                            paper.get('abstract', ''),
                            {
                                'main_findings': paper.get('main_findings', ''),
                                'innovations': paper.get('innovations', ''),
                                'limitations': paper.get('limitations', ''),
                                'future_directions': paper.get('future_directions', ''),
                                'abstract_cn': paper.get('abstract_cn', '')
                            }
                        )
        
        # 4. 为每个用户生成个性化推送
        print("\n为用户生成个性化推送...")
        results = {}
        
        for user_id, user in self.user_manager.users.items():
            if not user.get('is_active', True):
                continue
            
            user_keywords = user.get('keywords', [])
            if not user_keywords:
                continue
            
            personalized = self.push_engine.get_personalized_papers(
                user_id, user_keywords, all_papers, limit=20
            )
            
            results[user_id] = {
                'username': user['username'],
                'pushed_count': len(personalized)
            }
            
            if personalized:
                paper_hashes = [
                    p.get('hash', hash(p.get('title', ''))) 
                    for p in personalized
                ]
                self.push_engine.record_push(user_id, paper_hashes, 'batch')
        
        # 打印结果
        print("\n" + "="*60)
        print("批量推送完成")
        print(f"涉及用户: {len(results)}")
        total_pushed = sum(r['pushed_count'] for r in results.values())
        print(f"总推送: {total_pushed} 篇")
        
        stats = self.analyzer.get_stats()
        print(f"\nAPI使用统计:")
        print(f"  - 总调用: {stats['total_calls']} 次")
        print(f"  - 缓存命中: {stats['cache_hits']} 次")
        print(f"  - 节省费用: ${stats['cache_hits'] * 0.002:.4f} (预估)")
        print("="*60)
        
        return {
            'success': True,
            'users_processed': len(results),
            'total_pushed': total_pushed,
            'api_stats': stats,
            'user_results': results
        }
    
    def get_system_stats(self) -> Dict:
        """获取系统统计信息"""
        cache_stats = self.cache.get_cache_stats()
        
        # 统计所有用户获取过的总文献数
        total_user_papers = self.cache.get_total_papers_count()
        
        user_stats = {
            'total_users': len(self.user_manager.users),
            'active_users': sum(1 for u in self.user_manager.users.values() 
                              if u.get('is_active', True))
        }
        
        return {
            'cache': cache_stats,
            'users': user_stats,
            'analyzer': self.analyzer.get_stats(),
            'total_papers': total_user_papers
        }
    
    def cleanup(self):
        """清理系统"""
        print("\n执行系统清理...")
        
        # 清理过期会话
        expired = self.user_manager.cleanup_expired_sessions()
        print(f"  - 清理过期会话: {expired}")
        
        # 优化缓存
        result = self.cache_optimizer.optimize_storage()
        print(f"  - 优化缓存完成")
        
        # 清理推送数据
        cleanup_result = self.push_engine.cleanup_old_data(days=90)
        print(f"  - 清理旧推送数据: {cleanup_result}")
        
        print("清理完成\n")
        return result


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='V2文献推送系统')
    parser.add_argument('--user', type=str, help='特定用户ID')
    parser.add_argument('--days', type=int, default=2, help='获取多少天内的文献')
    parser.add_argument('--batch', action='store_true', help='批量模式（所有用户）')
    parser.add_argument('--stats', action='store_true', help='显示统计信息')
    parser.add_argument('--cleanup', action='store_true', help='清理系统')
    
    args = parser.parse_args()
    
    system = LiteraturePushSystemV2()
    
    if args.stats:
        stats = system.get_system_stats()
        print("\n系统统计:")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    elif args.cleanup:
        system.cleanup()
    
    elif args.batch:
        result = system.run_batch_for_all_users(days_back=args.days)
        print("\n批量运行结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif args.user:
        result = system.run_for_user(args.user, days_back=args.days)
        print("\n运行结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    else:
        print("请指定模式: --user <user_id>, --batch, --stats, 或 --cleanup")


if __name__ == '__main__':
    import json
    main()
