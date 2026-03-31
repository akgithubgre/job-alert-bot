import feedparser
import requests
import os
from datetime import datetime, timezone, timedelta
from dateutil import parser as date_parser

# ─── CONFIG ───────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

SEARCH_QUERIES = [
    "software engineer",
    "software developer",
    "backend developer",
    "data analyst",
    "data engineer",
]

HOURS_BACK = 24

# ─── RSS FEED BUILDERS ────────────────────────────────────────────────────────

def get_feeds(query: str) -> list[tuple[str, str]]:
    q_plus    = query.replace(" ", "+")
    q_encoded = query.replace(" ", "%20")
    feeds = [
        # Indeed India
        (f"https://www.indeed.com/rss?q={q_plus}&l=India&sort=date&fromage=1", "Indeed"),
        # Indeed Remote
        (f"https://www.indeed.com/rss?q={q_plus}&l=Remote&sort=date&fromage=1", "Indeed"),
        # LinkedIn RSS (public, no auth)
        (f"https://www.linkedin.com/jobs/search?keywords={q_encoded}&location=India&f_TPR=r86400&format=rss", "LinkedIn"),
        # RemoteOK (good for remote tech jobs)
        (f"https://remoteok.com/remote-{q_plus}-jobs.rss", "RemoteOK"),
        # We Work Remotely
        (f"https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss", "WWR"),
        # Jobicy
        (f"https://jobicy.com/?feed=job_feed&job_categories=dev-engineer&job_types=full-time&search_keywords={q_plus}", "Jobicy"),
    ]
    return feeds

# ─── FEED PARSER ──────────────────────────────────────────────────────────────

def is_recent(entry, hours: int = 24) -> bool:
    try:
        for field in ["published", "updated", "created"]:
            val = getattr(entry, field, None)
            if val:
                pub = date_parser.parse(val)
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                return pub >= cutoff
    except Exception:
        pass
    return True  # include if date can't be determined

def fetch_jobs_from_feed(url: str, source: str, query: str) -> list[dict]:
    jobs = []
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            print(f"[WARN] No entries from {source} for '{query}': {url}")
            return []
        print(f"[INFO] {source} returned {len(feed.entries)} entries for '{query}'")
        for entry in feed.entries:
            if not is_recent(entry, HOURS_BACK):
                continue
            title = entry.get("title", "N/A")
            # Try multiple fields for company name
            company = (
                entry.get("author")
                or entry.get("dc_creator")
                or (entry.get("source") or {}).get("title")
                or "N/A"
            )
            jobs.append({
                "title":   title,
                "company": company,
                "link":    entry.get("link", ""),
                "date":    entry.get("published", entry.get("updated", "N/A")),
                "source":  source,
                "query":   query,
            })
    except Exception as e:
        print(f"[ERROR] Failed to fetch {source} ({url}): {e}")
    return jobs

# ─── FETCH ALL JOBS ───────────────────────────────────────────────────────────

def fetch_all_jobs() -> list[dict]:
    all_jobs  = []
    seen_links = set()

    for query in SEARCH_QUERIES:
        for url, source in get_feeds(query):
            jobs = fetch_jobs_from_feed(url, source, query)
            for job in jobs:
                if job["link"] and job["link"] not in seen_links:
                    seen_links.add(job["link"])
                    all_jobs.append(job)

    print(f"[INFO] Total unique recent jobs found: {len(all_jobs)}")
    return all_jobs

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────

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

# ─── FORMAT ───────────────────────────────────────────────────────────────────

def format_digest(jobs: list[dict]) -> str:
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    header = (
        f"🔔 <b>Job Alert Digest</b>\n"
        f"🕐 {now_ist.strftime('%d %b %Y, %I:%M %p')} IST\n"
        f"📋 <b>{len(jobs)} new job(s)</b> in last 24 hrs\n"
        f"{'─'*30}\n\n"
    )

    if not jobs:
        return (
            header
            + "😴 No new jobs found this time.\n"
            + "RSS feeds may be slow — check back in a few hours!"
        )

    grouped: dict[str, list] = {}
    for job in jobs:
        q = job["query"].title()
        grouped.setdefault(q, []).append(job)

    body = ""
    for role, role_jobs in grouped.items():
        body += f"<b>💼 {role}</b> ({len(role_jobs)} jobs)\n\n"
        for job in role_jobs[:8]:  # max 8 per role
            body += (
                f"  📌 <b>{job['title']}</b>\n"
                f"  🏢 {job['company']}\n"
                f"  🌐 {job['source']}\n"
                f"  🔗 <a href='{job['link']}'>Apply Here</a>\n\n"
            )

    return header + body

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"[INFO] Job scraper started at {datetime.now(timezone.utc).isoformat()}")
    jobs = fetch_all_jobs()
    digest = format_digest(jobs)
    for chunk in chunk_messages(digest):
        send_telegram(chunk)
    print("[INFO] Done!")

if __name__ == "__main__":
    main()
