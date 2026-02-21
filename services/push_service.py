#!/usr/bin/env python3
"""
个性化推送引擎 - 根据用户关键词推送相关文献
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from collections import defaultdict

class PersonalizedPushEngine:
    """
    个性化文献推送引擎
    - 基于用户关键词匹配
    - 去重（用户已看过的文献）
    - 优先级排序
    - 每日限制
    """
    
    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        self.user_papers_file = os.path.join(data_dir, 'user_papers.json')
        self.push_history_file = os.path.join(data_dir, 'push_history.json')
        
        self._ensure_data_dir()
        self.user_papers = self._load_json(self.user_papers_file)
        self.push_history = self._load_json(self.push_history_file)
    
    def _ensure_data_dir(self):
        """确保数据目录存在"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
    
    def _load_json(self, filepath: str) -> Dict:
        """加载JSON文件"""
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_json(self, filepath: str, data: Dict):
        """保存JSON文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _calculate_group_match_score(self, paper: Dict, group: Dict) -> Dict:
        """
        计算文献与单个关键词组的匹配分数
        
        Args:
            paper: 文献数据
            group: 关键词组数据，包含 keywords, match_mode 等
            
        Returns:
            {
                'score': float,  # 0-100分
                'matched_keywords': List[str],  # 匹配到的关键词
                'match_details': Dict  # 详细匹配信息
            }
        """
        # 检查 paper 是否为 None
        if paper is None:
            return {'score': 0, 'matched_keywords': [], 'match_details': {}}
        
        group_keywords = group.get('keywords', [])
        match_mode = group.get('match_mode', 'any')  # 'any' 或 'all'
        min_match_score = group.get('min_match_score', 0.3)
        
        if not group_keywords:
            return {'score': 0, 'matched_keywords': [], 'match_details': {}}
        
        title = (paper.get('title') or '').lower()
        abstract = (paper.get('abstract') or '').lower()
        text = title + ' ' + abstract
        
        matched_keywords = []
        total_keyword_score = 0
        
        for keyword in group_keywords:
            kw = keyword.lower()
            kw_variants = [kw, kw.replace('-', ''), kw.replace('-', ' ')]
            
            keyword_score = 0
            for variant in kw_variants:
                # 使用单词边界匹配，避免短关键词误匹配
                if len(variant) <= 3:
                    # 短关键词使用单词边界
                    pattern = r'\b' + re.escape(variant) + r'\b'
                    if re.search(pattern, title):
                        keyword_score += 5
                        break
                else:
                    # 长关键词可以宽松匹配
                    if variant in title:
                        keyword_score += 5
                        break
            
            for variant in kw_variants:
                if len(variant) <= 3:
                    # 短关键词使用单词边界
                    pattern = r'\b' + re.escape(variant) + r'\b'
                    if re.search(pattern, abstract):
                        keyword_score += 2
                        break
                else:
                    # 长关键词可以宽松匹配
                    if variant in abstract:
                        keyword_score += 2
                        break
            
            if keyword_score > 0:
                matched_keywords.append(keyword)
                total_keyword_score += keyword_score
        
        # 检查匹配模式
        if match_mode == 'all':
            # 必须匹配所有关键词
            if len(matched_keywords) < len(group_keywords):
                return {'score': 0, 'matched_keywords': [], 'match_details': {}}
        
        # 如果没有匹配任何关键词，返回0分
        if not matched_keywords:
            return {'score': 0, 'matched_keywords': [], 'match_details': {}}
        
        # 计算关键词匹配分数 (0-70分)
        keyword_score = min(70, total_keyword_score * 7)
        
        # 2. 发表时间（0-10分）
        time_score = 0
        try:
            pub_date = paper.get('publication_date')
            if pub_date:
                if isinstance(pub_date, str):
                    pub_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                days_old = (datetime.now() - pub_date).days
                
                if days_old <= 1:
                    time_score = 10
                elif days_old <= 3:
                    time_score = 8
                elif days_old <= 7:
                    time_score = 6
                elif days_old <= 14:
                    time_score = 4
                elif days_old <= 30:
                    time_score = 2
        except:
            pass
        
        # 3. 影响因子（0-10分）
        if_score = 0
        impact_factor = paper.get('impact_factor')
        if impact_factor:
            if impact_factor >= 20:
                if_score = 10
            elif impact_factor >= 10:
                if_score = 8
            elif impact_factor >= 5:
                if_score = 6
            elif impact_factor >= 3:
                if_score = 4
            else:
                if_score = 2
        
        # 4. 文献类型（0-10分）- Research优先
        type_score = 5
        paper_type = paper.get('paper_type', 'research')
        if paper_type == 'research':
            type_score = 10
        elif paper_type == 'review':
            type_score = 7
        
        total_score = keyword_score + time_score + if_score + type_score
        
        return {
            'score': total_score,
            'matched_keywords': matched_keywords,
            'match_details': {
                'keyword_score': keyword_score,
                'time_score': time_score,
                'if_score': if_score,
                'type_score': type_score
            }
        }
    
    def _calculate_paper_score(self, paper: Dict, user_keywords: List[str]) -> float:
        """
        计算文献与用户的匹配分数（兼容旧版，使用用户所有关键词作为一个组）
        """
        if not paper:
            return 0.0
        
        # 创建临时组
        temp_group = {
            'keywords': user_keywords,
            'match_mode': 'any',
            'min_match_score': 0.3
        }
        
        result = self._calculate_group_match_score(paper, temp_group)
        return result['score']
    
    def get_personalized_papers_for_group(self, user_id: str, group: Dict,
                                         available_papers: List[Dict],
                                         limit: int = 20,
                                         exclude_seen: bool = True) -> List[Dict]:
        """
        获取特定关键词组的个性化文献
        
        Args:
            user_id: 用户ID
            group: 关键词组数据
            available_papers: 可用的文献列表
            limit: 返回数量限制
            exclude_seen: 是否排除已看过的文献
        
        Returns:
            按优先级排序的文献列表，包含组匹配信息
        """
        # 获取组数据
        group_id = group.get('id')
        
        # 获取已看过的文献（从组独立数据中）
        seen_papers = set()
        if exclude_seen and group_id:
            # 从组数据文件读取
            group_data_file = os.path.join(self.data_dir, 'group_data', f"{user_id}_{group_id}.json")
            if os.path.exists(group_data_file):
                try:
                    with open(group_data_file, 'r', encoding='utf-8') as f:
                        group_data = json.load(f)
                        seen_papers = set(group_data.get('viewed_papers', []))
                except:
                    pass
        
        # 评分和筛选
        scored_papers = []
        for paper in available_papers:
            # 跳过无效的文献数据
            if not paper:
                continue
            
            paper_hash = paper.get('hash') or self._get_paper_hash(paper)
            
            # 跳过已看过的
            if paper_hash in seen_papers:
                continue
            
            # 计算与该组的匹配分数
            match_result = self._calculate_group_match_score(paper, group)
            score = match_result['score']
            
            # 只要有任何关键词匹配就显示（分数>0）
            if score >= 1:
                paper_copy = paper.copy()
                paper_copy['personalized_score'] = score
                paper_copy['hash'] = paper_hash
                
                # 添加组匹配信息
                paper_copy['matched_group'] = {
                    'id': group.get('id'),
                    'name': group.get('name'),
                    'icon': group.get('icon', '🔬'),
                    'color': group.get('color', '#5a9a8f'),
                    'match_score': score,
                    'matched_keywords': match_result['matched_keywords'],
                    'match_details': match_result['match_details']
                }
                
                scored_papers.append(paper_copy)
        
        # 按分数排序
        scored_papers.sort(key=lambda x: x['personalized_score'], reverse=True)
        
        # 限制数量
        return scored_papers[:limit]
    
    def get_personalized_papers(self, user_id: str, user_keywords: List[str], 
                               available_papers: List[Dict], 
                               limit: int = 20,
                               exclude_seen: bool = True) -> List[Dict]:
        """
        获取个性化推送的文献
        
        Args:
            user_id: 用户ID
            user_keywords: 用户的关键词
            available_papers: 可用的文献列表
            limit: 返回数量限制
            exclude_seen: 是否排除已看过的文献
        
        Returns:
            按优先级排序的文献列表
        """
        # 获取用户已看过的文献
        seen_papers = set()
        if exclude_seen and user_id in self.user_papers:
            seen_papers = set(self.user_papers[user_id].get('seen_papers', []))
        
        # 评分和筛选
        scored_papers = []
        for paper in available_papers:
            # 跳过无效的文献数据
            if not paper:
                continue
            
            paper_hash = paper.get('hash') or self._get_paper_hash(paper)
            
            # 跳过已看过的
            if paper_hash in seen_papers:
                continue
            
            # 计算分数
            score = self._calculate_paper_score(paper, user_keywords)
            
            # 只要有任何关键词匹配就显示（分数>0）
            if score >= 1:
                paper_copy = paper.copy()
                paper_copy['personalized_score'] = score
                paper_copy['hash'] = paper_hash
                scored_papers.append(paper_copy)
        
        # 按分数排序
        scored_papers.sort(key=lambda x: x['personalized_score'], reverse=True)
        
        # 限制数量
        return scored_papers[:limit]
    
    def _get_paper_hash(self, paper: Dict) -> str:
        """生成文献哈希"""
        import hashlib
        doi = paper.get('doi', '')
        pmid = paper.get('pmid', '')
        title = paper.get('title', '').lower().strip()
        
        if doi:
            return hashlib.md5(f"doi:{doi}".encode()).hexdigest()
        elif pmid:
            return hashlib.md5(f"pmid:{pmid}".encode()).hexdigest()
        else:
            return hashlib.md5(f"title:{title}".encode()).hexdigest()
    
    def mark_papers_as_seen(self, user_id: str, paper_hashes: List[str]):
        """
        标记文献为已看过
        
        Args:
            user_id: 用户ID
            paper_hashes: 文献哈希列表
        """
        if user_id not in self.user_papers:
            self.user_papers[user_id] = {
                'seen_papers': [],
                'saved_papers': [],
                'interactions': []
            }
        
        # 添加新的已看文献
        for paper_hash in paper_hashes:
            if paper_hash not in self.user_papers[user_id]['seen_papers']:
                self.user_papers[user_id]['seen_papers'].append(paper_hash)
        
        self._save_json(self.user_papers_file, self.user_papers)
    
    def save_paper_for_user(self, user_id: str, paper_hash: str):
        """
        用户收藏文献
        
        Args:
            user_id: 用户ID
            paper_hash: 文献哈希
        """
        if user_id not in self.user_papers:
            self.user_papers[user_id] = {
                'seen_papers': [],
                'saved_papers': [],
                'interactions': []
            }
        
        if paper_hash not in self.user_papers[user_id]['saved_papers']:
            self.user_papers[user_id]['saved_papers'].append(paper_hash)
            self._save_json(self.user_papers_file, self.user_papers)
    
    def unsave_paper_for_user(self, user_id: str, paper_hash: str):
        """取消收藏"""
        if user_id in self.user_papers:
            if paper_hash in self.user_papers[user_id]['saved_papers']:
                self.user_papers[user_id]['saved_papers'].remove(paper_hash)
                self._save_json(self.user_papers_file, self.user_papers)
    
    def record_interaction(self, user_id: str, paper_hash: str, 
                          interaction_type: str, metadata: Dict = None):
        """
        记录用户交互
        
        Args:
            user_id: 用户ID
            paper_hash: 文献哈希
            interaction_type: 交互类型（view, click, save, share）
            metadata: 额外元数据
        """
        if user_id not in self.user_papers:
            self.user_papers[user_id] = {
                'seen_papers': [],
                'saved_papers': [],
                'interactions': []
            }
        
        interaction = {
            'paper_hash': paper_hash,
            'type': interaction_type,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        
        self.user_papers[user_id]['interactions'].append(interaction)
        
        # 限制交互记录数量（保留最近1000条）
        interactions = self.user_papers[user_id]['interactions']
        if len(interactions) > 1000:
            self.user_papers[user_id]['interactions'] = interactions[-1000:]
        
        self._save_json(self.user_papers_file, self.user_papers)
    
    def get_user_feed(self, user_id: str, user_keywords: List[str],
                     all_papers: List[Dict], page: int = 1, 
                     per_page: int = 10) -> Dict:
        """
        获取用户的个性化文献流
        
        Args:
            user_id: 用户ID
            user_keywords: 用户关键词
            all_papers: 所有可用文献
            page: 页码
            per_page: 每页数量
        
        Returns:
            包含文献列表和分页信息的字典
        """
        # 获取个性化排序的文献
        personalized = self.get_personalized_papers(
            user_id, user_keywords, all_papers, 
            limit=page * per_page
        )
        
        # 分页
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_papers = personalized[start_idx:end_idx]
        
        # 获取用户收藏的文献
        saved_papers = []
        if user_id in self.user_papers:
            saved_hashes = set(self.user_papers[user_id].get('saved_papers', []))
            for paper in all_papers:
                paper_hash = paper.get('hash') or self._get_paper_hash(paper)
                if paper_hash in saved_hashes:
                    saved_papers.append(paper)
        
        return {
            'papers': page_papers,
            'saved_papers': saved_papers,
            'total_available': len(personalized),
            'page': page,
            'per_page': per_page,
            'has_more': len(personalized) > end_idx
        }
    
    def get_user_stats(self, user_id: str) -> Dict:
        """获取用户的阅读统计"""
        if user_id not in self.user_papers:
            return {
                'total_seen': 0,
                'total_saved': 0,
                'interactions_7d': 0,
                'interactions_30d': 0,
                'favorite_keywords': []
            }
        
        user_data = self.user_papers[user_id]
        interactions = user_data.get('interactions', [])
        
        # 计算最近7天和30天的交互数
        now = datetime.now()
        interactions_7d = 0
        interactions_30d = 0
        
        for interaction in interactions:
            try:
                ts = datetime.fromisoformat(interaction['timestamp'].replace('Z', '+00:00'))
                days_diff = (now - ts).days
                if days_diff <= 7:
                    interactions_7d += 1
                if days_diff <= 30:
                    interactions_30d += 1
            except:
                continue
        
        return {
            'total_seen': len(user_data.get('seen_papers', [])),
            'total_saved': len(user_data.get('saved_papers', [])),
            'interactions_7d': interactions_7d,
            'interactions_30d': interactions_30d,
            'favorite_keywords': self._extract_favorite_keywords(interactions)
        }
    
    def _extract_favorite_keywords(self, interactions: List[Dict]) -> List[str]:
        """从交互中提取用户最感兴趣的关键词"""
        # 简化的实现：基于交互频率
        # 实际应用中可以使用更复杂的NLP分析
        keyword_count = defaultdict(int)
        
        for interaction in interactions:
            metadata = interaction.get('metadata', {})
            keywords = metadata.get('keywords', [])
            for kw in keywords:
                keyword_count[kw.lower()] += 1
        
        # 返回前5个关键词
        sorted_keywords = sorted(keyword_count.items(), key=lambda x: x[1], reverse=True)
        return [kw for kw, count in sorted_keywords[:5]]
    
    def get_push_history(self, user_id: str = None, days: int = 7) -> List[Dict]:
        """
        获取推送历史
        
        Args:
            user_id: 特定用户（None表示所有用户）
            days: 最近多少天
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        history = []
        for push_id, push_data in self.push_history.items():
            if push_data['timestamp'] >= cutoff:
                if user_id is None or push_data.get('user_id') == user_id:
                    history.append(push_data)
        
        history.sort(key=lambda x: x['timestamp'], reverse=True)
        return history
    
    def record_push(self, user_id: str, paper_hashes: List[str], 
                   push_type: str = 'daily'):
        """
        记录一次推送
        
        Args:
            user_id: 用户ID
            paper_hashes: 推送的文献哈希列表
            push_type: 推送类型（daily, weekly, instant）
        """
        push_id = f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        self.push_history[push_id] = {
            'id': push_id,
            'user_id': user_id,
            'paper_hashes': paper_hashes,
            'timestamp': datetime.now().isoformat(),
            'type': push_type,
            'count': len(paper_hashes)
        }
        
        self._save_json(self.push_history_file, self.push_history)
    
    def cleanup_old_data(self, days: int = 90):
        """
        清理旧数据
        
        Args:
            days: 清理超过多少天的数据
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        # 清理推送历史
        pushes_to_remove = []
        for push_id, push_data in self.push_history.items():
            if push_data['timestamp'] < cutoff:
                pushes_to_remove.append(push_id)
        
        for push_id in pushes_to_remove:
            del self.push_history[push_id]
        
        # 清理用户交互记录
        for user_id, user_data in self.user_papers.items():
            interactions = user_data.get('interactions', [])
            filtered_interactions = [
                i for i in interactions 
                if i.get('timestamp', '2000-01-01') >= cutoff
            ]
            user_data['interactions'] = filtered_interactions
        
        self._save_json(self.push_history_file, self.push_history)
        self._save_json(self.user_papers_file, self.user_papers)
        
        return {
            'removed_pushes': len(pushes_to_remove)
        }


class PushScheduler:
    """
    推送调度器
    管理定时推送任务
    """
    
    def __init__(self, push_engine: PersonalizedPushEngine):
        self.push_engine = push_engine
    
    def schedule_daily_push(self, user_manager, paper_cache, 
                           send_callback=None):
        """
        执行每日推送
        
        Args:
            user_manager: 用户管理器实例
            paper_cache: 文献缓存实例
            send_callback: 发送推送的回调函数
        """
        users = user_manager.get_all_users()
        push_results = []
        
        for user_id, user_info in users.items():
            # 检查用户是否启用推送
            if not user_info.get('is_active', True):
                continue
            
            # 获取用户完整信息
            user_full = user_manager.users.get(user_id)
            if not user_full:
                continue
            
            preferences = user_full.get('preferences', {})
            if not preferences.get('email_notifications', True):
                continue
            
            # 获取用户关键词
            keywords = user_full.get('keywords', [])
            if not keywords:
                continue
            
            # 从缓存获取匹配的关键词文献
            from smart_cache import SmartCache
            cache = SmartCache()
            paper_hashes = cache.find_papers_by_keywords(keywords)
            papers = cache.batch_get_papers(paper_hashes)
            
            # 获取个性化推送列表
            daily_limit = preferences.get('daily_limit', 20)
            personalized = self.push_engine.get_personalized_papers(
                user_id, keywords, papers, limit=daily_limit
            )
            
            if personalized:
                # 记录推送
                paper_hashes = [p['hash'] for p in personalized]
                self.push_engine.record_push(user_id, paper_hashes, 'daily')
                
                # 调用发送回调
                if send_callback:
                    send_callback(user_id, user_info, personalized)
                
                push_results.append({
                    'user_id': user_id,
                    'username': user_info['username'],
                    'papers_count': len(personalized)
                })
        
        return push_results
