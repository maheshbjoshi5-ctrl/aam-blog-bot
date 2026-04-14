import os, json, time, threading, hashlib, re
from datetime import datetime, timezone, timedelta
from flask import Flask, request as flask_request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN", "")
NETLIFY_SITE_ID = os.environ.get("NETLIFY_SITE_ID", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
TELEGRAM_CHANNEL = "@askacharyamahesh"
IST = timezone(timedelta(hours=5, minutes=30))
SUBSCRIBERS_FILE = "subscribers.json"
CATEGORIES = ["vastu", "jyotish", "numerology", "samkhya", "branding", "prakriti", "business", "wisdom"]
cat_index = 0
pending_article = None


@app.route("/")
def health():
    return {"status": "running", "bot": "AskAcharyaMahesh Blog", "time": datetime.now(IST).isoformat()}


def load_subscribers():
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_subscriber(sub):
    subs = load_subscribers()
    if any(s["email"] == sub["email"] for s in subs):
        return False
    subs.append(sub)
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(subs, f)
    return True


@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    data = flask_request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    source = data.get("source", "website")
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400
    sub = {"name": name, "email": email, "phone": phone, "source": source, "date": datetime.now(IST).isoformat()}
    added = save_subscriber(sub)
    if BREVO_API_KEY:
        try:
            requests.post("https://api.brevo.com/v3/contacts", headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"}, json={"email": email, "attributes": {"FIRSTNAME": name}, "listIds": [2], "updateEnabled": True}, timeout=10)
        except Exception:
            pass
    if ADMIN_CHAT_ID:
        send(int(ADMIN_CHAT_ID), "New Subscriber: " + name + " | " + email)
    return jsonify({"status": "subscribed" if added else "already_subscribed"})


def send_blog_email(title, slug, description):
    now = datetime.now(IST)
    if now.hour < 10 or now.hour >= 18:
        with open("pending_email.json", "w") as f:
            json.dump({"title": title, "slug": slug, "description": description}, f)
        return "queued_for_10am"
    if not BREVO_API_KEY:
        return "no_api_key"
    subs = load_subscribers()
    if not subs:
        return "no_subscribers"
    url = "https://www.askacharyamahesh.com/blog/" + slug + ".html"
    html_body = '<div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:32px"><h2 style="color:#3A2B1E">New from Acharya Mahesh</h2><h1 style="font-size:22px;color:#3A2B1E">' + title + '</h1><p style="color:#8C7B6C">' + description + '</p><a href="' + url + '" style="display:inline-block;padding:14px 32px;background:#BFA04A;color:#fff;border-radius:50px;text-decoration:none;font-weight:600">Read Article</a><p style="margin-top:24px;font-size:11px;color:#ccc">Acharya Mahesh Joshi | Vasturang Corp LLP</p></div>'
    to_list = [{"email": s["email"], "name": s.get("name", "")} for s in subs[:50]]
    try:
        requests.post("https://api.brevo.com/v3/smtp/email", headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"}, json={"sender": {"name": "Acharya Mahesh Joshi", "email": "a81ef6001@smtp-brevo.com"}, "to": to_list, "subject": "New: " + title, "htmlContent": html_body}, timeout=15)
        return "sent_to_" + str(len(to_list))
    except Exception as e:
        return "error"


def check_pending_emails():
    try:
        with open("pending_email.json", "r") as f:
            p = json.load(f)
        if 10 <= datetime.now(IST).hour < 18:
            send_blog_email(p["title"], p["slug"], p["description"])
            os.remove("pending_email.json")
    except Exception:
        pass


def tg(method, data=None):
    try:
        return requests.post("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/" + method, json=data, timeout=30).json()
    except Exception as e:
        print("[TG] " + str(e), flush=True)
        return {}


def send(chat_id, text):
    for i in range(0, len(text), 4000):
        tg("sendMessage", {"chat_id": chat_id, "text": text[i:i+4000], "parse_mode": "Markdown"})
        time.sleep(0.3)


def generate_article(topic, category):
    labels = {"vastu": "MahaVastu", "jyotish": "KP Jyotish", "numerology": "Numerology", "samkhya": "Samkhya Sutra", "branding": "Astro-Vastu Branding", "prakriti": "Prakriti", "business": "Business Vastu", "wisdom": "Vedic Wisdom"}
    prompt = 'Write 800-word blog as Acharya Mahesh Joshi (MahaVastu Acharya, KP Jyotish Scholar, Vasturang Corp LLP, Pune, guiding since 2013) on: "' + topic + '" (' + labels.get(category, "") + '). Warm authoritative tone. Practical examples. Reference VAP methodology. No AI mention. End with CTA for askacharyamahesh.com. Return ONLY JSON: {"title":"SEO title","slug":"url-slug","description":"150 char","keywords":["k1","k2","k3","k4","k5"],"body_html":"<h2>..</h2><p>..</p>"}'
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}, json={"model": "claude-sonnet-4-20250514", "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]}, timeout=60)
        text = r.json()["content"][0]["text"]
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        return json.loads(text)
    except Exception as e:
        print("[CLAUDE] " + str(e), flush=True)
        return None


def build_html(d, cat):
    labels = {"vastu": "MahaVastu", "jyotish": "KP Jyotish", "numerology": "Numerology", "samkhya": "Samkhya Sutra", "branding": "Branding", "prakriti": "Prakriti", "business": "Business Vastu", "wisdom": "Vedic Wisdom"}
    t, s, desc, b = d["title"], d["slug"], d["description"], d["body_html"]
    kw = ", ".join(d["keywords"])
    cl = labels.get(cat, cat)
    dt = datetime.now(IST).strftime("%B %Y")
    return '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>' + t + ' | Ask Acharya Mahesh Joshi</title><meta name="description" content="' + desc + '"><meta name="keywords" content="' + kw + '"><meta name="author" content="Acharya Mahesh Joshi"><link rel="canonical" href="https://www.askacharyamahesh.com/blog/' + s + '.html"><link rel="icon" type="image/svg+xml" href="../favicon.svg"><script type="application/ld+json">{"@context":"https://schema.org","@type":"Article","headline":"' + t + '","author":{"@type":"Person","name":"Acharya Mahesh Joshi"},"publisher":{"@type":"Organization","name":"Vasturang Corporation LLP"},"datePublished":"' + datetime.now(IST).strftime("%Y-%m-%d") + '"}</script><link href="https://fonts.googleapis.com/css2?family=Cormorant+Infant:ital,wght@0,400;0,700;1,400&family=Josefin+Sans:wght@300;400;600&display=swap" rel="stylesheet"><style>*{box-sizing:border-box;margin:0;padding:0}:root{--bg:#FFFEF9;--g:#BFA04A;--gd:rgba(191,160,74,.12);--e:#3A2B1E;--t:#42352A;--tl:#8C7B6C;--l:#FAF4E8;--fs:"Cormorant Infant",serif;--fb:"Josefin Sans",sans-serif}html{font-size:17px}body{font-family:var(--fb);color:var(--t);background:var(--bg);line-height:1.85}a{color:var(--g);text-decoration:none}.n{background:rgba(255,254,249,.92);backdrop-filter:blur(20px);border-bottom:1px solid rgba(191,160,74,.06);padding:0 24px;position:sticky;top:0;z-index:9}.ni{max-width:760px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;height:60px}.lo{font-family:var(--fs);font-weight:700;font-size:1.15rem;color:var(--e)}.lo i{color:var(--g)}.ar{max-width:760px;margin:0 auto;padding:48px 24px 80px}.cb{display:inline-block;font-size:.68rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:5px 14px;border-radius:100px;margin-bottom:16px;background:var(--gd);color:var(--g)}.ar h1{font-family:var(--fs);font-size:clamp(1.8rem,4vw,2.4rem);font-weight:700;color:var(--e);line-height:1.15;margin-bottom:12px}.me{font-size:.82rem;color:var(--tl);margin-bottom:32px}.ar h2{font-family:var(--fs);font-size:1.4rem;font-weight:700;color:var(--e);margin:36px 0 12px}.ar p{margin-bottom:16px;font-size:.95rem;font-weight:300}.ar ul{margin:0 0 16px 24px;font-size:.95rem;font-weight:300}.ar li{margin-bottom:8px}.ar strong{color:var(--e);font-weight:600}.hl{background:var(--gd);border-left:3px solid var(--g);padding:16px 20px;border-radius:0 12px 12px 0;margin:24px 0;font-size:.9rem}.ct{margin:40px 0;padding:28px;background:linear-gradient(135deg,var(--e),#5B4636);border-radius:16px;text-align:center;color:#fff}.ct h3{font-family:var(--fs);font-size:1.3rem;margin-bottom:8px}.ct p{font-size:.88rem;opacity:.7;margin-bottom:16px}.cl{display:inline-block;background:var(--g);color:#fff;padding:12px 28px;border-radius:100px;font-weight:600;font-size:.88rem}.ab{display:flex;gap:16px;align-items:center;padding:24px;background:var(--l);border-radius:14px;margin:40px 0}.av{width:56px;height:56px;border-radius:50%;background:linear-gradient(145deg,#BFA04A,#D4923A);display:flex;align-items:center;justify-content:center;color:#fff;font-size:1.2rem;font-weight:700;flex-shrink:0;font-family:var(--fs)}.ai h4{font-size:.95rem;font-weight:600;color:var(--e)}.ai p{font-size:.8rem;color:var(--tl);margin:0}.ft{background:var(--e);color:rgba(255,254,249,.5);text-align:center;padding:20px;font-size:.78rem;margin-top:48px}.ft a{color:rgba(255,254,249,.4);margin:0 6px}</style></head><body><nav class="n"><div class="ni"><a href="../index.html" class="lo">Ask <i>Acharya</i> Mahesh</a><a href="../blog.html" style="font-size:.85rem;color:var(--g)">All Articles</a></div></nav><article class="ar"><span class="cb">' + cl + '</span><h1>' + t + '</h1><div class="me">By Acharya Mahesh Joshi | ' + dt + '</div>' + b + '<div class="ct"><h3>Want Personalised Analysis?</h3><p>16/32 zone Shakti Chakra analysis</p><a href="../vastu-check.html" class="cl">Free Vastu Check</a></div><div class="ab"><div class="av">AM</div><div class="ai"><h4>Acharya Mahesh Joshi</h4><p>MahaVastu Acharya | KP Jyotish Scholar | Vasturang Corp LLP</p></div></div></article><footer class="ft"><a href="../index.html">Home</a><a href="../blog.html">Blog</a><a href="../contact.html">Contact</a><br>2025 Vasturang Corporation LLP</footer></body></html>'


def deploy(slug, html):
    try:
        fb = html.encode("utf-8")
        fh = hashlib.sha1(fb).hexdigest()
        fp = "blog/" + slug + ".html"
        r = requests.post("https://api.netlify.com/api/v1/sites/" + NETLIFY_SITE_ID + "/deploys", headers={"Authorization": "Bearer " + NETLIFY_TOKEN, "Content-Type": "application/json"}, json={"files": {"/" + fp: fh}}, timeout=15)
        did = r.json().get("id", "")
        if not did:
            return False, "No deploy ID"
        r = requests.put("https://api.netlify.com/api/v1/deploys/" + did + "/files/" + fp, headers={"Authorization": "Bearer " + NETLIFY_TOKEN, "Content-Type": "application/octet-stream"}, data=fb, timeout=30)
        if r.status_code in [200, 201]:
            return True, "https://www.askacharyamahesh.com/blog/" + slug + ".html"
        return False, "Status " + str(r.status_code)
    except Exception as e:
        return False, str(e)


def get_next_topic():
    global cat_index
    try:
        with open("topics.json", "r") as f:
            topics = json.load(f)
    except Exception:
        cat_index = (cat_index + 1) % len(CATEGORIES)
        return CATEGORIES[cat_index], "Vastu Tips for Modern Living"
    tc = CATEGORIES[cat_index % len(CATEGORIES)]
    for t in topics:
        if not t["used"] and t["category"] == tc:
            t["used"] = True
            with open("topics.json", "w") as f:
                json.dump(topics, f)
            cat_index = (cat_index + 1) % len(CATEGORIES)
            return t["category"], t["title"]
    cat_index = (cat_index + 1) % len(CATEGORIES)
    return tc, "Vedic Wisdom for Daily Life"


def handle_message(cid, text):
    global pending_article, ADMIN_CHAT_ID
    if not ADMIN_CHAT_ID:
        ADMIN_CHAT_ID = str(cid)
    text = text.strip()
    if text == "/start":
        send(cid, "AskAcharyaMahesh Blog Bot\n\n/generate - Auto topic\n/topic X - Custom topic\n/publish - Publish article\n/skip - Discard\n/status - Status\n\nOr type any topic!")
        return
    if text == "/status":
        send(cid, "Running | Rotation: " + CATEGORIES[cat_index % len(CATEGORIES)] + " | Pending: " + ("Yes" if pending_article else "No") + " | Subs: " + str(len(load_subscribers())))
        return
    if text == "/generate":
        send(cid, "Generating article...")
        cat, topic = get_next_topic()
        result = generate_article(topic, cat)
        if result:
            pending_article = {"data": result, "category": cat}
            bt = re.sub(r"<[^>]+>", "", result["body_html"])[:2000]
            send(cid, "Article Ready!\n\nTitle: " + result["title"] + "\nCategory: " + cat + "\n\n" + bt + "\n\n/publish or /skip")
        else:
            send(cid, "Generation failed. Try again.")
        return
    if text == "/publish":
        if not pending_article:
            send(cid, "No pending article. /generate first.")
            return
        send(cid, "Publishing...")
        slug = pending_article["data"]["slug"]
        html = build_html(pending_article["data"], pending_article["category"])
        ok, url = deploy(slug, html)
        if ok:
            send(cid, "Published! " + url)
            er = send_blog_email(pending_article["data"]["title"], slug, pending_article["data"]["description"])
            send(cid, "Email: " + er)
            tg("sendMessage", {"chat_id": TELEGRAM_CHANNEL, "text": "New Article\n\n" + pending_article["data"]["title"] + "\n\n" + pending_article["data"]["description"] + "\n\nRead: " + url + "\n\naskacharyamahesh.com", "parse_mode": "Markdown"})
            send(cid, "Posted to " + TELEGRAM_CHANNEL)
            pending_article = None
        else:
            send(cid, "Deploy failed: " + url)
        return
    if text == "/skip":
        pending_article = None
        send(cid, "Discarded. /generate for next.")
        return
    if text.startswith("/topic "):
        custom = text[7:].strip()
        if len(custom) < 3:
            send(cid, "Example: /topic Kitchen in NE zone")
            return
        send(cid, "Writing: " + custom + "...")
        cat = "vastu"
        lw = custom.lower()
        if any(w in lw for w in ["jyotish","planet","dasha","kundali","nakshatra"]):
            cat = "jyotish"
        elif any(w in lw for w in ["number","numerology","chaldean"]):
            cat = "numerology"
        elif any(w in lw for w in ["guna","tattva","samkhya"]):
            cat = "samkhya"
        elif any(w in lw for w in ["logo","brand","colour"]):
            cat = "branding"
        elif any(w in lw for w in ["vata","pitta","kapha"]):
            cat = "prakriti"
        elif any(w in lw for w in ["shop","office","factory"]):
            cat = "business"
        elif any(w in lw for w in ["panchang","muhurat","festival"]):
            cat = "wisdom"
        result = generate_article(custom, cat)
        if result:
            pending_article = {"data": result, "category": cat}
            send(cid, "Ready: " + result["title"] + "\n\n/publish or /skip")
        else:
            send(cid, "Failed. Try again.")
        return
    if len(text) > 3 and not text.startswith("/"):
        handle_message(cid, "/topic " + text)
        return
    send(cid, "/generate or type any topic")


def poll_telegram():
    print("[POLL] Token: " + TELEGRAM_TOKEN[:15] + "...", flush=True)
    offset = 0
    while True:
        try:
            r = requests.get("https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/getUpdates", params={"offset": offset, "timeout": 25}, timeout=30)
            resp = r.json()
            if not resp.get("ok"):
                print("[POLL ERR] " + str(resp), flush=True)
                time.sleep(5)
                continue
            for u in resp.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                cid = msg.get("chat", {}).get("id")
                txt = msg.get("text", "")
                if cid and txt:
                    print("[MSG] " + str(cid) + ": " + txt, flush=True)
                    try:
                        handle_message(cid, txt)
                    except Exception as e:
                        print("[ERR] " + str(e), flush=True)
        except Exception as e:
            print("[POLL ERR] " + str(e), flush=True)
            time.sleep(5)


def daily_cron():
    while True:
        now = datetime.now(IST)
        if 10 <= now.hour < 18 and now.minute == 0:
            check_pending_emails()
        if now.hour == 7 and now.minute == 0 and ADMIN_CHAT_ID:
            send(int(ADMIN_CHAT_ID), "Good morning! Generating article...")
            handle_message(int(ADMIN_CHAT_ID), "/generate")
            time.sleep(61)
        time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=poll_telegram, daemon=True).start()
    print("[BOT] Started", flush=True)
    threading.Thread(target=daily_cron, daemon=True).start()
    print("[CRON] Started", flush=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
