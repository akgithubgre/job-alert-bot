import feedparser
import requests
import os
from datetime import datetime, timezone, timedelta
from dateutil import parser as date_parser

# ─── CONFIG ───────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

# Roles to search for
SEARCH_QUERIES = [
    "software engineer",
    "backend developer",
    "data analyst",
    "data engineer",
]

# India + Remote focus
LOCATIONS = ["India", "Remote"]

# Only show jobs posted in last 24 hours
HOURS_BACK = 24

# ─── RSS FEED BUILDERS ────────────────────────────────────────────────────────

def build_indeed_rss(query: str, location: str) -> str:
    base = "https://www.indeed.com/rss"
    q = query.replace(" ", "+")
    l = location.replace(" ", "+")
    return f"{base}?q={q}&l={l}&sort=date"

def build_linkedin_rss(query: str) -> str:
    q = query.replace(" ", "%20")
    # LinkedIn public job RSS (no auth needed, limited results)
    return f"https://www.linkedin.com/jobs/search?keywords={q}&location=India&f_TPR=r86400&format=rss"

# ─── FEED PARSER ──────────────────────────────────────────────────────────────

def is_recent(entry, hours: int = 24) -> bool:
    """Check if a job was posted within the last N hours."""
    try:
        if hasattr(entry, "published"):
            pub = date_parser.parse(entry.published)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            return pub >= cutoff
    except Exception:
        pass
    return True  # include if date can't be parsed

def fetch_jobs_from_feed(url: str, source: str) -> list[dict]:
    jobs = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if not is_recent(entry, HOURS_BACK):
                continue
            jobs.append({
                "title":   entry.get("title", "N/A"),
                "company": entry.get("source", {}).get("title", "N/A") if source == "LinkedIn"
                           else entry.get("author", "N/A"),
                "link":    entry.get("link", ""),
                "date":    entry.get("published", "N/A"),
                "source":  source,
            })
    except Exception as e:
        print(f"[ERROR] Failed to fetch {source} feed ({url}): {e}")
    return jobs

# ─── FETCH ALL JOBS ───────────────────────────────────────────────────────────

def fetch_all_jobs() -> list[dict]:
    all_jobs = []
    seen_links = set()

    for query in SEARCH_QUERIES:
        for location in LOCATIONS:
            # Indeed
            url = build_indeed_rss(query, location)
            jobs = fetch_jobs_from_feed(url, "Indeed")
            for job in jobs:
                if job["link"] not in seen_links:
                    seen_links.add(job["link"])
                    job["query"] = query
                    all_jobs.append(job)

        # LinkedIn (location baked into URL)
        url = build_linkedin_rss(query)
        jobs = fetch_jobs_from_feed(url, "LinkedIn")
        for job in jobs:
            if job["link"] not in seen_links:
                seen_links.add(job["link"])
                job["query"] = query
                all_jobs.append(job)

    return all_jobs

# ─── TELEGRAM SENDER ──────────────────────────────────────────────────────────

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload)
    if not resp.ok:
        print(f"[ERROR] Telegram send failed: {resp.text}")

def chunk_messages(text: str, limit: int = 4000) -> list[str]:
    """Split long messages into chunks within Telegram's limit."""
    lines = text.split("\n")
    chunks, current = [], ""
    for line in lines:
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        chunks.append(current)
    return chunks

# ─── FORMAT MESSAGE ───────────────────────────────────────────────────────────

def format_digest(jobs: list[dict]) -> str:
    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    header = (
        f"🔔 <b>Job Alert Digest</b>\n"
        f"🕐 {now_ist.strftime('%d %b %Y, %I:%M %p')} IST\n"
        f"📋 <b>{len(jobs)} new job(s)</b> in last 24 hrs\n"
        f"{'─'*30}\n\n"
    )

    if not jobs:
        return header + "😴 No new jobs found this time. Check back later!"

    # Group by role/query
    grouped: dict[str, list] = {}
    for job in jobs:
        q = job["query"].title()
        grouped.setdefault(q, []).append(job)

    body = ""
    for role, role_jobs in grouped.items():
        body += f"<b>💼 {role}</b> ({len(role_jobs)} jobs)\n\n"
        for job in role_jobs[:10]:  # max 10 per role
            body += (
                f"  🏢 <b>{job['title']}</b>\n"
                f"  🔹 {job['company']}\n"
                f"  🌐 {job['source']}\n"
                f"  🔗 <a href='{job['link']}'>Apply Here</a>\n\n"
            )

    return header + body

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"[INFO] Fetching jobs at {datetime.now(timezone.utc).isoformat()}")
    jobs = fetch_all_jobs()
    print(f"[INFO] Found {len(jobs)} recent jobs")

    digest = format_digest(jobs)
    for chunk in chunk_messages(digest):
        send_telegram(chunk)

    print("[INFO] Telegram notification sent!")

if __name__ == "__main__":
    main()
