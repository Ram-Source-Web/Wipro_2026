import os
import re
import json
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, flash
from werkzeug.security import generate_password_hash, check_password_hash
from pypdf import PdfReader

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
        ("mistakes_json", "TEXT"),
        ("breakdown_json", "TEXT"),
        ("is_free", "INTEGER DEFAULT 1"),
        ("payment_status", "TEXT DEFAULT 'free'")
    ]:
        try:
            cursor.execute(f"ALTER TABLE scans ADD COLUMN {col} {col_type};")
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

def analyze_resume_file(file_path):
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

    clean_text = text.lower()
    
    # 1. Contact Info Detection (15 pts max)
    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    phones = re.findall(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    has_email = len(emails) > 0
    has_phone = len(phones) > 0
    has_linkedin = "linkedin.com" in clean_text
    has_github = "github.com" in clean_text
    
    contact_pts = 0
    if has_email: contact_pts += 5
    if has_phone: contact_pts += 4
    if has_linkedin: contact_pts += 3
    if has_github: contact_pts += 3
    
    # 2. Section Detection (25 pts max)
    sections_found = []
    sec_pts = 0
    for sec in ["education", "experience", "projects", "skills", "certifications"]:
        if sec in clean_text:
            sections_found.append(sec.title())
            sec_pts += 5
            
    # 3. Technical Skills Extraction (35 pts max)
    skills_found = []
    for kw in CORE_TECH_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', clean_text):
            skills_found.append(kw.title())
            
    skills_found = list(dict.fromkeys(skills_found))
    skills_pts = min(35, int((len(skills_found) / 10) * 35))
    
    recommended_skills = [
        s for s in ["Python", "Selenium", "SQL", "React", "REST API", "Git", "PyTest", "Docker", "Postman", "CI/CD"]
        if s.title() not in skills_found
    ][:6]
    
    # 4. Action Verbs & Metrics (25 pts max)
    verbs_found = []
    for v in IMPACT_ACTION_VERBS:
        if re.search(r'\b' + re.escape(v) + r'\b', clean_text):
            verbs_found.append(v.title())
    verbs_found = list(dict.fromkeys(verbs_found))
    
    metrics_match = re.findall(r'\d+%', text) + re.findall(r'\$\d+', text) + re.findall(r'\d+\s*(?:sec|seconds|ms|hours|x)', clean_text)
    
    verb_pts = min(15, len(verbs_found) * 3)
    metric_pts = min(10, len(metrics_match) * 4)
    impact_pts = verb_pts + metric_pts
    
    # Calculate Total ATS Score (Max 96)
    raw_score = contact_pts + sec_pts + skills_pts + impact_pts
    total_score = max(38, min(96, raw_score)) if len(text) > 80 else 25
    
    # Extracted candidate name
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    candidate_name = lines[0] if lines else "Candidate"

    # ----------------- DETECT CRITICAL RED-FLAG MISTAKES -----------------
    mistakes = []
    
    if not has_linkedin:
        mistakes.append({
            "title": "Missing LinkedIn Profile URL",
            "desc": "Recruiters and ATS software prioritize candidates with verified LinkedIn URLs to validate employment history.",
            "severity": "High"
        })
    if not has_github:
        mistakes.append({
            "title": "Missing GitHub / Portfolio Link",
            "desc": "For software, QA, and web engineering roles, lack of a code repository severely lowers technical credibility.",
            "severity": "High"
        })
    if len(metrics_match) == 0:
        mistakes.append({
            "title": "Zero Quantifiable Business Metrics Found",
            "desc": "Your bullet points lack quantifiable proof (e.g. 'reduced testing time by 40%', 'improved speed by 2x'). ATS algorithms downgrade non-measurable claims.",
            "severity": "Critical"
        })
    
    # Detect weak passive words in text
    detected_weak_words = [w for w in WEAK_PASSIVE_WORDS if w in clean_text]
    if detected_weak_words:
        mistakes.append({
            "title": f"Weak Passive Phrasing Detected ('{detected_weak_words[0]}')",
            "desc": "Replace passive phrases like 'worked on' or 'responsible for' with assertive action verbs like 'Engineered', 'Automated', or 'Spearheaded'.",
            "severity": "Medium"
        })

    if "certifications" not in [s.lower() for s in sections_found]:
        mistakes.append({
            "title": "Missing Dedicated Certifications Section",
            "desc": "ATS filters actively scan for credentials (e.g. Python, SQL, Agile, Selenium certifications). Add an explicit Certifications section.",
            "severity": "Medium"
        })

    if len(skills_found) < 6:
        mistakes.append({
            "title": "Low Technical Keyword Density",
            "desc": f"Your resume only has {len(skills_found)} recognizable tech keywords. Add missing industry standards like {', '.join(recommended_skills[:3])}.",
            "severity": "Critical"
        })

    # AI Generated Professional Summary
    primary_role = "QA Automation & Test Engineer" if any(s.lower() in clean_text for s in ["selenium", "testing", "pytest", "qa"]) else "Full-Stack Software Engineer"
    summary_ai = (
        f"Results-driven {primary_role} proficient in {', '.join(skills_found[:4]) if skills_found else 'modern software engineering'}. "
        f"Experienced in developing scalable applications and test suites, focusing on code reliability, defect reduction, and rapid deployment cycles."
    )
    
    # AI Sample Bullet Point Transformation
    before_bullet = "Worked on manual testing and writing python scripts for the web app."
    after_bullet = f"Engineered automated test suites using {skills_found[0] if skills_found else 'Python'}, reducing regression testing turnaround time by 45% and eliminating critical production defects."

    # Top tailored interview questions
    interview_questions = [
        f"How have you applied {skills_found[0] if skills_found else 'Python'} to solve a challenging performance or automation bottleneck?",
        f"Can you explain your approach to test framework design or API validation when working with {skills_found[1] if len(skills_found) > 1 else 'REST APIs'}?",
        "Describe a time when you identified a critical bug right before deployment. How did you diagnose and remediate it?",
        "How do you ensure proper version control and cross-functional collaboration using Git and Agile practices?",
        "What metrics do you use to quantify the business impact and reliability of your software deliverable?"
    ]

    # Generate 15 targeted live job links across Bangalore, Hyderabad & Remote
    top_skill = skills_found[0] if skills_found else "Software"
    second_skill = skills_found[1] if len(skills_found) > 1 else "Developer"
    
    jobs_list = [
        # Bangalore Jobs
        {"title": f"{top_skill} Automation Engineer", "company": "Top MNC / Tech Product", "location": "Bangalore, India", "match": "95%", "url": f"https://www.linkedin.com/jobs/search/?keywords={top_skill}+Automation+Engineer&location=Bengaluru"},
        {"title": f"Junior QA & Test Automation Specialist", "company": "Software Enterprise", "location": "Bangalore, India", "match": "92%", "url": f"https://www.linkedin.com/jobs/search/?keywords=QA+Automation+Engineer&location=Bengaluru"},
        {"title": f"{top_skill} Software Engineer - Fresher / Associate", "company": "Global IT Services", "location": "Bangalore, India", "match": "90%", "url": f"https://www.linkedin.com/jobs/search/?keywords={top_skill}+Engineer+Fresher&location=Bengaluru"},
        {"title": f"Associate Full-Stack Developer ({second_skill})", "company": "High-Growth Startup", "location": "Bangalore, India", "match": "88%", "url": f"https://www.linkedin.com/jobs/search/?keywords=Associate+Software+Engineer&location=Bengaluru"},
        {"title": "SDET / Automation Test Engineer", "company": "Cloud SaaS Company", "location": "Bangalore, India", "match": "87%", "url": f"https://www.linkedin.com/jobs/search/?keywords=SDET&location=Bengaluru"},

        # Hyderabad Jobs
        {"title": f"{top_skill} Developer & Scripting Specialist", "company": "Global Technology Center", "location": "Hyderabad, India", "match": "94%", "url": f"https://www.linkedin.com/jobs/search/?keywords={top_skill}+Developer&location=Hyderabad"},
        {"title": "Software Test Engineer (Selenium / BDD)", "company": "Enterprise Solutions", "location": "Hyderabad, India", "match": "93%", "url": f"https://www.linkedin.com/jobs/search/?keywords=Selenium+QA+Engineer&location=Hyderabad"},
        {"title": f"Associate Engineer - {second_skill} / Python", "company": "IT Consulting Firm", "location": "Hyderabad, India", "match": "91%", "url": f"https://www.linkedin.com/jobs/search/?keywords=Associate+Engineer&location=Hyderabad"},
        {"title": "Web Application QA Tester", "company": "Digital Solutions", "location": "Hyderabad, India", "match": "89%", "url": f"https://www.linkedin.com/jobs/search/?keywords=Software+QA+Tester&location=Hyderabad"},
        {"title": "Junior Python Automation Analyst", "company": "FinTech Systems", "location": "Hyderabad, India", "match": "88%", "url": f"https://www.linkedin.com/jobs/search/?keywords=Python+Automation&location=Hyderabad"},

        # Remote Jobs (India & Global)
        {"title": f"Remote {top_skill} Engineer", "company": "Remote First Company", "location": "Remote (Work From Home)", "match": "96%", "url": f"https://www.linkedin.com/jobs/search/?keywords={top_skill}+Remote&f_WT=2"},
        {"title": "Junior QA Automation Engineer (Remote)", "company": "SaaS Platform", "location": "Remote (India)", "match": "93%", "url": "https://www.linkedin.com/jobs/search/?keywords=QA+Automation+Remote&f_WT=2"},
        {"title": f"Freelance / Contract {top_skill} Developer", "company": "Digital Agency", "location": "Remote", "match": "90%", "url": f"https://www.linkedin.com/jobs/search/?keywords={top_skill}+Contract&f_WT=2"},
        {"title": "Software Engineering Trainee (Remote)", "company": "Tech Accelerator", "location": "Remote", "match": "89%", "url": "https://www.linkedin.com/jobs/search/?keywords=Software+Trainee+Remote&f_WT=2"},
        {"title": "Full-Stack Automation Trainee", "company": "Global Solutions", "location": "Remote", "match": "86%", "url": f"https://www.linkedin.com/jobs/search/?keywords={second_skill}+Developer+Remote&f_WT=2"}
    ]

    breakdown = {
        "contact_pts": contact_pts,
        "sec_pts": sec_pts,
        "skills_pts": skills_pts,
        "impact_pts": impact_pts,
        "has_email": has_email,
        "has_phone": has_phone,
        "has_linkedin": has_linkedin,
        "has_github": has_github,
        "sections_detected": sections_found,
        "metrics_detected": len(metrics_match) > 0,
        "summary_ai": summary_ai,
        "before_bullet": before_bullet,
        "after_bullet": after_bullet,
        "interview_questions": interview_questions,
        "jobs_list": jobs_list
    }

    return {
        "candidate_name": candidate_name[:60],
        "email": emails[0] if emails else "",
        "phone": phones[0] if phones else "",
        "score": total_score,
        "skills_found": skills_found,
        "missing_skills": recommended_skills,
        "action_verbs": verbs_found,
        "sections_found": sections_found,
        "resume_text": text.strip()[:4000], # clean preview
        "mistakes": mistakes,
        "breakdown": breakdown
    }

# ----------------- USER AUTHENTICATION & ACCESS -----------------

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

    return render_template("dashboard.html", user=user, scans=scans)

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

    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    # Perform ATS Analysis
    result = analyze_resume_file(file_path)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO scans (
            user_id, filename, candidate_name, email, phone, score,
            skills_found, missing_skills, action_verbs, sections_found,
            resume_text, mistakes_json, breakdown_json, is_free, payment_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user["id"], filename, result["candidate_name"], result["email"], result["phone"],
        result["score"], ", ".join(result["skills_found"]), ", ".join(result["missing_skills"]),
        ", ".join(result["action_verbs"]), ", ".join(result["sections_found"]),
        result["resume_text"], json.dumps(result["mistakes"]), json.dumps(result["breakdown"]),
        1 if has_free_credit else 0,
        "free" if has_free_credit else "unpaid"
    ))
    scan_id = cursor.lastrowid

    if has_free_credit:
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
    is_unlocked = (scan["is_free"] == 1) or (scan["payment_status"] == "verified")

    return render_template(
        "report.html",
        scan=scan,
        breakdown=breakdown,
        mistakes=mistakes,
        skills_list=skills_list,
        missing_list=missing_list,
        verbs_list=verbs_list,
        jobs_list=jobs_list,
        is_unlocked=is_unlocked
    )

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
    conn.execute("""
        UPDATE scans 
        SET txn_id = ?, payment_status = 'pending'
        WHERE id = ? AND user_id = ?
    """, (txn_id, scan_id, user["id"]))
    conn.commit()
    conn.close()

    return jsonify({
        "success": True, 
        "message": "Payment submitted! Admin will verify and unlock your full AI report within minutes."
    })

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
    conn.execute("UPDATE scans SET payment_status = 'verified' WHERE id = ?", (scan_id,))
    conn.commit()
    conn.close()
    flash(f"Scan #{scan_id} payment verified and report unlocked!", "success")
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
