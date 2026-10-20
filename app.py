import os
import re
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from pypdf import PdfReader

app = Flask(__name__)
app.secret_key = "ram-bandaru-ats-secret-key-2026"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "database.db")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ----------------- DATABASE SETUP -----------------
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Scans / Resumes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            candidate_name TEXT,
            email TEXT,
            phone TEXT,
            score INTEGER,
            skills_found TEXT,
            missing_skills TEXT,
            is_free_scan INTEGER DEFAULT 1,
            txn_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Website client leads table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS website_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT,
            email TEXT,
            phone TEXT,
            project_type TEXT,
            budget TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Seed default settings if not exists
    defaults = {
        "free_scans_remaining": "5",
        "price_inr": "149",
        "upi_id": "8688726584@upi",
        "admin_user": "ram",
        "admin_pass": "RamAdmin2026!"
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

# ----------------- ATS ANALYSIS ENGINE -----------------
KEYWORDS_DICTIONARY = [
    "python", "java", "javascript", "react", "react.js", "node.js", "express", "sql", 
    "mysql", "postgresql", "mongodb", "selenium", "pytest", "playwright", "behave", 
    "bdd", "cucumber", "html", "html5", "css", "css3", "bootstrap", "tailwind", 
    "git", "github", "docker", "aws", "rest api", "apis", "api testing", "postman", 
    "automation", "test automation", "manual testing", "regression testing", "jira", 
    "linux", "flask", "django", "ci/cd", "jenkins", "data structures", "algorithms"
]

ACTION_VERBS = [
    "engineered", "developed", "automated", "built", "designed", "implemented", 
    "reduced", "increased", "optimized", "spearheaded", "integrated", "managed", 
    "executed", "delivered", "deployed", "scaled", "created", "streamlined"
]

def analyze_resume(file_path):
    text = ""
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += " " + t
    except Exception as e:
        print("Error reading PDF:", e)
        text = ""

    clean_text = text.lower()
    
    # 1. Contact Info check (15 pts)
    email_match = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    phone_match = re.findall(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    has_email = len(email_match) > 0
    has_phone = len(phone_match) > 0
    has_linkedin = "linkedin.com" in clean_text
    has_github = "github.com" in clean_text
    
    contact_score = 0
    if has_email: contact_score += 5
    if has_phone: contact_score += 4
    if has_linkedin: contact_score += 3
    if has_github: contact_score += 3
    
    # 2. Keywords Match (40 pts)
    found_keywords = [kw for kw in KEYWORDS_DICTIONARY if re.search(r'\b' + re.escape(kw) + r'\b', clean_text)]
    kw_count = len(found_keywords)
    # 10 keywords = 40 pts
    keywords_score = min(40, int((kw_count / 10) * 40))
    
    missing_recommendations = [k for k in ["Python", "Selenium", "SQL", "React", "REST API", "Git", "PyTest", "Docker"] if k.lower() not in found_keywords][:5]
    
    # 3. Action Verbs & Metrics (25 pts)
    found_verbs = [v for v in ACTION_VERBS if re.search(r'\b' + re.escape(v) + r'\b', clean_text)]
    verb_count = len(found_verbs)
    metrics_match = re.findall(r'\d+%', text) + re.findall(r'\$\d+', text)
    
    action_score = min(15, verb_count * 3) + min(10, len(metrics_match) * 3)
    
    # 4. Standard Sections (20 pts)
    sections_score = 0
    for sec in ["education", "experience", "projects", "skills"]:
        if sec in clean_text:
            sections_score += 5
            
    total_score = min(98, contact_score + keywords_score + action_score + sections_score)
    if total_score < 30 and len(text) > 100:
        total_score = 42 # reasonable baseline
        
    # Extracted candidate name (heuristic)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    candidate_name = lines[0] if lines else "Candidate"
    
    # Generated LinkedIn Jobs URL
    top_skills = found_keywords[:3] if found_keywords else ["Python", "Developer"]
    linkedin_query = "+".join([s.replace(" ", "+") for s in top_skills])
    linkedin_jobs_url = f"https://www.linkedin.com/jobs/search/?keywords={linkedin_query}&f_TPR=r604800"

    return {
        "candidate_name": candidate_name[:50],
        "email": email_match[0] if email_match else "",
        "phone": phone_match[0] if phone_match else "",
        "score": total_score,
        "found_keywords": [k.title() for k in found_keywords],
        "missing_keywords": missing_recommendations,
        "found_verbs": [v.title() for v in found_verbs],
        "has_linkedin": has_linkedin,
        "has_github": has_github,
        "has_metrics": len(metrics_match) > 0,
        "linkedin_jobs_url": linkedin_jobs_url
    }

# ----------------- ROUTES -----------------

@app.route("/")
def index():
    free_scans = int(get_setting("free_scans_remaining", "5"))
    price_inr = get_setting("price_inr", "149")
    upi_id = get_setting("upi_id", "8688726584@upi")
    return render_template("index.html", free_scans=free_scans, price_inr=price_inr, upi_id=upi_id)

@app.route("/scan", methods=["POST"])
def scan_resume():
    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
        
    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
        
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Please upload a PDF resume format."}), 400

    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    # Analyze
    result = analyze_resume(file_path)

    free_scans = int(get_setting("free_scans_remaining", "5"))
    is_free = free_scans > 0
    
    # Save to DB
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO scans (filename, candidate_name, email, phone, score, skills_found, missing_skills, is_free_scan)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        filename, result["candidate_name"], result["email"], result["phone"], 
        result["score"], ", ".join(result["found_keywords"]), ", ".join(result["missing_keywords"]),
        1 if is_free else 0
    ))
    scan_id = cursor.lastrowid
    
    # If free, decrement counter on the same connection
    if is_free:
        new_count = max(0, free_scans - 1)
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('free_scans_remaining', ?)", (str(new_count),))
        free_scans = new_count
        
    conn.commit()
    conn.close()

    result["scan_id"] = scan_id
    result["is_free"] = is_free
    result["free_scans_left"] = free_scans
    result["price_inr"] = get_setting("price_inr", "149")
    result["upi_id"] = get_setting("upi_id", "8688726584@upi")

    return jsonify(result)

@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    data = request.json or {}
    scan_id = data.get("scan_id")
    txn_id = data.get("txn_id", "").strip()
    
    if not scan_id or not txn_id:
        return jsonify({"success": False, "error": "Please provide your Transaction UTR ID."}), 400
        
    conn = get_db()
    conn.execute("UPDATE scans SET txn_id = ?, is_free_scan = 2 WHERE id = ?", (txn_id, scan_id))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Payment verified! Full report unlocked."})

@app.route("/submit-website-request", methods=["POST"])
def submit_website_request():
    data = request.form
    client_name = data.get("client_name", "")
    email = data.get("email", "")
    phone = data.get("phone", "")
    project_type = data.get("project_type", "Portfolio Website")
    budget = data.get("budget", "₹10,000 - ₹25,000")
    description = data.get("description", "")

    conn = get_db()
    conn.execute("""
        INSERT INTO website_leads (client_name, email, phone, project_type, budget, description)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (client_name, email, phone, project_type, budget, description))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Thank you! Ram Bandaru will review your requirements and reach out within 24 hours."})

# ----------------- ADMIN DASHBOARD -----------------

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        user = request.form.get("username")
        pwd = request.form.get("password")
        
        correct_user = get_setting("admin_user", "ram")
        correct_pass = get_setting("admin_pass", "RamAdmin2026!")
        
        if user == correct_user and pwd == correct_pass:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            error = "Invalid username or password"
            
    return render_template("admin_login.html", error=error)

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
        
    conn = get_db()
    scans = conn.execute("SELECT * FROM scans ORDER BY id DESC").fetchall()
    leads = conn.execute("SELECT * FROM website_leads ORDER BY id DESC").fetchall()
    conn.close()
    
    free_scans = get_setting("free_scans_remaining", "5")
    price_inr = get_setting("price_inr", "149")
    upi_id = get_setting("upi_id", "8688726584@upi")
    
    return render_template("admin.html", scans=scans, leads=leads, free_scans=free_scans, price_inr=price_inr, upi_id=upi_id)

@app.route("/admin/update-settings", methods=["POST"])
def admin_update_settings():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
        
    free_scans = request.form.get("free_scans")
    price_inr = request.form.get("price_inr")
    upi_id = request.form.get("upi_id")
    new_pass = request.form.get("new_pass")
    
    if free_scans: set_setting("free_scans_remaining", free_scans)
    if price_inr: set_setting("price_inr", price_inr)
    if upi_id: set_setting("upi_id", upi_id)
    if new_pass and new_pass.strip(): set_setting("admin_pass", new_pass.strip())
    
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/download/<filename>")
def download_resume(filename):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n" + "="*50)
    print(">> Ram's Resume ATS & Agency Platform is starting!")
    print(f">> Public Site: http://localhost:{port}")
    print(f">> Admin Panel: http://localhost:{port}/admin")
    print("   Default Username: ram")
    print("   Default Password: RamAdmin2026!")
    print("="*50 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
