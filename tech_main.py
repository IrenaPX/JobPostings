"""
tech_main.py
Multi-company tech jobs digest for the CareerMirror page.

Collects recent roles from the companies listed in src/tech_jobs.py, asks
Claude to format a LinkedIn-ready post, and emails the draft. Nothing is
posted anywhere: the email is a draft for Irena to review.

The Walmart bot (main.py) is separate and unchanged.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.tech_jobs import COMPANY_STATUS, collect_jobs

DRY_RUN = os.environ.get("DRY_RUN", "").lower() == "true"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5")
POINTER = (
    "If you are in a job search, CareerMirror helps with resume and fit questions. "
    "It is free for 30 days and needs no card: https://careermirror.ai"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def plain_post(theme, jobs):
    """Fallback post with no AI formatting, also used as the source list."""
    lines = []
    for j in jobs:
        lines.append(j["company"] + ": " + j["title"] + " - " + j["location"] + "\n" + j["url"])
    return (
        "Open roles this week: " + theme + "\n\n"
        + "\n\n".join(lines)
        + "\n\nRoles come from each company's public careers page.\n\n"
        + POINTER
    )


def draft_post_with_claude(theme, jobs):
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    job_lines = [
        j["company"] + ": " + j["title"] + " - " + j["location"] + "\n" + j["url"] for j in jobs
    ]
    prompt = (
        "Write a LinkedIn post for the CareerMirror company page listing these open roles at "
        "several tech companies. The theme is: " + theme + ". Readers are job seekers.\n"
        "Rules:\n"
        "1. A calm, practical opener of 1 or 2 sentences. No hype, no exclamation marks.\n"
        "2. List EVERY job below exactly as: 'Company: job title - location' and then the full "
        "URL on the next line. Do not shorten, change or omit any URL. Do not use hyperlink text.\n"
        "3. Group the jobs by company.\n"
        "4. Then this line, unchanged: Roles come from each company's public careers page.\n"
        "5. End with this line, unchanged: " + POINTER + "\n"
        "6. Do not claim any partnership with or endorsement from these companies.\n"
        "7. Never use an em-dash. Add at most 4 relevant hashtags at the very end.\n"
        "8. Max 3000 characters.\n"
        "Return ONLY the post text, nothing else.\n\n"
        "Jobs:\n\n" + "\n\n".join(job_lines)
    )
    message = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def send_email(subject, body):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    notify_email = os.environ.get("NOTIFY_EMAIL")
    if not all([gmail_user, gmail_password, notify_email]):
        logger.warning("Email secrets not set.")
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


def status_report():
    return "\n".join(name + ": " + status for name, status in COMPANY_STATUS.items())


def main():
    logger.info("Collecting tech jobs...")
    theme, jobs = collect_jobs()
    failed = [n for n, s in COMPANY_STATUS.items() if s.startswith("FAILED")]

    for name, status in COMPANY_STATUS.items():
        level = "warning" if status.startswith("FAILED") else "notice"
        print("::" + level + "::" + name + ": " + status)

    if DRY_RUN:
        for j in jobs:
            print("::notice::[" + j["department"] + "] " + j["company"] + ": " + j["title"]
                  + " - " + j["location"] + " | " + j["url"])
        print("::notice::Theme '" + theme + "': " + str(len(jobs)) + " jobs; "
              + str(len(failed)) + " of " + str(len(COMPANY_STATUS)) + " companies failed")
        return

    if not jobs:
        send_email("Tech Jobs Bot - No results (" + theme + ")",
                   "No jobs matched this run.\n\n" + status_report())
        return

    try:
        post_text = draft_post_with_claude(theme, jobs)
    except Exception as e:  # keep the run useful if the AI call fails
        logger.warning("Claude draft failed, sending the plain list: %s", e)
        post_text = plain_post(theme, jobs)

    body = post_text
    if failed:
        body += "\n\n---\nNot part of the post. Companies skipped this run: " + ", ".join(failed)
    send_email("Tech Jobs Bot - Draft ready (" + str(len(jobs)) + " jobs, " + theme + ")", body)
    logger.info("Done.")


if __name__ == "__main__":
    main()
