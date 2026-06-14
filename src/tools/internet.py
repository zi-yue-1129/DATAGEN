from langchain_core.tools import tool
from langchain_community.document_loaders import WebBaseLoader, FireCrawlLoader
# fastCRW (Firecrawl-compatible web scraper; single binary, self-host or cloud)
from langchain_crw import CrwLoader
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from typing import Annotated, List
from bs4 import BeautifulSoup

from ..logger import setup_logger
from ..config import FIRECRAWL_API_KEY,CRW_API_KEY,CRW_API_URL,CHROMEDRIVER_PATH
# Set up logger
logger = setup_logger()

@tool
def google_search(query: Annotated[str, "The search query to use"]) -> Annotated[str, "The top 5 Google search results."]:
    """
    Perform a Google search based on the given query and return the top 5 results.

    This function uses Selenium to perform a headless Google search and BeautifulSoup to parse the results.

    """
    try:
        logger.info(f"Performing Google search for query: {query}")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        service = Service(CHROMEDRIVER_PATH)

        with webdriver.Chrome(options=chrome_options, service=service) as driver:
            # Set a timeout to prevent hanging on slow network
            driver.set_page_load_timeout(30)
            url = f"https://www.google.com/search?q={query}"
            logger.debug(f"Accessing URL: {url}")
            driver.get(url)
            html = driver.page_source

        soup = BeautifulSoup(html, 'html.parser')
        search_results = soup.select('.g') 
        search = ""
        for result in search_results[:5]:
            title_element = result.select_one('h3')
            title = title_element.text if title_element else 'No Title'
            snippet_element = result.select_one('.VwiC3b')
            snippet = snippet_element.text if snippet_element else 'No Snippet'
            link_element = result.select_one('a')
            link = link_element['href'] if link_element else 'No Link'
            search += f"{title}\n{snippet}\n{link}\n\n"

        logger.info("Google search completed successfully")
        return search
    except Exception as e:
        logger.error(f"Error during Google search: {str(e)}")
        return f'Error: {e}'
\
def _scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from WebBaseLoader."]:
    """
    Scrape the provided web pages for detailed information using WebBaseLoader.

    This function uses the WebBaseLoader to load and scrape the content of the provided URLs.
    """
    try:
        logger.info(f"Scraping webpages: {urls}")
        loader = WebBaseLoader(urls)
        docs = loader.load()
        content = "\n\n".join([f'\n{doc.page_content}\n' for doc in docs])
        logger.info("Webpage scraping completed successfully")
        return content
    except Exception as e:
        logger.error(f"Error during webpage scraping: {str(e)}")
        raise  # Re-raise the exception to be caught by the calling function

def _firecrawl_scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from FireCrawl."]:
    """
    Scrape the provided web pages for detailed information using FireCrawlLoader.

    This function uses the FireCrawlLoader to load and scrape the content of the provided URLs.

    """
    if not FIRECRAWL_API_KEY:
        raise ValueError("FireCrawl API key is not set")

    try:
        logger.info(f"Scraping webpages using FireCrawl: {urls}")
        results = []
        for url in urls:
            loader = FireCrawlLoader(
                api_key=FIRECRAWL_API_KEY,
                url=url,
                mode="scrape"
            )
            res = loader.load()
            # Normalize different possible return types from the loader
            if isinstance(res, list):
                for doc in res:
                    if hasattr(doc, "page_content"):
                        results.append(str(doc.page_content))
                    else:
                        results.append(str(doc))
            else:
                results.append(str(res))
        aggregated = "\n\n".join(results)
        logger.info("FireCrawl scraping completed successfully")
        return aggregated
    except Exception as e:
        logger.error(f"Error during FireCrawl scraping: {str(e)}")
        raise  # Re-raise the exception to be caught by the calling function
def _crw_scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from fastCRW."]:
    """
    Scrape the provided web pages for detailed information using fastCRW.

    fastCRW is a Firecrawl-compatible web scraper (single binary; self-host or cloud).
    This function uses the CrwLoader to load and scrape the content of the provided URLs.

    """
    try:
        logger.info(f"Scraping webpages using fastCRW: {urls}")
        results = []
        for url in urls:
            loader = CrwLoader(
                api_key=CRW_API_KEY,
                api_url=CRW_API_URL,
                url=url,
                mode="scrape"
            )
            res = loader.load()
            # Normalize different possible return types from the loader
            if isinstance(res, list):
                for doc in res:
                    if hasattr(doc, "page_content"):
                        results.append(str(doc.page_content))
                    else:
                        results.append(str(doc))
            else:
                results.append(str(res))
        aggregated = "\n\n".join(results)
        logger.info("fastCRW scraping completed successfully")
        return aggregated
    except Exception as e:
        logger.error(f"Error during fastCRW scraping: {str(e)}")
        raise  # Re-raise the exception to be caught by the calling function
@tool
def scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from fastCRW, FireCrawl or WebBaseLoader."]:
    """
    Attempt to scrape webpages using fastCRW, falling back to FireCrawl then WebBaseLoader if unsuccessful.
    """
    try:
        return _crw_scrape_webpages(urls)
    except Exception as e:
        logger.warning(f"fastCRW scraping failed: {str(e)}. Falling back to FireCrawl.")
    try:
        return _firecrawl_scrape_webpages(urls)
    except Exception as e:
        logger.warning(f"FireCrawl scraping failed: {str(e)}. Falling back to WebBaseLoader.")
        try:
            return _scrape_webpages(urls)
        except Exception as e:
            logger.error(f"Both scraping methods failed. Error: {str(e)}")
            return f"Error: Unable to scrape webpages using both methods. {str(e)}"

logger.info("Web scraping tools initialized")