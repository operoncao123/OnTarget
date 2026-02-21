#!/usr/bin/env python3
"""
优化版分析器 - 支持多API供应商
- 使用缓存避免重复分析
- 支持DeepSeek/OpenAI/Anthropic/Google/智谱/Kimi/豆包/千问等
- 用户自定义API配置
"""

import os
import json
import time
from typing import Dict, Optional, List
import requests

API_PROVIDERS = {
    # 国外主流
    'deepseek': {
        'name': 'DeepSeek',
        'default_model': 'deepseek-chat',
        'default_base_url': 'https://api.deepseek.com',
        'endpoint': '/v1/chat/completions',
        'auth_type': 'bearer'
    },
    'openai': {
        'name': 'OpenAI',
        'default_model': 'gpt-3.5-turbo',
        'default_base_url': 'https://api.openai.com',
        'endpoint': '/v1/chat/completions',
        'auth_type': 'bearer'
    },
    'anthropic': {
        'name': 'Anthropic Claude',
        'default_model': 'claude-3-haiku-20240307',
        'default_base_url': 'https://api.anthropic.com',
        'endpoint': '/v1/messages',
        'auth_type': 'anthropic',
        'requires_api_key_header': True
    },
    'google': {
        'name': 'Google Gemini',
        'default_model': 'gemini-1.5-flash',
        'default_base_url': 'https://generativelanguage.googleapis.com',
        'endpoint': '/v1beta/models',
        'auth_type': 'google',
        'stream': False
    },
    # 国内主流
    'zhipu': {
        'name': '智谱AI (GLM)',
        'default_model': 'glm-4',
        'default_base_url': 'https://open.bigmodel.cn',
        'endpoint': '/api/paas/v4/chat/completions',
        'auth_type': 'bearer'
    },
    'kimi': {
        'name': 'Kimi (月之暗面)',
        'default_model': 'moonshot-v1-8k',
        'default_base_url': 'https://api.moonshot.cn',
        'endpoint': '/v1/chat/completions',
        'auth_type': 'bearer'
    },
    'doubao': {
        'name': '豆包 (字节跳动)',
        'default_model': 'doubao-lite-4k',
        'default_base_url': 'https://ark.cn-beijing.volces.com',
        'endpoint': '/api/v3/chat/completions',
        'auth_type': 'bearer'
    },
    'qwen': {
        'name': '千问 (阿里云)',
        'default_model': 'qwen-turbo',
        'default_base_url': 'https://dashscope.aliyuncs.com',
        'endpoint': '/api/v1/services/aigc/text-generation/generation',
        'auth_type': 'dashscope'
    },
    'minimax': {
        'name': 'MiniMax',
        'default_model': 'abab6.5s-chat',
        'default_base_url': 'https://api.minimax.chat',
        'endpoint': '/v1/text/chatcompletion_v2',
        'auth_type': 'bearer'
    },
    'tongyi': {
        'name': '通义千问 (阿里)',
        'default_model': 'qwen-turbo',
        'default_base_url': 'https://dashscope.aliyuncs.com',
        'endpoint': '/api/v1/services/aigc/text-generation/generation',
        'auth_type': 'dashscope'
    },
    'spark': {
        'name': '讯飞星火',
        'default_model': 'Spark4.0 Ultra',
        'default_base_url': 'https://spark-api.xf-yun.com',
        'endpoint': '/v4.0/chat',
        'auth_type': 'xfyun'
    },
    'wenxin': {
        'name': '文心一言 (百度)',
        'default_model': 'ernie-4.0-8k',
        'default_base_url': 'https://qianfan.baidubce.com',
        'endpoint': '/v2/chat/completions',
        'auth_type': 'bce'
    },
    'hunyuan': {
        'name': '腾讯混元',
        'default_model': 'hunyuan',
        'default_base_url': 'https://hunyuan.tencentcloudapi.com',
        'endpoint': '/v1/assistant/chatcompletion',
        'auth_type': 'tc'
    }
}

class OptimizedAnalyzer:
    """
    优化的AI分析器
    支持多API供应商和用户自定义配置
    """
    
    def __init__(self, api_key: Optional[str] = None, 
                 base_url: Optional[str] = None,
                 cache=None,
                 provider: str = 'deepseek',
                 model: str = None,
                 user_api_config: Optional[Dict] = None):
        """
        初始化分析器
        
        Args:
            api_key: API Key (系统级)
            base_url: API基础URL (系统级)
            cache: SmartCache实例
            provider: API供应商 (deepseek/openai/anthropic)
            model: 模型名称
            user_api_config: 用户自定义API配置
        """
        # 如果用户有自定义配置，优先使用
        if user_api_config:
            self.provider = user_api_config.get('provider', 'deepseek')
            self.api_key = user_api_config.get('api_key') or api_key or os.getenv('DEEPSEEK_API_KEY')
            self.base_url = user_api_config.get('base_url') or base_url or os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
            self.model = user_api_config.get('model') or model or 'deepseek-chat'
        else:
            self.provider = provider
            self.api_key = api_key or os.getenv('DEEPSEEK_API_KEY')
            self.base_url = base_url or os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
            self.model = model or 'deepseek-chat'
        
        # 获取供应商配置
        provider_config = API_PROVIDERS.get(self.provider, API_PROVIDERS['deepseek'])
        self.endpoint = provider_config.get('endpoint', '/v1/chat/completions')
        
        self.cache = cache
        
        # API调用统计
        self.stats = {
            'total_calls': 0,
            'cache_hits': 0,
            'failed_calls': 0,
            'tokens_used': 0,
            'cost_estimate_usd': 0.0
        }
    
    def _get_provider_config(self) -> Dict:
        """获取当前供应商配置"""
        return API_PROVIDERS.get(self.provider, API_PROVIDERS['deepseek'])
    
    def analyze_paper(self, title: str, abstract: str, 
                     force_refresh: bool = False) -> Dict[str, str]:
        """
        分析单篇文献（带缓存）
        
        Args:
            title: 文献标题
            abstract: 文献摘要
            force_refresh: 是否强制刷新（忽略缓存）
        
        Returns:
            分析结果字典
        """
        # 检查缓存
        if not force_refresh and self.cache:
            cached_result = self.cache.get_cached_analysis(title, abstract)
            if cached_result:
                self.stats['cache_hits'] += 1
                return cached_result
        
        # 检查API配置
        if not self.api_key:
            return self._get_error_result("未配置API Key，请在设置中配置")
        
        # 检查摘要长度
        if not abstract or len(abstract.strip()) < 50:
            return self._get_simple_analysis(title, abstract)
        
        # 调用API进行分析
        result = self._call_api_for_analysis(title, abstract)
        
        # 缓存结果
        if result and self.cache and not result.get('error'):
            self.cache.cache_analysis(title, abstract, result)
        
        return result
    
    def _get_error_result(self, error_msg: str) -> Dict:
        """生成错误结果"""
        return {
            'main_findings': error_msg,
            'innovations': '',
            'limitations': '',
            'future_directions': '',
            'error': error_msg
        }
    
    def _get_simple_analysis(self, title: str, abstract: str) -> Dict:
        """对短摘要进行简单分析（不调用API）"""
        return {
            'main_findings': f"摘要较短，无法深入分析。标题：{title[:100]}",
            'innovations': '摘要信息不足',
            'limitations': '摘要信息不足',
            'future_directions': '建议查看原文获取更多信息',
            'is_simple': True
        }
    
    def _call_api_for_analysis(self, title: str, abstract: str, 
                               max_retries: int = 3) -> Dict:
        """
        调用AI API进行分析
        
        Args:
            title: 标题
            abstract: 摘要
            max_retries: 最大重试次数
        
        Returns:
            分析结果
        """
        prompt = self._build_analysis_prompt(title, abstract)
        
        for attempt in range(max_retries):
            try:
                content = None
                
                # 根据不同供应商构建请求
                if self.provider == 'anthropic':
                    content = self._call_anthropic_api_content(prompt)
                elif self.provider == 'google':
                    content = self._call_google_api_content(prompt)
                elif self.provider == 'qwen' or self.provider == 'tongyi':
                    content = self._call_dashscope_api_content(prompt)
                elif self.provider == 'zhipu':
                    content = self._call_zhipu_api_content(prompt)
                elif self.provider == 'kimi':
                    content = self._call_kimi_api_content(prompt)
                elif self.provider == 'doubao':
                    content = self._call_doubao_api_content(prompt)
                elif self.provider == 'minimax':
                    content = self._call_minimax_api_content(prompt)
                elif self.provider == 'spark':
                    content = self._call_spark_api_content(prompt)
                elif self.provider == 'wenxin':
                    content = self._call_wenxin_api_content(prompt)
                elif self.provider == 'hunyuan':
                    content = self._call_hunyuan_api_content(prompt)
                else:
                    # 默认使用 OpenAI 兼容格式
                    response = requests.post(
                        f"{self.base_url}/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": "You are an expert in biomedical research."},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.5,
                            "max_tokens": 1500
                        },
                        timeout=60
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = data['choices'][0]['message']['content']
                    self._update_stats(data, self.provider)
                
                if content:
                    return self._parse_analysis_response(content)
                
            except Exception as e:
                print(f"Analysis attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    self.stats['failed_calls'] += 1
                    return self._get_error_result(f"API调用失败: {str(e)}")
        
        return self._get_error_result("达到最大重试次数")
    
    def _update_stats(self, data: Dict, provider: str):
        """更新API调用统计"""
        self.stats['total_calls'] += 1
        tokens = data.get('usage', {}).get('total_tokens', 0)
        self.stats['tokens_used'] += tokens
        
        # 根据供应商估算费用
        pricing = {
            'deepseek': 0.001,
            'openai': 0.0015,
            'anthropic': 0.00025,
            'google': 0.00035,
            'zhipu': 0.0001,
            'kimi': 0.00012,
            'doubao': 0.00008,
            'qwen': 0.0001,
            'tongyi': 0.0001,
            'minimax': 0.0001,
            'spark': 0.0001,
            'wenxin': 0.00012,
            'hunyuan': 0.0001
        }
        price = pricing.get(provider, 0.001)
        self.stats['cost_estimate_usd'] += tokens * price / 1000
    
    def _call_anthropic_api_content(self, prompt: str) -> str:
        """调用Anthropic Claude API"""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "max_tokens": 1500,
            "messages": [
                {"role": "user", "content": f"You are an expert in biomedical research. {prompt}"}
            ]
        }
        
        response = requests.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=body,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['content'][0]['text']
        self._update_stats(data, 'anthropic')
        return content
    
    def _call_google_api_content(self, prompt: str) -> str:
        """调用Google Gemini API"""
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        body = {
            "contents": [{
                "parts": [{"text": f"You are an expert in biomedical research. {prompt}"}]
            }],
            "generationConfig": {
                "temperature": 0.5,
                "maxOutputTokens": 1500
            }
        }
        
        response = requests.post(
            url,
            headers=headers,
            json=body,
            params={"key": self.api_key},
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['candidates'][0]['content']['parts'][0]['text']
        self._update_stats(data, 'google')
        return content
    
    def _call_dashscope_api_content(self, prompt: str) -> str:
        """调用阿里DashScope API (千问/通义)"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "input": {
                "messages": [
                    {"role": "system", "content": "You are an expert in biomedical research."},
                    {"role": "user", "content": prompt}
                ]
            },
            "parameters": {
                "temperature": 0.5,
                "max_tokens": 1500
            }
        }
        
        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            headers=headers,
            json=body,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['output']['choices'][0]['message']['content']
        self._update_stats(data, 'qwen')
        return content
    
    def _call_zhipu_api_content(self, prompt: str) -> str:
        """调用智谱AI API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert in biomedical research."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 1500
        }
        
        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            headers=headers,
            json=body,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['choices'][0]['message']['content']
        self._update_stats(data, 'zhipu')
        return content
    
    def _call_kimi_api_content(self, prompt: str) -> str:
        """调用Kimi API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert in biomedical research."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 1500
        }
        
        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            headers=headers,
            json=body,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['choices'][0]['message']['content']
        self._update_stats(data, 'kimi')
        return content
    
    def _call_doubao_api_content(self, prompt: str) -> str:
        """调用豆包API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert in biomedical research."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 1500
        }
        
        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            headers=headers,
            json=body,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['choices'][0]['message']['content']
        self._update_stats(data, 'doubao')
        return content
    
    def _call_minimax_api_content(self, prompt: str) -> str:
        """调用MiniMax API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert in biomedical research."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "max_tokens": 1500
        }
        
        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            headers=headers,
            json=body,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['choices'][0]['message']['content']
        self._update_stats(data, 'minimax')
        return content
    
    def _call_spark_api_content(self, prompt: str) -> str:
        """调用讯飞星火API"""
        import base64
        import hmac
        import hashlib
        import uuid
        from datetime import datetime
        
        # 生成鉴权参数
        now = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        headers = {
            "Content-Type": "application/json",
            "X-Date": now
        }
        
        body = {
            "header": {
                "app_id": self.api_key.split(':')[0] if ':' in self.api_key else self.api_key
            },
            "parameter": {
                "chat": {
                    "temperature": 0.5,
                    "max_tokens": 1500
                }
            },
            "payload": {
                "message": {
                    "text": [
                        {"role": "system", "content": "You are an expert in biomedical research."},
                        {"role": "user", "content": prompt}
                    ]
                }
            }
        }
        
        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            headers=headers,
            json=body,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['payload']['choices']['text'][0]['content']
        self._update_stats(data, 'spark')
        return content
    
    def _call_wenxin_api_content(self, prompt: str) -> str:
        """调用百度文心一言API"""
        headers = {
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert in biomedical research."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "max_output_tokens": 1500
        }
        
        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            headers=headers,
            json=body,
            params={"access_token": self.api_key},
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['result']
        self._update_stats(data, 'wenxin')
        return content
    
    def _call_hunyuan_api_content(self, prompt: str) -> str:
        """调用腾讯混元API"""
        import hmac
        import hashlib
        import base64
        import json
        from datetime import datetime
        
        timestamp = int(datetime.now().timestamp())
        
        headers = {
            "Content-Type": "application/json",
            "X-TC-Action": "ChatCompletions",
            "X-TC-Version": "2023-09-01",
            "X-TC-Timestamp": str(timestamp)
        }
        
        body = {
            "Model": self.model,
            "Messages": [
                {"Role": "system", "Content": "You are an expert in biomedical research."},
                {"Role": "user", "Content": prompt}
            ],
            "Temperature": 0.5,
            "MaxTokens": 1500
        }
        
        response = requests.post(
            f"{self.base_url}{self.endpoint}",
            headers=headers,
            json=body,
            params={"SecretId": self.api_key.split(':')[0], "Signature": "placeholder", "Timestamp": timestamp},
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['Choices'][0]['Message']['Content']
        self._update_stats(data, 'hunyuan')
        return content
    
    def _call_anthropic_api(self, prompt: str) -> requests.Response:
        """调用Anthropic Claude API"""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": self.model,
            "max_tokens": 1500,
            "messages": [
                {"role": "user", "content": f"You are an expert in biomedical research. {prompt}"}
            ]
        }
        
        response = requests.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=body,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        content = data['content'][0]['text']
        
        # 更新统计
        self.stats['total_calls'] += 1
        tokens = data.get('usage', {}).get('input_tokens', 0) + data.get('usage', {}).get('output_tokens', 0)
        self.stats['tokens_used'] += tokens
        self.stats['cost_estimate_usd'] += tokens * 0.00025 / 1000  # Claude pricing
        
        # 将content存入response对象以保持一致
        class MockResponse:
            def __init__(self, content):
                self._content = content
            def json(self):
                return {'choices': [{'message': {'content': self._content}}]}
        
        return MockResponse(content)
    
    def _build_analysis_prompt(self, title: str, abstract: str) -> str:
        """构建分析提示词（优化版本）"""
        return f"""分析以下生物医学文献，提供简洁分析（每项100字以内）：

标题: {title}

摘要: {abstract[:1000]}

请用中文提供：
1. 主要发现：核心结论
2. 创新点：技术/概念突破
3. 局限性：方法缺陷
4. 未来方向：后续研究建议

返回JSON格式：
{{"main_findings": "...", "innovations": "...", "limitations": "...", "future_directions": "..."}}"""
    
    def _parse_analysis_response(self, content: str) -> Dict[str, str]:
        """解析API返回的分析结果"""
        try:
            result = json.loads(content)
            return {
                'main_findings': result.get('main_findings', ''),
                'innovations': result.get('innovations', ''),
                'limitations': result.get('limitations', ''),
                'future_directions': result.get('future_directions', '')
            }
        except json.JSONDecodeError:
            # 尝试从文本中提取JSON
            try:
                if '```json' in content:
                    json_str = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    json_str = content.split('```')[1].split('```')[0].strip()
                else:
                    start = content.find('{')
                    end = content.rfind('}')
                    if start != -1 and end != -1:
                        json_str = content[start:end+1]
                    else:
                        raise ValueError("No JSON found")
                
                result = json.loads(json_str)
                return {
                    'main_findings': result.get('main_findings', ''),
                    'innovations': result.get('innovations', ''),
                    'limitations': result.get('limitations', ''),
                    'future_directions': result.get('future_directions', '')
                }
            except:
                # 返回原始内容作为main_findings
                return {
                    'main_findings': content[:500],
                    'innovations': '',
                    'limitations': '',
                    'future_directions': ''
                }
    
    def translate_abstract(self, abstract: str, max_retries: int = 3) -> str:
        """
        翻译摘要为中文（带缓存）
        
        Args:
            abstract: 英文摘要
            max_retries: 最大重试次数
        
        Returns:
            中文翻译
        """
        if not self.api_key:
            return "未配置API Key"
        
        if not abstract or len(abstract.strip()) < 10:
            return "摘要不可用"
        
        prompt = f"""将以下生物医学文献摘要翻译成中文（保持学术性，简洁）：

{abstract[:1500]}

直接返回翻译，不添加解释。"""
        
        for attempt in range(max_retries):
            try:
                # 使用与分析相同的API调用逻辑
                result = self._call_api_for_analysis_translate(prompt)
                return result
                
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return f"翻译失败: {str(e)}"
        
        return "翻译失败"
    
    def _call_api_for_analysis_translate(self, prompt: str) -> str:
        """调用API进行翻译"""
        if self.provider == 'anthropic':
            content = self._call_anthropic_api_content(prompt)
        elif self.provider == 'google':
            content = self._call_google_api_content(prompt)
        elif self.provider == 'qwen' or self.provider == 'tongyi':
            content = self._call_dashscope_api_content(prompt)
        elif self.provider == 'zhipu':
            content = self._call_zhipu_api_content(prompt)
        elif self.provider == 'kimi':
            content = self._call_kimi_api_content(prompt)
        elif self.provider == 'doubao':
            content = self._call_doubao_api_content(prompt)
        elif self.provider == 'minimax':
            content = self._call_minimax_api_content(prompt)
        elif self.provider == 'spark':
            content = self._call_spark_api_content(prompt)
        elif self.provider == 'wenxin':
            content = self._call_wenxin_api_content(prompt)
        elif self.provider == 'hunyuan':
            content = self._call_hunyuan_api_content(prompt)
        else:
            # 默认使用 OpenAI 兼容格式
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a professional biomedical translator."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1000
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            content = data['choices'][0]['message']['content']
            self._update_stats(data, self.provider)
        
        return content.strip()
    
    def batch_analyze(self, papers: List[Dict], batch_size: int = 10,
                     delay: float = 0.5, skip_translation: bool = False) -> List[Dict]:
        """
        批量分析文献（优化版）
        
        Args:
            papers: 文献列表
            batch_size: 批处理大小
            delay: 批次间延迟（秒）
            skip_translation: 是否跳过翻译
        
        Returns:
            分析后的文献列表
        """
        analyzed_papers = []
        api_calls = 0
        cache_hits = 0
        
        for i, paper in enumerate(papers):
            print(f"[{i+1}/{len(papers)}] 分析: {paper.get('title', 'Unknown')[:50]}...")
            
            title = paper.get('title', '')
            abstract = paper.get('abstract', '')
            
            # 分析
            analysis = self.analyze_paper(title, abstract)
            
            if analysis.get('is_simple'):
                cache_hits += 1
            elif not analysis.get('error'):
                api_calls += 1
            
            paper_copy = paper.copy()
            paper_copy['main_findings'] = analysis.get('main_findings', '')
            paper_copy['innovations'] = analysis.get('innovations', '')
            paper_copy['limitations'] = analysis.get('limitations', '')
            paper_copy['future_directions'] = analysis.get('future_directions', '')
            paper_copy['is_analyzed'] = True
            
            # 翻译（如果启用）
            if not skip_translation and abstract and len(abstract) > 50:
                abstract_cn = self.translate_abstract(abstract)
                paper_copy['abstract_cn'] = abstract_cn
                if not abstract_cn.startswith('翻译失败') and not abstract_cn.startswith('未配置'):
                    api_calls += 1
            else:
                paper_copy['abstract_cn'] = ''
            
            analyzed_papers.append(paper_copy)
            
            # 批次间延迟
            if (i + 1) % batch_size == 0 and i < len(papers) - 1:
                print(f"批次完成，等待 {delay} 秒...")
                time.sleep(delay)
        
        print(f"\n批量分析完成:")
        print(f"  - API调用: {api_calls} 次")
        print(f"  - 缓存命中: {cache_hits} 次")
        print(f"  - 总消耗: ${self.stats['cost_estimate_usd']:.4f}")
        
        return analyzed_papers
    
    def get_stats(self) -> Dict:
        """获取分析统计信息"""
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_calls': 0,
            'cache_hits': 0,
            'failed_calls': 0,
            'tokens_used': 0,
            'cost_estimate_usd': 0.0
        }


class AnalysisQueue:
    """
    分析队列
    用于管理待分析的文献，支持优先级和批量处理
    """
    
    def __init__(self, queue_file='data/analysis_queue.json'):
        self.queue_file = queue_file
        self.queue = self._load_queue()
    
    def _load_queue(self) -> List[Dict]:
        """加载队列"""
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_queue(self):
        """保存队列"""
        os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
        with open(self.queue_file, 'w', encoding='utf-8') as f:
            json.dump(self.queue, f, ensure_ascii=False, indent=2)
    
    def add_paper(self, paper: Dict, priority: int = 1):
        """
        添加文献到分析队列
        
        Args:
            paper: 文献字典
            priority: 优先级（1-5，5最高）
        """
        # 检查是否已在队列中
        paper_hash = paper.get('hash') or hash(paper.get('title', ''))
        for item in self.queue:
            if item.get('hash') == paper_hash:
                return False
        
        self.queue.append({
            'hash': paper_hash,
            'paper': paper,
            'priority': priority,
            'added_at': time.time(),
            'status': 'pending'
        })
        
        # 按优先级排序
        self.queue.sort(key=lambda x: (-x['priority'], x['added_at']))
        self._save_queue()
        return True
    
    def get_next_batch(self, batch_size: int = 10) -> List[Dict]:
        """获取下一批待分析的文献"""
        pending = [item for item in self.queue if item['status'] == 'pending']
        return pending[:batch_size]
    
    def mark_completed(self, paper_hashes: List[str]):
        """标记文献为已完成"""
        for item in self.queue:
            if item['hash'] in paper_hashes:
                item['status'] = 'completed'
                item['completed_at'] = time.time()
        
        # 清理已完成的文献
        self.queue = [item for item in self.queue if item['status'] != 'completed']
        self._save_queue()
    
    def get_queue_stats(self) -> Dict:
        """获取队列统计"""
        pending = sum(1 for item in self.queue if item['status'] == 'pending')
        completed = sum(1 for item in self.queue if item['status'] == 'completed')
        
        return {
            'pending': pending,
            'completed': completed,
            'total': len(self.queue)
        }
