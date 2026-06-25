import asyncio
import time

from backend.services.search import SearchService
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from backend.models.search import SearchResult
from sentence_transformers import SentenceTransformer
import numpy as np



class ResearchWorker:
    def __init__(self):
        self.search_service = SearchService(engines=["google", "bing", "brave", "duckduckgo"])
        self.num_results = 20
        
        self.embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
        
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
    
    async def search(self, query: str) -> list[SearchResult]:
        results = await self.search_service.search(query, num_results=self.num_results)
        filtered_results = self._mmr_selection(query, results, lambda_param=0.7, top_k=5)
        return filtered_results

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
    
    def _mmr_selection(
        self,
        query: str,
        candidates: list[SearchResult],
        lambda_param: float = 0.7,
        top_k: int = 5
    ) -> list[SearchResult]:
        """
        Select top_k URLs using Maximal Marginal Relevance, powered by SentenceTransformer similarity.
        """
        if len(candidates) <= top_k:
            return candidates

        # Prepare texts
        texts = [f"{r.title} {r.content}" for r in candidates]

        # Encode query and documents
        query_embed = self.embedder.encode(query, convert_to_tensor=True, normalize_embeddings=True)
        doc_embeds = self.embedder.encode(texts, convert_to_tensor=True, normalize_embeddings=True)  # shape (n_docs, embed_dim)

        # Relevance: cosine similarity of each doc to query
        relevance = self.embedder.similarity(doc_embeds, query_embed).flatten()  # type: ignore # tensor of shape (n_docs,)

        # All-pair similarities between documents
        doc_sim_matrix = self.embedder.similarity(doc_embeds, doc_embeds)  # type: ignore # (n_docs, n_docs)

        selected_indices = []
        unselected = list(range(len(candidates)))

        for _ in range(min(top_k, len(candidates))):
            if not selected_indices:
                best_idx = int(relevance.argmax().item())
                best_unselected_idx = best_idx
            else:
                selected_embeds = doc_embeds[selected_indices]  # type: ignore # already a subset
                # Max similarity of each candidate to any already-selected
                max_sim_to_selected = doc_sim_matrix[unselected][:, selected_indices].max(dim=1).values
                mmr = lambda_param * relevance[unselected] - (1 - lambda_param) * max_sim_to_selected
                best_idx = int(mmr.argmax().item())
                best_unselected_idx = unselected[best_idx]

            selected_indices.append(best_unselected_idx)
            unselected.remove(best_unselected_idx)

        return [candidates[i] for i in selected_indices]

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
        query = "Best Movies of 2026"
        results = await worker.research(query)
        
        for i, result in enumerate(results):
            print(f"\nResult {i + 1}:\nURL: {result['url']}\nMarkdown: {result['markdown'][:100]}\nQuery: {result['query']}\n{'-' * 80}")

    asyncio.run(main())