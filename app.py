import os
import re
import json
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from pypdf import PdfReader
from ai_engine import AIResumeAnalyzer
from pdf_service import generate_ats_report_pdf

app = Flask(__name__)
app.secret_key = "skillboost-ats-ram-bandaru-production-key-2026"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "database.db")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ----------------- DATABASE CONFIG & SETUP -----------------
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=25)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Users table (Each new user gets 1 free scan credit)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            free_credits INTEGER DEFAULT 1,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. Resumes & Scans table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT NOT NULL,
            candidate_name TEXT,
            email TEXT,
            phone TEXT,
            score INTEGER DEFAULT 0,
            skills_found TEXT,
            missing_skills TEXT,
            action_verbs TEXT,
            sections_found TEXT,
            resume_text TEXT,
            mistakes_json TEXT,
            breakdown_json TEXT,
            is_free INTEGER DEFAULT 1,
            txn_id TEXT,
            payment_status TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    # 3. Founder / B2B website leads table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS website_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            project_type TEXT,
            budget TEXT,
            description TEXT,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 4. Settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Safe migrations
    for col, col_type in [
        ("resume_text", "TEXT"),
        ("job_description", "TEXT"),
        ("mistakes_json", "TEXT"),
        ("breakdown_json", "TEXT"),
        ("is_free", "INTEGER DEFAULT 1"),
        ("payment_status", "TEXT DEFAULT 'free'")
    ]:
        try:
            cursor.execute(f"ALTER TABLE scans ADD COLUMN {col} {col_type};")
        except Exception:
            pass

    # User table migrations — subscription system
    for col, col_type in [
        ("subscription_expires", "TEXT"),
        ("subscription_plan", "TEXT DEFAULT 'free'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type};")
        except Exception:
            pass

    # Seed default system settings
    defaults = {
        "price_inr": "149",
        "upi_id": "8688726584@upi",
        "admin_user": "ram",
        "admin_pass": "RamAdmin2026!",
        "owner_email": "ramudubandaru987@gmail.com"
    }
    for k, v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

init_db()

def get_setting(key, default=""):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

# ----------------- ADVANCED ATS ANALYSIS & MISTAKES ENGINE -----------------
CORE_TECH_KEYWORDS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "react", "react.js", 
    "node.js", "express", "sql", "mysql", "postgresql", "mongodb", "oracle sql",
    "selenium", "pytest", "playwright", "behave", "bdd", "cucumber", "testng",
    "manual testing", "automation testing", "regression testing", "api testing",
    "postman", "rest api", "html", "html5", "css", "css3", "bootstrap", "tailwind",
    "git", "github", "docker", "kubernetes", "aws", "azure", "linux", "jira",
    "ci/cd", "jenkins", "data structures", "algorithms", "oop", "pandas", "numpy"
]

IMPACT_ACTION_VERBS = [
    "engineered", "developed", "automated", "designed", "implemented", "reduced",
    "increased", "optimized", "spearheaded", "integrated", "managed", "executed",
    "delivered", "deployed", "scaled", "created", "streamlined", "built", "accelerated"
]

WEAK_PASSIVE_WORDS = [
    "worked on", "responsible for", "helped with", "assisted in", "handled",
    "participated in", "tasked with", "duties included", "familiar with"
]

def analyze_resume_file(file_path, job_description=""):
    text = ""
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += "\n" + extracted
    except Exception as e:
        print("PDF parse error:", e)
        text = ""

    analysis = AIResumeAnalyzer.analyze_resume(text, job_description)

    primary_skill = analysis["detected_skills"][0] if analysis["detected_skills"] else "Software"
    second_skill = analysis["detected_skills"][1] if len(analysis["detected_skills"]) > 1 else "Engineer"

    jobs_list = [
        {"title": f"{primary_skill} Test Automation Engineer", "company": "Tech Product & Consulting", "location": "Bangalore, India", "match": "95%", "url": f"https://www.linkedin.com/jobs/search/?keywords={primary_skill}+Automation+Engineer&location=Bengaluru"},
        {"title": f"Quality Assurance & {second_skill} Specialist", "company": "Enterprise Software", "location": "Bangalore, India", "match": "92%", "url": f"https://www.linkedin.com/jobs/search/?keywords=QA+{second_skill}&location=Bengaluru"},
        {"title": f"Associate {primary_skill} Developer", "company": "Global Technology Hub", "location": "Bangalore, India", "match": "90%", "url": f"https://www.linkedin.com/jobs/search/?keywords={primary_skill}+Developer&location=Bengaluru"},
        {"title": f"{primary_skill} Systems Specialist", "company": "IT Solutions", "location": "Hyderabad, India", "match": "94%", "url": f"https://www.linkedin.com/jobs/search/?keywords={primary_skill}+Developer&location=Hyderabad"},
        {"title": f"SDET Automation Engineer ({second_skill})", "company": "FinTech Innovations", "location": "Hyderabad, India", "match": "91%", "url": f"https://www.linkedin.com/jobs/search/?keywords=SDET+{second_skill}&location=Hyderabad"},
        {"title": f"Remote {primary_skill} Engineer", "company": "Cloud SaaS Distributed", "location": "Remote (Work From Home)", "match": "96%", "url": f"https://www.linkedin.com/jobs/search/?keywords={primary_skill}+Remote&f_WT=2"}
    ]

    breakdown = {
        "contact_pts": analysis["contact_score"],
        "sec_pts": analysis["struct_score"],
        "skills_pts": analysis["skills_score"],
        "impact_pts": analysis["evidence_score"],
        "resume_quality_score": analysis["resume_quality_score"],
        "formatting_score": analysis["formatting_score"],
        "sections_detected": analysis["sections_detected"],
        "metrics_detected": len(analysis["metrics_found"]) > 0,
        "summary_ai": analysis["ai_summary"],
        "ai_summary": analysis["ai_summary"],
        "before_bullet": analysis["before_bullet"],
        "after_bullet": analysis["after_bullet"],
        "interview_questions": analysis["interview_questions"],
        "recommendations": analysis["recommendations"],
        "deductions": analysis["deductions"],
        "optimized_sections": analysis["optimized_sections"],
        "point_transformations": analysis.get("point_transformations", []),
        "is_ai_powered": analysis["is_ai_powered"],
        "jobs_list": jobs_list
    }

    mistakes = []
    for d in analysis["deductions"]:
        mistakes.append({
            "title": d["item"],
            "desc": d["reason"],
            "severity": "Critical" if abs(d["points"]) >= 8 else "Medium"
        })

    return {
        "candidate_name": analysis["candidate_name"][:60],
        "email": analysis["email"],
        "phone": analysis["phone"],
        "score": analysis["score"],
        "skills_found": analysis["detected_skills"],
        "missing_skills": analysis["missing_skills"],
        "action_verbs": analysis["action_verbs"],
        "sections_found": analysis["sections_detected"],
        "resume_text": text.strip()[:4000],
        "mistakes": mistakes,
        "breakdown": breakdown
    }

def send_owner_alert(subject, body_html):
    """Send email alert to owner (Ram) via Gmail SMTP."""
    try:
        owner_email = get_setting("owner_email", "ramudubandaru987@gmail.com")
        sender_email = os.environ.get("ALERT_EMAIL", "")
        sender_password = os.environ.get("ALERT_EMAIL_PASS", "")
        
        if not sender_email or not sender_password:
            print(f"[ALERT - no email creds] {subject}: {body_html[:200]}")
            return False
            
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔔 SkillBoost ATS | {subject}"
        msg["From"] = sender_email
        msg["To"] = owner_email
        msg.attach(MIMEText(body_html, "html"))
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, owner_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ALERT ERROR] {e}")
        return False

def user_has_active_subscription(user):
    """Check if user has a valid (non-expired) paid subscription."""
    if not user:
        return False
    try:
        expires = user["subscription_expires"]
        if expires:
            exp_date = datetime.strptime(expires, "%Y-%m-%d %H:%M:%S")
            return datetime.now() < exp_date
    except Exception:
        pass
    return False

def get_subscription_expiry_str(user):
    """Return a human-readable expiry string."""
    try:
        expires = user["subscription_expires"]
        if expires:
            exp_date = datetime.strptime(expires, "%Y-%m-%d %H:%M:%S")
            if datetime.now() < exp_date:
                days_left = (exp_date - datetime.now()).days
                return f"{exp_date.strftime('%d %b %Y')} ({days_left} days left)"
    except Exception:
        pass
    return None


def get_current_user():
    if "user_id" in session:
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        conn.close()
        return user
    return None

@app.context_processor
def inject_user():
    return {
        "current_user": get_current_user(),
        "is_admin": session.get("is_admin", False),
        "price_inr": get_setting("price_inr", "149"),
        "upi_id": get_setting("upi_id", "8688726584@upi")
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if get_current_user():
        return redirect(url_for("dashboard"))
        
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            error = "All fields are required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        else:
            conn = get_db()
            try:
                hashed = generate_password_hash(password)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (name, email, password_hash, free_credits)
                    VALUES (?, ?, ?, 1)
                """, (name, email, hashed))
                conn.commit()
                user_id = cursor.lastrowid
                conn.close()

                session["user_id"] = user_id
                session["user_name"] = name
                flash("Welcome to SkillBoost! You received 1 Free ATS Resume Scan.", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                conn.close()
                error = "An account with this email already exists. Please log in."

    return render_template("register.html", error=error)

@app.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid email or password. Please try again."

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_name", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

# ----------------- USER DASHBOARD & SCANNING -----------------

@app.route("/dashboard")
def dashboard():
    user = get_current_user()
    if not user:
        flash("Please log in or create a free account to scan your resume.", "info")
        return redirect(url_for("login"))

    conn = get_db()
    scans = conn.execute("SELECT * FROM scans WHERE user_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
    conn.close()

    has_subscription = user_has_active_subscription(user)
    subscription_info = get_subscription_expiry_str(user) if has_subscription else None

    return render_template("dashboard.html", user=user, scans=scans, 
                          has_subscription=has_subscription, subscription_info=subscription_info)

@app.route("/scan", methods=["POST"])
def scan():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Please sign in to scan your resume."}), 401

    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported."}), 400

    has_free_credit = user["free_credits"] > 0
    has_subscription = user_has_active_subscription(user)

    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    job_description = request.form.get("job_description", "").strip()

    # Perform ATS Analysis
    result = analyze_resume_file(file_path, job_description)

    # Determine unlock status:
    # 1. Active subscription → always unlocked (no credit used)
    # 2. Free credit available → unlocked (credit deducted)
    # 3. Neither → locked (needs payment)
    if has_subscription:
        is_free_scan = 0
        pay_status = "verified"   # auto-unlocked via subscription
    elif has_free_credit:
        is_free_scan = 1
        pay_status = "free"
    else:
        is_free_scan = 0
        pay_status = "unpaid"

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO scans (
            user_id, filename, candidate_name, email, phone, score,
            skills_found, missing_skills, action_verbs, sections_found,
            resume_text, mistakes_json, breakdown_json, is_free, payment_status, job_description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user["id"], filename, result["candidate_name"], result["email"], result["phone"],
        result["score"], ", ".join(result["skills_found"]), ", ".join(result["missing_skills"]),
        ", ".join(result["action_verbs"]), ", ".join(result["sections_found"]),
        result["resume_text"], json.dumps(result["mistakes"]), json.dumps(result["breakdown"]),
        is_free_scan, pay_status, job_description
    ))
    scan_id = cursor.lastrowid

    if has_free_credit and not has_subscription:
        cursor.execute("UPDATE users SET free_credits = free_credits - 1 WHERE id = ?", (user["id"],))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "scan_id": scan_id,
        "is_free": has_free_credit,
        "redirect_url": url_for("view_report", scan_id=scan_id)
    })

@app.route("/report/<int:scan_id>")
def view_report(scan_id):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    conn = get_db()
    scan = conn.execute("SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, user["id"])).fetchone()
    conn.close()

    if not scan:
        flash("Report not found.", "error")
        return redirect(url_for("dashboard"))

    breakdown = json.loads(scan["breakdown_json"]) if scan["breakdown_json"] else {}
    mistakes = json.loads(scan["mistakes_json"]) if scan["mistakes_json"] else []
    
    skills_list = [s.strip() for s in scan["skills_found"].split(",") if s.strip()]
    missing_list = [m.strip() for m in scan["missing_skills"].split(",") if m.strip()]
    verbs_list = [v.strip() for v in scan["action_verbs"].split(",") if v.strip()]
    
    jobs_list = breakdown.get("jobs_list", [])
    
    # Unlock logic: free scan OR verified payment OR active subscription
    has_subscription = user_has_active_subscription(user)
    is_unlocked = (scan["is_free"] == 1) or (scan["payment_status"] == "verified") or has_subscription
    
    subscription_info = get_subscription_expiry_str(user) if has_subscription else None

    return render_template(
        "report.html",
        scan=scan,
        breakdown=breakdown,
        mistakes=mistakes,
        skills_list=skills_list,
        missing_list=missing_list,
        verbs_list=verbs_list,
        jobs_list=jobs_list,
        is_unlocked=is_unlocked,
        has_subscription=has_subscription,
        subscription_info=subscription_info
    )

@app.route("/report/<int:scan_id>/download-pdf")
def download_pdf_report(scan_id):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    conn = get_db()
    scan = conn.execute("SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, user["id"])).fetchone()
    conn.close()

    if not scan:
        flash("Scan record not found.", "error")
        return redirect(url_for("dashboard"))

    has_subscription = user_has_active_subscription(user)
    is_unlocked = (scan["is_free"] == 1) or (scan["payment_status"] == "verified") or has_subscription

    if not is_unlocked:
        flash("Please unlock the report with payment or subscription before downloading PDF.", "error")
        return redirect(url_for("view_report", scan_id=scan_id))

    breakdown = json.loads(scan["breakdown_json"]) if scan["breakdown_json"] else {}
    pdf_bytes = generate_ats_report_pdf(dict(scan), breakdown)

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment;filename=SkillBoost_ATS_Report_{scan_id}.pdf"}
    )

@app.route("/api/rewrite-section", methods=["POST"])
def api_rewrite_section():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    scan_id = data.get("scan_id")
    section_name = data.get("section", "summary")
    original_text = data.get("original_text", "").strip()

    conn = get_db()
    scan = conn.execute("SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, user["id"])).fetchone()
    conn.close()

    if not scan:
        return jsonify({"error": "Scan not found"}), 404

    has_subscription = user_has_active_subscription(user)
    is_unlocked = (scan["is_free"] == 1) or (scan["payment_status"] == "verified") or has_subscription

    if not is_unlocked:
        return jsonify({"error": "Premium subscription required for AI Rewriter."}), 403

    breakdown = json.loads(scan["breakdown_json"]) if scan["breakdown_json"] else {}
    opt = breakdown.get("optimized_sections", {})

    if section_name == "summary":
        rewritten = opt.get("summary") or "Results-oriented Software Engineer specializing in automated testing, full-stack software development, and CI/CD pipelines."
    elif section_name == "experience":
        rewritten = opt.get("experience_bullet") or "Engineered automated test frameworks and performance-critical modules, decreasing test cycles by 60% and eliminating defect escapes."
    elif section_name == "project":
        rewritten = opt.get("project_description") or "Designed and deployed enterprise automation microservices with automated telemetry, achieving 99.9% uptime SLA."
    else:
        rewritten = f"Spearheaded technical implementation utilizing {scan['skills_found']}, increasing system throughput by 35%."

    return jsonify({
        "success": True,
        "section": section_name,
        "original": original_text,
        "rewritten": rewritten,
        "boosted_score": 98
    })

@app.route("/submit-payment", methods=["POST"])
def submit_payment():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    scan_id = data.get("scan_id")
    txn_id = data.get("txn_id", "").strip()

    if not scan_id or not txn_id:
        return jsonify({"error": "Please provide your 12-digit UPI Transaction / UTR ID."}), 400

    conn = get_db()
    scan = conn.execute("SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, user["id"])).fetchone()
    conn.execute("""
        UPDATE scans 
        SET txn_id = ?, payment_status = 'pending'
        WHERE id = ? AND user_id = ?
    """, (txn_id, scan_id, user["id"]))
    conn.commit()
    conn.close()

    # Send email alert to owner
    candidate_name = scan["candidate_name"] if scan else "Unknown"
    price_inr = get_setting("price_inr", "149")
    admin_url = f"https://skillboost-ats.onrender.com/admin/dashboard"
    alert_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;background:#0f172a;color:#e2e8f0;padding:24px;border-radius:12px;">
      <h2 style="color:#34d399;margin-bottom:4px;">💰 New Payment Received!</h2>
      <p style="color:#94a3b8;font-size:13px;">Someone just paid for SkillBoost ATS report unlock.</p>
      <table style="width:100%;margin-top:16px;border-collapse:collapse;">
        <tr><td style="padding:8px;color:#94a3b8;font-size:13px;">👤 User Name</td><td style="padding:8px;color:#fff;font-weight:bold;">{user['name']}</td></tr>
        <tr style="background:#1e293b;"><td style="padding:8px;color:#94a3b8;font-size:13px;">📧 User Email</td><td style="padding:8px;color:#38bdf8;">{user['email']}</td></tr>
        <tr><td style="padding:8px;color:#94a3b8;font-size:13px;">📄 Resume / Scan ID</td><td style="padding:8px;color:#fff;">#{scan_id} — {candidate_name}</td></tr>
        <tr style="background:#1e293b;"><td style="padding:8px;color:#94a3b8;font-size:13px;">💳 UTR / Transaction ID</td><td style="padding:8px;color:#fbbf24;font-weight:bold;font-family:monospace;">{txn_id}</td></tr>
        <tr><td style="padding:8px;color:#94a3b8;font-size:13px;">💵 Amount</td><td style="padding:8px;color:#34d399;font-weight:bold;">₹{price_inr}</td></tr>
        <tr style="background:#1e293b;"><td style="padding:8px;color:#94a3b8;font-size:13px;">🕐 Time</td><td style="padding:8px;color:#fff;">{datetime.now().strftime('%d %b %Y, %I:%M %p IST')}</td></tr>
      </table>
      <div style="margin-top:20px;text-align:center;">
        <a href="{admin_url}" style="display:inline-block;padding:12px 28px;background:#6366f1;color:#fff;border-radius:8px;text-decoration:none;font-weight:bold;">
          ✅ Verify Payment in Admin Panel →
        </a>
      </div>
      <p style="color:#475569;font-size:11px;margin-top:16px;text-align:center;">SkillBoost ATS Platform | Owner: Ram Bandaru</p>
    </div>
    """
    send_owner_alert(f"Payment Pending — {user['name']} | ₹{price_inr} | UTR: {txn_id}", alert_html)

    return jsonify({
        "success": True, 
        "message": "✅ Payment submitted! Your report will auto-unlock once the owner verifies. This page will update automatically."
    })

@app.route("/check-payment-status/<int:scan_id>")
def check_payment_status(scan_id):
    """API endpoint polled by the report page to check if payment was verified."""
    user = get_current_user()
    if not user:
        return jsonify({"unlocked": False}), 401

    # Check subscription first
    if user_has_active_subscription(user):
        return jsonify({"unlocked": True, "reason": "subscription"})

    conn = get_db()
    scan = conn.execute("SELECT payment_status, is_free FROM scans WHERE id = ? AND user_id = ?", 
                       (scan_id, user["id"])).fetchone()
    conn.close()

    if not scan:
        return jsonify({"unlocked": False})

    is_unlocked = (scan["is_free"] == 1) or (scan["payment_status"] == "verified")
    return jsonify({"unlocked": is_unlocked, "status": scan["payment_status"]})

# ----------------- B2B AGENCY WEBSITE REQUEST -----------------

@app.route("/submit-website-request", methods=["POST"])
def submit_website_request():
    data = request.form
    client_name = data.get("client_name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    project_type = data.get("project_type", "Portfolio Website")
    budget = data.get("budget", "₹10,000 - ₹20,000")
    description = data.get("description", "").strip()

    if not client_name or not email:
        return jsonify({"error": "Name and email are required."}), 400

    conn = get_db()
    conn.execute("""
        INSERT INTO website_leads (client_name, email, phone, project_type, budget, description)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (client_name, email, phone, project_type, budget, description))
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Thank you! Ram Bandaru has received your inquiry and will reach out with a proposal within 24 hours."
    })

# ----------------- ADMIN DASHBOARD (OWNER FULL MANAGEMENT) -----------------

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pwd = request.form.get("password", "").strip()
        
        correct_user = get_setting("admin_user", "ram")
        correct_pass = get_setting("admin_pass", "RamAdmin2026!")
        
        if user == correct_user and pwd == correct_pass:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            error = "Invalid admin credentials."
            
    return render_template("admin_login.html", error=error)

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
        
    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    scans = conn.execute("""
        SELECT s.*, u.name as user_name, u.email as user_email
        FROM scans s
        LEFT JOIN users u ON s.user_id = u.id
        ORDER BY s.id DESC
    """).fetchall()
    leads = conn.execute("SELECT * FROM website_leads ORDER BY id DESC").fetchall()
    conn.close()
    
    price_inr = get_setting("price_inr", "149")
    upi_id = get_setting("upi_id", "8688726584@upi")
    
    return render_template(
        "admin.html",
        users=users,
        scans=scans,
        leads=leads,
        price_inr=price_inr,
        upi_id=upi_id
    )

@app.route("/admin/delete-scan/<int:scan_id>", methods=["POST"])
def admin_delete_scan(scan_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    scan = conn.execute("SELECT filename FROM scans WHERE id = ?", (scan_id,)).fetchone()
    
    if scan:
        file_path = os.path.join(UPLOAD_FOLDER, scan["filename"])
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print("Error deleting PDF file:", e)
                
        conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
        conn.commit()
        flash(f"Resume #{scan_id} and its PDF file were permanently deleted.", "success")
        
    conn.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete-user/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    # Delete associated scans and physical files first
    scans = conn.execute("SELECT filename FROM scans WHERE user_id = ?", (user_id,)).fetchall()
    for s in scans:
        fp = os.path.join(UPLOAD_FOLDER, s["filename"])
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass
                
    conn.execute("DELETE FROM scans WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash(f"User Account #{user_id} and all their uploaded resumes were permanently deleted.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete-lead/<int:lead_id>", methods=["POST"])
def admin_delete_lead(lead_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    conn.execute("DELETE FROM website_leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()
    flash(f"Founder Website Inquiry #{lead_id} was deleted.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/verify-payment/<int:scan_id>", methods=["POST"])
def admin_verify_payment(scan_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    # Mark this scan as verified
    conn.execute("UPDATE scans SET payment_status = 'verified' WHERE id = ?", (scan_id,))
    
    # Get the user who owns this scan and give them 1 YEAR subscription
    scan = conn.execute("SELECT user_id FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if scan:
        user_id = scan["user_id"]
        # Check if user already has an active subscription — extend it, don't replace
        user = conn.execute("SELECT subscription_expires FROM users WHERE id = ?", (user_id,)).fetchone()
        
        now = datetime.now()
        try:
            existing_exp = datetime.strptime(user["subscription_expires"], "%Y-%m-%d %H:%M:%S") if user and user["subscription_expires"] else None
        except Exception:
            existing_exp = None
        
        # If existing subscription is still active, add 1 year from its expiry
        # Otherwise start 1 year from today
        if existing_exp and existing_exp > now:
            new_expiry = existing_exp + timedelta(days=365)
        else:
            new_expiry = now + timedelta(days=365)
        
        expiry_str = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE users SET subscription_expires = ?, subscription_plan = 'premium_1yr' WHERE id = ?", 
                     (expiry_str, user_id))
        
        # Also auto-verify ALL unpaid scans for this user (so old locked scans unlock too)
        conn.execute("UPDATE scans SET payment_status = 'verified' WHERE user_id = ? AND payment_status IN ('unpaid', 'pending')", 
                     (user_id,))
        
        flash(f"✅ Scan #{scan_id} verified! User #{user_id} now has Premium subscription until {new_expiry.strftime('%d %b %Y')}. All their scans are unlocked.", "success")
    
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/grant-credit/<int:user_id>", methods=["POST"])
def admin_grant_credit(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    conn.execute("UPDATE users SET free_credits = free_credits + 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash(f"Added +1 free credit to User #{user_id}.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/update-settings", methods=["POST"])
def admin_update_settings():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
        
    price_inr = request.form.get("price_inr")
    upi_id = request.form.get("upi_id")
    new_pass = request.form.get("new_pass")
    
    if price_inr: set_setting("price_inr", price_inr.strip())
    if upi_id: set_setting("upi_id", upi_id.strip())
    if new_pass and new_pass.strip(): set_setting("admin_pass", new_pass.strip())
    
    flash("Settings updated successfully.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/download/<filename>")
def download_resume(filename):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Logged out of Admin Portal.", "info")
    return redirect(url_for("admin_login"))

# ----------------- MAIN LAUNCHER -----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "="*50)
    print(">> SkillBoost ATS & Agency Platform Live")
    print(f">> Public: http://localhost:{port}")
    print(f">> Admin:  http://localhost:{port}/admin")
    print("   Owner User: ram")
    print("   Owner Pass: RamAdmin2026!")
    print("="*50 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
