"""
AskAcharyaMahesh Blog Bot
=========================
Telegram bot that auto-generates and publishes blog articles.
Deploy on Render as Web Service.

Features:
- Daily auto article at 7 AM IST
- On-demand via Telegram messages
- Claude API for article generation
- Netlify API for auto-deployment
- 8-category round-robin rotation
- Full SEO in every article
"""

import os, json, time, threading, hashlib, base64, re
from datetime import datetime, timezone, timedelta
from flask import Flask, request as flask_request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# ═══ CONFIG ═══
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
NETLIFY_TOKEN = os.environ.get("NETLIFY_TOKEN", "")
NETLIFY_SITE_ID = os.environ.get("NETLIFY_SITE_ID", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
IST = timezone(timedelta(hours=5, minutes=30))
SUBSCRIBERS_FILE = "subscribers.json"

# ═══ TOPIC ROTATION ═══
CATEGORIES = ["vastu","jyotish","numerology","samkhya","branding","prakriti","business","wisdom"]
cat_index = 0  # Current category pointer
topic_counter = 0

# Pending article awaiting approval
pending_article = None

# ═══ FLASK HEALTH ═══
@app.route("/")
def health():
    return {"status": "running", "bot": "AskAcharyaMahesh Blog", "time": datetime.now(IST).isoformat()}

# ═══ SUBSCRIBER MANAGEMENT ═══
def load_subscribers():
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            return json.load(f)
    except:
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
    sub = {
        "name": name, "email": email, "phone": phone,
        "source": source, "date": datetime.now(IST).isoformat()
    }
    added = save_subscriber(sub)
    # Also add to Brevo contacts
    if BREVO_API_KEY:
        try:
            requests.post("https://api.brevo.com/v3/contacts", headers={
                "api-key": BREVO_API_KEY, "Content-Type": "application/json"
            }, json={
                "email": email,
                "attributes": {"FIRSTNAME": name, "PHONE": phone, "SOURCE": source},
                "listIds": [2],
                "updateEnabled": True
            }, timeout=10)
        except:
            pass
    if ADMIN_CHAT_ID:
        send(int(ADMIN_CHAT_ID), f"\U0001f4e9 *New Subscriber!*\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nSource: {source}")
    return jsonify({"status": "subscribed" if added else "already_subscribed"})

@app.route("/api/subscribers", methods=["GET"])
def list_subscribers():
    subs = load_subscribers()
    return jsonify({"count": len(subs), "subscribers": subs})

# ═══ EMAIL NOTIFICATION VIA BREVO ═══
def send_blog_email(title, slug, description):
    """Send blog notification email to all subscribers. Only between 10 AM - 6 PM IST."""
    now = datetime.now(IST)
    if now.hour < 10 or now.hour >= 18:
        # Queue for next day 10 AM — store pending
        with open("pending_email.json", "w") as f:
            json.dump({"title": title, "slug": slug, "description": description}, f)
        return "queued_for_10am"
    
    if not BREVO_API_KEY:
        return "no_api_key"
    
    subs = load_subscribers()
    if not subs:
        return "no_subscribers"
    
    article_url = f"https://www.askacharyamahesh.com/blog/{slug}.html"
    
    html_email = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#FFFEF9;padding:32px">
    <div style="text-align:center;margin-bottom:24px">
    <h2 style="font-family:Georgia,serif;color:#3A2B1E;font-size:20px;margin:0">Ask <em style="color:#BFA04A">Acharya</em> Mahesh</h2>
    <p style="font-size:12px;color:#8C7B6C;margin:4px 0 0">Vedic Sciences Consultancy</p>
    </div>
    <div style="border-top:2px solid #BFA04A;padding-top:24px">
    <p style="font-size:12px;color:#BFA04A;font-weight:700;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px">NEW ARTICLE</p>
    <h1 style="font-family:Georgia,serif;font-size:22px;color:#3A2B1E;line-height:1.3;margin:0 0 12px">{title}</h1>
    <p style="font-size:14px;color:#8C7B6C;line-height:1.7;margin-bottom:24px">{description}</p>
    <a href="{article_url}" style="display:inline-block;padding:14px 32px;background:#BFA04A;color:#fff;border-radius:50px;text-decoration:none;font-weight:600;font-size:14px">Read Full Article</a>
    </div>
    <div style="margin-top:32px;padding-top:20px;border-top:1px solid #F3EBDA;text-align:center">
    <p style="font-size:12px;color:#B8A898;margin:0">Acharya Mahesh Joshi</p>
    <p style="font-size:11px;color:#B8A898;font-style:italic;margin:2px 0">Illuminating paths through Vedic Sciences since 2013</p>
    <p style="font-size:11px;color:#B8A898;margin:8px 0 0">
    <a href="https://www.askacharyamahesh.com" style="color:#BFA04A">askacharyamahesh.com</a> |
    <a href="https://www.vasturang.com" style="color:#BFA04A">vasturang.com</a> |
    <a href="https://wa.me/919552608856" style="color:#BFA04A">WhatsApp</a>
    </p>
    <p style="font-size:10px;color:#ccc;margin-top:16px">You received this because you opted in for Vedic tips & articles.<br>
    <a href="https://www.askacharyamahesh.com/contact.html" style="color:#B8A898">Unsubscribe</a></p>
    </div>
    </div>"""
    
    # Send via Brevo API
    to_list = [{"email": s["email"], "name": s.get("name", "")} for s in subs]
    
    try:
        r = requests.post("https://api.brevo.com/v3/smtp/email", headers={
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json"
        }, json={
            "sender": {"name": "Acharya Mahesh Joshi", "email": "a81ef6001@smtp-brevo.com"},
            "to": to_list[:50],
            "subject": f"New: {title}",
            "htmlContent": html_email,
            "tags": ["blog-notification"]
        }, timeout=15)
        return f"sent_to_{len(to_list)}"
    except Exception as e:
        return f"error: {str(e)}"

def check_pending_emails():
    """Check if there are queued emails to send (for time-restricted delivery)"""
    try:
        with open("pending_email.json", "r") as f:
            pending = json.load(f)
        now = datetime.now(IST)
        if 10 <= now.hour < 18 and pending:
            result = send_blog_email(pending["title"], pending["slug"], pending["description"])
            os.remove("pending_email.json")
            if ADMIN_CHAT_ID:
                send(int(ADMIN_CHAT_ID), f"\U0001f4e8 Queued email sent: {result}")
    except:
        pass

# ═══ TELEGRAM HELPERS ═══
def tg(method, data=None, files=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    try:
        r = requests.post(url, json=data, timeout=30) if not files else requests.post(url, data=data, files=files, timeout=30)
        return r.json()
    except Exception as e:
        print(f"[TG ERROR] {e}")
        return {}

def send(chat_id, text):
    # Telegram max message = 4096 chars, split if needed
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        tg("sendMessage", {"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"})
        time.sleep(0.3)

# ═══ CLAUDE API — ARTICLE GENERATION ═══
def generate_article(topic, category):
    cat_labels = {
        "vastu": "MahaVastu", "jyotish": "KP Jyotish", "numerology": "Ank Shastra / Numerology",
        "samkhya": "Samkhya Sutra", "branding": "Astro-Vastu Branding", "prakriti": "Prakriti & Ayurvedic Lifestyle",
        "business": "Business Vastu & Six Sigma", "wisdom": "Vedic Daily Wisdom & Festivals"
    }

    prompt = f"""You are writing a blog article as Acharya Mahesh Joshi, founder of Vasturang Corporation LLP, Pune. 
He is a MahaVastu Acharya, KP Jyotish Scholar, Samkhya Sutra Scholar, and Six Sigma Professional, guiding since 2013.

Write an 800-1000 word article on: "{topic}"
Category: {cat_labels.get(category, category)}

RULES:
- Write in first person as Acharya Mahesh Joshi
- Authoritative but warm, accessible tone
- Use practical examples and real-world applications
- Reference the Value Amplification Program (VAP) methodology where relevant
- Include specific technical details (zone names, element associations, planet connections)
- NO mention of AI anywhere
- End with a subtle CTA about booking consultation or trying free tools at askacharyamahesh.com

FORMAT YOUR RESPONSE AS JSON:
{{
  "title": "SEO optimized title with primary keyword",
  "slug": "url-friendly-slug-with-keywords",
  "description": "150 char meta description with keyword",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "body_html": "<h2>...</h2><p>...</p> (full article body in HTML with h2, h3, p, ul, li, strong, div class=highlight tags)"
}}

Return ONLY valid JSON. No markdown backticks."""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        data = r.json()
        text = data["content"][0]["text"]
        # Clean any markdown fences
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        return json.loads(text)
    except Exception as e:
        print(f"[CLAUDE ERROR] {e}")
        return None

# ═══ ARTICLE HTML BUILDER ═══
def build_article_html(article_data, category):
    cat_labels = {
        "vastu":"MahaVastu","jyotish":"KP Jyotish","numerology":"Numerology",
        "samkhya":"Samkhya Sutra","branding":"Astro-Vastu Branding","prakriti":"Prakriti & Lifestyle",
        "business":"Business Vastu","wisdom":"Vedic Wisdom"
    }
    title = article_data["title"]
    desc = article_data["description"]
    kw = ", ".join(article_data["keywords"])
    slug = article_data["slug"]
    body = article_data["body_html"]
    cat_label = cat_labels.get(category, category)
    today = datetime.now(IST).strftime("%B %Y")

    return f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} | Ask Acharya Mahesh Joshi</title>
<meta name="description" content="{desc}">
<meta name="keywords" content="{kw}">
<meta name="author" content="Acharya Mahesh Joshi">
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://www.askacharyamahesh.com/blog/{slug}.html">
<link rel="icon" type="image/svg+xml" href="../favicon.svg">
<meta property="og:type" content="article"><meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Article","headline":"{title}","author":{{"@type":"Person","name":"Acharya Mahesh Joshi"}},"publisher":{{"@type":"Organization","name":"Vasturang Corporation LLP"}},"datePublished":"{datetime.now(IST).strftime("%Y-%m-%d")}","description":"{desc}"}}
</script>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Infant:ital,wght@0,400;0,600;0,700;1,400&family=Josefin+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--ivory:#FFFEF9;--cream:#FDF8EF;--linen:#FAF4E8;--gold:#BFA04A;--gold-dim:rgba(191,160,74,0.12);--amber:#D4923A;--earth:#5B4636;--earth-deep:#3A2B1E;--ink:#42352A;--ink-light:#8C7B6C;--ink-faint:#B8A898;--font-serif:'Cormorant Infant',Georgia,serif;--font-sans:'Josefin Sans',system-ui,sans-serif}}
html{{font-size:17px}}body{{font-family:var(--font-sans);color:var(--ink);background:var(--ivory);line-height:1.85}}
a{{color:var(--gold);text-decoration:none}}
.nav{{background:rgba(255,254,249,0.92);backdrop-filter:blur(20px);border-bottom:1px solid rgba(191,160,74,0.06);padding:0 24px;position:sticky;top:0;z-index:100}}
.nav-inner{{max-width:760px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;height:60px}}
.logo{{font-family:var(--font-serif);font-weight:700;font-size:1.15rem;color:var(--earth-deep)}}.logo i{{color:var(--gold);font-style:italic}}
.article{{max-width:760px;margin:0 auto;padding:48px 24px 80px}}
.cat-badge{{display:inline-block;font-size:.68rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:5px 14px;border-radius:100px;margin-bottom:16px;background:var(--gold-dim);color:var(--gold)}}
.article h1{{font-family:var(--font-serif);font-size:clamp(1.8rem,4vw,2.4rem);font-weight:700;color:var(--earth-deep);line-height:1.15;margin-bottom:12px}}
.meta{{font-size:.82rem;color:var(--ink-faint);margin-bottom:32px}}
.article h2{{font-family:var(--font-serif);font-size:1.4rem;font-weight:700;color:var(--earth-deep);margin:36px 0 12px}}
.article h3{{font-size:1.05rem;font-weight:600;color:var(--earth);margin:28px 0 8px}}
.article p{{margin-bottom:16px;font-size:.95rem;font-weight:300}}
.article ul,.article ol{{margin:0 0 16px 24px;font-size:.95rem;font-weight:300}}.article li{{margin-bottom:8px}}
.article strong{{color:var(--earth-deep);font-weight:600}}
.highlight{{background:var(--gold-dim);border-left:3px solid var(--gold);padding:16px 20px;border-radius:0 12px 12px 0;margin:24px 0;font-size:.9rem}}
.cta-box{{margin:40px 0;padding:28px;background:linear-gradient(135deg,var(--earth-deep),var(--earth));border-radius:16px;text-align:center;color:#fff}}
.cta-box h3{{font-family:var(--font-serif);font-size:1.3rem;font-weight:700;margin-bottom:8px}}
.cta-box p{{font-size:.88rem;opacity:.7;margin-bottom:16px}}
.cta-link{{display:inline-flex;align-items:center;gap:8px;background:var(--gold);color:var(--ivory);padding:12px 28px;border-radius:100px;font-weight:600;font-size:.88rem}}.cta-link:hover{{color:var(--ivory)}}
.author-box{{display:flex;gap:16px;align-items:center;padding:24px;background:var(--linen);border-radius:14px;margin:40px 0}}
.author-av{{width:56px;height:56px;border-radius:50%;background:linear-gradient(145deg,var(--gold),var(--amber));display:flex;align-items:center;justify-content:center;font-family:var(--font-serif);color:#fff;font-size:1.2rem;font-weight:700;flex-shrink:0}}
.author-info h4{{font-size:.95rem;font-weight:600;color:var(--earth-deep)}}.author-info p{{font-size:.8rem;color:var(--ink-light);margin:0}}
.foot{{background:var(--earth-deep);color:rgba(255,254,249,0.5);text-align:center;padding:20px;font-size:.78rem;margin-top:48px}}.foot a{{color:rgba(255,254,249,0.4);margin:0 6px}}
</style></head><body>
<nav class="nav"><div class="nav-inner"><a href="../index.html" class="logo">Ask <i>Acharya</i> Mahesh</a><a href="../blog.html" style="font-size:.85rem;color:var(--gold)">\u2190 All Articles</a></div></nav>
<article class="article">
<span class="cat-badge">{cat_label}</span>
<h1>{title}</h1>
<div class="meta">By Acharya Mahesh Joshi \u00b7 {today} \u00b7 5 min read</div>
{body}
<div class="cta-box"><h3>Want Personalised Analysis?</h3><p>Get your property analysed with 16/32 zone Shakti Chakra, Devta mapping & remedies</p><a href="../vastu-check.html" class="cta-link">\u2605 Free Vastu Check</a></div>
<div class="author-box"><div class="author-av">AM</div><div class="author-info"><h4>Acharya Mahesh Joshi</h4><p>MahaVastu Acharya \u00b7 KP Jyotish Scholar \u00b7 Samkhya Sutra Scholar<br>Founder, Vasturang Corporation LLP \u00b7 Guiding since 2013</p></div></div>
</article>
<footer class="foot"><a href="../index.html">Home</a><a href="../vastu-check.html">Free Vastu Check</a><a href="../blog.html">Blog</a><a href="../contact.html">Contact</a><br>\u00a9 2025 Vasturang Corporation LLP</footer>
</body></html>'''

# ═══ NETLIFY DEPLOY ═══
def deploy_to_netlify(slug, html_content):
    """Deploy a single file to Netlify using file digest API"""
    try:
        file_path = f"blog/{slug}.html"
        file_bytes = html_content.encode('utf-8')
        file_hash = hashlib.sha1(file_bytes).hexdigest()

        # Get current deploy
        r = requests.get(
            f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}",
            headers={"Authorization": f"Bearer {NETLIFY_TOKEN}"},
            timeout=15
        )
        site = r.json()
        
        # Create new file deploy
        r = requests.post(
            f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/deploys",
            headers={
                "Authorization": f"Bearer {NETLIFY_TOKEN}",
                "Content-Type": "application/json"
            },
            json={"files": {f"/{file_path}": file_hash}},
            timeout=15
        )
        deploy = r.json()
        deploy_id = deploy.get("id", "")

        if not deploy_id:
            return False, "Deploy creation failed"

        # Upload the file
        r = requests.put(
            f"https://api.netlify.com/api/v1/deploys/{deploy_id}/files/{file_path}",
            headers={
                "Authorization": f"Bearer {NETLIFY_TOKEN}",
                "Content-Type": "application/octet-stream"
            },
            data=file_bytes,
            timeout=30
        )

        if r.status_code in [200, 201]:
            return True, f"https://www.askacharyamahesh.com/blog/{slug}.html"
        else:
            return False, f"Upload failed: {r.status_code}"

    except Exception as e:
        return False, str(e)

# ═══ NEXT TOPIC (ROUND ROBIN) ═══
def get_next_topic():
    global cat_index, topic_counter
    try:
        with open("topics.json", "r") as f:
            topics = json.load(f)
    except:
        return CATEGORIES[cat_index % len(CATEGORIES)], "Vastu Tips for Modern Living"

    # Find next unused topic
    for t in topics:
        if not t["used"] and t["category"] == CATEGORIES[cat_index % len(CATEGORIES)]:
            t["used"] = True
            with open("topics.json", "w") as f:
                json.dump(topics, f)
            cat_index = (cat_index + 1) % len(CATEGORIES)
            return t["category"], t["title"]

    # If current category exhausted, try next
    cat_index = (cat_index + 1) % len(CATEGORIES)
    topic_counter += 1
    if topic_counter > len(CATEGORIES):
        return "vastu", "Vastu Wisdom for Everyday Life"
    return get_next_topic()

# ═══ TELEGRAM BOT LOOP ═══
def handle_message(chat_id, text):
    global pending_article, ADMIN_CHAT_ID

    if not ADMIN_CHAT_ID:
        ADMIN_CHAT_ID = str(chat_id)
        os.environ["ADMIN_CHAT_ID"] = ADMIN_CHAT_ID

    text = text.strip()

    if text == "/start":
        send(chat_id, "\u2728 *AskAcharyaMahesh Blog Bot*\n\nCommands:\n\n/generate - Auto pick topic & write article\n/topic Kitchen in NE zone - Write on specific topic\n/publish - Publish pending article + email subscribers\n/skip - Discard pending article\n/status - Bot status & subscriber count\n\nOr just type any topic and I'll write an article!\n\nEmail notifications auto-send to subscribers between 10 AM - 6 PM IST only.")
        return

    if text == "/status":
        subs = load_subscribers()
        send(chat_id, f"\u2705 Bot running\nCategory rotation: {CATEGORIES[cat_index % len(CATEGORIES)]}\nPending article: {'Yes' if pending_article else 'No'}\nSubscribers: {len(subs)}")
        return

    if text == "/generate":
        send(chat_id, "\u23f3 Picking topic and generating article...")
        cat, topic = get_next_topic()
        result = generate_article(topic, cat)
        if result:
            pending_article = {"data": result, "category": cat}
            preview = f"\u2705 *Article Ready!*\n\n*Title:* {result['title']}\n*Category:* {cat}\n*Keywords:* {', '.join(result['keywords'][:4])}\n\n---\n\n"
            # Send body preview (strip HTML tags for Telegram)
            body_text = re.sub(r'<[^>]+>', '', result['body_html'])[:2000]
            preview += body_text + "\n\n---\n\n\u2705 Reply /publish to go live\n\u270f Reply /edit [changes] to modify\n\u274c Reply /skip to discard"
            send(chat_id, preview)
        else:
            send(chat_id, "\u274c Article generation failed. Try again.")
        return

    if text == "/publish":
        if not pending_article:
            send(chat_id, "\u274c No pending article. Use /generate first.")
            return
        send(chat_id, "\U0001f680 Publishing to askacharyamahesh.com...")
        slug = pending_article["data"]["slug"]
        html = build_article_html(pending_article["data"], pending_article["category"])
        success, url = deploy_to_netlify(slug, html)
        if success:
            send(chat_id, f"\U0001f389 *Published!*\n\n\U0001f517 {url}\n\nGoogle will index within 24-48 hours.")
            # Send email notification to subscribers
            email_result = send_blog_email(
                pending_article["data"]["title"],
                pending_article["data"]["slug"],
                pending_article["data"]["description"]
            )
            send(chat_id, f"\U0001f4e8 Email: {email_result}")
            pending_article = None
        else:
            send(chat_id, f"\u274c Deploy failed: {url}\n\nArticle saved. Try /publish again.")
        return

    if text == "/skip":
        pending_article = None
        send(chat_id, "\u274c Article discarded. Use /generate for next topic.")
        return

    if text.startswith("/topic "):
        custom_topic = text[7:].strip()
        if len(custom_topic) < 3:
            send(chat_id, "Please provide a topic. Example: /topic Kitchen in NE zone")
            return
        send(chat_id, f"\u23f3 Generating article on: *{custom_topic}*...")
        # Detect category from topic
        cat = "vastu"
        lower = custom_topic.lower()
        if any(w in lower for w in ["jyotish","planet","dasha","kundali","nakshatra","saturn","rahu","ketu","transit"]):
            cat = "jyotish"
        elif any(w in lower for w in ["number","numerology","name number","chaldean"]):
            cat = "numerology"
        elif any(w in lower for w in ["guna","tattva","samkhya","sattva","rajas","tamas","purusha","prakriti"]):
            cat = "samkhya"
        elif any(w in lower for w in ["logo","brand","colour","design","signboard"]):
            cat = "branding"
        elif any(w in lower for w in ["vata","pitta","kapha","dosha","ayurved"]):
            cat = "prakriti"
        elif any(w in lower for w in ["shop","office","factory","business","hotel","restaurant","cash counter"]):
            cat = "business"
        elif any(w in lower for w in ["panchang","muhurat","festival","mantra","yantra","tithi"]):
            cat = "wisdom"
        
        result = generate_article(custom_topic, cat)
        if result:
            pending_article = {"data": result, "category": cat}
            body_text = re.sub(r'<[^>]+>', '', result['body_html'])[:2000]
            preview = f"\u2705 *Article Ready!*\n\n*Title:* {result['title']}\n*Category:* {cat}\n\n---\n\n{body_text}\n\n---\n\n\u2705 /publish \u2014 Go live\n\u274c /skip \u2014 Discard"
            send(chat_id, preview)
        else:
            send(chat_id, "\u274c Generation failed. Try again.")
        return

    # Default: treat as topic
    if len(text) > 3 and not text.startswith("/"):
        handle_message(chat_id, f"/topic {text}")
        return

    send(chat_id, "Use /generate for auto topic or type any topic directly.\nExample: Kitchen in NE zone vastu")

def poll_telegram():
    """Long polling for Telegram updates"""
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35
            )
            updates = r.json().get("result", [])
            for u in updates:
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")
                if chat_id and text:
                    try:
                        handle_message(chat_id, text)
                    except Exception as e:
                        print(f"[HANDLER ERROR] {e}")
        except Exception as e:
            print(f"[POLL ERROR] {e}")
            time.sleep(5)

def daily_cron():
    """Daily article generation at 7 AM IST + pending email check"""
    while True:
        now = datetime.now(IST)
        # Check pending emails every hour between 10 AM - 6 PM
        if 10 <= now.hour < 18 and now.minute == 0:
            check_pending_emails()
        # Daily article at 7 AM
        if now.hour == 7 and now.minute == 0 and ADMIN_CHAT_ID:
            send(ADMIN_CHAT_ID, "\U0001f305 *Good morning Acharya!*\n\nGenerating today's article...")
            handle_message(int(ADMIN_CHAT_ID), "/generate")
            time.sleep(61)
        time.sleep(30)

# ═══ START ═══
if __name__ == "__main__":
    # Start Telegram polling in background
    t1 = threading.Thread(target=poll_telegram, daemon=True)
    t1.start()
    print("[BOT] Telegram polling started")

    # Start daily cron in background
    t2 = threading.Thread(target=daily_cron, daemon=True)
    t2.start()
    print("[CRON] Daily 7 AM IST scheduler started")

    # Run Flask (keeps Render alive)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
