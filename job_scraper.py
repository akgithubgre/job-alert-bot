import requests
import os
from datetime import datetime, timezone, timedelta

# ─── CONFIG ───────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
JSEARCH_API_KEY    = os.environ["JSEARCH_API_KEY"]

SEARCH_QUERIES = [
    "software engineer",
    "software developer",
    "backend developer",
    "data analyst",
    "data engineer",
]

# ─── JSEARCH API ──────────────────────────────────────────────────────────────

def fetch_jobs_jsearch(query: str) -> list[dict]:
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
        "x-rapidapi-key":  JSEARCH_API_KEY,
    }
    params = {
        "query":        f"{query} in India",
        "page":         "1",
        "num_pages":    "1",
        "date_posted":  "today",  # only today's jobs
        "country":      "in",
    }

    jobs = []
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        for job in data.get("data", []):
            jobs.append({
                "title":   job.get("job_title", "N/A"),
                "company": job.get("employer_name", "N/A"),
                "location": job.get("job_city") or job.get("job_country") or "N/A",
                "link":    job.get("job_apply_link") or job.get("job_google_link", ""),
                "source":  job.get("job_publisher", "N/A"),
                "posted":  job.get("job_posted_at_datetime_utc", ""),
                "remote":  job.get("job_is_remote", False),
                "query":   query,
            })
        print(f"[INFO] JSearch returned {len(jobs)} jobs for '{query}'")
    except Exception as e:
        print(f"[ERROR] JSearch failed for '{query}': {e}")

    return jobs

# ─── FETCH ALL ────────────────────────────────────────────────────────────────

def fetch_all_jobs() -> list[dict]:
    all_jobs   = []
    seen_links = set()

    for query in SEARCH_QUERIES:
        jobs = fetch_jobs_jsearch(query)
        for job in jobs:
            if job["link"] not in seen_links:
                seen_links.add(job["link"])
                all_jobs.append(job)

    print(f"[INFO] Total unique jobs: {len(all_jobs)}")
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
        print(f"[ERROR] Telegram failed: {resp.text}")

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
        f"📋 <b>{len(jobs)} new job(s)</b> found today\n"
        f"{'─'*30}\n\n"
    )

    if not jobs:
        return header + "😴 No new jobs found right now. Check back later!"

    # Group by role
    grouped: dict[str, list] = {}
    for job in jobs:
        q = job["query"].title()
        grouped.setdefault(q, []).append(job)

    body = ""
    for role, role_jobs in grouped.items():
        body += f"<b>💼 {role}</b> ({len(role_jobs)} jobs)\n\n"
        for job in role_jobs[:8]:
            remote_tag = "🌍 Remote" if job["remote"] else f"📍 {job['location']}"
            body += (
                f"  📌 <b>{job['title']}</b>\n"
                f"  🏢 {job['company']}\n"
                f"  {remote_tag}\n"
                f"  🌐 via {job['source']}\n"
                f"  🔗 <a href='{job['link']}'>Apply Here</a>\n\n"
            )

    return header + body

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"[INFO] Started at {datetime.now(timezone.utc).isoformat()}")
    jobs   = fetch_all_jobs()
    digest = format_digest(jobs)
    for chunk in chunk_messages(digest):
        send_telegram(chunk)
    print("[INFO] Done!")

if __name__ == "__main__":
    main()
