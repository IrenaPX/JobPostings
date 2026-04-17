"""
scraper.py
Fetches job postings from Walmart Careers API for target job families
posted in the current week (Monday through Friday).
"""

import requests
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Walmart careers search API endpoint (internal search API used by careers.walmart.com)
WALMART_API_URL = "https://careers.walmart.com/api/jobs"

# Search keywords that capture DS / Analytics / Engineering / Product roles
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

# Departments / categories to filter for (Walmart's internal category names)
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


def fetch_jobs_from_api(keyword: str, start: int = 0, count: int = 100) -> dict:
      """
          Calls Walmart's careers search API for a given keyword.
              Returns the raw JSON response or empty dict on failure.
                  """
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
        logger.warning(f"API request failed for keyword '{keyword}': {e}")
        return {}


def parse_posting_date(date_str: str) -> datetime | None:
      """Parses Walmart's date format. Returns None if unparseable."""
      if not date_str:
                return None
            formats = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"]
    for fmt in formats:
              try:
                            return datetime.strptime(date_str[:19], fmt)
except ValueError:
            continue
    return None


def normalize_job(raw: dict) -> dict | None:
      """Normalizes a raw API job dict into a clean structure. Returns None if missing key fields."""
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
              or f"https://careers.walmart.com/us/jobs/{job_id}"
    )

    return {
              "id": str(job_id),
              "title": title,
              "location": location,
              "department": department,
              "posted_date": posted_date,
              "url": url,
              "raw": raw,
    }


def is_target_role(job: dict) -> bool:
      """Returns True if the job title or department matches our target domains."""
    text = (job["title"] + " " + job["department"]).lower()
    target_terms = [
              "data science", "data scientist", "data analyst", "analytics", "analyst",
              "machine learning", "ml engineer", "software engineer", "software development",
              "product manager", "product management", "data engineer",
              "ai ", "artificial intelligence",
    ]
    return any(term in text for term in target_terms)


def scrape_this_week() -> list[dict]:
      """
          Main entry point. Returns deduplicated list of target jobs posted this week.
              """
      monday, friday = get_week_date_range()
      logger.info(f"Scraping jobs posted between {monday.date()} and {friday.date()}")

    seen_ids = set()
    results = []

    for keyword in TARGET_KEYWORDS:
              logger.info(f"Fetching keyword: '{keyword}'")
              raw_response = fetch_jobs_from_api(keyword)

        # Walmart API may return jobs under different keys
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

            # Date filter: posted this week
            if job["posted_date"]:
                              if not (monday <= job["posted_date"] <= friday):
                                                    continue
                                            # If no date available, include anyway (better to over-include)

                          seen_ids.add(job["id"])
            results.append(job)

    logger.info(f"Found {len(results)} qualifying jobs this week.")
    return results


if __name__ == "__main__":
      logging.basicConfig(level=logging.INFO)
    jobs = scrape_this_week()
    for j in jobs:
              print(f"[{j['posted_date']}] {j['title']} — {j['location']} | {j['url']}")
