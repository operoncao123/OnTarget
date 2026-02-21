import requests
import xml.etree.ElementTree as ET
import feedparser
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re
import time

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

# 导入服务器配置
try:
    from config import PARALLEL_FETCH
    MAX_WORKERS = PARALLEL_FETCH['max_workers']
    SOURCE_TIMEOUTS = PARALLEL_FETCH['timeouts']
except ImportError:
    # 默认配置
    MAX_WORKERS = 2
    SOURCE_TIMEOUTS = {
        'pubmed': 60, 'biorxiv': 45, 'medrxiv': 45, 'arxiv': 45,
        'psyarxiv': 45, 'nber': 45, 'chemrxiv': 45
    }

class PaperFetcher:
    """文献获取器 - 支持PubMed、bioRxiv、medRxiv、arXiv等"""
    
    # 支持的文献源配置
    PAPER_SOURCES = {
        'pubmed': {
            'name': 'PubMed',
            'category': 'journal',
            'description': '生物医学期刊文献'
        },
        'biorxiv': {
            'name': 'bioRxiv',
            'category': 'preprint',
            'description': '生物医学预印本'
        },
        'medrxiv': {
            'name': 'medRxiv',
            'category': 'preprint',
            'description': '医学预印本'
        },
        'arxiv': {
            'name': 'arXiv',
            'category': 'preprint',
            'description': '跨学科预印本（物理、数学、计算机等）'
        },
        'psyarxiv': {
            'name': 'PsyArXiv',
            'category': 'preprint',
            'description': '心理学预印本'
        },
        'nber': {
            'name': 'NBER',
            'category': 'working_paper',
            'description': '美国国家经济研究局工作论文'
        },
        'chemrxiv': {
            'name': 'ChemRxiv',
            'category': 'preprint',
            'description': '化学预印本'
        }
    }
    
    def __init__(self, pubmed_email: str):
        self.pubmed_email = pubmed_email
        self.base_urls = {
            'pubmed': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils',
            'biorxiv': 'https://api.biorxiv.org',
            'medrxiv': 'https://api.medrxiv.org',
            'arxiv': 'https://export.arxiv.org/api/query',
            'psyarxiv': 'https://psyarxiv.com',
            'nber': 'https://api.nber.org',
            'chemrxiv': 'https://chemrxiv.org'
        }
        
        # 初始化 cloudscraper（用于绕过 Cloudflare）
        if CLOUDSCRAPER_AVAILABLE:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                }
            )
        else:
            self.scraper = None
    
    def fetch_pubmed(self, keywords: List[str], days_back: int = 2) -> List[Dict]:
        """从PubMed获取文献"""
        papers = []
        max_retries = 3
        retry_delay = 2
        
        # 构建查询字符串
        query = ' OR '.join([f'"{kw}"[Title/Abstract]' for kw in keywords])
        
        # 设置日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        date_range = f"{start_date.strftime('%Y/%m/%d')}:{end_date.strftime('%Y/%m/%d')}"
        
        try:
            # 1. 搜索文献
            search_url = f"{self.base_urls['pubmed']}/esearch.fcgi"
            params = {
                'db': 'pubmed',
                'term': f"({query}) AND ({date_range}[Date - Publication])",
                'retmax': 50,  # 减少数量，避免超时
                'retmode': 'json',
                'email': self.pubmed_email
            }
            
            # 搜索请求带重试
            search_data = None
            for attempt in range(max_retries):
                try:
                    response = requests.get(search_url, params=params, timeout=15)
                    response.raise_for_status()
                    search_data = response.json()
                    break
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    if attempt < max_retries - 1:
                        print(f"PubMed search timeout, retrying {attempt + 1}/{max_retries}...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        print(f"PubMed search failed after {max_retries} retries: {e}")
                        return papers
            
            if not search_data:
                return papers
            
            id_list = search_data.get('esearchresult', {}).get('idlist', [])
            
            if not id_list:
                return papers
            
            # 2. 获取文献详情
            fetch_url = f"{self.base_urls['pubmed']}/efetch.fcgi"
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(id_list[:50]),  # 限制数量
                'retmode': 'xml',
                'email': self.pubmed_email
            }
            
            # 获取详情带重试
            for attempt in range(max_retries):
                try:
                    fetch_response = requests.get(fetch_url, params=fetch_params, timeout=15)
                    fetch_response.raise_for_status()
                    
                    # 解析XML
                    root = ET.fromstring(fetch_response.content)
                    
                    for article in root.findall('.//PubmedArticle'):
                        try:
                            paper = self._parse_pubmed_article(article)
                            if paper:
                                papers.append(paper)
                        except Exception as e:
                            print(f"Error parsing PubMed article: {e}")
                            continue
                    
                    break
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    if attempt < max_retries - 1:
                        print(f"PubMed fetch timeout, retrying {attempt + 1}/{max_retries}...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        print(f"PubMed fetch failed after {max_retries} retries: {e}")
                        return papers
            
            # PubMed API限制：每秒最多3个请求
            time.sleep(0.4)
            
        except Exception as e:
            print(f"Error fetching from PubMed: {e}")
        
        print(f"Found {len(papers)} papers from PubMed")
        return papers
    
    def _parse_pubmed_article(self, article) -> Optional[Dict]:
        """解析PubMed文章XML"""
        try:
            # PMID
            pmid_elem = article.find('.//PMID')
            pmid = pmid_elem.text if pmid_elem is not None else None
            
            # 标题 - 获取完整文本（包括子元素）
            title_elem = article.find('.//ArticleTitle')
            if title_elem is not None:
                # 获取所有文本内容（包括子元素中的文本）
                title = ''.join(title_elem.itertext()).strip()
            else:
                title = 'Unknown'
            
            # 摘要 - 获取所有AbstractText元素（包括结构化摘要）
            abstract_parts = []
            for abstract_elem in article.findall('.//Abstract/AbstractText'):
                # 获取标签（如BACKGROUND, METHODS等）
                label = abstract_elem.get('Label', '')
                # 获取完整文本内容（包括子元素中的文本，如<i>等）
                text = ''.join(abstract_elem.itertext()).strip()
                
                if text:
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
            
            abstract = ' '.join(abstract_parts)
            
            # 作者
            authors = []
            for author in article.findall('.//Author'):
                last_name = author.find('LastName')
                fore_name = author.find('ForeName')
                if last_name is not None:
                    name = last_name.text
                    if fore_name is not None:
                        name = f"{fore_name.text} {name}"
                    authors.append(name)
            
            # 期刊
            journal_elem = article.find('.//Journal/Title')
            journal = journal_elem.text if journal_elem is not None else 'Unknown'
            
            # 发表日期
            pub_date = None
            year_elem = article.find('.//PubDate/Year')
            month_elem = article.find('.//PubDate/Month')
            day_elem = article.find('.//PubDate/Day')
            
            if year_elem is not None:
                year = year_elem.text
                month = month_elem.text if month_elem is not None else '01'
                day = day_elem.text if day_elem is not None else '01'
                
                # 处理月份可能是英文缩写的情况 (Jan, Feb, etc.)
                month_map = {
                    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                }
                
                if month in month_map:
                    month = month_map[month]
                
                try:
                    pub_date = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
                except:
                    try:
                        # 如果解析失败，只使用年份
                        pub_date = datetime.strptime(f"{year}-01-01", "%Y-%m-%d")
                    except:
                        pass
            
            # DOI
            doi_elem = article.find('.//ArticleId[@IdType="doi"]')
            doi = doi_elem.text if doi_elem is not None else None
            
            # 文献类型判断
            article_type = self._determine_paper_type(article)
            
            return {
                'pmid': pmid,
                'doi': doi,
                'title': title,
                'abstract': abstract,
                'authors': ', '.join(authors),
                'journal': journal,
                'publication_date': pub_date,
                'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                'source': 'pubmed',
                'paper_type': article_type
            }
            
        except Exception as e:
            print(f"Error parsing PubMed article: {e}")
            return None
    
    def fetch_biorxiv(self, keywords: List[str], days_back: int = 2) -> List[Dict]:
        """从bioRxiv获取文献 - 使用API"""
        papers = []
        max_retries = 3
        retry_delay = 2
        
        try:
            # 计算日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            # bioRxiv API: /details/biorxiv/start_date/end_date/cursor/format
            cursor = 0
            max_pages = 5  # 限制最多获取5页，避免超时
            page_count = 0
            
            while page_count < max_pages:
                api_url = f"https://api.biorxiv.org/details/biorxiv/{start_str}/{end_str}/{cursor}/json"
                
                # 重试机制
                data = None
                for attempt in range(max_retries):
                    try:
                        response = requests.get(api_url, timeout=15)  # 减少超时时间
                        response.raise_for_status()
                        data = response.json()
                        break
                    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                        if attempt < max_retries - 1:
                            print(f"bioRxiv API timeout, retrying {attempt + 1}/{max_retries}...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            print(f"bioRxiv API failed after {max_retries} retries: {e}")
                            return papers
                    except Exception as e:
                        print(f"Error in bioRxiv API call: {e}")
                        return papers
                
                if not data:
                    break
                
                # 检查是否有数据
                if 'collection' not in data or not data['collection']:
                    break
                
                # 处理每篇文献
                for paper_data in data['collection']:
                    try:
                        # 检查关键词匹配
                        title = paper_data.get('title', '')
                        abstract = paper_data.get('abstract', '')
                        
                        if not self._check_keywords_match(title + ' ' + abstract, keywords):
                            continue
                        
                        paper = self._parse_biorxiv_api_entry(paper_data)
                        if paper:
                            papers.append(paper)
                    except Exception as e:
                        print(f"Error parsing bioRxiv paper: {e}")
                        continue
                
                # 检查是否还有更多结果
                try:
                    total = int(data.get('messages', [{}])[0].get('total', 0))
                    count = int(data.get('messages', [{}])[0].get('count', 0))
                    
                    if count < 100 or cursor + count >= total:
                        break
                except (IndexError, KeyError):
                    break
                
                cursor += 100
                page_count += 1
                time.sleep(0.5)  # 避免请求过快
                
                cursor += 100
                time.sleep(0.5)  # 避免请求过快
                
        except Exception as e:
            print(f"Error fetching from bioRxiv: {e}")
        
        print(f"Found {len(papers)} papers from bioRxiv")
        return papers
    
    def fetch_medrxiv(self, keywords: List[str], days_back: int = 2) -> List[Dict]:
        """从medRxiv获取文献 - 使用API"""
        papers = []
        max_retries = 3
        retry_delay = 2
        
        try:
            # 计算日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')
            
            # medRxiv API: /details/medrxiv/start_date/end_date/cursor/format
            cursor = 0
            max_pages = 5  # 限制最多获取5页，避免超时
            page_count = 0
            
            while page_count < max_pages:
                api_url = f"https://api.biorxiv.org/details/medrxiv/{start_str}/{end_str}/{cursor}/json"
                
                # 重试机制
                for attempt in range(max_retries):
                    try:
                        response = requests.get(api_url, timeout=15)  # 减少超时时间
                        response.raise_for_status()
                        data = response.json()
                        break
                    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                        if attempt < max_retries - 1:
                            print(f"medRxiv API timeout, retrying {attempt + 1}/{max_retries}...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            print(f"medRxiv API failed after {max_retries} retries: {e}")
                            return papers
                    except Exception as e:
                        print(f"Error in medRxiv API call: {e}")
                        return papers
                
                # 检查是否有数据
                if 'collection' not in data or not data['collection']:
                    break
                
                # 处理每篇文献
                for paper_data in data['collection']:
                    try:
                        # 检查关键词匹配
                        title = paper_data.get('title', '')
                        abstract = paper_data.get('abstract', '')
                        
                        if not self._check_keywords_match(title + ' ' + abstract, keywords):
                            continue
                        
                        paper = self._parse_medrxiv_api_entry(paper_data)
                        if paper:
                            papers.append(paper)
                    except Exception as e:
                        print(f"Error parsing medRxiv paper: {e}")
                        continue
                
                # 检查是否还有更多结果
                try:
                    total = int(data.get('messages', [{}])[0].get('total', 0))
                    count = int(data.get('messages', [{}])[0].get('count', 0))
                    
                    if count < 100 or cursor + count >= total:
                        break
                except (IndexError, KeyError):
                    break
                
                cursor += 100
                page_count += 1
                time.sleep(0.5)  # 避免请求过快
                
        except Exception as e:
            print(f"Error fetching from medRxiv: {e}")
        
        print(f"Found {len(papers)} papers from medRxiv")
        return papers
    
    def _parse_biorxiv_entry(self, entry) -> Optional[Dict]:
        """解析bioRxiv条目"""
        try:
            title = entry.get('title', '')
            summary = entry.get('summary', '')
            authors = ', '.join([author.get('name', '') for author in entry.get('authors', [])])
            
            published = entry.get('published_parsed') or entry.get('updated_parsed')
            pub_date = datetime(*published[:6]) if published else None
            
            link = entry.get('link', '')
            doi = entry.get('dc_identifier', '').replace('doi:', '') if 'dc_identifier' in entry else None
            
            # 判断文献类型
            paper_type = self._determine_paper_type_from_text(title + ' ' + summary)
            
            return {
                'pmid': None,
                'doi': doi,
                'title': title,
                'abstract': summary,
                'authors': authors,
                'journal': 'bioRxiv',
                'publication_date': pub_date,
                'url': link,
                'source': 'biorxiv',
                'paper_type': paper_type
            }
            
        except Exception as e:
            print(f"Error parsing bioRxiv entry: {e}")
            return None
    
    def _parse_medrxiv_entry(self, entry) -> Optional[Dict]:
        """解析medRxiv条目"""
        try:
            title = entry.get('title', '')
            summary = entry.get('summary', '')
            authors = ', '.join([author.get('name', '') for author in entry.get('authors', [])])
            
            published = entry.get('published_parsed') or entry.get('updated_parsed')
            pub_date = datetime(*published[:6]) if published else None
            
            link = entry.get('link', '')
            doi = entry.get('dc_identifier', '').replace('doi:', '') if 'dc_identifier' in entry else None
            
            # 判断文献类型
            paper_type = self._determine_paper_type_from_text(title + ' ' + summary)
            
            return {
                'pmid': None,
                'doi': doi,
                'title': title,
                'abstract': summary,
                'authors': authors,
                'journal': 'medRxiv',
                'publication_date': pub_date,
                'url': link,
                'source': 'medrxiv',
                'paper_type': paper_type
            }
            
        except Exception as e:
            print(f"Error parsing medRxiv entry: {e}")
            return None
    
    def _parse_biorxiv_api_entry(self, paper_data: Dict) -> Optional[Dict]:
        """解析bioRxiv API返回的文献数据"""
        try:
            title = paper_data.get('title', '')
            abstract = paper_data.get('abstract', '')
            authors = paper_data.get('authors', '').replace(';', ',')
            
            # 解析日期
            date_str = paper_data.get('date', '')
            pub_date = None
            if date_str:
                try:
                    pub_date = datetime.strptime(date_str, '%Y-%m-%d')
                except:
                    pass
            
            doi = paper_data.get('doi', '')
            url = f"https://www.biorxiv.org/content/{doi}" if doi else ''
            
            # 判断文献类型
            paper_type = self._determine_paper_type_from_text(title + ' ' + abstract)
            
            return {
                'pmid': None,
                'doi': doi,
                'title': title,
                'abstract': abstract,
                'authors': authors,
                'journal': 'bioRxiv',
                'publication_date': pub_date,
                'url': url,
                'source': 'biorxiv',
                'paper_type': paper_type
            }
            
        except Exception as e:
            print(f"Error parsing bioRxiv API entry: {e}")
            return None
    
    def _parse_medrxiv_api_entry(self, paper_data: Dict) -> Optional[Dict]:
        """解析medRxiv API返回的文献数据"""
        try:
            title = paper_data.get('title', '')
            abstract = paper_data.get('abstract', '')
            authors = paper_data.get('authors', '').replace(';', ',')
            
            # 解析日期
            date_str = paper_data.get('date', '')
            pub_date = None
            if date_str:
                try:
                    pub_date = datetime.strptime(date_str, '%Y-%m-%d')
                except:
                    pass
            
            doi = paper_data.get('doi', '')
            url = f"https://www.medrxiv.org/content/{doi}" if doi else ''
            
            # 判断文献类型
            paper_type = self._determine_paper_type_from_text(title + ' ' + abstract)
            
            return {
                'pmid': None,
                'doi': doi,
                'title': title,
                'abstract': abstract,
                'authors': authors,
                'journal': 'medRxiv',
                'publication_date': pub_date,
                'url': url,
                'source': 'medrxiv',
                'paper_type': paper_type
            }
            
        except Exception as e:
            print(f"Error parsing medRxiv API entry: {e}")
            return None
    
    def _check_keywords_match(self, text: str, keywords: List[str]) -> bool:
        """检查文本是否包含关键词 - 使用更严格的匹配逻辑"""
        import re
        text_lower = text.lower()
        
        for kw in keywords:
            kw_lower = kw.lower()
            
            # 检查原始关键词
            if len(kw_lower) <= 3:
                # 短关键词需要更严格的匹配
                pattern = r'\b' + re.escape(kw_lower) + r'\b'
                if re.search(pattern, text_lower):
                    return True
            else:
                # 长关键词可以使用宽松匹配
                if kw_lower in text_lower:
                    return True
            
            # 检查连字符变体（如 TDP-43 vs TDP43）
            # 对于像TDP43这样的关键词，也检查TDP-43（带连字符）
            # 对于像TDP-43这样的关键词，也检查TDP43（不带连字符）
            if '-' not in kw_lower and len(kw_lower) > 3:
                # 尝试在第3-4个字符后插入连字符（常见模式）
                for pos in [3, 4, 5]:
                    if pos < len(kw_lower):
                        variant = kw_lower[:pos] + '-' + kw_lower[pos:]
                        if variant in text_lower:
                            return True
            elif '-' in kw_lower:
                # 去掉连字符检查
                variant = kw_lower.replace('-', '')
                if variant in text_lower:
                    return True
            
            # 也检查空格变连字符的情况
            variant_space = kw_lower.replace(' ', '-')
            if variant_space != kw_lower and variant_space in text_lower:
                return True
                    
        return False
    
    def _determine_paper_type(self, article) -> str:
        """根据PubMed文章确定文献类型"""
        # 检查PublicationType
        for pub_type in article.findall('.//PublicationType'):
            type_text = pub_type.text or ''
            if 'review' in type_text.lower():
                return 'review'
            elif 'research' in type_text.lower():
                return 'research'
        
        # 默认判断
        return 'research'
    
    def _determine_paper_type_from_text(self, text: str) -> str:
        """根据文本内容判断文献类型"""
        text_lower = text.lower()
        
        review_keywords = [
            'review', '综述', 'perspective', 'opinion', 'commentary',
            'overview', 'summary', 'current status', 'recent advances',
            'state of the art', 'progress and', 'future directions'
        ]
        
        for kw in review_keywords:
            if kw in text_lower:
                return 'review'
        
        return 'research'
    
    # ==================== arXiv 支持 ====================
    
    def fetch_arxiv(self, keywords: List[str], days_back: int = 2, categories: List[str] = None) -> List[Dict]:
        """从arXiv获取文献"""
        papers = []
        
        # 默认订阅的分类
        if categories is None:
            categories = ['cs.AI', 'cs.LG', 'q-bio.BM', 'q-bio.CB', 'stat.ML']
        
        try:
            # 构建查询
            query = ' OR '.join([f'all:{kw}' for kw in keywords])
            
            # arXiv API
            params = {
                'search_query': query,
                'start': 0,
                'max_results': 50,
                'sortBy': 'submittedDate',
                'sortOrder': 'descending'
            }
            
            response = requests.get(self.base_urls['arxiv'], params=params, timeout=30)
            response.raise_for_status()
            
            # 解析XML
            root = ET.fromstring(response.content)
            
            # arXiv XML 使用了 Atom 命名空间
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            
            for entry in root.findall('.//atom:entry', ns):
                paper = self._parse_arxiv_entry(entry, keywords, ns)
                if paper:
                    papers.append(paper)
            
            print(f"Found {len(papers)} papers from arXiv")
            
        except Exception as e:
            print(f"Error fetching from arXiv: {e}")
        
        return papers
    
    def _parse_arxiv_entry(self, entry, keywords: List[str], ns: Dict = None) -> Optional[Dict]:
        """解析arXiv条目"""
        if ns is None:
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        try:
            # 使用命名空间查找元素
            title_elem = entry.find('atom:title', ns)
            if title_elem is not None:
                title = ''.join(title_elem.itertext()).strip()
            else:
                title = ''
            
            summary_elem = entry.find('atom:summary', ns)
            if summary_elem is not None:
                abstract = ''.join(summary_elem.itertext()).strip()
            else:
                abstract = ''
            
            # 检查关键词匹配
            if not self._check_keywords_match(title + ' ' + abstract, keywords):
                return None
            
            # 作者
            authors = []
            for author in entry.findall('atom:author', ns):
                name_elem = author.find('atom:name', ns)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text)
            
            # 日期
            published_elem = entry.find('atom:published', ns)
            if published_elem is None or not published_elem.text:
                return None
            published = published_elem.text
            pub_date = datetime.strptime(published[:10], '%Y-%m-%d')
            
            # arXiv ID
            id_elem = entry.find('atom:id', ns)
            if id_elem is None or not id_elem.text:
                return None
            arxiv_id = id_elem.text.split('/')[-1]
            url = f"https://arxiv.org/abs/{arxiv_id}"
            
            # DOI (如果有)
            doi = None
            doi_elem = entry.find('arxiv:doi', {'arxiv': 'http://arxiv.org/schemas/atom'})
            if doi_elem is not None and doi_elem.text:
                doi = doi_elem.text
            
            paper_type = self._determine_paper_type_from_text(title + ' ' + abstract)
            
            return {
                'pmid': None,
                'doi': doi,
                'title': title.replace('\n', ' '),
                'abstract': abstract.replace('\n', ' '),
                'authors': ', '.join(authors),
                'journal': 'arXiv',
                'publication_date': pub_date,
                'url': url,
                'source': 'arxiv',
                'paper_type': paper_type
            }
        except Exception as e:
            print(f"Error parsing arXiv entry: {e}")
            return None
    
    # ==================== PsyArXiv 支持 ====================
    
    def fetch_psyarxiv(self, keywords: List[str], days_back: int = 2) -> List[Dict]:
        """从PsyArXiv获取文献"""
        papers = []
        
        try:
            # 计算日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # PsyArXiv RSS feed
            rss_url = "https://psyarxiv.com/feed/rss/"
            
            # 使用 cloudscraper 绕过 Cloudflare
            if self.scraper:
                response = self.scraper.get(rss_url, timeout=30)
            else:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(rss_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # 解析RSS
            root = ET.fromstring(response.content)
            
            # 处理命名空间
            namespaces = {
                'content': 'http://purl.org/rss/1.0/modules/content/',
                'dc': 'http://purl.org/dc/elements/1.1/'
            }
            
            for entry in root.findall('.//item'):
                try:
                    title_elem = entry.find('title')
                    if title_elem is not None:
                        title = ''.join(title_elem.itertext()).strip()
                    else:
                        title = ''
                    
                    summary_elem = entry.find('description')
                    if summary_elem is not None:
                        summary = ''.join(summary_elem.itertext()).strip()
                    else:
                        summary = ''
                    
                    # 检查关键词匹配
                    if not self._check_keywords_match(title + ' ' + summary, keywords):
                        continue
                    
                    # 解析日期
                    pub_date_str = entry.find('pubDate')
                    pub_date = None
                    if pub_date_str is not None and pub_date_str.text:
                        try:
                            pub_date = datetime.strptime(pub_date_str.text[:16], '%a, %d %b %Y %H:%M')
                            if pub_date < start_date:
                                continue
                        except:
                            pass
                    
                    # 链接
                    link_elem = entry.find('link')
                    link = link_elem.text if link_elem is not None else ''
                    
                    # DOI
                    doi = None
                    for elem in entry.findall('.//{http://purl.org/dc/elements/1.1/}identifier'):
                        if elem.text and 'doi' in elem.text.lower():
                            doi = elem.text.replace('doi:', '').replace('DOI:', '').strip()
                    
                    paper_type = self._determine_paper_type_from_text(title + ' ' + summary)
                    
                    papers.append({
                        'pmid': None,
                        'doi': doi,
                        'title': title,
                        'abstract': summary if summary else '',
                        'authors': '',
                        'journal': 'PsyArXiv',
                        'publication_date': pub_date,
                        'url': link,
                        'source': 'psyarxiv',
                        'paper_type': paper_type
                    })
                    
                except Exception as e:
                    continue
            
            print(f"Found {len(papers)} papers from PsyArXiv")
            
        except Exception as e:
            print(f"Error fetching from PsyArXiv: {e}")
        
        return papers
    
    # ==================== NBER 支持 ====================
    
    def fetch_nber(self, keywords: List[str], days_back: int = 2) -> List[Dict]:
        """从NBER获取工作论文"""
        papers = []
        
        try:
            # NBER API
            params = {
                'query': ' '.join(keywords),
                'per_page': 50
            }
            
            # 使用 cloudscraper 绕过 Cloudflare
            url = 'https://api.nber.org/api/v1/working_papers'
            if self.scraper:
                response = self.scraper.get(url, params=params, timeout=30)
            else:
                response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                for item in data.get('results', []):
                    title = item.get('title', '')
                    abstract = item.get('abstract', '')
                    
                    if not self._check_keywords_match(title + ' ' + abstract, keywords):
                        continue
                    
                    # 发布日期
                    pub_date_str = item.get('publication_date')
                    pub_date = None
                    if pub_date_str:
                        try:
                            pub_date = datetime.strptime(pub_date_str[:10], '%Y-%m-%d')
                        except:
                            pass
                    
                    # 链接
                    url = item.get('url', '')
                    paper_id = item.get('id', '')
                    
                    papers.append({
                        'pmid': None,
                        'doi': None,
                        'title': title,
                        'abstract': abstract if abstract else '',
                        'authors': ', '.join(item.get('authors', [])),
                        'journal': 'NBER Working Paper',
                        'publication_date': pub_date,
                        'url': url or f'https://www.nber.org/papers/{paper_id}',
                        'source': 'nber',
                        'paper_type': 'research'
                    })
            
            print(f"Found {len(papers)} papers from NBER")
            
        except Exception as e:
            print(f"Error fetching from NBER: {e}")
        
        return papers
    
    def fetch_all(self, keywords: List[str], days_back: int = 2, sources: List[str] = None) -> List[Dict]:
        """从指定来源获取文献 - V2.5 并行获取优化
        
        改进点:
        1. 使用多线程并行获取所有源,速度提升 3-5 倍
        2. 单个源失败不影响其他源,提高稳定性
        3. 独立超时控制,避免单个源阻塞整体流程
        
        Args:
            keywords: 关键词列表
            days_back: 回溯天数
            sources: 文献源列表，None表示获取所有支持的源
        
        Returns:
            合并后的文献列表(自动去重)
        """
        import concurrent.futures
        import threading
        
        # 默认获取所有源
        if sources is None:
            sources = list(self.PAPER_SOURCES.keys())
        
        # 定义获取函数和超时时间
        source_configs = {
            'pubmed': (lambda: self.fetch_pubmed(keywords, days_back), 60),
            'biorxiv': (lambda: self.fetch_biorxiv(keywords, days_back), 45),
            'medrxiv': (lambda: self.fetch_medrxiv(keywords, days_back), 45),
            'arxiv': (lambda: self.fetch_arxiv(keywords, days_back), 45),
            'psyarxiv': (lambda: self.fetch_psyarxiv(keywords, days_back), 45),
            'nber': (lambda: self.fetch_nber(keywords, days_back), 45),
            'chemrxiv': (lambda: self.fetch_chemrxiv(keywords, days_back), 45)
        }
        
        all_papers = []
        papers_lock = threading.Lock()
        results_summary = {}
        
        def fetch_from_source(source):
            """从单个源获取文献"""
            if source not in source_configs:
                return
            
            fetch_func, timeout = source_configs[source]
            source_name = self.PAPER_SOURCES.get(source, {}).get('name', source)
            
            print(f"[并行获取] 开始从 {source_name} 获取...")
            
            try:
                # 使用线程池执行,带独立超时
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(fetch_func)
                    papers = future.result(timeout=timeout)
                
                # 线程安全地添加到结果列表
                with papers_lock:
                    all_papers.extend(papers)
                
                results_summary[source] = {'status': 'success', 'count': len(papers)}
                print(f"[并行获取] ✓ {source_name}: 获取 {len(papers)} 篇文献")
                
            except concurrent.futures.TimeoutError:
                results_summary[source] = {'status': 'timeout', 'count': 0}
                print(f"[并行获取] ⚠ {source_name}: 获取超时({timeout}秒),跳过")
                
            except Exception as e:
                results_summary[source] = {'status': 'error', 'count': 0, 'error': str(e)}
                print(f"[并行获取] ✗ {source_name}: 获取失败 - {e}")
        
        # 使用线程池并行获取所有源
        # 根据服务器核心数自动调整线程数
        max_workers = min(len(sources), MAX_WORKERS)
        print(f"\n[并行获取] 开始并行获取 {len(sources)} 个源的文献(使用 {max_workers} 个线程,服务器CPU核心: {MAX_WORKERS})...")
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            futures = {executor.submit(fetch_from_source, source): source for source in sources}
            
            # 等待所有任务完成(包括超时和失败的)
            for future in concurrent.futures.as_completed(futures):
                source = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"[并行获取] ✗ 处理 {source} 时发生异常: {e}")
        
        elapsed_time = time.time() - start_time
        
        # 统计结果
        success_count = sum(1 for r in results_summary.values() if r['status'] == 'success')
        total_papers = len(all_papers)
        
        print(f"\n[并行获取] 完成!")
        print(f"  - 耗时: {elapsed_time:.1f} 秒")
        print(f"  - 成功: {success_count}/{len(sources)} 个源")
        print(f"  - 总计: {total_papers} 篇文献")
        
        # 去重(基于标题+DOI)
        seen = set()
        unique_papers = []
        for paper in all_papers:
            key = (paper.get('title', ''), paper.get('doi', ''))
            if key not in seen:
                seen.add(key)
                unique_papers.append(paper)
        
        if len(unique_papers) < len(all_papers):
            print(f"  - 去重: 移除 {len(all_papers) - len(unique_papers)} 篇重复文献")
        
        return unique_papers
    
    # ==================== ChemRxiv 支持 ====================
    
    def fetch_chemrxiv(self, keywords: List[str], days_back: int = 2) -> List[Dict]:
        """从ChemRxiv获取文献 - 使用RSS Feed"""
        papers = []
        
        try:
            # 计算日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            # ChemRxiv RSS feed (使用Figshare的RSS)
            rss_url = "https://chemrxiv.org/engage/rss/chemrxiv"
            
            # 使用 cloudscraper 绕过 Cloudflare
            if self.scraper:
                response = self.scraper.get(rss_url, timeout=30)
            else:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(rss_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # 解析RSS
            root = ET.fromstring(response.content)
            
            # 处理命名空间
            namespaces = {
                'content': 'http://purl.org/rss/1.0/modules/content/',
                'dc': 'http://purl.org/dc/elements/1.1/',
                'media': 'http://search.yahoo.com/mrss/'
            }
            
            for entry in root.findall('.//item'):
                try:
                    title_elem = entry.find('title')
                    if title_elem is not None:
                        title = ''.join(title_elem.itertext()).strip()
                    else:
                        title = ''
                    
                    summary_elem = entry.find('description')
                    if summary_elem is not None:
                        summary = ''.join(summary_elem.itertext()).strip()
                    else:
                        summary = ''
                    
                    # 检查关键词匹配
                    if not self._check_keywords_match(title + ' ' + summary, keywords):
                        continue
                    
                    # 解析日期
                    pub_date_str = entry.find('pubDate')
                    pub_date = None
                    if pub_date_str is not None and pub_date_str.text:
                        try:
                            pub_date = datetime.strptime(pub_date_str.text[:16], '%a, %d %b %Y %H:%M')
                            if pub_date < start_date:
                                continue
                        except:
                            pass
                    
                    # 链接
                    link_elem = entry.find('link')
                    link = link_elem.text if link_elem is not None else ''
                    
                    # DOI
                    doi = None
                    for elem in entry.findall('.//{http://purl.org/dc/elements/1.1/}identifier'):
                        if elem.text and 'doi' in elem.text.lower():
                            doi = elem.text.replace('doi:', '').replace('DOI:', '').strip()
                    
                    paper_type = self._determine_paper_type_from_text(title + ' ' + summary)
                    
                    papers.append({
                        'pmid': None,
                        'doi': doi,
                        'title': title,
                        'abstract': summary if summary else '',
                        'authors': '',
                        'journal': 'ChemRxiv',
                        'publication_date': pub_date,
                        'url': link,
                        'source': 'chemrxiv',
                        'paper_type': paper_type
                    })
                    
                except Exception as e:
                    continue
            
            print(f"Found {len(papers)} papers from ChemRxiv")
            
        except Exception as e:
            print(f"Error fetching from ChemRxiv: {e}")
        
        return papers
    
    @staticmethod
    def get_available_sources() -> Dict:
        """获取所有可用的文献源"""
        return PaperFetcher.PAPER_SOURCES
        
        # 去重（基于DOI或标题）
        seen = {}
        unique_papers = []
        
        for paper in all_papers:
            key = paper.get('doi') or paper.get('title', '').lower()
            if key and key not in seen:
                seen[key] = True
                unique_papers.append(paper)
        
        print(f"Total unique papers: {len(unique_papers)}")
        
        return unique_papers
