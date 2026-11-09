"""Daily lead research. Reads the files in /config, finds new leads, saves them to /leads."""
import csv, json, os, re, sys, datetime
from urllib.parse import urlparse
import requests, yaml
import anthropic

FIELDS = ["date_found", "company", "website", "industry", "country",
          "contact_name", "contact_role", "contact_email", "contact_phone",
          "qualification_reason", "evidence_url", "confidence", "notes"]


def root_domain(url):
    url = (url or "").strip().lower()
    if not url.startswith("http"):
        url = "https://" + url
    host = urlparse(url).netloc.replace("www.", "")
    return host


def read_text(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def read_domains(path):
    """Read a CSV and return the set of website domains / company names in it."""
    found = set()
    if not os.path.exists(path):
        return found
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for key in ("website", "domain", "company"):
                if row.get(key):
                    found.add(root_domain(row[key]) if key != "company" else row[key].strip().lower())
    return found


def site_is_live(url):
    try:
        r = requests.get("https://" + root_domain(url), timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        return r.status_code < 400
    except Exception:
        return False


def ask_claude(client, model, prompt):
    """Run one research round. Claude searches the web and returns JSON."""
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}]
    for _ in range(5):
        resp = client.messages.create(model=model, max_tokens=4000,
                                      tools=tools, messages=messages)
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    text = "".join(b.text for b in resp.content if b.type == "text")
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []


def main():
    cfg = yaml.safe_load(read_text("config/config.yaml"))
    n = int(cfg.get("leads_per_day", 10))
    out_dir = cfg.get("output_dir", "leads")
    max_rounds = int(cfg.get("max_rounds", 6))
    model = cfg.get("model", "claude-sonnet-5-5")
    os.makedirs(out_dir, exist_ok=True)

    icp = read_text("config/icp.md")
    examples = read_text("config/examples.csv")
    excluded = read_domains("config/excluded.csv")
    all_path = os.path.join(out_dir, "all_leads.csv")
    already = read_domains(all_path)
    skip = excluded | already

    client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY
    today = datetime.date.today().isoformat()
    accepted, stats = [], {"rejected_duplicate": 0, "rejected_site_down": 0,
                           "rejected_no_evidence": 0, "rounds": 0}

    for rnd in range(max_rounds):
        if len(accepted) >= n:
            break
        stats["rounds"] += 1
        need = n - len(accepted)
        skip_list = sorted(skip | {l["website"] for l in accepted})
        prompt = f"""You are a lead researcher. Find {need + 3} NEW companies that fit the ideal customer profile below.
Use web search. Only use public business information. NEVER invent contact details: leave a field "" if you did not find it.
Every lead MUST have an evidence_url showing why it qualifies.

IDEAL CUSTOMER PROFILE:
{icp}

EXAMPLES OF QUALIFIED LEADS (CSV):
{examples}

DO NOT return any of these companies/domains:
{', '.join(skip_list) or '(none)'}

Return ONLY a JSON array, no other text. Each item has these keys:
company, website, industry, country, contact_name, contact_role, contact_email, contact_phone,
qualification_reason (one sentence tied to the profile), evidence_url, confidence (high/medium/low), notes.
Try a different angle each round (round {rnd + 1}): different industries, regions, or trigger events."""
        for lead in ask_claude(client, model, prompt):
            dom = root_domain(lead.get("website", ""))
            if not dom or dom in skip or dom in {l["website"] for l in accepted}:
                stats["rejected_duplicate"] += 1
                continue
            if not lead.get("evidence_url"):
                stats["rejected_no_evidence"] += 1
                continue
            if not site_is_live(dom):
                stats["rejected_site_down"] += 1
                continue
            lead["website"] = dom
            lead["date_found"] = today
            accepted.append({k: str(lead.get(k, "") or "") for k in FIELDS})
            if len(accepted) >= n:
                break

    # Save today's file and add to the master list
    day_path = os.path.join(out_dir, f"{today}.csv")
    with open(day_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(accepted)
    new_file = not os.path.exists(all_path)
    with open(all_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerows(accepted)

    log = {"date": today, "wanted": n, "saved": len(accepted), **stats}
    if len(accepted) < n:
        log["shortfall"] = f"Only {len(accepted)} good leads found. Not padded."
    with open(os.path.join(out_dir, "run_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(log) + "\n")
    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    sys.exit(main())
