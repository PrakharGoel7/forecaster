import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS


def web_search(query: str, max_results: int = 5) -> list[dict]:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in results]
    except Exception as e:
        return [{"error": str(e), "title": "", "url": "", "snippet": ""}]


def web_fetch(url: str, max_chars: int = 6000) -> dict:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ForecastBot/1.0)"}
        response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        lines = [line.strip() for line in soup.get_text(separator="\n").splitlines() if line.strip()]
        text = "\n".join(lines)
        return {
            "url": url,
            "title": soup.title.string.strip() if soup.title and soup.title.string else "",
            "content": text[:max_chars],
            "truncated": len(text) > max_chars,
        }
    except Exception as e:
        return {"url": url, "title": "", "content": "", "error": str(e)}
