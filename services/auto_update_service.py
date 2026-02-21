#!/usr/bin/env python3
"""
自动更新服务 - V2.5
管理用户的自动文献更新任务
"""

import random
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

logger = logging.getLogger(__name__)

class AutoUpdateService:
    """
    自动更新服务
    - 为每个用户调度独立的自动更新任务
    - 支持错峰更新（避免多个用户同时请求API）
    - 自动记录更新时间和结果
    """
    
    # 推荐间隔天数
    RECOMMENDED_INTERVALS = [2, 3, 7]
    
    # 最小间隔天数
    MIN_INTERVAL_DAYS = 2
    
    # 最大间隔天数
    MAX_INTERVAL_DAYS = 30
    
    # 错峰时间范围（分钟）- 在基准时间上随机偏移 0-30 分钟
    STAGGER_RANGE_MINUTES = 30
    
    def __init__(self, system, keyword_group_manager):
        """
        初始化自动更新服务
        
        Args:
            system: LiteraturePushSystemV2 实例
            keyword_group_manager: KeywordGroupManager 实例
        """
        self.system = system
        self.keyword_group_manager = keyword_group_manager
        self.scheduler = BackgroundScheduler()
        self.jobs = {}  # user_id -> job_id 映射
        
        # 添加事件监听器
        self.scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )
        
        logger.info("自动更新服务已初始化")
    
    def start(self):
        """启动调度器并加载所有用户的自动更新任务"""
        self.scheduler.start()
        logger.info("自动更新调度器已启动")
        
        # 加载所有用户的自动更新设置
        self._load_all_user_schedules()
    
    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("自动更新调度器已关闭")
    
    def _load_all_user_schedules(self):
        """加载所有启用了自动更新的用户"""
        try:
            # 获取所有用户
            users = self.system.user_manager.get_all_users()
            enabled_count = 0
            
            for user in users:
                user_id = user.get('id')
                if not user_id:
                    continue
                
                settings = self._get_auto_update_settings(user_id)
                if settings.get('enabled'):
                    self._schedule_user_update(user_id, settings['interval_days'])
                    enabled_count += 1
            
            logger.info(f"已加载 {enabled_count} 个用户的自动更新任务")
            
        except Exception as e:
            logger.error(f"加载用户自动更新任务失败: {e}")
    
    def _get_auto_update_settings(self, user_id: str) -> Dict:
        """
        获取用户的自动更新设置
        
        Args:
            user_id: 用户ID
            
        Returns:
            自动更新设置字典
        """
        try:
            user = self.system.user_manager.get_user(user_id)
            if not user:
                return {'enabled': False, 'interval_days': self.MIN_INTERVAL_DAYS}
            
            prefs = user.get('preferences', {})
            
            return {
                'enabled': prefs.get('auto_update_enabled', False),
                'interval_days': max(
                    self.MIN_INTERVAL_DAYS,
                    min(self.MAX_INTERVAL_DAYS, 
                        prefs.get('auto_update_interval_days', self.MIN_INTERVAL_DAYS))
                )
            }
        except Exception as e:
            logger.error(f"获取用户 {user_id} 自动更新设置失败: {e}")
            return {'enabled': False, 'interval_days': self.MIN_INTERVAL_DAYS}
    
    def _schedule_user_update(self, user_id: str, interval_days: int):
        """
        为指定用户调度更新任务
        
        Args:
            user_id: 用户ID
            interval_days: 更新间隔天数
        """
        # 移除旧任务
        self._remove_user_schedule(user_id)
        
        # 计算错峰时间（在基准时间上随机偏移 0-30 分钟）
        stagger_minutes = random.randint(0, self.STAGGER_RANGE_MINUTES)
        
        # 创建新任务
        job_id = f'auto_update_{user_id}'
        job = self.scheduler.add_job(
            func=self._run_user_update,
            trigger=IntervalTrigger(
                days=interval_days,
                start_date=datetime.now() + timedelta(minutes=stagger_minutes)
            ),
            id=job_id,
            args=[user_id],
            replace_existing=True,
            misfire_grace_time=3600  # 允许1小时的错过时间
        )
        
        self.jobs[user_id] = job_id
        logger.info(
            f"已为用户 {user_id} 调度自动更新，"
            f"间隔 {interval_days} 天，错峰 {stagger_minutes} 分钟"
        )
    
    def _remove_user_schedule(self, user_id: str):
        """
        移除用户的自动更新任务
        
        Args:
            user_id: 用户ID
        """
        if user_id in self.jobs:
            try:
                self.scheduler.remove_job(self.jobs[user_id])
                logger.info(f"已移除用户 {user_id} 的自动更新任务")
            except Exception as e:
                logger.warning(f"移除用户 {user_id} 任务时出错: {e}")
            finally:
                del self.jobs[user_id]
    
    def _run_user_update(self, user_id: str):
        """
        执行用户的自动更新
        
        Args:
            user_id: 用户ID
        """
        logger.info(f"[自动更新] 开始为用户 {user_id} 执行更新")
        
        try:
            # 执行更新
            result = self.system.run_for_user(user_id)
            
            # 更新用户的最后更新时间
            self._update_last_auto_update(user_id, result)
            
            logger.info(
                f"[自动更新] 用户 {user_id} 更新完成: "
                f"获取 {result.get('fetched', 0)} 篇，"
                f"分析 {result.get('new_analysis', 0)} 篇"
            )
            
        except Exception as e:
            logger.error(f"[自动更新] 用户 {user_id} 更新失败: {e}")
            # 静默失败，记录错误但不中断
            # 下次周期会再次尝试
    
    def _update_last_auto_update(self, user_id: str, result: Dict):
        """
        更新用户的最后自动更新记录
        
        Args:
            user_id: 用户ID
            result: 更新结果
        """
        try:
            now = datetime.now()
            
            # 更新用户 preferences
            prefs_update = {
                'last_auto_update_at': now.isoformat(),
                'last_auto_update_result': {
                    'fetched': result.get('fetched', 0),
                    'from_cache': result.get('from_cache', 0),
                    'new_analysis': result.get('new_analysis', 0),
                    'cached_analysis': result.get('cached_analysis', 0),
                    'success': True,
                    'updated_at': now.isoformat()
                }
            }
            
            # 保存到用户管理器
            self.system.user_manager.update_preferences(user_id, prefs_update)
            
        except Exception as e:
            logger.error(f"更新用户 {user_id} 最后更新时间失败: {e}")
    
    def _on_job_executed(self, event):
        """任务执行完成事件处理器"""
        if event.exception:
            logger.error(f"任务 {event.job_id} 执行失败: {event.exception}")
        else:
            logger.debug(f"任务 {event.job_id} 执行成功")
    
    def update_user_schedule(self, user_id: str, enabled: bool, interval_days: int):
        """
        更新用户的自动更新设置
        
        Args:
            user_id: 用户ID
            enabled: 是否启用
            interval_days: 更新间隔天数
        """
        # 验证间隔天数
        interval_days = max(self.MIN_INTERVAL_DAYS, 
                          min(self.MAX_INTERVAL_DAYS, interval_days))
        
        if enabled:
            self._schedule_user_update(user_id, interval_days)
            logger.info(f"已启用用户 {user_id} 的自动更新，间隔 {interval_days} 天")
        else:
            self._remove_user_schedule(user_id)
            logger.info(f"已禁用用户 {user_id} 的自动更新")
    
    def get_user_schedule_info(self, user_id: str) -> Dict:
        """
        获取用户的调度信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            调度信息字典
        """
        settings = self._get_auto_update_settings(user_id)
        
        # 获取最后更新时间
        last_update_info = self._get_last_update_info(user_id)
        
        return {
            'enabled': settings['enabled'],
            'interval_days': settings['interval_days'],
            'last_update_at': last_update_info.get('last_update_at'),
            'last_update_result': last_update_info.get('last_update_result'),
            'is_scheduled': user_id in self.jobs
        }
    
    def _get_last_update_info(self, user_id: str) -> Dict:
        """
        获取用户最后更新信息（包括手动和自动更新）
        
        Args:
            user_id: 用户ID
            
        Returns:
            最后更新信息字典
        """
        try:
            user = self.system.user_manager.get_user(user_id)
            if not user:
                return {}
            
            prefs = user.get('preferences', {})
            
            # 获取自动更新最后时间
            auto_update_at = prefs.get('last_auto_update_at')
            auto_update_result = prefs.get('last_auto_update_result', {})
            
            # 获取手动更新最后时间
            manual_update_at = prefs.get('last_manual_update_at')
            manual_update_result = prefs.get('last_manual_update_result', {})
            
            # 比较两个时间，返回最新的
            from datetime import datetime
            
            auto_time = None
            manual_time = None
            
            if auto_update_at:
                try:
                    auto_time = datetime.fromisoformat(auto_update_at)
                except:
                    pass
            
            if manual_update_at:
                try:
                    manual_time = datetime.fromisoformat(manual_update_at)
                except:
                    pass
            
            # 返回最新的更新信息
            if auto_time and manual_time:
                if auto_time > manual_time:
                    return {
                        'last_update_at': auto_update_at,
                        'last_update_result': auto_update_result
                    }
                else:
                    return {
                        'last_update_at': manual_update_at,
                        'last_update_result': manual_update_result
                    }
            elif auto_time:
                return {
                    'last_update_at': auto_update_at,
                    'last_update_result': auto_update_result
                }
            elif manual_time:
                return {
                    'last_update_at': manual_update_at,
                    'last_update_result': manual_update_result
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"获取用户 {user_id} 最后更新信息失败: {e}")
            return {}
    
    def get_recommended_intervals(self) -> list:
        """获取推荐的间隔天数"""
        return self.RECOMMENDED_INTERVALS
    
    def force_run_update(self, user_id: str) -> Dict:
        """
        强制立即运行一次更新（用于测试或手动触发）
        
        Args:
            user_id: 用户ID
            
        Returns:
            更新结果
        """
        logger.info(f"[强制更新] 为用户 {user_id} 执行更新")
        
        try:
            result = self.system.run_for_user(user_id)
            self._update_last_auto_update(user_id, result)
            return result
        except Exception as e:
            logger.error(f"[强制更新] 用户 {user_id} 更新失败: {e}")
            raise
