import asyncio
import time

from backend.services.search import SearchService
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from backend.models.search import SearchResult

class ResearchWorker:
    def __init__(self):
        self.search_service = SearchService(engines=["google", "bing", "brave", "duckduckgo"])
        self.num_results = 5
        
        self.crawler_config = CrawlerRunConfig(
            word_count_threshold=10,
            excluded_tags=["nav", "footer", "header"],
            exclude_external_links=True,
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(threshold=0.5, threshold_type="dynamic", min_word_threshold=5),
                options={
                    "ignore_links": True,
                    "ignore_images": True,
                    "escape_html": True,
                    "body_width": None
                }
            ),
            scan_full_page = False,
            scroll_delay=0.4,
            wait_until="domcontentloaded",
            page_timeout=10000,
            delay_before_return_html=0.1,
            stream = False,
            exclude_all_images = True,
            remove_overlay_elements = True,
            remove_consent_popups = True,
            simulate_user = True,
            override_navigator = True,
            magic = True
        )
        
        self.browser_config = BrowserConfig(
            browser_type="chromium",
            headless=True,
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/116.0.0.0 Safari/537.36",
            user_agent_mode = "random",
            text_mode = True,
            light_mode = True,
            enable_stealth = True,
            avoid_ads = True,
            
        )
    
    async def search(self, query: str):
        results = await self.search_service.search(query, num_results=self.num_results)
        return results
    
    async def crawl(self, entities: list[SearchResult]) -> list[dict]:
        result = []
        
        urls = [str(entity.url) for entity in entities]
        
        async with AsyncWebCrawler(config = self.browser_config) as crawler:
            # for entity in entities:
            #     try:
            #         crawl_result = await crawler.arun(url=str(entity.url), config=self.crawler_config)
            #         if crawl_result.success:
            #             result.append(crawl_result.markdown.fit_markdown)
            #             print(f"Length of markdown for {entity.url}: {len(crawl_result.markdown.fit_markdown.strip())} words")
            #     except Exception as e:
            #         print(f"Error crawling {entity.url}: {e}")
            #         print(f"Skipping {entity.url} due to error {crawl_result.error_message}.")
            
            try:
                t0 = time.time()
                crawl_results = await crawler.arun_many(urls=urls, config=self.crawler_config)
                print(f"Crawled {len(urls)} URLs in {time.time() - t0:.2f} seconds.")
                for i, crawl_result in enumerate(crawl_results): # type: ignore
                    if crawl_result.success:
                        result.append({"url": crawl_result.url, "markdown": crawl_result.markdown.fit_markdown})
                        print(f"Length of markdown for {crawl_result.url}: {len(crawl_result.markdown.fit_markdown.split())} words")
            except Exception as e:
                print(f"Error occurred while crawling: {e}")

        
        return result
    
    async def research(self, query: str) -> list[dict]:
        search_results = await self.search(query)
        print(f"Found {len(search_results)} search results for query: '{query}'")
        
        if not search_results:
            print("No search results found.")
            return []
        
        crawl_results = await self.crawl(search_results)
        print(f"Crawled {len(crawl_results)} pages for query: '{query}'")
        
        for result in crawl_results:
            result["query"] = query

        return crawl_results
    
if __name__ == "__main__":
    async def main():
        worker = ResearchWorker()
        query = "Advances in Ai"
        results = await worker.research(query)
        
        for i, result in enumerate(results):
            print(f"\nResult {i + 1}:\nURL: {result['url']}\nMarkdown: {result['markdown'][:100]}\nQuery: {result['query']}\n{'-' * 80}")

    asyncio.run(main())