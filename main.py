import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import anthropic
from src.scraper import scrape_this_week

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def draft_post_with_claude(jobs):
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        job_lines = []
        for j in jobs[:20]:
                    date_str = j["posted_date"].strftime("%b %d") if j["posted_date"] else "this week"
                    job_lines.append("- " + j["title"] + " | " + j["location"] + " | " + date_str)
                jobs_block = "\n".join(job_lines) if job_lines else "No new jobs this week."
    prompt = (
                "Write a LinkedIn post (max 1300 chars) about these Walmart tech jobs:\n\n"
                + jobs_block
                + "\n\nRules: short hook opener, list up to 8 roles (title+city), CTA to careers.walmart.com."
                + "\nReturn ONLY the post text."
    )
    message = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=600,
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
    jobs = scrape_this_week()
    logger.info("Found " + str(len(jobs)) + " jobs.")
    if not jobs:
                send_email("Walmart Jobs Bot - No new postings", "No new tech jobs this week.")
                return
            logger.info("Drafting post with Claude...")
    post_text = draft_post_with_claude(jobs)
    logger.info("Post drafted: " + str(len(post_text)) + " chars")
    job_lines = []
    for j in jobs:
                date_str = j["posted_date"].strftime("%Y-%m-%d") if j["posted_date"] else "unknown"
                job_lines.append("- " + j["title"] + " | " + j["location"] + " | " + date_str)
                job_lines.append("  " + j["url"])
            job_list = "\n".join(job_lines)
    subject = "Walmart Bot - Draft ready (" + str(len(jobs)) + " jobs)"
    body = (
                "DRAFT POST:\n\n"
                + post_text
                + "\n\nJobs scraped this week:\n"
                + job_list
                + "\n\nhttps://careers.walmart.com"
    )
    send_email(subject=subject, body=body)
    logger.info("Done.")


if __name__ == "__main__":
        main()
