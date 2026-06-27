"""
WhatsApp webhook server — Meta Cloud API.
- ngrok auto-starts on launch (one tunnel, port 5000)
- PDF report served via /report/<filename> on the same Flask app
- PDF link sent automatically in WhatsApp reply
- Supports BOTH keyword search AND full job-description paste
"""

import os
import re
import traceback
import requests
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

# ── Credentials ───────────────────────────────────────────────────────────────
WA_TOKEN     = os.getenv("WHATSAPP_TOKEN", "")
WA_PHONE_ID  = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WA_RECIPIENT = os.getenv("WHATSAPP_RECIPIENT_ID", "")
VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "resume_bot_secret")
DRIVE_FOLDER = os.getenv("GDRIVE_FOLDER_ID", "")
NGROK_TOKEN  = os.getenv("NGROK_AUTHTOKEN", "")

META_API_URL  = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
FLASK_PORT    = 5000
TOP_N         = 5
REPORTS_DIR   = "output/reports"

PUBLIC_BASE: str = ""

app = Flask(__name__)
Path(REPORTS_DIR).mkdir(parents=True, exist_ok=True)


# ── PDF file server ───────────────────────────────────────────────────────────

@app.route("/report/<path:filename>")
def serve_report(filename):
    return send_from_directory(
        os.path.abspath(REPORTS_DIR),
        filename,
        mimetype="application/pdf"
    )


# ── ngrok auto-start ──────────────────────────────────────────────────────────

def start_ngrok():
    global PUBLIC_BASE
    try:
        from pyngrok import ngrok, conf

        if NGROK_TOKEN:
            conf.get_default().auth_token = NGROK_TOKEN

        for t in ngrok.get_tunnels():
            ngrok.disconnect(t.public_url)

        tunnel      = ngrok.connect(FLASK_PORT, "http", bind_tls=True)
        PUBLIC_BASE = tunnel.public_url

        print("\n" + "=" * 58)
        print("  ✅ ngrok tunnel LIVE")
        print(f"  Webhook URL : {PUBLIC_BASE}/webhook")
        print(f"  PDF base    : {PUBLIC_BASE}/report/<file>")
        print("=" * 58)
        print("\n  👉 Paste into Meta → WhatsApp → Webhooks:")
        print(f"     Callback URL : {PUBLIC_BASE}/webhook")
        print(f"     Verify token : {VERIFY_TOKEN}")
        print("=" * 58 + "\n")

    except Exception as e:
        print(f"\n  ⚠ ngrok failed: {e}")
        print("  Set NGROK_AUTHTOKEN in .env and try again.\n")


# ── Webhook: verification GET ─────────────────────────────────────────────────

@app.route("/webhook", methods=["GET"])
def verify():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    print(f"  [verify] mode={mode} token={token}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("  [verify] ✅ Passed!")
        return challenge, 200

    print(f"  [verify] ❌ Expected '{VERIFY_TOKEN}', got '{token}'")
    return "Forbidden", 403


# ── Webhook: inbound messages POST ───────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        payload      = request.get_json(force=True) or {}
        sender, text = _parse_meta_payload(payload)

        if not text:
            return jsonify({"status": "ignored"}), 200

        reply_to = sender or WA_RECIPIENT
        print(f"\n  [msg] From {reply_to}: {text[:80]}")

        if not _is_job_query(text):
            _send_text(
                reply_to,
                "👋 Hi! Send me:\n"
                "• A *role* — e.g. _ML Engineer_ or _Civil Engineer 3+ years_\n"
                "• A *full job description* — paste it and I'll find the best fits 🎯"
            )
            return jsonify({"status": "prompted"}), 200

        # ── Route: JD or keyword ──────────────────────────────────────────────
        from matcher       import rank_candidates
        from pdf_generator import generate_report

        _send_text(reply_to, "⏳ Searching candidates… please wait.")

        if _is_full_jd(text):
            candidates, search_label, jd_header = _search_by_jd(text, rank_candidates)
        else:
            candidates, search_label, jd_header = _search_by_keyword(text, rank_candidates)

        if not candidates:
            _send_text(
                reply_to,
                "⚠️ No candidates found.\n\n"
                + (jd_header + "\n\n" if jd_header else "")
                + "• Try a different role or relax experience requirements\n"
                + "• Run *main.py* first to import resumes from Google Drive"
            )
            return jsonify({"status": "no_candidates"}), 200

        pdf_abs_path = generate_report(candidates, search_label)
        pdf_filename = Path(pdf_abs_path).name
        pdf_url      = f"{PUBLIC_BASE}/report/{pdf_filename}"

        print(f"  [pdf] {pdf_filename}")
        print(f"  [pdf] {pdf_url}")

        reply = _build_reply(
            candidates,
            pdf_url,
            search_label,
            jd_header=jd_header,
            show_contact=_is_full_jd(text),   # reveal email/phone for JD searches
        )
        _send_text(reply_to, reply)
        print(f"  [msg] ✅ Reply sent to {reply_to}")

        return jsonify({"status": "ok", "candidates": len(candidates)}), 200

    except Exception:
        traceback.print_exc()
        return jsonify({"status": "error"}), 500


# ── Search strategies ─────────────────────────────────────────────────────────

def _search_by_keyword(
    text: str,
    rank_fn,
) -> tuple[list[dict], str, str]:
    """
    Short keyword / role search.
    e.g. "find ml engineer", "civil engineer 3+ years"
    Returns (candidates, label, header_block)
    """
    min_exp = _parse_min_experience(text)
    candidates = rank_fn(text, min_experience=min_exp)

    label  = text[:60] + ("…" if len(text) > 60 else "")
    header = ""   # no extra header for keyword searches
    return candidates, label, header


def _search_by_jd(
    text: str,
    rank_fn,
) -> tuple[list[dict], str, str]:
    """
    Full job-description search.
    Parses role + skills + experience from JD, then runs enriched query.
    Returns (candidates, label, header_block)
    """
    parsed = _parse_jd(text)

    role_display = parsed["role_raw"] or parsed["role"] or "the role"
    skills       = parsed["skills"]
    min_exp      = parsed["min_experience"]

    # Enriched query: canonical role name + key skills found in JD
    query_parts = [parsed["role"] or text[:80]]
    if skills:
        query_parts.append(" ".join(skills[:6]))
    enriched = " ".join(query_parts)

    candidates = rank_fn(enriched, min_experience=min_exp)

    label = role_display.title()

    # Build a JD-analysis header to show the user what was understood
    header_lines = [
        "📋 *JD Understood As:*",
        f"🎯 Role   : _{role_display.title()}_",
    ]
    if skills:
        header_lines.append(
            f"🛠 Skills  : _{', '.join(s.title() for s in skills[:6])}_"
        )
    if min_exp is not None:
        header_lines.append(f"📅 Min exp : _{min_exp}+ years_")
    header_lines.append("─" * 25)
    header = "\n".join(header_lines)

    return candidates, label, header


# ── Reply builder ─────────────────────────────────────────────────────────────

def _build_reply(
    candidates: list[dict],
    pdf_url: str,
    search_label: str,
    jd_header: str = "",
    show_contact: bool = False,
) -> str:
    lines = []

    if jd_header:
        lines.append(jd_header)
        lines.append("")

    lines.append(f"✅ *Top {len(candidates)} candidates for:* _{search_label}_")
    lines.append("")

    for i, c in enumerate(candidates, 1):
        skills_raw = c.get("skills", "") or ""
        # Skills can be semicolon or comma separated
        skill_parts = re.split(r"[;,]", skills_raw)
        top_skills  = ", ".join(s.strip().title() for s in skill_parts[:4] if s.strip())

        exp     = c.get("experience_years", "") or ""
        reasons = c.get("match_reasons", []) or []
        score   = c.get("score", 0)
        role    = c.get("job_role") or "—"
        name    = (c.get("name") or "Unknown").upper()

        # Score badge
        if score >= 70:   badge = "🥇"
        elif score >= 50: badge = "🥈"
        elif score >= 30: badge = "🥉"
        else:             badge = "👤"

        exp_str = f"  ·  {exp} yrs" if exp else ""

        block = (
            f"{badge} *{i}. {name}*  — {score:.0f}% match\n"
            f"   📌 {role}{exp_str}\n"
            f"   🛠 {top_skills or '—'}\n"
        )

        # Contact info (only for JD searches)
        if show_contact:
            email = c.get("email") or "—"
            phone = c.get("phone") or ""
            block += f"   📧 {email}\n"
            if phone:
                block += f"   📱 {phone}\n"

        # Top match reason
        if reasons:
            block += f"   ✅ _{reasons[0]}_\n"

        lines.append(block)

    lines += [
        "─────────────────────",
        "📄 *Full candidate report (PDF):*",
        pdf_url,
        "",
        "_Send another role or job description to search again._",
    ]
    return "\n".join(lines)


# ── JD parser (self-contained, no extra module needed) ────────────────────────

# Canonical role aliases — keep in sync with matcher.py
_ROLE_ALIASES: dict[str, list[str]] = {
    "ml engineer":           ["machine learning engineer", "ml engineer", "ai engineer",
                               "deep learning engineer", "nlp engineer", "ml developer"],
    "data scientist":        ["data scientist", "data science", "research scientist"],
    "data engineer":         ["data engineer", "big data", "etl engineer"],
    "data analyst":          ["data analyst", "business analyst", "bi analyst"],
    "software engineer":     ["software engineer", "software developer", "sde", "swe",
                               "backend engineer", "backend developer",
                               "full stack", "fullstack"],
    "frontend engineer":     ["frontend engineer", "frontend developer", "ui engineer",
                               "react developer", "angular developer"],
    "devops engineer":       ["devops", "site reliability engineer", "sre",
                               "cloud engineer", "infrastructure engineer"],
    "civil engineer":        ["civil engineer", "structural engineer",
                               "construction engineer", "geotechnical engineer"],
    "mechanical engineer":   ["mechanical engineer", "manufacturing engineer",
                               "production engineer", "hvac engineer"],
    "electrical engineer":   ["electrical engineer", "electronics engineer",
                               "power engineer", "embedded engineer"],
    "qa engineer":           ["qa engineer", "quality assurance", "test engineer",
                               "sdet", "automation engineer"],
    "product manager":       ["product manager", "product owner"],
    "project manager":       ["project manager", "program manager"],
    "android developer":     ["android developer", "android engineer"],
    "ios developer":         ["ios developer", "swift developer"],
    "network engineer":      ["network engineer", "network administrator"],
    "chemical engineer":     ["chemical engineer", "process engineer"],
    "environmental engineer":["environmental engineer", "environmental scientist"],
}

_SKILLS_DB = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
    "html", "css", "react", "angular", "vue", "node.js", "django", "flask",
    "fastapi", "spring", "express", "next.js",
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "keras", "scikit-learn", "pandas", "numpy",
    "opencv", "huggingface", "llm", "langchain", "rag",
    "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    "sqlite", "oracle", "cassandra",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins",
    "git", "github", "gitlab", "linux", "bash",
    "rest api", "graphql", "microservices", "agile", "scrum", "jira",
    "tableau", "power bi", "excel", "spark", "hadoop", "kafka",
    "autocad", "staad pro", "revit", "ansys", "solidworks", "catia",
}


def _parse_jd(text: str) -> dict:
    t = text.lower()
    return {
        "role":           _jd_canonical_role(t),
        "role_raw":       _jd_raw_role(t),
        "skills":         _jd_skills(t),
        "min_experience": _parse_min_experience(text),
    }


def _jd_canonical_role(t: str) -> str | None:
    for canon, aliases in _ROLE_ALIASES.items():
        for alias in aliases:
            if alias in t:
                return canon
    return None


def _jd_raw_role(t: str) -> str | None:
    patterns = [
        r"(?:position|role|title|hiring for|looking for|seeking)[:\s]+([^\n,\.]{5,60})",
        r"(?:job\s+(?:title|description|role))[:\s]+([^\n,\.]{5,60})",
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            if len(raw.split()) <= 8:
                return raw.title()
    # First line often is the title
    first_line = t.strip().splitlines()[0].strip() if t.strip() else ""
    if first_line and len(first_line.split()) <= 6:
        return first_line.title()
    return None


def _jd_skills(t: str) -> list[str]:
    return sorted(skill for skill in _SKILLS_DB if skill in t)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _is_full_jd(text: str) -> bool:
    """True when the message looks like a pasted job description."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) >= 3:
        return True
    if len(text.strip()) > 150:
        return True
    jd_signals = [
        "responsibilities", "requirements", "qualifications",
        "we are looking", "looking for a", "must have", "nice to have",
        "preferred", "job description", "about the role", "you will",
        "candidate should", "key skills", "experience required",
    ]
    tl = text.lower()
    return sum(1 for s in jd_signals if s in tl) >= 2


def _is_job_query(text: str) -> bool:
    t = text.lower().strip()
    if len(t) > 40:
        return True
    triggers = [
        "developer", "engineer", "analyst", "designer", "manager",
        "intern", "scientist", "architect", "consultant", "lead",
        "find", "search", "top", "best", "hire", "candidate", "role",
        "python", "java", "react", "node", "data", "ml", "ai", "backend",
        "frontend", "fullstack", "devops", "cloud", "flutter", "android",
        "civil", "mechanical", "electrical", "chemical",
    ]
    return any(kw in t for kw in triggers)


def _parse_min_experience(text: str) -> float | None:
    patterns = [
        r"(?:at\s+least|minimum|min\.?|atleast)\s+(\d+\.?\d*)\s*(?:years?|yrs?)",
        r"(\d+\.?\d*)\+\s*(?:years?|yrs?)\s*(?:of\s+)?exp",
        r"(\d+\.?\d*)\s*\+\s*(?:years?|yrs?)",
        r"(?:more\s+than|over|above)\s+(\d+\.?\d*)\s*(?:years?|yrs?)",
        r"(\d+\.?\d*)\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
        r"(\d+)\s*-\s*\d+\s*(?:years?|yrs?)",           # "3-5 years" → take lower bound
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


# ── Meta API helpers ──────────────────────────────────────────────────────────

def _send_text(to: str, message: str):
    if not WA_TOKEN or not WA_PHONE_ID:
        print(f"\n[DRY-RUN → {to}]\n{message}\n{'─'*50}")
        return

    resp = requests.post(
        META_API_URL,
        headers={"Authorization": f"Bearer {WA_TOKEN}",
                 "Content-Type":  "application/json"},
        json={
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to,
            "type":              "text",
            "text":              {"preview_url": True, "body": message},
        },
        timeout=10,
    )
    if resp.ok:
        print(f"  [Meta] ✅ Sent to {to}")
    else:
        print(f"  [Meta] ❌ {resp.status_code}: {resp.text}")


def _parse_meta_payload(payload: dict) -> tuple[str, str]:
    try:
        msgs = (payload
                .get("entry",   [{}])[0]
                .get("changes", [{}])[0]
                .get("value",   {})
                .get("messages", []))
        if not msgs or msgs[0].get("type") != "text":
            return "", ""
        return msgs[0].get("from", ""), msgs[0]["text"].get("body", "").strip()
    except Exception:
        return "", ""


# ── Optional Drive sync ───────────────────────────────────────────────────────

def _maybe_sync_drive():
    if not DRIVE_FOLDER:
        return
    try:
        from modules.drive_client   import DriveClient
        from modules.pdf_extractor  import extract_text as extract_pdf
        from modules.docx_extractor import extract_text_from_docx
        from modules.extractor      import extract_candidate_info
        from modules.storage        import CandidateStore
        from modules.processing_log import ProcessingLog

        print("  [drive] Syncing resumes…")
        client = DriveClient()
        store  = CandidateStore("output/candidates.csv")
        log    = ProcessingLog("output/processed_files.csv")
        new    = 0

        for f in client.list_resume_files(DRIVE_FOLDER):
            if log.is_processed(f["id"]):
                continue
            try:
                raw  = client.download_file(f["id"])
                text = (extract_pdf(raw) if f["file_type"] == "pdf"
                        else extract_text_from_docx(raw, f["name"]))
                info = extract_candidate_info(text, f["name"])
                info.update({"file_type": f["file_type"],
                             "file_id":   f["id"],
                             "filename":  f["name"]})
                store.save(info)
                log.mark(f["id"], f["name"], "processed")
                new += 1
            except Exception as e:
                print(f"    ✗ {f['name']}: {e}")
                log.mark(f["id"], f["name"], "error")

        print(f"  [drive] {new} new resume(s) synced.")
    except Exception as e:
        print(f"  [drive] Skipped ({e}). Run main.py manually first.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== WhatsApp Resume Bot (Meta Cloud API) ===")
    print(f"  Phone ID  : {WA_PHONE_ID  or '⚠ NOT SET'}")
    print(f"  Token     : {'✓ set' if WA_TOKEN else '⚠ NOT SET'}")
    print(f"  Reply to  : {WA_RECIPIENT or '(from inbound msg)'}")
    print(f"  Drive     : {DRIVE_FOLDER or '⚠ NOT SET'}")

    _maybe_sync_drive()
    start_ngrok()
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)