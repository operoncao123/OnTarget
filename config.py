# OnTarget V2.5 服务器配置
# 根据服务器硬件自动调整性能参数

import os
import multiprocessing

# 获取服务器硬件信息
CPU_COUNT = multiprocessing.cpu_count()
print(f"[系统配置] 检测到服务器 CPU 核心数: {CPU_COUNT}")

# 并行获取配置
PARALLEL_FETCH = {
    # 线程池大小: 不超过CPU核心数,最少2个
    'max_workers': max(2, CPU_COUNT),
    
    # 各源超时时间(秒)
    'timeouts': {
        'pubmed': 60,
        'biorxiv': 45,
        'medrxiv': 45,
        'arxiv': 45,
        'psyarxiv': 45,
        'nber': 45,
        'chemrxiv': 45
    }
}

# 缓存配置  
CACHE_CONFIG = {
    # 搜索缓存有效期(小时)
    'search_cache_hours': 48,
    
    # 文献缓存有效期(天)
    'paper_cache_days': 30,
    
    # 分析结果缓存(天)
    'analysis_cache_days': 90
}

# 数据库配置
DB_CONFIG = {
    # 连接池大小
    'pool_size': max(5, CPU_COUNT * 2),
    
    # 最大溢出连接
    'max_overflow': max(10, CPU_COUNT * 3)
}

print(f"[系统配置] 并行获取线程池: {PARALLEL_FETCH['max_workers']}")
print(f"[系统配置] 数据库连接池: {DB_CONFIG['pool_size']}")
