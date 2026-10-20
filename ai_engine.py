import os
import re
import json
import logging
import requests

logger = logging.getLogger(__name__)

class AIResumeAnalyzer:
    """
    Production-grade AI Resume Intelligence Engine.
    Connects to external LLM (Gemini or OpenAI) when API key is provided,
    and falls back to an advanced deterministic semantic rule engine if no key is configured or offline.
    """

    CORE_SKILL_TAXONOMY = {
        "Languages": ["Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go", "Rust", "PHP", "Ruby", "SQL", "HTML", "CSS"],
        "Frameworks & Web": ["React", "React.js", "Angular", "Vue.js", "Node.js", "Express", "Django", "Flask", "Spring Boot", "FastAPI", "Tailwind CSS", "Bootstrap"],
        "Testing & QA Automation": ["Selenium", "PyTest", "Playwright", "Cypress", "Cucumber", "BDD", "TestNG", "Junit", "Postman", "Rest Assured", "Manual Testing", "API Testing", "Regression Testing"],
        "Data & AI": ["Pandas", "NumPy", "Scikit-Learn", "TensorFlow", "PyTorch", "PowerBI", "Tableau", "Data Analysis", "Machine Learning", "NLP"],
        "Cloud & DevOps": ["AWS", "Azure", "GCP", "Docker", "Kubernetes", "CI/CD", "Jenkins", "GitHub Actions", "Terraform", "Linux"],
        "Databases & Tools": ["PostgreSQL", "MySQL", "MongoDB", "Oracle", "Redis", "Git", "GitHub", "Jira", "Agile", "Scrum"]
    }

    ACTION_VERBS = [
        "engineered", "architected", "developed", "automated", "designed", "implemented", 
        "optimized", "spearheaded", "integrated", "deployed", "scaled", "streamlined", 
        "reduced", "increased", "accelerated", "resolved", "executed", "collaborated"
    ]

    WEAK_PHRASES = [
        "worked on", "responsible for", "helped with", "assisted in", "handled", 
        "participated in", "tasked with", "duties included", "familiar with", "involved in"
    ]

    @classmethod
    def get_api_key(cls):
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")

    @classmethod
    def extract_skills(cls, text):
        clean_text = text.lower()
        found_skills = []
        for category, skills in cls.CORE_SKILL_TAXONOMY.items():
            for skill in skills:
                pattern = r'(?<!\w)' + re.escape(skill.lower()) + r'(?!\w)'
                if re.search(pattern, clean_text):
                    found_skills.append({"skill": skill, "category": category})
        # Remove duplicates while preserving order
        unique = []
        seen = set()
        for item in found_skills:
            if item["skill"].lower() not in seen:
                seen.add(item["skill"].lower())
                unique.append(item)
        return unique

    @classmethod
    def analyze_resume(cls, resume_text, job_description=""):
        """
        Executes AI analysis. Attempts LLM call if API key exists; otherwise executes high-precision semantic fallback.
        """
        api_key = cls.get_api_key()
        if api_key:
            try:
                if os.environ.get("GEMINI_API_KEY"):
                    return cls._call_gemini(resume_text, job_description, os.environ.get("GEMINI_API_KEY"))
                elif os.environ.get("OPENAI_API_KEY"):
                    return cls._call_openai(resume_text, job_description, os.environ.get("OPENAI_API_KEY"))
            except Exception as e:
                logger.warning(f"External AI LLM call failed, falling back to local semantic engine: {e}")

        # Deterministic, explainable semantic analysis
        return cls._semantic_rule_analysis(resume_text, job_description)

    @classmethod
    def _semantic_rule_analysis(cls, resume_text, job_description=""):
        clean_res = resume_text.lower()
        clean_jd = job_description.lower() if job_description else ""

        # 1. Contact & Hierarchy Info
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', resume_text)
        phones = re.findall(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', resume_text)
        has_linkedin = "linkedin.com" in clean_res
        has_github = "github.com" in clean_res or "gitlab.com" in clean_res

        sections_detected = []
        for sec in ["experience", "education", "skills", "projects", "certifications", "summary"]:
            if re.search(r'\b' + sec + r'\b', clean_res):
                sections_detected.append(sec.title())

        # 2. Extract Candidate Name
        lines = [l.strip() for l in resume_text.split("\n") if l.strip()]
        candidate_name = lines[0] if lines else "Candidate"
        if len(candidate_name) > 50 or "@" in candidate_name:
            candidate_name = "Candidate"

        # 3. Skills Analysis
        detected_skills_objs = cls.extract_skills(resume_text)
        detected_skill_names = [s["skill"] for s in detected_skills_objs]

        # 4. Job Description Matching (If JD provided)
        jd_skills_required = []
        matched_skills = []
        missing_skills = []

        if job_description and len(job_description.strip()) > 30:
            jd_skills_objs = cls.extract_skills(job_description)
            jd_skills_required = [s["skill"] for s in jd_skills_objs]
            
            for sk in jd_skills_required:
                if any(sk.lower() == ds.lower() for ds in detected_skill_names):
                    matched_skills.append(sk)
                else:
                    missing_skills.append(sk)
        else:
            # Fallback recommendations if no JD provided
            all_core = [s for sublist in cls.CORE_SKILL_TAXONOMY.values() for s in sublist]
            missing_skills = [s for s in ["Git", "Docker", "REST API", "SQL", "CI/CD", "Postman", "PyTest"] if s not in detected_skill_names][:6]
            matched_skills = detected_skill_names[:8]

        # 5. Evidence & Action Verbs Analysis
        verbs_found = []
        for v in cls.ACTION_VERBS:
            if re.search(r'\b' + v + r'\b', clean_res):
                verbs_found.append(v.title())
        verbs_found = list(dict.fromkeys(verbs_found))

        metrics_found = re.findall(r'\d+%', resume_text) + re.findall(r'\$\d+', resume_text) + re.findall(r'\b\d+\s*(?:users|clients|ms|sec|hours|x)\b', clean_res)

        # 6. Flag Weak Lines & Build Specific Actionable Transformations
        weak_lines = []
        point_transformations = []
        for line in lines:
            line_clean = line.lower()
            if any(w in line_clean for w in cls.WEAK_PHRASES) and len(line) > 18 and len(line) < 240:
                weak_lines.append(line.strip())

        # Create 3-5 specific line-by-line transformations
        candidate_lines_to_transform = weak_lines[:5]
        if len(candidate_lines_to_transform) < 3:
            for line in lines:
                if len(line) > 25 and len(line) < 180 and not any(skip in line.lower() for skip in ['@', 'http', 'linkedin', 'phone', 'education', 'skills', 'b.tech']):
                    if line.strip() not in candidate_lines_to_transform:
                        candidate_lines_to_transform.append(line.strip())
                if len(candidate_lines_to_transform) >= 4:
                    break

        p_skill = detected_skill_names[0] if detected_skill_names else "Python"
        s_skill = detected_skill_names[1] if len(detected_skill_names) > 1 else "Automation"

        action_templates = [
            ("Engineered and automated end-to-end {p_skill} workflows", "reducing manual execution overhead by 45% and eliminating regression test bottlenecks."),
            ("Architected scalable {p_skill} modules integrated with {s_skill}", "accelerating release velocity by 35% across 5 consecutive sprint cycles."),
            ("Led technical validation and optimization using {p_skill}", "delivering 99.4% test pass accuracy and improving system turnaround time by 30%."),
            ("Spearheaded automated CI/CD integration with {s_skill}", "slashing deployment turnaround from 3 hours to 20 minutes with zero downtime escapes.")
        ]

        for i, original_line in enumerate(candidate_lines_to_transform):
            tmpl_prefix, tmpl_suffix = action_templates[i % len(action_templates)]
            fixed_line = f"{tmpl_prefix.format(p_skill=p_skill, s_skill=s_skill)}, {tmpl_suffix}"
            point_transformations.append({
                "original": original_line,
                "problem": "Passive phrasing lacks measurable impact metrics (%) and strong technical action verb.",
                "improved": fixed_line,
                "why_it_works": "Replaces vague claim with measurable outcome + specific technical stack, passing ATS parser filters."
            })

        # 7. Multi-Tier Explainable Scoring
        # A. Skills Alignment (35 pts max)
        if jd_skills_required:
            skills_score = int((len(matched_skills) / max(1, len(jd_skills_required))) * 35)
        else:
            skills_score = min(35, int((len(detected_skill_names) / 10) * 35))

        # B. Technical Evidence & Metrics (25 pts max)
        evidence_score = min(15, len(verbs_found) * 3) + min(10, len(metrics_found) * 4)

        # C. Structure & Completeness (20 pts max)
        struct_score = min(20, len(sections_detected) * 4)

        # D. Contact & Professional Presence (20 pts max)
        contact_score = 0
        if emails: contact_score += 6
        if phones: contact_score += 6
        if has_linkedin: contact_score += 4
        if has_github: contact_score += 4

        raw_score = skills_score + evidence_score + struct_score + contact_score
        total_score = max(28, min(95, raw_score)) if len(resume_text) > 80 else 20

        # Quality & Formatting Sub-Scores
        resume_quality_score = max(35, min(96, evidence_score * 2 + skills_score))
        formatting_score = max(40, min(98, struct_score * 3 + contact_score * 2))

        # 8. Deductions with Reasons
        deductions = []
        if not has_linkedin:
            deductions.append({"item": "LinkedIn Profile", "points": -4, "reason": "Missing verified LinkedIn URL reduces recruiter trust."})
        if not has_github:
            deductions.append({"item": "GitHub / Portfolio", "points": -4, "reason": "Missing code repository or portfolio proof of work."})
        if not metrics_found:
            deductions.append({"item": "Quantifiable Metrics", "points": -10, "reason": "No measurable business results found (e.g. 'reduced latency by 35%')."})
        if len(missing_skills) > 0 and jd_skills_required:
            deductions.append({"item": "Missing Target Skills", "points": -12, "reason": f"Target job explicitly requires: {', '.join(missing_skills[:4])}."})
        if weak_lines:
            deductions.append({"item": "Passive Phrasing", "points": -6, "reason": f"Detected {len(weak_lines)} weak phrases (e.g. '{weak_lines[0][:50]}...')."})

        # 9. Recommendations
        recommendations = [
            f"Embed quantifiable achievements into experience bullet points (use the X-Y-Z formula: Accomplished [X], measured by [Y], by doing [Z]).",
            f"Add missing industry standard keywords: {', '.join(missing_skills[:4]) if missing_skills else 'Docker, Kubernetes, Cloud Services'}.",
            f"Replace passive phrases ('worked on', 'responsible for') with impactful action verbs like 'Engineered', 'Optimized', or 'Automated'."
        ]
        if not has_github:
            recommendations.append("Include links to active GitHub repositories showcasing code quality, test coverage, and documentation.")

        # 10. AI Summary and Bullet Rewrites
        primary_skill = detected_skill_names[0] if detected_skill_names else "Software"
        second_skill = detected_skill_names[1] if len(detected_skill_names) > 1 else "Cloud Solutions"

        ai_summary = (
            f"Performance-driven {primary_skill} Engineer with proven expertise in building scalable applications and automated workflows using {', '.join(detected_skill_names[:4]) if detected_skill_names else 'modern technologies'}. "
            f"Adept at collaborating in Agile teams, improving system reliability, and delivering measurable results under tight release cycles."
        )

        before_bullet = weak_lines[0] if weak_lines else (lines[5] if len(lines) > 5 else "Responsible for software development and bug fixes.")
        after_bullet = (
            f"Engineered high-performance {primary_skill} modules and automated testing workflows utilizing {second_skill}, "
            f"slashing production bug escape rate by 45% and reducing manual testing cycles from 8 hours to 45 minutes."
        )

        # 11. Tailored Interview Questions
        interview_questions = [
            f"How have you leveraged {primary_skill} in production to overcome scalability or architectural bottlenecks?",
            f"Can you explain your methodology for end-to-end integration and error handling when working with {second_skill}?",
            "Describe a high-stakes production incident you resolved under tight deadline pressures. What was your root cause analysis approach?",
            "How do you maintain clean code architecture, comprehensive test coverage, and continuous integration in Agile sprints?",
            "What metrics or KPI indicators do you track to demonstrate the business impact of your technical implementations?"
        ]

        # 12. Full-Resume Rewrite Suggestions (For 98-100% Score Mode)
        optimized_sections = {
            "summary": ai_summary,
            "skills": ", ".join(detected_skill_names + missing_skills[:4]),
            "experience_bullet": after_bullet,
            "project_description": f"Architected an enterprise {primary_skill} & {second_skill} automation platform featuring real-time telemetry, sub-second API response times, and 99.9% uptime SLA."
        }

        return {
            "candidate_name": candidate_name,
            "email": emails[0] if emails else "",
            "phone": phones[0] if phones else "",
            "score": total_score,
            "resume_quality_score": resume_quality_score,
            "formatting_score": formatting_score,
            "skills_score": skills_score,
            "evidence_score": evidence_score,
            "struct_score": struct_score,
            "contact_score": contact_score,
            "sections_detected": sections_detected,
            "detected_skills": detected_skill_names,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "action_verbs": verbs_found,
            "metrics_found": metrics_found,
            "weak_lines": weak_lines,
            "deductions": deductions,
            "recommendations": recommendations,
            "ai_summary": ai_summary,
            "before_bullet": before_bullet,
            "after_bullet": after_bullet,
            "interview_questions": interview_questions,
            "optimized_sections": optimized_sections,
            "point_transformations": point_transformations,
            "is_ai_powered": bool(cls.get_api_key())
        }

    @classmethod
    def _call_gemini(cls, resume_text, job_description, api_key):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = f"""
You are an expert ATS (Applicant Tracking System) Auditor and Senior Technical Recruiter.
Analyze the following resume against the job description (if provided).
Return ONLY a valid JSON object matching this exact schema:
{{
  "candidate_name": string,
  "score": integer (20 to 95),
  "resume_quality_score": integer (20 to 95),
  "formatting_score": integer (20 to 95),
  "skills_score": integer (0 to 35),
  "evidence_score": integer (0 to 25),
  "struct_score": integer (0 to 20),
  "contact_score": integer (0 to 20),
  "sections_detected": [string],
  "detected_skills": [string],
  "matched_skills": [string],
  "missing_skills": [string],
  "action_verbs": [string],
  "metrics_found": [string],
  "weak_lines": [string],
  "deductions": [{{"item": string, "points": integer, "reason": string}}],
  "recommendations": [string],
  "ai_summary": string,
  "before_bullet": string,
  "after_bullet": string,
  "interview_questions": [string],
  "optimized_sections": {{
      "summary": string,
      "skills": string,
      "experience_bullet": string,
      "project_description": string
  }}
}}

RESUME TEXT:
{resume_text[:4000]}

JOB DESCRIPTION:
{job_description[:2000] if job_description else "General Software / Technical Engineer"}
"""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }
        res = requests.post(url, json=payload, timeout=20)
        res.raise_for_status()
        data = res.json()
        raw_content = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_content)
        parsed["is_ai_powered"] = True
        return parsed

    @classmethod
    def _call_openai(cls, resume_text, job_description, api_key):
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        prompt = f"""
Analyze this resume for an ATS parser. Return strictly valid JSON with candidate_name, score (20-95), resume_quality_score, formatting_score, skills_score, evidence_score, struct_score, contact_score, sections_detected, detected_skills, matched_skills, missing_skills, action_verbs, metrics_found, weak_lines, deductions (list of {{item, points, reason}}), recommendations (list of strings), ai_summary, before_bullet, after_bullet, interview_questions (5 questions), optimized_sections (summary, skills, experience_bullet, project_description).

Resume:
{resume_text[:4000]}

Target Job Description:
{job_description[:2000] if job_description else "Software Engineer"}
"""
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}
        }
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        res.raise_for_status()
        data = res.json()
        parsed = json.loads(data["choices"][0]["message"]["content"])
        parsed["is_ai_powered"] = True
        return parsed
