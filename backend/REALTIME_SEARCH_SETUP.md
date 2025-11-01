# 🔍 Real-Time Web Search Setup Guide

## Overview

Project Maya now includes real-time web search functionality that combines:
- **Personal Memory** (Redis, Neo4j, MongoDB, Pinecone)
- **Real-Time Web Information** (SerpAPI or Google Custom Search API)

## 🚀 Quick Setup

### 1. Add API Keys to `.env`

Add these to your `backend/.env` file:

```bash
# Option 1: SerpAPI (Primary - Recommended)
SERPAPI_KEY="f779c65c8080fab7fe6004ae483533cd25571b61b56774097fb11092bde51269"

# Option 2: Google Custom Search API (Fallback)
GOOGLE_API_KEY="AIzaSyCrxzJryS50Rtluqoeq475jbace9QlR2kw"
GOOGLE_SEARCH_CX_ID="d0cffd3ed90854b08"

# Note: The same GOOGLE_API_KEY can be used for multiple Google services
# (YouTube API, Custom Search API, etc.) - just enable the APIs in Google Cloud Console
```

### 2. How It Works

The system automatically:
- ✅ Detects when a query needs real-time info (keywords like "latest", "news", "recent", "tech updates")
- ✅ Searches using SerpAPI first, falls back to Google Custom Search if needed
- ✅ **Scrapes full article content** from top URLs using BeautifulSoup and newspaper3k
- ✅ Extracts detailed information, summaries, and key facts from articles
- ✅ Caches results in Redis for 1 hour (saves bandwidth)
- ✅ Combines search results with user memory
- ✅ Provides formatted context with **full article content** to the AI

### 3. Usage Example

The search is **automatically integrated** into the AI response flow. When a user asks:

> "What's new in AI since last week?"

The system will:
1. Detect the query needs real-time info (`should_use_search()` returns `True`)
2. Execute web search (`smart_search()`)
3. Combine with user memory
4. Generate a smart response using both

### 4. Manual Usage (For Testing)

You can also use the search service directly:

```python
from app.services.realtime_search import smart_search, format_search_context

# Perform a search
results = await smart_search("latest AI news 2025")

# Format for display
context = await format_search_context(results, max_results=5)
print(context)
```

### 5. Cache Management

Results are cached in Redis with a 1-hour TTL. To clear cache for a query:

```python
from app.services.redis_service import get_client

client = get_client()
cache_key = f"search:query:{hashlib.sha256(query.lower().encode()).hexdigest()[:16]}"
await client.delete(cache_key)
```

## 🔐 Security Reminders

- ✅ Never commit `.env` file to Git
- ✅ Add `.env` to `.gitignore`
- ✅ Use separate keys for dev/prod environments
- ✅ Never log API keys in console or logs

## 📊 Search Triggers

The system automatically uses search when queries contain:

- **Temporal keywords**: "latest", "recent", "current", "today", "now", "this week"
- **News/Updates**: "news", "update", "updates", "what's happening", "trending"
- **Tech keywords**: "tech", "technology", "gadget", "gadgets", "innovation"
- **News sources**: "reuters", "cnn", "wired", "techcrunch"
- **Search requests**: "search", "find", "look up", "web", "online"
- **Recent years**: "2024", "2025"
- **Questions**: "what's new", "what happened", "tell me about", "tech updates"

## 🛠️ Troubleshooting

### Search Not Working?

1. **Check API keys are set**:
   ```python
   from app.config import settings
   print(f"SerpAPI: {bool(settings.SERPAPI_KEY)}")
   print(f"Google: {bool(settings.GOOGLE_API_KEY)}")
   ```

2. **Test search directly**:
   ```python
   from app.services.realtime_search import smart_search
   results = await smart_search("test query")
   print(results)
   ```

3. **Check Redis connection** (for caching):
   ```python
   from app.services.redis_service import ping
   is_connected = await ping()
   print(f"Redis: {is_connected}")
   ```

## 🎯 Features

- ✅ Dual provider support (SerpAPI + Google Custom Search)
- ✅ **Web scraping** - Extracts full article content from URLs
- ✅ **Content extraction** - Uses BeautifulSoup + newspaper3k for robust scraping
- ✅ **Concurrent scraping** - Scrapes multiple articles in parallel (max 3 at once)
- ✅ Automatic failover between providers
- ✅ Redis caching (1-hour TTL)
- ✅ Async/await support
- ✅ Memory + Search integration
- ✅ Smart trigger detection
- ✅ **Detailed responses** - AI uses scraped content to provide comprehensive answers

## 📝 Notes

- Cache TTL: 1 hour (3600 seconds)
- Max results: 10 per search
- Max scraped articles: 5 (top results)
- Scraping timeout: 8 seconds per article
- Max article length: 3000 characters
- Concurrent scraping: 3 articles at once
- Timeout: 10 seconds per search provider
- Results formatted for AI prompts automatically with **full article content**

## 🔄 What Gets Scraped?

When a search is triggered, the system:
1. Gets top 10 search results
2. Selects top 5 URLs for scraping
3. Scrapes article content using BeautifulSoup (primary) or newspaper3k (fallback)
4. Extracts: title, full text, summary, authors, publish date
5. Provides this detailed content to the AI for comprehensive answers

The AI now receives **actual article content** instead of just snippets, enabling detailed, accurate responses!

