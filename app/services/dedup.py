"""
Deduplication logic for the LLM Scraper API.
Handles Level 1 (URL-only) and Level 2 (Content Hash) deduplication.
"""

def filter_urls(urls: list[str], already_scraped: list[dict]) -> dict:
    """
    Separates URLs into two groups: those that need processing and those to skip immediately.
    
    Level 1 Deduplication:
    - If URL is in already_scraped AND has NO content_hash -> skip_no_hash (cost $0).
    - Otherwise -> to_process.
    
    Returns:
        dict: {
            "to_process": list[str],
            "skipped_level1": list[str],
            "hash_map": dict[str, str]
        }
    """
    to_process = []
    skipped_level1 = []
    hash_map = {}

    # Create a mapping for quick lookup: url -> content_hash (if exists)
    scraped_data = {item["url"]: item.get("content_hash") for item in already_scraped}

    for url in urls:
        if url in scraped_data:
            content_hash = scraped_data[url]
            if content_hash:
                # Level 2 candidate: we have a hash, need to fetch and compare
                hash_map[url] = content_hash
                to_process.append(url)
            else:
                # Level 1 skip: URL exists but no hash provided
                skipped_level1.append(url)
        else:
            # New URL
            to_process.append(url)

    return {
        "to_process": to_process,
        "skipped_level1": skipped_level1,
        "hash_map": hash_map
    }

def check_hash_changed(url: str, new_hash: str, hash_map: dict[str, str]) -> bool:
    """
    Decides if the content of a URL changed after preprocessing.
    
    Level 2 Deduplication:
    - If URL not in hash_map -> True (no previous hash to compare).
    - If new_hash != old_hash -> True (content changed).
    - If new_hash == old_hash -> False (content identical).
    """
    if url not in hash_map:
        return True
    
    old_hash = hash_map[url]
    return new_hash != old_hash
