"""
WhatsApp webhook server — Meta Cloud API.
- ngrok auto-starts on launch (one tunnel, port 5000)
- PDF report served via /report/<filename> on the same Flask app
- PDF link sent automatically in WhatsApp reply
"""

import os
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

# Shared ngrok public base URL (e.g. https://xxxx.ngrok-free.dev)
PUBLIC_BASE: str = ""

app = Flask(__name__)
Path(REPORTS_DIR).mkdir(parents=True, exist_ok=True)


# ── PDF file server route ─────────────────────────────────────────────────────

@app.route("/report/<path:filename>")
def serve_report(filename):
    """Serve generated PDF files publicly via ngrok."""
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

        # Kill any leftover tunnels
        for t in ngrok.get_tunnels():
            ngrok.disconnect(t.public_url)

        tunnel     = ngrok.connect(FLASK_PORT, "http", bind_tls=True)
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
            _send_text(reply_to,
                "👋 Hi! Send me a *job role* (e.g. _Python Developer_) "
                "or paste a full *job description* to find matching candidates.")
            return jsonify({"status": "prompted"}), 200

        # ── Pipeline ──────────────────────────────────────────────────────────
        from matcher       import rank_candidates
        from pdf_generator import generate_report

        _send_text(reply_to, "⏳ Searching candidates… please wait.")

        candidates = rank_candidates(text, top_n=TOP_N)
        if not candidates:
            _send_text(reply_to,
                "⚠️ No candidates found. Run *main.py* first to import resumes from Google Drive.")
            return jsonify({"status": "no_candidates"}), 200

        # Generate PDF → get filename → build public URL
        pdf_abs_path = generate_report(candidates, text)
        pdf_filename = Path(pdf_abs_path).name
        pdf_url      = f"{PUBLIC_BASE}/report/{pdf_filename}"

        print(f"  [pdf] Generated: {pdf_filename}")
        print(f"  [pdf] Public URL: {pdf_url}")

        reply = _build_reply(candidates, pdf_url, text)
        _send_text(reply_to, reply)
        print(f"  [msg] ✅ Reply sent to {reply_to}")

        return jsonify({"status": "ok", "candidates": len(candidates)}), 200

    except Exception:
        traceback.print_exc()
        return jsonify({"status": "error"}), 500


# ── Meta API: send text ───────────────────────────────────────────────────────

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


# ── Parse Meta webhook payload ────────────────────────────────────────────────

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


# ── Reply message ─────────────────────────────────────────────────────────────

def _build_reply(candidates: list[dict], pdf_url: str, query: str) -> str:
    preview = query[:60] + ("…" if len(query) > 60 else "")
    lines   = [f"✅ *Top {len(candidates)} candidates for:* _{preview}_", ""]

    for i, c in enumerate(candidates, 1):
        skills_raw = c.get("skills", "") or ""
        top_skills = ", ".join(s.strip() for s in skills_raw.split(",")[:4] if s.strip())
        exp        = c.get("experience_years", "")
        reasons    = c.get("match_reasons", [])

        block = (
            f"*{i}. {c.get('name') or 'Unknown'}*  — {c.get('score', 0):.0f}% match\n"
            f"   📌 {c.get('job_role') or '—'}" + (f"  ·  {exp} yrs" if exp else "") + "\n"
            f"   🛠 {top_skills or '—'}\n"
        )
        if reasons:
            block += f"   _{reasons[0]}_\n"
        lines.append(block)

    lines += [
        "─────────────────────",
        "📄 *Full candidate report (PDF):*",
        pdf_url,
        "",
        "_Send another role or job description to search again._",
    ]
    return "\n".join(lines)


# ── Job query detector ────────────────────────────────────────────────────────

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
    ]
    return any(kw in t for kw in triggers)


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


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== WhatsApp Resume Bot (Meta Cloud API) ===")
    print(f"  Phone ID  : {WA_PHONE_ID  or '⚠ NOT SET'}")
    print(f"  Token     : {'✓ set' if WA_TOKEN else '⚠ NOT SET'}")
    print(f"  Reply to  : {WA_RECIPIENT or '(from inbound msg)'}")
    print(f"  Drive     : {DRIVE_FOLDER or '⚠ NOT SET'}")

    _maybe_sync_drive()  # sync any new resumes from Drive
    start_ngrok()        # start tunnel → prints URL to paste in Meta
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)