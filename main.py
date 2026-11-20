import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import anthropic
from src.scraper import scrape_top_jobs, REGION, SEEN_COUNTRIES

REGION_LABEL = {"US": "US", "IN": "India (IDC)"}[REGION]
DRY_RUN = os.environ.get("DRY_RUN", "").lower() == "true"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def draft_post_with_claude(jobs):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Build the job list for the prompt: each line is "Title - City, State\nURL"
    job_lines = []
    for j in jobs:
        line = j["title"] + " - " + j["location"] + "\n" + j["url"]
        job_lines.append(line)
    jobs_block = "\n\n".join(job_lines)

    region_note = (
        "These roles are at the Walmart Global Tech India Development Center (IDC). "
        "Make clear in the opener that these are India-based roles. "
        if REGION == "IN" else ""
    )
    prompt = (
        "Write a LinkedIn post about these Walmart job openings. "
        + region_note +
        "Rules:\n"
        "1. Short punchy opener (1-2 sentences).\n"
        "2. List EVERY job below exactly as: job title and then the full URL on the next line. "
        "Do not shorten, change, or omit any URLs. Do not use hyperlink text.\n"
        "3. Group by category: Data Science, Data Analytics, Software Engineering, Product Management.\n"
        "4. Short closing line encouraging people to apply.\n"
        "5. Add relevant hashtags at the end.\n"
        "6. Max 3000 characters.\n"
        "Return ONLY the post text, nothing else.\n\n"
        "Jobs:\n\n" + jobs_block
    )

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
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


def main():
    logger.info("Scraping Walmart Careers...")
    jobs = scrape_top_jobs()
    logger.info("Found " + str(len(jobs)) + " jobs.")

    if DRY_RUN:
        for j in jobs:
            print("::notice::[" + j["department"] + "] " + j["title"] + " - " + j["location"] + " | " + j["url"])
        print("::notice::" + REGION + " total " + str(len(jobs)) + "; countries seen " + str(SEEN_COUNTRIES))
        return

    if not jobs:
        send_email("Walmart Jobs Bot " + REGION_LABEL + " - No results",
                   "No jobs returned by scraper. Countries seen: " + str(SEEN_COUNTRIES))
        return

    logger.info("Drafting post with Claude...")
    post_text = draft_post_with_claude(jobs)
    logger.info("Post drafted (" + str(len(post_text)) + " chars)")

    subject = "Walmart Bot " + REGION_LABEL + " - Draft ready (" + str(len(jobs)) + " jobs)"
    send_email(subject=subject, body=post_text)
    logger.info("Done.")


if __name__ == "__main__":
    main()
