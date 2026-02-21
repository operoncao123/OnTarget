#!/usr/bin/env python3
"""
V2.6 异步分析队列 - 使用进程池处理 AI 分析任务
避免阻塞主线程，提升并发能力
"""

import multiprocessing
import threading
import queue
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable
from concurrent.futures import ProcessPoolExecutor, as_completed

class AsyncAnalysisQueue:
    """
    V2.6 异步分析队列
    - 使用进程池执行 AI 分析
    - 限制并发数量，避免 API 限流
    - 支持任务优先级和回调
    """
    
    def __init__(self, max_workers: int = 2, max_queue_size: int = 100):
        """
        初始化异步分析队列
        
        Args:
            max_workers: 最大并发工作进程数（建议 2-4）
            max_queue_size: 最大队列长度
        """
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        
        # 任务队列
        self.task_queue = queue.PriorityQueue(maxsize=max_queue_size)
        
        # 执行中的任务
        self.running_tasks = {}
        self._lock = threading.RLock()
        
        # 线程池（用于管理进程）
        self.executor = ProcessPoolExecutor(max_workers=max_workers)
        
        # 任务结果
        self.results = {}
        
        # 回调函数
        self.callbacks = {}
        
        # 统计信息
        self.stats = {
            'submitted': 0,
            'completed': 0,
            'failed': 0,
            'cancelled': 0
        }
        
        # 启动工作线程
        self._shutdown = False
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()
    
    def submit(self, task_id: str, func: Callable, args: tuple = (), 
               kwargs: dict = None, priority: int = 5, 
               callback: Callable = None) -> Dict:
        """
        提交分析任务
        
        Args:
            task_id: 任务唯一标识
            func: 要执行的函数
            args: 函数参数
            kwargs: 函数关键字参数
            priority: 优先级（1-10，数字越小优先级越高）
            callback: 完成后的回调函数
            
        Returns:
            {'success': True, 'task_id': '...', 'position': N} or 
            {'success': False, 'error': '...'}
        """
        if kwargs is None:
            kwargs = {}
        
        if self._shutdown:
            return {'success': False, 'error': '队列已关闭'}
        
        try:
            # 检查任务是否已存在
            with self._lock:
                if task_id in self.running_tasks:
                    return {'success': False, 'error': '任务已存在'}
            
            # 提交到队列（使用优先级，数字越小优先级越高）
            task = {
                'id': task_id,
                'func': func,
                'args': args,
                'kwargs': kwargs,
                'submitted_at': datetime.now()
            }
            
            # 添加到队列
            self.task_queue.put((priority, task))
            
            # 记录回调
            if callback:
                self.callbacks[task_id] = callback
            
            # 更新统计
            with self._lock:
                self.stats['submitted'] += 1
            
            return {
                'success': True,
                'task_id': task_id,
                'position': self.task_queue.qsize(),
                'message': '任务已提交到队列'
            }
            
        except queue.Full:
            return {'success': False, 'error': '队列已满，请稍后重试'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        with self._lock:
            if task_id in self.results:
                result = self.results[task_id]
                return {
                    'task_id': task_id,
                    'status': result.get('status', 'unknown'),
                    'result': result.get('data'),
                    'error': result.get('error'),
                    'completed_at': result.get('completed_at')
                }
            
            if task_id in self.running_tasks:
                return {
                    'task_id': task_id,
                    'status': 'running',
                    'started_at': self.running_tasks[task_id].get('started_at')
                }
        
        return {'task_id': task_id, 'status': 'pending'}
    
    def cancel(self, task_id: str) -> bool:
        """取消任务（仅对未开始的任务有效）"""
        # 注意：已开始的任务无法取消
        # 这里仅做标记，实际无法从队列中移除
        with self._lock:
            if task_id in self.running_tasks:
                return False  # 已在运行，无法取消
        
        return True  # 返回 True 表示已尝试取消
    
    def _process_queue(self):
        """工作线程：从队列取出任务并执行"""
        while not self._shutdown:
            try:
                # 获取任务（阻塞等待，超时 1 秒）
                priority, task = self.task_queue.get(timeout=1)
                
                task_id = task['id']
                func = task['func']
                args = task['args']
                kwargs = task['kwargs']
                
                with self._lock:
                    self.running_tasks[task_id] = {
                        'started_at': datetime.now()
                    }
                
                # 提交到进程池执行
                future = self.executor.submit(func, *args, **kwargs)
                
                # 添加完成回调
                future.add_done_callback(
                    lambda f, tid=task_id: self._on_task_complete(tid, f)
                )
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[AsyncAnalysisQueue] 处理队列错误: {e}")
                continue
    
    def _on_task_complete(self, task_id: str, future):
        """任务完成回调"""
        try:
            result = future.result()
            status = 'completed'
            error = None
            data = result
        except Exception as e:
            status = 'failed'
            error = str(e)
            data = None
        
        with self._lock:
            # 保存结果
            self.results[task_id] = {
                'status': status,
                'data': data,
                'error': error,
                'completed_at': datetime.now()
            }
            
            # 从运行列表移除
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
            
            # 更新统计
            if status == 'completed':
                self.stats['completed'] += 1
            else:
                self.stats['failed'] += 1
            
            # 执行用户回调
            if task_id in self.callbacks:
                callback = self.callbacks.pop(task_id)
                try:
                    callback(task_id, status, data, error)
                except Exception as e:
                    print(f"[AsyncAnalysisQueue] 回调执行错误: {e}")
    
    def get_stats(self) -> Dict:
        """获取队列统计信息"""
        with self._lock:
            return {
                **self.stats,
                'queue_size': self.task_queue.qsize(),
                'running_count': len(self.running_tasks),
                'completed_results': len(self.results)
            }
    
    def clear_results(self, max_age_minutes: int = 60):
        """清理过期的结果"""
        cutoff_time = datetime.now() - __import__('datetime').timedelta(minutes=max_age_minutes)
        
        with self._lock:
            to_remove = [
                task_id for task_id, result in self.results.items()
                if result.get('completed_at') and result['completed_at'] < cutoff_time
            ]
            for task_id in to_remove:
                del self.results[task_id]
    
    def shutdown(self, wait: bool = True):
        """关闭队列"""
        self._shutdown = True
        
        if wait:
            # 等待队列清空
            while not self.task_queue.empty():
                time.sleep(0.1)
        
        # 关闭进程池
        self.executor.shutdown(wait=wait)

# 全局队列实例
_analysis_queue = None
_queue_lock = threading.Lock()

def get_analysis_queue(max_workers: int = 2) -> AsyncAnalysisQueue:
    """获取全局分析队列实例（单例模式）"""
    global _analysis_queue
    if _analysis_queue is None:
        with _queue_lock:
            if _analysis_queue is None:
                _analysis_queue = AsyncAnalysisQueue(max_workers=max_workers)
    return _analysis_queue

# 便捷函数
def submit_analysis(task_id: str, func: Callable, args: tuple = (), 
                   kwargs: dict = None, priority: int = 5,
                   callback: Callable = None) -> Dict:
    """提交分析任务"""
    return get_analysis_queue().submit(task_id, func, args, kwargs, priority, callback)

def get_analysis_status(task_id: str) -> Optional[Dict]:
    """获取分析状态"""
    return get_analysis_queue().get_status(task_id)

def cancel_analysis(task_id: str) -> bool:
    """取消分析任务"""
    return get_analysis_queue().cancel(task_id)

def get_analysis_stats() -> Dict:
    """获取分析统计"""
    return get_analysis_queue().get_stats()
