"""
main.py
Orchestrates the full Walmart Jobs Bot pipeline:
  1. Scrape this week's Walmart job postings
  2. Use Claude (Anthropic) to draft a LinkedIn-style post
  3. Try to post directly to LinkedIn (requires LINKEDIN_ACCESS_TOKEN secret)
  4. Send an email notification with the post content (always, as confirmation)

Required GitHub Secrets:
  ANTHROPIC_API_KEY, NOTIFY_EMAIL, GMAIL_USER, GMAIL_APP_PASSWORD

Optional GitHub Secrets:
  LINKEDIN_ACCESS_TOKEN
"""

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic

from src.scraper import scrape_this_week
from src.poster import post_to_linkedin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def draft_post_with_claude(jobs):
    """Uses Claude to draft a LinkedIn post summarising this week's job openings."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    job_lines = []
    for j in jobs[:20]:
        date_str = j["posted_date"].strftime("%b %d") if j["posted_date"] else "this week"
        job_lines.append(
            "- " + j["title"] + " | " + j["location"] + " | " + date_str + " | " + j["url"]
        )

    jobs_block = "\n".join(job_lines) if job_lines else "No new jobs found this week."

    prompt = (
        "You are a helpful assistant that writes engaging LinkedIn posts "
        "for a job-board newsletter.\n\n"
        "Here are the Walmart tech & analytics roles posted this week:\n\n"
        + jobs_block
        + "\n\nWrite a LinkedIn post (max 1,300 characters) that:\n"
        "- Opens with a short, attention-grabbing hook "
        "(no generic openers like Exciting news)\n"
        "- Briefly highlights the variety or volume of roles\n"
        "- Lists up to 8 of the most interesting roles as short bullet lines (title + city)\n"
        "- Ends with a call-to-action directing readers to the Walmart Careers page\n"
        "- Uses a friendly, professional tone\n"
        "- Does NOT include the raw URLs in the body\n\n"
        "Return ONLY the post text, nothing else."
    )

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def send_email(subject, body):
    """Sends a plain-text email via Gmail SMTP."""
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    notify_email = os.environ.get("NOTIFY_EMAIL")

    if not all([gmail_user, gmail_password, notify_email]):
        logger.warning("Email secrets not set -- skipping email notification.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = notify_email
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, notify_email, msg.as_string())
    logger.info("Email sent to " + str(notify_email))


def main():
    # 1. Scrape
    logger.info("=== Step 1: Scraping Walmart Careers ===")
    jobs = scrape_this_week()
    logger.info("Scraped " + str(len(jobs)) + " qualifying job(s) this week.")

    if not jobs:
        logger.info("No new jobs found -- sending a brief email and exiting.")
        send_email(
            subject="Walmart Jobs Bot -- No new postings this week",
            body=(
                "The scraper ran successfully but found no new "
                "tech/analytics jobs posted this week on Walmart Careers."
            ),
        )
        return

    # 2. Draft post with Claude
    logger.info("=== Step 2: Drafting LinkedIn post with Claude ===")
    post_text = draft_post_with_claude(jobs)
    logger.info("Drafted post (" + str(len(post_text)) + " chars)")

    # 3. Try LinkedIn
    logger.info("=== Step 3: Attempting LinkedIn post ===")
    linkedin_token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    linkedin_success = False
    linkedin_error = ""

    if linkedin_token:
        try:
            result = post_to_linkedin(post_text)
            logger.info("LinkedIn post successful: " + str(result))
            linkedin_success = True
        except Exception as exc:
            linkedin_error = str(exc)
            logger.error("LinkedIn posting failed: " + str(exc))
    else:
        linkedin_error = "LINKEDIN_ACCESS_TOKEN secret not set."
        logger.warning(linkedin_error)

    # 4. Email notification
    logger.info("=== Step 4: Sending email notification ===")
    job_list_lines = []
    for j in jobs:
        date_str = j["posted_date"].strftime("%Y-%m-%d") if j["posted_date"] else "unknown"
        job_list_lines.append("  - " + j["title"] + " | " + j["location"] + " | " + date_str)
        job_list_lines.append("    " + j["url"])
    job_list = "\n".join(job_list_lines)

    if linkedin_success:
        subject = "Walmart Jobs Bot -- LinkedIn post published (" + str(len(jobs)) + " jobs)"
        body = (
            "The LinkedIn post was published successfully.\n\n"
            "-- PUBLISHED POST --\n" + post_text + "\n\n"
            "-- ALL SCRAPED JOBS THIS WEEK (" + str(len(jobs)) + ") --\n" + job_list + "\n"
        )
    else:
        subject = "Walmart Jobs Bot -- Draft ready for manual post (" + str(len(jobs)) + " jobs)"
        body = (
            "LinkedIn posting was skipped or failed.\n"
            "Reason: " + linkedin_error + "\n\n"
            "-- DRAFT POST (copy & paste to LinkedIn) --\n" + post_text + "\n\n"
            "-- ALL SCRAPED JOBS THIS WEEK (" + str(len(jobs)) + ") --\n" + job_list + "\n"
            "\nWalmart Careers: https://careers.walmart.com\n"
        )

    send_email(subject=subject, body=body)
    logger.info("=== Pipeline complete ===")


if __name__ == "__main__":
    main()
main.py
Orchestrates the full Walmart Jobs Bot pipeline:
  1. Scrape this week's Walmart job postings
    2. Use Claude (Anthropic) to draft a LinkedIn-style post
      3. Try to post directly to LinkedIn (requires LINKEDIN_ACCESS_TOKEN secret)
        4. Send an email notification with the post content (always, as confirmation)
             - On LinkedIn success: email confirms the live post
                  - On LinkedIn failure / no token: email contains the drafted post for manual posting

                  Required GitHub Secrets:
                    ANTHROPIC_API_KEY       - Your Anthropic API key
                      NOTIFY_EMAIL            - Destination email address (where to send the digest)
                        GMAIL_USER              - Gmail address used to send (e.g. yourname@gmail.com)
                          GMAIL_APP_PASSWORD      - Gmail App Password (16-char, from Google Account > Security)

                          Optional GitHub Secrets (LinkedIn posting):
                            LINKEDIN_ACCESS_TOKEN   - OAuth 2.0 token; see README for how to obtain one
                            """

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic

from src.scraper import scrape_this_week
from src.poster import post_to_linkedin

logging.basicConfig(
      level=logging.INFO,
      format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


# -- helpers ------------------------------------------------------------------

def draft_post_with_claude(jobs: list) -> str:
      """Uses Claude to draft a LinkedIn post summarising this week's job openings."""
      client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    job_lines = []
    for j in jobs[:20]:          # cap at 20 so the prompt stays reasonable
              date_str = j["posted_date"].strftime("%b %d") if j["posted_date"] else "this week"
              job_lines.append(f"- {j['title']} | {j['location']} | {date_str} | {j['url']}")

    jobs_block = "\n".join(job_lines) if job_lines else "No new jobs found this week."

    prompt = (
              "You are a helpful assistant that writes engaging LinkedIn posts "
              "for a job-board newsletter.\n\n"
              "Here are the Walmart tech & analytics roles posted this week:\n\n"
              + jobs_block
              + "\n\nWrite a LinkedIn post (max 1,300 characters) that:\n"
              "- Opens with a short, attention-grabbing hook "
              "(no generic openers like 'Exciting news!')\n"
              "- Briefly highlights the variety or volume of roles\n"
              "- Lists up to 8 of the most interesting roles as short bullet lines "
              "(title + city)\n"
              "- Ends with a call-to-action directing readers to the Walmart Careers page\n"
              "- Uses a friendly, professional tone -- no fluff, no excessive emojis\n"
              "- Does NOT include the raw URLs in the body (keep it clean)\n\n"
              "Return ONLY the post text, nothing else."
    )

    message = client.messages.create(
              model="claude-opus-4-5",
              max_tokens=600,
              messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def send_email(subject: str, body: str) -> None:
      """Sends a plain-text email via Gmail SMTP."""
      gmail_user = os.environ.get("GMAIL_USER")
      gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
      notify_email = os.environ.get("NOTIFY_EMAIL")

    if not all([gmail_user, gmail_password, notify_email]):
              logger.warning("Email secrets not set -- skipping email notification.")
              return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = notify_email
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
              server.login(gmail_user, gmail_password)
              server.sendmail(gmail_user, notify_email, msg.as_string())
          logger.info(f"Email sent to {notify_email}")


# -- main pipeline ------------------------------------------------------------

def main() -> None:
      # 1. Scrape
      logger.info("=== Step 1: Scraping Walmart Careers ===")
      jobs = scrape_this_week()
      logger.info(f"Scraped {len(jobs)} qualifying job(s) this week.")

    if not jobs:
              logger.info("No new jobs found -- sending a brief email and exiting.")
              send_email(
                  subject="Walmart Jobs Bot -- No new postings this week",
                  body=(
                      "The scraper ran successfully but found no new "
                      "tech/analytics jobs posted this week on Walmart Careers."
                  ),
              )
              return

    # 2. Draft post with Claude
    logger.info("=== Step 2: Drafting LinkedIn post with Claude ===")
    post_text = draft_post_with_claude(jobs)
    logger.info(f"Drafted post ({len(post_text)} chars):\n{post_text}")

    # 3. Try LinkedIn
    logger.info("=== Step 3: Attempting LinkedIn post ===")
    linkedin_token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    linkedin_success = False
    linkedin_error = ""

    if linkedin_token:
              try:
                            result = post_to_linkedin(post_text)
                            logger.info(f"LinkedIn post successful: {result}")
                            linkedin_success = True
except Exception as exc:
            linkedin_error = str(exc)
            logger.error(f"LinkedIn posting failed: {exc}")
else:
        linkedin_error = "LINKEDIN_ACCESS_TOKEN secret not set."
          logger.warning(linkedin_error)

    # 4. Email notification
    logger.info("=== Step 4: Sending email notification ===")
    job_list_lines = []
    for j in jobs:
              date_str = (
                            j["posted_date"].strftime("%Y-%m-%d") if j["posted_date"] else "unknown date"
              )
              job_list_lines.append(
                  f"  - {j['title']} | {j['location']} | {date_str}\n    {j['url']}"
              )
          job_list = "\n".join(job_list_lines)

    if linkedin_success:
              subject = f"Walmart Jobs Bot -- LinkedIn post published ({len(jobs)} jobs)"
              body = (
                  f"The LinkedIn post was published successfully.\n\n"
                  f"-- PUBLISHED POST --\n{post_text}\n\n"
                  f"-- ALL SCRAPED JOBS THIS WEEK ({len(jobs)}) --\n{job_list}\n"
              )
else:
        subject = (
                      f"Walmart Jobs Bot -- Draft ready for manual post ({len(jobs)} jobs)"
        )
        body = (
                      f"LinkedIn posting was skipped or failed.\n"
                      f"Reason: {linkedin_error}\n\n"
                      f"-- DRAFT POST (copy & paste to LinkedIn) --\n{post_text}\n\n"
                      f"-- ALL SCRAPED JOBS THIS WEEK ({len(jobs)}) --\n{job_list}\n"
                      f"\nWalmart Careers: https://careers.walmart.com\n"
        )

    send_email(subject=subject, body=body)
    logger.info("=== Pipeline complete ===")


if __name__ == "__main__":
      main()
