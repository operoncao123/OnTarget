#!/usr/bin/env python3
"""
V2.6 内存缓存系统 - 使用 cachetools 实现高性能缓存
替代 SQLite 缓存，减少磁盘 I/O，降低内存占用
"""

import hashlib
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from cachetools import TTLCache, LRUCache

class MemoryCache:
    """
    V2.6 内存缓存管理器
    - 使用 TTLCache 实现带过期时间的缓存
    - 使用 LRUCache 限制内存使用
    - 线程安全
    """
    
    def __init__(self):
        # 搜索缓存：48小时过期，最多500个条目（约 25-50MB）
        self.search_cache = TTLCache(maxsize=500, ttl=48 * 3600)
        
        # 文献缓存：30天过期，最多3000个条目（约 60-120MB）
        self.paper_cache = TTLCache(maxsize=3000, ttl=30 * 24 * 3600)
        
        # 分析结果缓存：90天过期，最多1000个条目（约 25-50MB）
        self.analysis_cache = TTLCache(maxsize=1000, ttl=90 * 24 * 3600)
        
        # 用户会话缓存：2小时过期，最多300个条目
        self.session_cache = TTLCache(maxsize=300, ttl=2 * 3600)
        
        # 关键词索引缓存：12小时过期，最多100个条目
        self.keyword_index_cache = TTLCache(maxsize=100, ttl=12 * 3600)
        
        # 统计缓存：5分钟过期，最多50个条目
        self.stats_cache = TTLCache(maxsize=50, ttl=5 * 60)
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 统计信息
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }
    
    def _get_cache(self, cache_type: str) -> TTLCache:
        """获取指定类型的缓存"""
        caches = {
            'search': self.search_cache,
            'paper': self.paper_cache,
            'analysis': self.analysis_cache,
            'session': self.session_cache,
            'keyword_index': self.keyword_index_cache,
            'stats': self.stats_cache
        }
        return caches.get(cache_type)
    
    def get(self, cache_type: str, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            cache_type: 缓存类型 (search/paper/analysis/session/keyword_index/stats)
            key: 缓存键
            
        Returns:
            缓存值或 None
        """
        cache = self._get_cache(cache_type)
        if cache is None:
            return None
        
        with self._lock:
            try:
                value = cache[key]
                self._stats['hits'] += 1
                return value
            except KeyError:
                self._stats['misses'] += 1
                return None
    
    def set(self, cache_type: str, key: str, value: Any) -> bool:
        """
        设置缓存值
        
        Args:
            cache_type: 缓存类型
            key: 缓存键
            value: 缓存值
            
        Returns:
            是否成功
        """
        cache = self._get_cache(cache_type)
        if cache is None:
            return False
        
        with self._lock:
            try:
                cache[key] = value
                return True
            except Exception:
                return False
    
    def delete(self, cache_type: str, key: str) -> bool:
        """删除缓存"""
        cache = self._get_cache(cache_type)
        if cache is None:
            return False
        
        with self._lock:
            try:
                del cache[key]
                return True
            except KeyError:
                return False
    
    def clear(self, cache_type: Optional[str] = None):
        """
        清空缓存
        
        Args:
            cache_type: 指定类型或 None 清空所有
        """
        with self._lock:
            if cache_type:
                cache = self._get_cache(cache_type)
                if cache:
                    cache.clear()
            else:
                self.search_cache.clear()
                self.paper_cache.clear()
                self.analysis_cache.clear()
                self.session_cache.clear()
                self.keyword_index_cache.clear()
                self.stats_cache.clear()
    
    def get_stats(self) -> Dict:
        """获取缓存统计信息"""
        with self._lock:
            total = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total * 100) if total > 0 else 0
            
            return {
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate': round(hit_rate, 2),
                'search_cache_size': len(self.search_cache),
                'paper_cache_size': len(self.paper_cache),
                'analysis_cache_size': len(self.analysis_cache),
                'session_cache_size': len(self.session_cache),
                'keyword_index_cache_size': len(self.keyword_index_cache),
                'stats_cache_size': len(self.stats_cache),
                'total_items': (
                    len(self.search_cache) +
                    len(self.paper_cache) +
                    len(self.analysis_cache) +
                    len(self.session_cache) +
                    len(self.keyword_index_cache) +
                    len(self.stats_cache)
                )
            }
    
    def generate_key(self, *args) -> str:
        """
        生成缓存键
        
        Args:
            *args: 任意参数
            
        Returns:
            MD5 哈希键
        """
        key_str = ':'.join(str(arg) for arg in args)
        return hashlib.md5(key_str.encode()).hexdigest()

# 全局缓存实例
_memory_cache = None
_cache_lock = threading.Lock()

def get_memory_cache() -> MemoryCache:
    """获取全局内存缓存实例（单例模式）"""
    global _memory_cache
    if _memory_cache is None:
        with _cache_lock:
            if _memory_cache is None:
                _memory_cache = MemoryCache()
    return _memory_cache

# 便捷函数
def cache_get(cache_type: str, key: str) -> Optional[Any]:
    """获取缓存"""
    return get_memory_cache().get(cache_type, key)

def cache_set(cache_type: str, key: str, value: Any) -> bool:
    """设置缓存"""
    return get_memory_cache().set(cache_type, key, value)

def cache_delete(cache_type: str, key: str) -> bool:
    """删除缓存"""
    return get_memory_cache().delete(cache_type, key)

def cache_clear(cache_type: Optional[str] = None):
    """清空缓存"""
    return get_memory_cache().clear(cache_type)

def cache_stats() -> Dict:
    """获取缓存统计"""
    return get_memory_cache().get_stats()
