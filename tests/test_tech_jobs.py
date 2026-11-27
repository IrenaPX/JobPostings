"""Offline tests for src/tech_jobs.py. No network calls."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import tech_jobs as tj  # noqa: E402

NOW = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)


def job(i, company, title, location, days_old=1):
    return {
        "id": "t-" + str(i),
        "company": company,
        "title": title,
        "location": location,
        "url": "https://example.com/jobs/" + str(i),
        "posted": NOW - timedelta(days=days_old) if days_old is not None else None,
    }


class LocationTests(unittest.TestCase):
    def test_us_locations(self):
        for loc in ["San Francisco, CA", "New York, NY; Seattle, WA", "Remote - US",
                    "United States", "Remote", "Austin, TX (Hybrid)", "NYC",
                    "New York, NY; London, UK", "London, UK or Remote - US"]:
            self.assertTrue(tj.is_us_location(loc), loc)

    def test_non_us_locations(self):
        for loc in ["London, UK", "Remote - Canada", "Bengaluru, India", "Dublin, Ireland",
                    "Toronto", "Remote, EMEA", "", None, "Tokyo", "Bengaluru, IN",
                    "London, UK; Dublin, Ireland"]:
            self.assertFalse(tj.is_us_location(loc), loc)


class ParserTests(unittest.TestCase):
    def test_greenhouse(self):
        data = {"jobs": [{"id": 7, "title": " Data Scientist ", "location": {"name": "Seattle, WA"},
                          "absolute_url": "https://boards.greenhouse.io/x/jobs/7",
                          "updated_at": "2026-11-30T10:00:00-05:00"}]}
        j = tj.parse_greenhouse(data)[0]
        self.assertEqual((j["id"], j["title"], j["location"]), ("gh-7", "Data Scientist", "Seattle, WA"))
        self.assertEqual(j["posted"].tzinfo is not None, True)

    def test_lever(self):
        data = [{"id": "abc", "text": "Product Manager", "categories": {"location": "New York, NY"},
                 "hostedUrl": "https://jobs.lever.co/x/abc", "createdAt": 1796126400000}]
        j = tj.parse_lever(data)[0]
        self.assertEqual((j["id"], j["title"], j["url"]), ("lv-abc", "Product Manager", "https://jobs.lever.co/x/abc"))
        self.assertIsNotNone(j["posted"])
        self.assertEqual(tj.parse_lever({"error": "not found"}), [])

    def test_ashby(self):
        data = {"jobs": [
            {"id": "1", "title": "Research Scientist", "location": "San Francisco",
             "jobUrl": "https://jobs.ashbyhq.com/x/1", "publishedAt": "2026-11-29T00:00:00.000Z", "isListed": True},
            {"id": "2", "title": "Hidden", "location": "Remote", "jobUrl": "u", "isListed": False},
        ]}
        jobs = tj.parse_ashby(data)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "ab-1")

    def test_bad_dates(self):
        self.assertIsNone(tj._parse_date("not a date"))
        self.assertIsNone(tj._parse_date(None))


class SelectionTests(unittest.TestCase):
    def test_category_and_region_filter(self):
        jobs = [
            job(1, "A", "Senior Data Scientist", "Seattle, WA"),
            job(2, "A", "Account Executive", "Seattle, WA"),
            job(3, "B", "Data Analyst", "London, UK"),
            job(4, "B", "Product Manager", "Austin, TX"),
        ]
        picked = tj.select_jobs(jobs, ["Data Science", "Data Analytics"], now=NOW)
        self.assertEqual([j["id"] for j in picked], ["t-1"])
        self.assertEqual(picked[0]["department"], "Data Science")

    def test_limits_age_and_order(self):
        jobs = [job(i, "A", "Data Scientist " + str(i), "Remote - US", days_old=i) for i in range(1, 6)]
        jobs.append(job(9, "B", "Data Scientist", "Boston, MA", days_old=60))
        jobs.append(job(10, "C", "Data Scientist", "Boston, MA", days_old=None))
        jobs.append(dict(jobs[0]))  # duplicate id
        picked = tj.select_jobs(jobs, ["Data Science"], now=NOW)
        ids = [j["id"] for j in picked]
        self.assertEqual(ids[:2], ["t-1", "t-2"])           # newest first
        self.assertEqual(ids.count("t-1"), 1)                # no duplicates
        self.assertEqual(sum(1 for j in picked if j["company"] == "A"), tj.MAX_PER_COMPANY)
        self.assertNotIn("t-9", ids)                         # too old
        self.assertEqual(ids[-1], "t-10")                    # undated kept, last

    def test_total_cap(self):
        jobs = [job(i, "Co" + str(i), "Software Engineer", "Denver, CO") for i in range(40)]
        self.assertEqual(len(tj.select_jobs(jobs, ["Software Engineering"], now=NOW)), tj.MAX_JOBS)

    def test_themes(self):
        self.assertEqual(tj.theme_for(1)[1], ["Data Science", "Data Analytics"])
        self.assertEqual(tj.theme_for(0), tj.DEFAULT_THEME)
        for _, cats in tj.THEMES.values():
            for c in cats:
                self.assertIn(c, tj.CATEGORIES)


if __name__ == "__main__":
    unittest.main()
