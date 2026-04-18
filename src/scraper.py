"""
scraper.py

Fetches the most recent Walmart job postings from careers.walmart.com
using their GraphQL API. Returns top 5 most recent jobs per category:
  - Data Scientist (senior / staff / principal)
    - Data Analyst
      - Software Engineer
        - Product Manager

        Each job URL is validated before inclusion — jobs whose listing page
        returns a 404 / job-not-found are automatically filtered out.
        """

import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://careers.walmart.com/api/talent/job"
BASE_JOB_URL = "https://careers.walmart.com/us/en/jobs/"
JOB_NOT_FOUND_PATH = "/job-not-found"

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

JOB_SEARCH_GQL = """
query JobSearch($req: JobSearchRequest!) {
  jobSearch(jobSearchRequest: $req) {
      totalResults
          searchResults {
                jobId
                      jobTitle
                            city
                                  state
                                        country
                                              jobPostingDate
                                                    area
                                                          category
                                                              }
                                                                }
                                                                }
                                                                """

SEARCH_CATEGORIES = [
      {
                "label": "Data Scientist",
                "query": "senior staff principal data scientist",
                "title_keywords": ["data scientist"],
      },
      {
                "label": "Data Analyst",
                "query": "senior data analyst",
                "title_keywords": ["data analyst", "analytics analyst"],
      },
      {
                "label": "Software Engineer",
                "query": "senior staff principal software engineer",
                "title_keywords": ["software engineer", "software developer"],
      },
      {
                "label": "Product Manager",
                "query": "senior staff principal product manager",
                "title_keywords": ["product manager", "product management"],
      },
]

RESULTS_PER_CATEGORY = 5


def validate_url(url):
      """
          Returns True if the job listing URL resolves to a valid, live page.
              Walmart redirects expired/invalid job IDs to /job-not-found, so we
                  follow redirects and check the final URL path.
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
                # 404 status or redirected to the job-not-found page means invalid
                if resp.status_code == 404:
                              return False
                          if JOB_NOT_FOUND_PATH in resp.url:
                                        return False
                                    return True
except requests.exceptions.RequestException as e:
        logger.warning("URL validation request failed for %s: %s", url, e)
        return False


def fetch_jobs(search_query, size=50):
      payload = {
                "query": JOB_SEARCH_GQL,
                "variables": {
                              "req": {
                                                "searchString": search_query,
                                                "from": 0,
                                                "size": size,
                                                "isTitleSearch": False,
                              }
                },
      }
      try:
                resp = requests.post(GRAPHQL_ENDPOINT, json=payload, headers=HEADERS, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                if "errors" in data:
                              logger.warning("GraphQL errors for '%s': %s", search_query, data["errors"])
                              return []
                          search_data = data.get("data", {}).get("jobSearch", {})
                return search_data.get("searchResults", [])
except requests.exceptions.RequestException as e:
        logger.warning("API request failed for '%s': %s", search_query, e)
        return []
except (ValueError, KeyError) as e:
        logger.warning("Failed to parse response for '%s': %s", search_query, e)
        return []


def parse_posting_date(date_str):
      if not date_str:
                return None
            try:
                      return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
except (ValueError, AttributeError):
        return None


def is_title_match(job_title, keywords):
      title_lower = job_title.lower()
    return any(kw in title_lower for kw in keywords)


def is_target_seniority(job_title):
      title_lower = job_title.lower()
    senior_terms = ["senior", "sr.", "sr,", "staff", "principal", "lead", "distinguished"]
    return any(term in title_lower for term in senior_terms)


def normalize_job(raw, category_label):
      job_id = raw.get("jobId") or ""
    title = raw.get("jobTitle") or ""
    city = raw.get("city") or ""
    state = raw.get("state") or ""
    country = raw.get("country") or ""
    posting_date = parse_posting_date(raw.get("jobPostingDate"))

    location_parts = [p for p in [city.title(), state.upper()] if p]
    location = ", ".join(location_parts) if location_parts else (country or "Unknown")

    url = BASE_JOB_URL + job_id if job_id else "https://careers.walmart.com/"

    return {
              "id": job_id,
              "title": title,
              "location": location,
              "country": country,
              "department": category_label,
              "posted_date": posting_date,
              "url": url,
    }


def scrape_top_jobs():
      all_results = []
    seen_ids = set()

    for cat in SEARCH_CATEGORIES:
              label = cat["label"]
              logger.info("Fetching category: %s", label)
              raw_jobs = fetch_jobs(cat["query"], size=50)
              logger.info("  Raw results: %d", len(raw_jobs))

        filtered = []
        for raw in raw_jobs:
                      job_id = raw.get("jobId", "")
                      if not job_id or job_id in seen_ids:
                                        continue
                                    title = raw.get("jobTitle") or ""
            country = raw.get("country") or ""
            if country and country.upper() != "US":
                              continue
                          if not is_title_match(title, cat["title_keywords"]):
                                            continue
                                        if not is_target_seniority(title):
                                                          continue

            job = normalize_job(raw, label)

            # Validate the URL before including this job
            logger.info("  Validating URL for: %s (%s)", title, job["url"])
            if not validate_url(job["url"]):
                              logger.warning("  INVALID (404/not-found) — skipping: %s", job["url"])
                              continue

            filtered.append(job)
            seen_ids.add(job_id)

        filtered.sort(
                      key=lambda j: j["posted_date"] if j["posted_date"] else datetime.min,
                      reverse=True,
        )
        top5 = filtered[:RESULTS_PER_CATEGORY]
        logger.info("  Kept %d valid, taking top %d", len(filtered), len(top5))
        all_results.extend(top5)

    logger.info("Total jobs collected: %d", len(all_results))
    return all_results


if __name__ == "__main__":
      logging.basicConfig(level=logging.INFO)
    jobs = scrape_top_jobs()
    for j in jobs:
              date_str = j["posted_date"].strftime("%Y-%m-%d") if j["posted_date"] else "Unknown"
        print("[%s] [%s] %s - %s | %s" % (
                      date_str, j["department"], j["title"], j["location"], j["url"]
        ))
