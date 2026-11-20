"""
scraper.py
Fetches the most recent Walmart job postings from careers.walmart.com
using their GraphQL API. Returns 2-3 most recent validated jobs per category:
- Data Science (senior / staff / principal data scientist)
- Data Analytics (senior / staff / principal data analyst)
- Software Engineering (senior / staff / principal software engineer)
- Product Management (senior / staff / principal product manager)
Each job URL is validated before inclusion -- jobs whose listing page
returns a 404 / job-not-found are automatically filtered out.
"""

import os
import time
import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://careers.walmart.com/api/graphql"
QUERY_ID = "b0467c1f-f578-4261-9280-0ea4614f251c"

BASE_JOB_URL = "https://careers.walmart.com/us/en/jobs/"
JOB_NOT_FOUND_PATH = "/job-not-found"

# Number of result pages to pull per search query (each page ~10 jobs).
# Pulling more pages gives the filters a larger candidate pool so that
# categories like Data Science are not starved by the top-10 results.
PAGES_PER_QUERY = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://careers.walmart.com/",
    "Origin": "https://careers.walmart.com",
}

SEARCH_CATEGORIES = [
    {
        "label": "Data Science",
        "queries": [
            "principal data scientist",
            "staff data scientist",
            "senior data scientist",
            "data scientist",
        ],
        "title_keywords": ["data scientist"],
    },
    {
        "label": "Data Analytics",
        "queries": [
            "principal data analyst",
            "staff data analyst",
            "senior data analyst",
            "data analyst",
            "analytics analyst",
            "data analytics",
        ],
        "title_keywords": ["data analyst", "analytics analyst", "data analytics", "analyst, data", "analytics"],
    },
    {
        "label": "Software Engineering",
        "queries": [
            "principal software engineer",
            "staff software engineer",
            "senior software engineer",
            "software engineer",
        ],
        "title_keywords": ["software engineer", "software developer"],
    },
    {
        "label": "Product Management",
        "queries": [
            "principal product manager",
            "staff product manager",
            "senior product manager",
            "product manager",
            "product management",
        ],
        "title_keywords": ["product manager", "product management"],
    },
]

RESULTS_PER_CATEGORY = 3
MIN_RESULTS_PER_CATEGORY = 2

# Region is set per workflow: "US" (default) or "IN" (India / IDC).
REGION = os.environ.get("REGION", "US").upper()
REGIONS = {
    "US": {"countries": {"US", "USA", "UNITED STATES"}, "query_suffix": ""},
    "IN": {"countries": {"IN", "IND", "INDIA"}, "query_suffix": ""},
}
# Workday rate-limits heavily, so India uses one broad search per category
# (about 12 requests total) instead of the US multi-query approach.
IN_QUERIES = {
    "Data Science": ["(IND) data scientist"],
    "Data Analytics": ["(IND) data analyst"],
    "Software Engineering": ["(IND) software engineer"],
    "Product Management": ["(IND) product manager"],
}
INDIA_CITIES = {"bengaluru", "bangalore", "chennai", "gurugram", "gurgaon", "hyderabad", "pune"}

# Countries seen during a run, logged when a region comes back empty.
SEEN_COUNTRIES = {}
WORKDAY_FAILURES = []


def in_region(raw):
    country = (raw.get("country") or "").strip().upper()
    SEEN_COUNTRIES[country] = SEEN_COUNTRIES.get(country, 0) + 1
    if country:
        return country in REGIONS[REGION]["countries"]
    # No country on the record: fall back to the city for India.
    city = (raw.get("city") or "").strip().lower()
    if REGION == "IN":
        return city in INDIA_CITIES
    return True


def validate_url(url):
    """
    Returns True if the job listing URL resolves to a valid, live page.
    Walmart redirects expired/invalid job IDs to /job-not-found,
    so we follow redirects and check the final URL path.
    """
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
            timeout=10,
            allow_redirects=True,
        )
        if resp.status_code == 404:
            return False
        if JOB_NOT_FOUND_PATH in resp.url:
            return False
        return True
    except requests.exceptions.RequestException as e:
        logger.warning("URL validation request failed for %s: %s", url, e)
        return False


def fetch_jobs(search_query, page=0):
    """
    Calls the /api/graphql persisted-query endpoint and returns a flat list
    of raw job dicts from the artifact payload for a single result page.

    The site uses a chat/AI wrapper (jobSearchAssistant). We send a
    single-turn message and read back the first tool_message artifact.
    Response path: data.jobSearchAssistant.tool_messages[0].artifact.jobs[]

    Each job dict contains:
    job_id, city, title, jobPostingTitle, state, country,
    jobPostingStartDate, minPay, maxPay, areas, categories, brand, ...
    """
    payload = {
        "queryId": QUERY_ID,
        "variables": {
            "chatRequest": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": search_query}],
                    }
                ],
                "thread_id": f"bot-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "channel": "job_search",
                "context": {
                    "job_search_context": {
                        "locale": "en_US",
                        "sort": "relevance",
                        "active_tab": "jobs",
                        "management_levels": [],
                        "content_page": 0,
                        "future_roles_page": 0,
                        "job_page": page,
                    }
                },
            }
        },
        "headers": {},
    }

    try:
        resp = requests.post(GRAPHQL_ENDPOINT, json=payload, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        if "errors" in data:
            logger.warning("GraphQL errors for '%s': %s", search_query, data["errors"])
            return []

        tool_messages = (
            data.get("data", {})
            .get("jobSearchAssistant", {})
            .get("tool_messages", [])
        )
        if not tool_messages:
            logger.warning("No tool_messages in response for '%s'", search_query)
            return []

        artifact = tool_messages[0].get("artifact", {})
        jobs = artifact.get("jobs", [])
        logger.info(
            " '%s' (page %d) -> %d total, %d returned",
            search_query,
            page,
            artifact.get("total_jobs", 0),
            len(jobs),
        )
        return jobs

    except requests.exceptions.RequestException as e:
        logger.warning("API request failed for '%s': %s", search_query, e)
        return []
    except (ValueError, KeyError) as e:
        logger.warning("Failed to parse response for '%s': %s", search_query, e)
        return []


WORKDAY_BASE = "https://walmart.wd504.myworkdayjobs.com"
WORKDAY_API = WORKDAY_BASE + "/wday/cxs/walmart/WalmartExternal/jobs"
WORKDAY_PAGE_SIZE = 20


def days_ago(posted_on):
    """'Posted Today' -> 0, 'Posted Yesterday' -> 1, 'Posted 8 Days Ago' -> 8, '30+' -> 30."""
    text = (posted_on or "").lower()
    if "today" in text:
        return 0
    if "yesterday" in text:
        return 1
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else 99


def fetch_workday_jobs(search_query, page=0):
    """
    India (IDC) roles are not on careers.walmart.com; they are listed on
    Walmart's Workday site. Returns raw dicts shaped like the GraphQL ones.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": "en-US",
        "User-Agent": HEADERS["User-Agent"],
    }
    body = {
        "appliedFacets": {},
        "limit": WORKDAY_PAGE_SIZE,
        "offset": page * WORKDAY_PAGE_SIZE,
        "searchText": search_query,
    }
    postings = None
    for attempt in range(4):
        time.sleep(1 + attempt * 4)  # be polite; back off on retries
        try:
            resp = requests.post(WORKDAY_API, json=body, headers=headers, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.exceptions.HTTPError("HTTP " + str(resp.status_code))
            resp.raise_for_status()
            postings = resp.json().get("jobPostings", [])
            break
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning("Workday attempt %d failed for '%s': %s", attempt + 1, search_query, e)
            last_error = str(e)
    if postings is None:
        WORKDAY_FAILURES.append(search_query + ": " + last_error)
        return []

    jobs = []
    now_ms = datetime.utcnow().timestamp() * 1000
    for p in postings:
        path = p.get("externalPath") or ""
        loc = p.get("locationsText") or ""
        parts = loc.split()
        is_india = loc.startswith("IN ") or "(IND)" in (p.get("title") or "")
        title = (p.get("title") or "").replace("(IND)", "").strip()
        if title.isupper():
            title = title.title()
        job_id = path.rsplit("_", 1)[-1] if "_" in path else path
        jobs.append({
            "job_id": job_id,
            "jobPostingTitle": title,
            "city": parts[2] if loc.startswith("IN ") and len(parts) > 2 else "",
            "state": "",
            "country": "IN" if is_india else (parts[0] if parts else ""),
            "jobPostingStartDate": now_ms - days_ago(p.get("postedOn")) * 86400000,
            "url": WORKDAY_BASE + "/WalmartExternal" + path,
        })
    logger.info(" Workday '%s' (page %d) -> %d returned", search_query, page, len(jobs))
    return jobs


def fetch_jobs_pages(search_query, pages=PAGES_PER_QUERY):
    """
    Pulls multiple result pages for a query and returns a combined,
    de-duplicated list of raw job dicts. Stops early if a page is empty.
    """
    combined = []
    seen = set()
    for page in range(pages):
        if REGION == "IN":
            page_jobs = fetch_workday_jobs(search_query, page=page)
        else:
            page_jobs = fetch_jobs(search_query, page=page)
        if not page_jobs:
            break
        for raw in page_jobs:
            jid = raw.get("job_id", "")
            if jid and jid in seen:
                continue
            if jid:
                seen.add(jid)
            combined.append(raw)
    return combined


def parse_posting_date(date_str):
    if not date_str:
        return None
    # Handle Unix timestamp in milliseconds (new API returns int)
    if isinstance(date_str, (int, float)):
        try:
            return datetime.utcfromtimestamp(date_str / 1000)
        except (ValueError, OSError):
            return None
    try:
        return datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def is_title_match(job_title, keywords):
    title_lower = job_title.lower()
    return any(kw in title_lower for kw in keywords)


def is_target_seniority(job_title):
    title_lower = job_title.lower()
    senior_terms = [
        "senior",
        "sr.",
        "sr,",
        "sr ",
        "staff",
        "principal",
        "lead",
        "distinguished",
        "manager",
        "director",
        " iii",
        " iv",
        " v",
        " ii",
    ]
    return any(term in title_lower for term in senior_terms)


def normalize_job(raw, category_label):
    """
    Converts a raw job dict from the new API into the same shape the rest
    of the pipeline expects.

    New API field mapping (old -> new):
    jobId -> job_id
    jobTitle -> jobPostingTitle (title field is internal name)
    jobPostingDate -> jobPostingStartDate (int ms timestamp)
    area/category -> areas / categories (now lists)
    """
    job_id = raw.get("job_id", "")
    # Prefer jobPostingTitle (human-readable); fall back to title
    title = raw.get("jobPostingTitle") or raw.get("title") or ""
    city = raw.get("city") or ""
    state = raw.get("state") or ""
    country = raw.get("country") or ""
    posting_date = parse_posting_date(raw.get("jobPostingStartDate"))

    if REGION == "IN":
        location_parts = [p for p in [city.title(), "India"] if p]
    else:
        location_parts = [p for p in [city.title(), state.upper()] if p]
    location = ", ".join(location_parts) if location_parts else (country or "Unknown")
    url = raw.get("url") or (BASE_JOB_URL + job_id if job_id else "https://careers.walmart.com/")

    return {
        "id": job_id,
        "title": title,
        "location": location,
        "country": country,
        "department": category_label,
        "posted_date": posting_date,
        "url": url,
    }


def scrape_category(cat, seen_ids):
    """
    Tries multiple search queries for a category until we have enough
    validated, unique results. Returns up to RESULTS_PER_CATEGORY jobs.
    """
    label = cat["label"]
    collected = []
    collected_ids = set()

    # US keeps the first valid hits (each needs a slow link check).
    # India gathers every match, then keeps the most recently posted.
    take_all = REGION == "IN"

    queries = IN_QUERIES.get(label, cat["queries"]) if REGION == "IN" else cat["queries"]
    for query in queries:
        if len(collected) >= RESULTS_PER_CATEGORY and not take_all:
            break

        query = query + REGIONS[REGION]["query_suffix"]
        logger.info(" [%s] Trying query: '%s'", label, query)
        raw_jobs = fetch_jobs_pages(query)

        if not raw_jobs:
            logger.info(" [%s] No results for '%s'", label, query)
            continue

        for raw in raw_jobs:
            if len(collected) >= RESULTS_PER_CATEGORY and not take_all:
                break

            job_id = raw.get("job_id", "")
            if not job_id or job_id in seen_ids or job_id in collected_ids:
                continue

            title = raw.get("jobPostingTitle") or raw.get("title") or ""
            if not in_region(raw):
                continue
            if not is_title_match(title, cat["title_keywords"]):
                continue
            if not is_target_seniority(title):
                continue

            job = normalize_job(raw, label)

            logger.info(" Validating: %s (%s)", title, job["url"])
            # Workday listings come straight from the live search, so only
            # careers.walmart.com links need the 404 check.
            if REGION != "IN" and not validate_url(job["url"]):
                logger.warning(" INVALID (404/not-found) -- skipping: %s", job["url"])
                continue

            collected.append(job)
            collected_ids.add(job_id)
            logger.info(" VALID -- added (%d/%d)", len(collected), RESULTS_PER_CATEGORY)

    collected.sort(
        key=lambda j: j["posted_date"] if j["posted_date"] else datetime.min,
        reverse=True,
    )
    collected = collected[:RESULTS_PER_CATEGORY]

    logger.info(" [%s] Final count: %d", label, len(collected))
    return collected


def scrape_top_jobs():
    all_results = []
    seen_ids = set()

    for cat in SEARCH_CATEGORIES:
        label = cat["label"]
        logger.info("Fetching category: %s", label)
        jobs = scrape_category(cat, seen_ids)

        if len(jobs) < MIN_RESULTS_PER_CATEGORY:
            logger.warning(
                "Category '%s' only yielded %d jobs (minimum is %d) -- skipping.",
                label, len(jobs), MIN_RESULTS_PER_CATEGORY
            )
            continue

        for j in jobs:
            seen_ids.add(j["id"])

        all_results.extend(jobs)

    logger.info("Region %s: %d jobs. Countries seen: %s", REGION, len(all_results), SEEN_COUNTRIES)
    return all_results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    jobs = scrape_top_jobs()
    for j in jobs:
        date_str = j["posted_date"].strftime("%Y-%m-%d") if j["posted_date"] else "Unknown"
        print("[%s] [%s] %s - %s | %s" % (
            date_str, j["department"], j["title"], j["location"], j["url"]
        ))
