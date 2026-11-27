"""
tech_jobs.py
Collects recent job postings from several tech companies, for the CareerMirror
page. This is separate from scraper.py (the Walmart bot), which it does not
touch or import.

It reads only the public job-board feeds that companies publish for this
purpose (Greenhouse, Lever and Ashby). No login, no page scraping.

To add or remove a company, edit COMPANIES below. Each entry is:
    (display name, job board type, the company's board id)
A company whose feed fails is skipped and reported; the run carries on.
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- settings --

COMPANIES = [
    # Greenhouse boards
    ("Anthropic", "greenhouse", "anthropic"),
    ("Stripe", "greenhouse", "stripe"),
    ("Databricks", "greenhouse", "databricks"),
    ("Airbnb", "greenhouse", "airbnb"),
    ("Figma", "greenhouse", "figma"),
    ("Pinterest", "greenhouse", "pinterest"),
    ("Reddit", "greenhouse", "reddit"),
    ("Instacart", "greenhouse", "instacart"),
    ("Lyft", "greenhouse", "lyft"),
    ("Coinbase", "greenhouse", "coinbase"),
    ("Duolingo", "greenhouse", "duolingo"),
    ("Datadog", "greenhouse", "datadog"),
    ("Discord", "greenhouse", "discord"),
    ("Dropbox", "greenhouse", "dropbox"),
    # Ashby boards
    ("OpenAI", "ashby", "openai"),
    ("Notion", "ashby", "notion"),
    ("Ramp", "ashby", "ramp"),
    ("Cohere", "ashby", "cohere"),
    # Lever boards
    ("Spotify", "lever", "spotify"),
    ("Palantir", "lever", "palantir"),
]

# Title keywords per category. A job is kept when its title contains one.
CATEGORIES = {
    "Data Science": ["data scientist", "data science"],
    "Data Analytics": ["data analyst", "analytics", "business intelligence"],
    "Machine Learning and AI": [
        "machine learning", "ml engineer", "ai engineer", "applied scientist",
        "applied ai", "research engineer",
    ],
    "Economics and Research": ["economist", "research scientist", "quantitative researcher"],
    "Product Management": ["product manager", "product management"],
    "Software Engineering": ["software engineer", "software developer"],
}

# Each run has a theme, so three posts a week do not repeat each other.
# Python weekday(): Monday is 0.
THEMES = {
    1: ("Data Science and Analytics", ["Data Science", "Data Analytics"]),
    3: ("AI, Machine Learning and Research", ["Machine Learning and AI", "Economics and Research"]),
    5: ("Product and Engineering", ["Product Management", "Software Engineering"]),
}
DEFAULT_THEME = ("Data, AI and Product", list(CATEGORIES.keys()))

MAX_JOBS = int(os.environ.get("MAX_JOBS", "12"))
MAX_PER_COMPANY = int(os.environ.get("MAX_PER_COMPANY", "2"))
MAX_AGE_DAYS = int(os.environ.get("MAX_AGE_DAYS", "21"))
TIMEOUT = 25

HEADERS = {
    "User-Agent": "CareerMirrorJobsDigest/1.0 (+https://careermirror.ai)",
    "Accept": "application/json",
}

# Filled during a run and printed in the summary.
COMPANY_STATUS = {}

# --------------------------------------------------------------- locations --

US_STATES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC"
).split()
_STATE_RE = re.compile(r",\s*(" + "|".join(US_STATES) + r")\b")
_US_WORDS = re.compile(r"\b(united states|usa|u\.s\.a?\.?|us)\b", re.IGNORECASE)
_US_CITIES = re.compile(
    r"\b(san francisco|new york|nyc|seattle|austin|boston|chicago|los angeles|"
    r"mountain view|palo alto|sunnyvale|san jose|bellevue|denver|atlanta|"
    r"washington|bay area|menlo park|san mateo|redwood city)\b",
    re.IGNORECASE,
)
_NON_US = re.compile(
    r"\b(canada|toronto|vancouver|montreal|united kingdom|uk|london|dublin|ireland|"
    r"germany|berlin|munich|france|paris|netherlands|amsterdam|spain|madrid|barcelona|"
    r"sweden|stockholm|switzerland|zurich|poland|warsaw|india|bengaluru|bangalore|"
    r"hyderabad|singapore|japan|tokyo|korea|seoul|australia|sydney|melbourne|"
    r"brazil|sao paulo|mexico|israel|tel aviv|china|emea|apac|latam|europe)\b",
    re.IGNORECASE,
)


def is_us_location(location):
    """True when a location string points to the United States."""
    loc = (location or "").strip()
    if not loc:
        return False
    # A posting can list several places ("New York, NY; London, UK").
    # It counts as US when any one of them is in the US.
    for part in re.split(r";|\||/|\bor\b|\band\b", loc):
        part = part.strip()
        if not part:
            continue
        if _US_WORDS.search(part):
            return True
        if _NON_US.search(part):
            continue  # also guards "Bengaluru, IN" against the Indiana code
        if _STATE_RE.search(part) or _US_CITIES.search(part):
            return True
        # A bare "Remote" at a US company is treated as US.
        if "remote" in part.lower():
            return True
    return False


# ------------------------------------------------------------------- dates --

def _parse_date(value):
    """Accepts ISO text or a millisecond timestamp. Returns aware UTC datetime or None."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


# ---------------------------------------------------------------- fetchers --

def _get_json(url, params=None):
    resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def parse_greenhouse(data):
    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "id": "gh-" + str(j.get("id")),
            "title": (j.get("title") or "").strip(),
            "location": ((j.get("location") or {}).get("name") or "").strip(),
            "url": j.get("absolute_url") or "",
            "posted": _parse_date(j.get("first_published") or j.get("updated_at")),
        })
    return jobs


def parse_lever(data):
    jobs = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories") or {}
        jobs.append({
            "id": "lv-" + str(j.get("id")),
            "title": (j.get("text") or "").strip(),
            "location": (cats.get("location") or "").strip(),
            "url": j.get("hostedUrl") or "",
            "posted": _parse_date(j.get("createdAt")),
        })
    return jobs


def parse_ashby(data):
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        jobs.append({
            "id": "ab-" + str(j.get("id")),
            "title": (j.get("title") or "").strip(),
            "location": (j.get("location") or "").strip(),
            "url": j.get("jobUrl") or j.get("applyUrl") or "",
            "posted": _parse_date(j.get("publishedAt")),
        })
    return jobs


def fetch_company(name, board, slug):
    """Returns the company's open jobs in a common shape. Raises on failure."""
    if board == "greenhouse":
        data = _get_json("https://boards-api.greenhouse.io/v1/boards/" + slug + "/jobs")
        jobs = parse_greenhouse(data)
    elif board == "lever":
        data = _get_json("https://api.lever.co/v0/postings/" + slug, params={"mode": "json"})
        jobs = parse_lever(data)
    elif board == "ashby":
        data = _get_json("https://api.ashbyhq.com/posting-api/job-board/" + slug)
        jobs = parse_ashby(data)
    else:
        raise ValueError("Unknown board type: " + board)
    for j in jobs:
        j["company"] = name
    return jobs


# --------------------------------------------------------------- selection --

def categorize(title):
    t = (title or "").lower()
    for label, keywords in CATEGORIES.items():
        if any(k in t for k in keywords):
            return label
    return None


def theme_for(day=None):
    """Theme name and categories for a weekday (defaults to today, UTC)."""
    if os.environ.get("THEME_DAY", "").strip().isdigit():
        day = int(os.environ["THEME_DAY"])
    if day is None:
        day = datetime.now(timezone.utc).weekday()
    return THEMES.get(day, DEFAULT_THEME)


def select_jobs(all_jobs, categories, now=None):
    """
    Keeps US jobs in the wanted categories, newest first, at most
    MAX_PER_COMPANY per company and MAX_JOBS in total. Jobs with a known
    date older than MAX_AGE_DAYS are dropped; undated jobs are kept last.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAX_AGE_DAYS)
    candidates = []
    seen = set()
    for j in all_jobs:
        if not j.get("url") or not j.get("title") or j["id"] in seen:
            continue
        label = categorize(j["title"])
        if label not in categories:
            continue
        if not is_us_location(j.get("location")):
            continue
        if j.get("posted") and j["posted"] < cutoff:
            continue
        seen.add(j["id"])
        candidates.append(dict(j, department=label))

    oldest = datetime.min.replace(tzinfo=timezone.utc)
    candidates.sort(key=lambda j: j.get("posted") or oldest, reverse=True)

    picked, per_company = [], {}
    for j in candidates:
        if len(picked) >= MAX_JOBS:
            break
        if per_company.get(j["company"], 0) >= MAX_PER_COMPANY:
            continue
        per_company[j["company"]] = per_company.get(j["company"], 0) + 1
        picked.append(j)
    return picked


def collect_jobs(day=None):
    """Fetches every company, then returns (theme name, selected jobs)."""
    theme_name, categories = theme_for(day)
    all_jobs = []
    for name, board, slug in COMPANIES:
        try:
            jobs = fetch_company(name, board, slug)
            COMPANY_STATUS[name] = "ok, " + str(len(jobs)) + " open roles"
            all_jobs.extend(jobs)
        except (requests.exceptions.RequestException, ValueError) as e:
            COMPANY_STATUS[name] = "FAILED: " + str(e)[:140]
            logger.warning("Skipping %s: %s", name, e)
    picked = select_jobs(all_jobs, categories)
    logger.info("Theme '%s': %d jobs picked from %d fetched", theme_name, len(picked), len(all_jobs))
    return theme_name, picked


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    theme, jobs = collect_jobs()
    print("Theme:", theme)
    for j in jobs:
        when = j["posted"].strftime("%Y-%m-%d") if j.get("posted") else "undated"
        print("[%s] [%s] %s: %s - %s | %s" % (when, j["department"], j["company"], j["title"], j["location"], j["url"]))
    for name, status in COMPANY_STATUS.items():
        print(name + ": " + status)
