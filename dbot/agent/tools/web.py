"""Web 工具：web_search 和 web_fetch。"""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from dbot.agent.tools.base import Tool

# 共享常量
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5  # 限制重定向以防止 DoS 攻击


def _strip_tags(text: str) -> str:
    """移除 HTML 标签并解码实体。"""
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """标准化空白字符。"""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """验证 URL：必须是带有有效域名的 http(s)。"""
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, f"仅允许 http/https，得到 '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "缺少域名"
        return True, ""
    except Exception as e:
        return False, str(e)


class WebSearchTool(Tool):
    """使用百度搜索 API（千帆平台）搜索网页。"""

    name = "web_search"
    description = "搜索网页。返回标题、URL 和摘要。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "count": {"type": "integer", "description": "结果数（1-20）", "minimum": 1, "maximum": 20},
            "recency": {"type": "string", "description": "时间过滤器：week、month、semiyear、year", "enum": ["week", "month", "semiyear", "year"]}
        },
        "required": ["query"]
    }

    # 百度搜索的 API 端点
    BAIDU_SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"

    def __init__(self, api_key: str | None = None, max_results: int = 5, proxy: str | None = None):
        # 支持 BAIDU_SEARCH_API_KEY 和 BRAVE_API_KEY 以实现向后兼容
        self._init_api_key = api_key
        self.max_results = max_results
        self.proxy = proxy

    @property
    def api_key(self) -> str:
        """在调用时解析 API 密钥，以便获取环境/配置更改。"""
        key = self._init_api_key or os.environ.get("BAIDU_SEARCH_API_KEY") or os.environ.get("BRAVE_API_KEY", "")
        return key

    async def execute(self, query: str, count: int | None = None, recency: str | None = None, **kwargs: Any) -> str:
        if not self.api_key:
            return (
                "错误: 未配置百度搜索 API 密钥。请在 "
                "~/.dbot/config.json 中的 tools.web.search.apiKey 设置，"
                "（或导出 BAIDU_SEARCH_API_KEY），然后重启网关。"
            )

        try:
            n = min(max(count or self.max_results, 1), 20)
            logger.debug("WebSearch: {}", "已启用代理" if self.proxy else "直连")

            # 构建百度搜索 API 的请求体
            body = {
                "messages": [
                    {"role": "user", "content": query}
                ],
                "search_source": "baidu_search_v2",
                "resource_type_filter": [{"type": "web", "top_k": n}]
            }

            # 如果指定，添加时间过滤器
            if recency:
                body["search_recency_filter"] = recency

            async with httpx.AsyncClient(proxy=self.proxy) as client:
                r = await client.post(
                    self.BAIDU_SEARCH_URL,
                    json=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    },
                    timeout=15.0
                )
                r.raise_for_status()

            data = r.json()

            # 检查错误响应
            if "code" in data and data["code"]:
                return f"错误: {data.get('message', '未知错误')} (代码: {data.get('code')})"

            results = data.get("references", [])
            if not results:
                return f"没有结果: {query}"

            lines = [f"结果: {query}\n"]
            for i, item in enumerate(results[:n], 1):
                title = item.get("title", "")
                url = item.get("url", "")
                website = item.get("website", "")
                content = item.get("content", "")
                date = item.get("date", "")

                lines.append(f"{i}. {title}")
                lines.append(f"   URL: {url}")
                if website:
                    lines.append(f"   站点: {website}")
                if date:
                    lines.append(f"   日期: {date}")
                if content:
                    # 截断长内容
                    snippet = content[:300] + "..." if len(content) > 300 else content
                    lines.append(f"   {snippet}")
            return "\n".join(lines)
        except httpx.ProxyError as e:
            logger.error("WebSearch 代理错误: {}", e)
            return f"代理错误: {e}"
        except httpx.HTTPStatusError as e:
            logger.error("WebSearch HTTP 错误: {}", e)
            return f"HTTP 错误: {e.response.status_code} - {e.response.text[:200]}"
        except Exception as e:
            logger.error("WebSearch 错误: {}", e)
            return f"错误: {e}"


class WebFetchTool(Tool):
    """使用 Readability 从 URL 获取并提取内容。"""

    name = "web_fetch"
    description = "获取 URL 并提取可读内容（HTML → markdown/文本）。"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要获取的 URL"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100}
        },
        "required": ["url"]
    }

    def __init__(self, max_chars: int = 50000, proxy: str | None = None):
        self.max_chars = max_chars
        self.proxy = proxy

    async def execute(self, url: str, extractMode: str = "markdown", maxChars: int | None = None, **kwargs: Any) -> str:
        from readability import Document

        max_chars = maxChars or self.max_chars
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps({"error": f"URL 验证失败: {error_msg}", "url": url}, ensure_ascii=False)

        try:
            logger.debug("WebFetch: {}", "已启用代理" if self.proxy else "直连")
            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0,
                proxy=self.proxy,
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()

            ctype = r.headers.get("content-type", "")

            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2, ensure_ascii=False), "json"
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                doc = Document(r.text)
                content = self._to_markdown(doc.summary()) if extractMode == "markdown" else _strip_tags(doc.summary())
                text = f"# {doc.title()}\n\n{content}" if doc.title() else content
                extractor = "readability"
            else:
                text, extractor = r.text, "raw"

            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]

            return json.dumps({"url": url, "finalUrl": str(r.url), "status": r.status_code,
                              "extractor": extractor, "truncated": truncated, "length": len(text), "text": text}, ensure_ascii=False)
        except httpx.ProxyError as e:
            logger.error("WebFetch {} 代理错误: {}", url, e)
            return json.dumps({"error": f"代理错误: {e}", "url": url}, ensure_ascii=False)
        except Exception as e:
            logger.error("WebFetch {} 错误: {}", url, e)
            return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)

    def _to_markdown(self, html: str) -> str:
        """将 HTML 转换为 markdown。"""
        # 在剥离标签之前转换链接、标题、列表
        text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
                      lambda m: f'[{_strip_tags(m[2])}]({m[1]})', html, flags=re.I)
        text = re.sub(r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
                      lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n', text, flags=re.I)
        text = re.sub(r'<li[^>]*>([\s\S]*?)</li>', lambda m: f'\n- {_strip_tags(m[1])}', text, flags=re.I)
        text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
        text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
        return _normalize(_strip_tags(text))
