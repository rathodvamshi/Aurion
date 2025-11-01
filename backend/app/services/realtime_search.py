"""Real-Time Web Search Service

Provides real-time web search functionality using SerpAPI and Google Custom Search API.
Includes web scraping to extract full article content from URLs.

Features:
- Dual provider support (SerpAPI primary, Google Custom Search fallback)
- Web scraping using newspaper3k and BeautifulSoup
- Content extraction and summarization
- Redis caching for search results (1 hour TTL)
- Automatic failover between providers
- Async/await support for non-blocking searches
- Result filtering and relevance scoring
"""

from __future__ import annotations

import logging
import json
import hashlib
import asyncio
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from newspaper import Article
from app.config import settings
from app.services.redis_service import get_client, get_prefetched_data, set_prefetched_data

logger = logging.getLogger(__name__)

# Cache TTL: 1 hour (3600 seconds) for search results
SEARCH_CACHE_TTL = 3600
# Max article length to extract (characters)
MAX_ARTICLE_LENGTH = 3000
# Timeout for scraping (seconds)
SCRAPE_TIMEOUT = 8.0


def _generate_cache_key(query: str) -> str:
    """Generate a cache key for the search query."""
    query_normalized = query.strip().lower()
    key_hash = hashlib.sha256(query_normalized.encode()).hexdigest()[:16]
    return f"search:query:{key_hash}"


async def _serpapi_search(query: str) -> List[Dict[str, Any]]:
    """Search using SerpAPI (primary provider)."""
    if not settings.SERPAPI_KEY:
        raise ValueError("SERPAPI_KEY not configured")
    
    logger.debug(f"🔍 Using SerpAPI for query: {query[:50]}")
    
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": settings.SERPAPI_KEY,
        "engine": "google",
        "num": 10,  # Get top 10 results
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Extract organic results
            results = data.get("organic_results", [])
            
            # Format results consistently
            formatted = []
            for item in results[:10]:  # Limit to 10
                formatted.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "source": "serpapi",
                })
            
            return formatted
    except Exception as e:
        logger.error(f"SerpAPI search failed: {e}")
        raise


async def _google_custom_search(query: str) -> List[Dict[str, Any]]:
    """Search using Google Custom Search API (fallback provider)."""
    if not settings.GOOGLE_API_KEY or not settings.GOOGLE_SEARCH_CX_ID:
        raise ValueError("GOOGLE_API_KEY or GOOGLE_SEARCH_CX_ID not configured")
    
    logger.debug(f"🔍 Using Google Custom Search for query: {query[:50]}")
    
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": settings.GOOGLE_API_KEY,
        "cx": settings.GOOGLE_SEARCH_CX_ID,
        "q": query,
        "num": 10,  # Get top 10 results
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Extract items
            items = data.get("items", [])
            
            # Format results consistently
            formatted = []
            for item in items[:10]:  # Limit to 10
                formatted.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "source": "google_custom_search",
                })
            
            return formatted
    except Exception as e:
        logger.error(f"Google Custom Search failed: {e}")
        raise


async def smart_search(query: str, use_cache: bool = True) -> List[Dict[str, Any]]:
    """
    Perform a smart web search with automatic provider failover and caching.
    
    Args:
        query: The search query string
        use_cache: Whether to use Redis cache (default: True)
    
    Returns:
        List of search results, each containing:
        - title: Result title
        - link: URL
        - snippet: Description/snippet
        - source: Provider used ("serpapi" or "google_custom_search")
    
    Example:
        results = await smart_search("latest AI news 2025")
        for result in results:
            print(f"{result['title']}: {result['link']}")
    """
    if not query or not query.strip():
        return []
    
    query = query.strip()
    
    # Check cache first
    if use_cache:
        try:
            cache_key = _generate_cache_key(query)
            cached = await get_prefetched_data(cache_key)
            if cached and isinstance(cached, list):
                logger.info(f"✅ Cache hit for query: {query[:50]}")
                return cached
        except Exception as e:
            logger.debug(f"Cache check failed (non-fatal): {e}")
    
    # Try SerpAPI first (primary)
    results = None
    provider_used = None
    
    try:
        results = await _serpapi_search(query)
        provider_used = "serpapi"
        logger.info(f"✅ SerpAPI search successful for: {query[:50]}")
    except Exception as e:
        logger.warning(f"⚠️ SerpAPI failed, trying Google Custom Search: {e}")
        
        # Fallback to Google Custom Search
        try:
            results = await _google_custom_search(query)
            provider_used = "google_custom_search"
            logger.info(f"✅ Google Custom Search successful for: {query[:50]}")
        except Exception as e2:
            logger.error(f"❌ Both search providers failed. SerpAPI: {e}, Google: {e2}")
            # Return empty list - system will continue without search results
            # This is non-fatal and won't break the conversation
            return []
    
    # Update source field if needed
    if results and provider_used:
        for result in results:
            result["source"] = provider_used
    
    # Cache the results
    if use_cache and results:
        try:
            cache_key = _generate_cache_key(query)
            await set_prefetched_data(cache_key, results, ttl_seconds=SEARCH_CACHE_TTL)
        except Exception as e:
            logger.debug(f"Cache store failed (non-fatal): {e}")
    
    return results or []


async def format_search_context(search_results: List[Dict[str, Any]], max_results: int = 5) -> str:
    """
    Format search results into a context string for AI prompts.
    
    Args:
        search_results: List of search result dictionaries
        max_results: Maximum number of results to include (default: 5)
    
    Returns:
        Formatted string ready for inclusion in AI prompts
    """
    if not search_results:
        return ""
    
    # Limit results
    limited = search_results[:max_results]
    
    formatted_parts = []
    for idx, result in enumerate(limited, 1):
        title = result.get("title", "").strip()
        snippet = result.get("snippet", "").strip()
        link = result.get("link", "").strip()
        
        if title or snippet:
            part = f"[Result {idx}]"
            if title:
                part += f"\nTitle: {title}"
            if snippet:
                part += f"\nSummary: {snippet}"
            if link:
                part += f"\nSource: {link}"
            formatted_parts.append(part)
    
    return "\n\n".join(formatted_parts) if formatted_parts else ""


async def build_search_context(user_memory: Optional[str], search_results: List[Dict[str, Any]]) -> str:
    """
    Combine user memory with real-time search results into a unified context.
    
    Args:
        user_memory: Formatted user memory/facts (from memory system)
        search_results: List of search result dictionaries
    
    Returns:
        Combined context string for AI prompts
    """
    parts = []
    
    if user_memory:
        parts.append(f"🔹 Personal Memory:\n{user_memory}")
    
    if search_results:
        formatted_results = await format_search_context(search_results)
        if formatted_results:
            parts.append(f"🔹 Real-Time Web Info:\n{formatted_results}")
    
    return "\n\n".join(parts) if parts else ""


def should_use_search(user_message: str) -> bool:
    """
    Determine if a user message requires real-time web search.
    
    Args:
        user_message: The user's message
    
    Returns:
        True if search is recommended, False otherwise
    """
    if not user_message:
        return False
    
    message_lower = user_message.lower()
    
    # Keywords that suggest real-time info is needed
    search_triggers = [
        "latest", "recent", "current", "today", "now", "this week", "this month",
        "news", "update", "updates", "what's happening", "trending", "new", "recently",
        "search", "find", "look up", "web", "internet", "online",
        "tech", "technology", "gadget", "gadgets", "innovation",
        "2024", "2025",  # Recent years suggest current events
        "breaking", "happening", "going on",
        "reuters", "cnn", "wired", "techcrunch", "the verge",  # News sources
    ]
    
    # Questions that likely need real-time data
    question_triggers = [
        "what's new", "what is new", "what happened", "what is happening",
        "tell me about", "show me", "find me", "what are", "what is",
        "recent tech", "latest tech", "tech updates", "tech news",
    ]
    
    # Check for triggers
    for trigger in search_triggers + question_triggers:
        if trigger in message_lower:
            return True
    
    return False


async def scrape_article_content(url: str) -> Optional[Dict[str, Any]]:
    """
    Scrape full article content from a URL using newspaper3k and BeautifulSoup.
    
    Args:
        url: The URL to scrape
    
    Returns:
        Dictionary containing:
        - title: Article title
        - text: Full article text (truncated to MAX_ARTICLE_LENGTH)
        - summary: Article summary if available
        - authors: List of authors
        - publish_date: Publication date if available
        - success: Whether scraping was successful
    """
    if not url or not url.startswith(("http://", "https://")):
        return None
    
    # Try BeautifulSoup first (async-friendly)
    try:
        async with httpx.AsyncClient(timeout=SCRAPE_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Remove script, style, and other non-content elements
            for element in soup(["script", "style", "meta", "link", "nav", "header", "footer", "aside"]):
                element.decompose()
            
            # Extract title
            title = ""
            title_selectors = ['h1', 'title', '.article-title', '.post-title', '[itemprop="headline"]']
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text().strip()
                    break
            
            # Try to find main content areas (prioritize semantic HTML5 and common class names)
            content_selectors = [
                'article', 'main', '[role="main"]',
                '.content', '.article-body', '.post-content', 
                '#content', '.entry-content', '.article-content',
                '[itemprop="articleBody"]', '.article-text'
            ]
            
            text_parts = []
            for selector in content_selectors:
                elements = soup.select(selector)
                if elements:
                    for elem in elements:
                        text = elem.get_text(separator=' ', strip=True)
                        if len(text) > 200:  # Only include substantial content
                            text_parts.append(text)
                    break
            
            # Fallback: extract from body but filter out likely non-content
            if not text_parts or len(' '.join(text_parts)) < 200:
                body = soup.find('body')
                if body:
                    # Remove navigation, headers, footers
                    for elem in body.find_all(['nav', 'header', 'footer', 'aside', 'form']):
                        elem.decompose()
                    body_text = body.get_text(separator=' ', strip=True)
                    if len(body_text) > 200:
                        text_parts.append(body_text)
            
            if text_parts:
                full_text = ' '.join(text_parts)
                # Clean up excessive whitespace
                full_text = ' '.join(full_text.split())[:MAX_ARTICLE_LENGTH]
                
                if len(full_text) > 100:
                    return {
                        "title": title,
                        "text": full_text,
                        "summary": full_text[:500] + "..." if len(full_text) > 500 else full_text,
                        "authors": [],
                        "publish_date": None,
                        "success": True,
                    }
    except Exception as e:
        logger.debug(f"BeautifulSoup scraping failed for {url}: {e}")
    
    # Fallback: Try newspaper3k (run in thread pool since it's synchronous)
    try:
        def _newspaper_scrape():
            article = Article(url, language='en')
            article.download()
            article.parse()
            article.nlp()
            return {
                "title": article.title or "",
                "text": (article.text or "")[:MAX_ARTICLE_LENGTH],
                "summary": article.summary or "",
                "authors": article.authors or [],
                "publish_date": article.publish_date.isoformat() if article.publish_date else None,
                "success": True,
            }
        
        content = await asyncio.to_thread(_newspaper_scrape)
        
        if content.get("text") and len(content["text"]) > 100:
            return content
    except Exception as e:
        logger.debug(f"Newspaper3k scraping failed for {url}: {e}")
    
    return None


async def scrape_multiple_articles(urls: List[str], max_concurrent: int = 3) -> List[Dict[str, Any]]:
    """
    Scrape multiple articles concurrently with rate limiting.
    
    Args:
        urls: List of URLs to scrape
        max_concurrent: Maximum concurrent scrapes (default: 3)
    
    Returns:
        List of scraped article content dictionaries
    """
    if not urls:
        return []
    
    # Limit to top 5 URLs to avoid too many requests
    urls = urls[:5]
    
    async def scrape_one(url: str) -> Optional[Dict[str, Any]]:
        try:
            result = await scrape_article_content(url)
            if result:
                result["url"] = url
            return result
        except Exception as e:
            logger.debug(f"Scrape failed for {url}: {e}")
            return None
    
    # Use semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def scrape_with_limit(url: str):
        async with semaphore:
            return await scrape_one(url)
    
    # Scrape all URLs concurrently
    tasks = [scrape_with_limit(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out None and exceptions
    valid_results = []
    for result in results:
        if result and isinstance(result, dict) and result.get("success"):
            valid_results.append(result)
    
    return valid_results


async def smart_search_with_scraping(query: str, scrape_content: bool = True, use_cache: bool = True) -> List[Dict[str, Any]]:
    """
    Perform a smart web search and optionally scrape article content.
    
    Args:
        query: The search query string
        scrape_content: Whether to scrape full article content (default: True)
        use_cache: Whether to use Redis cache (default: True)
    
    Returns:
        List of search results with scraped content, each containing:
        - title: Result title
        - link: URL
        - snippet: Description/snippet
        - content: Scraped article text (if scraping enabled)
        - summary: Article summary (if available)
        - source: Provider used
    """
    # Get search results
    search_results = await smart_search(query, use_cache=use_cache)
    
    if not search_results or not scrape_content:
        return search_results
    
    # Extract URLs for scraping
    urls = [result.get("link") for result in search_results if result.get("link")]
    
    if not urls:
        return search_results
    
    logger.info(f"📄 Scraping {len(urls)} articles for detailed content...")
    
    # Scrape articles concurrently
    scraped_articles = await scrape_multiple_articles(urls, max_concurrent=3)
    
    # Create a URL to content mapping
    url_to_content = {}
    for article in scraped_articles:
        url = article.get("url")
        if url:
            url_to_content[url] = article
    
    # Enhance search results with scraped content
    enhanced_results = []
    for result in search_results:
        url = result.get("link", "")
        enhanced = result.copy()
        
        if url in url_to_content:
            article = url_to_content[url]
            # Prefer scraped title if available and better
            if article.get("title") and len(article["title"]) > len(result.get("title", "")):
                enhanced["title"] = article["title"]
            
            # Add scraped content
            if article.get("text"):
                enhanced["content"] = article["text"]
            if article.get("summary"):
                enhanced["summary"] = article["summary"]
            if article.get("authors"):
                enhanced["authors"] = article["authors"]
            if article.get("publish_date"):
                enhanced["publish_date"] = article["publish_date"]
        
        enhanced_results.append(enhanced)
    
    logger.info(f"✅ Successfully scraped {len(scraped_articles)} articles")
    
    return enhanced_results


async def format_search_context(search_results: List[Dict[str, Any]], max_results: int = 5, include_content: bool = True) -> str:
    """
    Format search results into a context string for AI prompts.
    
    Args:
        search_results: List of search result dictionaries
        max_results: Maximum number of results to include (default: 5)
        include_content: Whether to include scraped content (default: True)
    
    Returns:
        Formatted string ready for inclusion in AI prompts
    """
    if not search_results:
        return ""
    
    # Limit results
    limited = search_results[:max_results]
    
    formatted_parts = []
    for idx, result in enumerate(limited, 1):
        title = result.get("title", "").strip()
        snippet = result.get("snippet", "").strip()
        link = result.get("link", "").strip()
        content = result.get("content", "").strip()
        summary = result.get("summary", "").strip()
        
        if title or snippet or content:
            part = f"[Result {idx}]"
            if title:
                part += f"\nTitle: {title}"
            
            # Prefer scraped content over snippet
            if include_content and content:
                # Use summary if available, otherwise truncate content
                if summary:
                    part += f"\nContent: {summary[:1000]}"
                else:
                    part += f"\nContent: {content[:1000]}"
            elif snippet:
                part += f"\nSummary: {snippet}"
            
            if link:
                part += f"\nSource: {link}"
            
            formatted_parts.append(part)
    
    return "\n\n".join(formatted_parts) if formatted_parts else ""


async def build_search_context(user_memory: Optional[str], search_results: List[Dict[str, Any]]) -> str:
    """
    Combine user memory with real-time search results into a unified context.
    Now includes scraped article content for detailed information.
    
    Args:
        user_memory: Formatted user memory/facts (from memory system)
        search_results: List of search result dictionaries (with scraped content)
    
    Returns:
        Combined context string for AI prompts
    """
    parts = []
    
    if user_memory:
        parts.append(f"🔹 Personal Memory:\n{user_memory}")
    
    if search_results:
        # Format with scraped content included
        formatted_results = await format_search_context(search_results, include_content=True)
        if formatted_results:
            parts.append(f"🔹 Real-Time Web Info (with full article content):\n{formatted_results}")
    
    return "\n\n".join(parts) if parts else ""


__all__ = [
    "smart_search",
    "smart_search_with_scraping",
    "scrape_article_content",
    "scrape_multiple_articles",
    "format_search_context",
    "build_search_context",
    "should_use_search",
]

