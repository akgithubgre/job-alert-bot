import requests
import os
from datetime import datetime, timezone, timedelta

# ─── CONFIG ───────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
JSEARCH_API_KEY    = os.environ["JSEARCH_API_KEY"]

# Entry level focused search queries
SEARCH_QUERIES = [
    "junior software engineer",
    "associate software engineer",
    "software engineer fresher",
    "SDE 1 software engineer",
    "entry level software developer",
    "junior backend developer",
    "associate data analyst",
    "junior data engineer",
    "graduate software engineer",
    "trainee software engineer",
]

# ─── FILTER: Block senior/experienced roles ────────────────────────────────────

BLOCKED_KEYWORDS = [
    "senior", "sr.", "sr ", "lead", "principal", "staff",
    "manager", "director", "head of", "architect", "vp ",
    "vice president", "distinguished", "fellow",
    "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
    "5 years", "6 years", "7 years", "8 years", "10 years",
    "15+ yrs", "8+ yrs", "10+ yrs",
]

ALLOWED_KEYWORDS = [
    "junior", "associate", "fresher", "graduate", "trainee",
    "entry", "sde 1", "sde1", "sde-1", "intern", "0-2", "0-1",
    "1-2", "1-3", "2 years", "2+ years", "1 year", "fresh",
]

def is_entry_level(title: str) -> bool:
    title_lower = title.lower()

    # Block if contains senior/lead/etc keywords
    for keyword in BLOCKED_KEYWORDS:
        if keyword in title_lower:
            return False

    return True

# ─── JSEARCH API ──────────────────────────────────────────────────────────────

def fetch_jobs_jsearch(query: str) -> list:
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
        "x-rapidapi-key":  JSEARCH_API_KEY,
    }
    params = {
        "query":            f"{query} in India",
        "page":             "1",
        "num_pages":        "1",
        "date_posted":      "3days",
        "country":          "in",
        "employment_types": "FULLTIME",
    }

    jobs = []
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        print(f"[INFO] JSearch '{query}' status: {resp.status_code}")
        if not resp.ok:
            print(f"[WARN] Bad response: {resp.text[:300]}")
            return []

        data = resp.json()
        results = data.get("data", [])
        print(f"[INFO] '{query}' returned {len(results)} raw jobs")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        for job in results:
            title = job.get("job_title", "N/A")

            # Skip senior/lead roles
            if not is_entry_level(title):
                print(f"[SKIP] '{title}' — not entry level")
                continue

            # Filter by last 24 hours
            posted_at = job.get("job_posted_at_timestamp")
            if posted_at:
                posted_dt = datetime.fromtimestamp(posted_at, tz=timezone.utc)
                if posted_dt < cutoff:
                    continue

            jobs.append({
                "title":    title,
                "company":  job.get("employer_name", "N/A"),
                "location": job.get("job_city") or job.get("job_state") or job.get("job_country", "N/A"),
                "link":     job.get("job_apply_link") or job.get("job_google_link", ""),
                "source":   job.get("job_publisher", "N/A"),
                "remote":   job.get("job_is_remote", False),
                "query":    query,
            })

        print(f"[INFO] '{query}' → {len(jobs)} entry-level jobs after filter")

    except Exception as e:
        print(f"[ERROR] JSearch failed for '{query}': {e}")

    return jobs

# ─── FETCH ALL ────────────────────────────────────────────────────────────────

def fetch_all_jobs() -> list:
    all_jobs   = []
    seen_links = set()

    for query in SEARCH_QUERIES:
        jobs = fetch_jobs_jsearch(query)
        for job in jobs:
            if job["link"] not in seen_links:
                seen_links.add(job["link"])
                all_jobs.append(job)

    print(f"[INFO] Total unique entry-level jobs: {len(all_jobs)}")
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

def chunk_messages(text: str, limit: int = 4000) -> list:
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

def format_digest(jobs: list) -> str:
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    header = (
        f"🔔 <b>Job Alert — Fresher/Entry Level</b>\n"
        f"🕐 {now_ist.strftime('%d %b %Y, %I:%M %p')} IST\n"
        f"📋 <b>{len(jobs)} job(s)</b> in last 24 hrs\n"
        f"🎯 SDE 1 · Associate · Junior · Graduate\n"
        f"{'─' * 30}\n\n"
    )

    if not jobs:
        return header + "😴 No new entry-level jobs found. Check back later!"

    # Group by clean category
    category_map = {
        "software engineer": "💻 Software Engineer",
        "software developer": "💻 Software Developer",
        "backend developer": "⚙️ Backend Developer",
        "data analyst": "📊 Data Analyst",
        "data engineer": "🛠️ Data Engineer",
    }

    grouped = {}
    for job in jobs:
        q = job["query"].lower()
        # map to a clean category
        category = "🔍 Other"
        for key, label in category_map.items():
            if key in q:
                category = label
                break
        grouped.setdefault(category, []).append(job)

    body = ""
    for role, role_jobs in grouped.items():
        body += f"<b>{role}</b> ({len(role_jobs)} jobs)\n\n"
        for job in role_jobs[:10]:
            remote_tag = " 🌍 Remote" if job["remote"] else f" 📍 {job['location']}"
            body += (
                f"  📌 <b>{job['title']}</b>\n"
                f"  🏢 {job['company']}{remote_tag}\n"
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
