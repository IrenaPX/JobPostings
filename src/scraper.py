"""
scraper.py
Fetches job postings from Walmart Careers API for target job families
posted in the current week (Monday through Friday).
"""
import requests
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

WALMART_API_URL = "https://careers.walmart.com/api/jobs"

TARGET_KEYWORDS = [
    "data science",
    "data scientist",
    "data analytics",
    "data analyst",
    "analytics",
    "machine learning",
    "software engineer",
    "software engineering",
    "product manager",
    "product management",
]

TARGET_CATEGORIES = [
    "Data Science & Analytics",
    "Software Engineering & Technology",
    "Product Management",
    "Information Technology",
    "Business Analytics",
]


def get_week_date_range():
    """Returns Monday and Friday of the current week as datetime objects."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    return monday.replace(hour=0, minute=0, second=0), friday.replace(hour=23, minute=59, second=59)


def fetch_jobs_from_api(keyword, start=0, count=100):
    """Calls Walmart careers search API. Returns raw JSON or empty dict on failure."""
    params = {
        "q": keyword,
        "start": start,
        "count": count,
        "sort": "date",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://careers.walmart.com/",
    }
    try:
        response = requests.get(WALMART_API_URL, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.warning("API request failed for keyword '%s': %s" % (keyword, e))
        return {}


def parse_posting_date(date_str):
    """Parses Walmart date format. Returns None if unparseable."""
    if not date_str:
        return None
    formats = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str[:19], fmt)
        except ValueError:
            continue
    return None


def normalize_job(raw):
    """Normalizes a raw API job dict. Returns None if missing key fields."""
    job_id = raw.get("jobId") or raw.get("id") or raw.get("requisitionId")
    title = raw.get("title") or raw.get("jobTitle") or raw.get("positionTitle")
    if not job_id or not title:
        return None
    posted_str = (
        raw.get("postedDate")
        or raw.get("postingDate")
        or raw.get("datePosted")
        or raw.get("createdDate")
    )
    posted_date = parse_posting_date(posted_str)
    location = raw.get("locationName") or raw.get("location") or raw.get("primaryLocation") or "Unknown"
    department = raw.get("department") or raw.get("jobFamily") or raw.get("category") or ""
    url = (
        raw.get("url")
        or raw.get("jobUrl")
        or "https://careers.walmart.com/us/jobs/" + str(job_id)
    )
    return {
        "id": str(job_id),
        "title": title,
        "location": location,
        "department": department,
        "posted_date": posted_date,
        "url": url,
    }


def is_target_role(job):
    """Returns True if title or department matches target domains."""
    text = (job["title"] + " " + job["department"]).lower()
    target_terms = [
        "data science", "data scientist", "data analyst", "analytics", "analyst",
        "machine learning", "ml engineer", "software engineer", "software development",
        "product manager", "product management", "data engineer", "ai ", "artificial intelligence",
    ]
    return any(term in text for term in target_terms)


def scrape_this_week():
    """Main entry point. Returns deduplicated list of target jobs posted this week."""
    monday, friday = get_week_date_range()
    logger.info("Scraping jobs posted between %s and %s" % (monday.date(), friday.date()))
    seen_ids = set()
    results = []
    for keyword in TARGET_KEYWORDS:
        logger.info("Fetching keyword: '%s'" % keyword)
        raw_response = fetch_jobs_from_api(keyword)
        jobs_raw = (
            raw_response.get("jobs")
            or raw_response.get("results")
            or raw_response.get("jobPostings")
            or []
        )
        for raw_job in jobs_raw:
            job = normalize_job(raw_job)
            if not job:
                continue
            if job["id"] in seen_ids:
                continue
            if not is_target_role(job):
                continue
            if job["posted_date"]:
                if not (monday <= job["posted_date"] <= friday):
                    continue
            seen_ids.add(job["id"])
            results.append(job)
    logger.info("Found %d qualifying jobs this week." % len(results))
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    jobs = scrape_this_week()
    for j in jobs:
        print("[%s] %s - %s | %s" % (j["posted_date"], j["title"], j["location"], j["url"]))
