import pytest
import os
import json
from ai_engine import AIResumeAnalyzer
from pdf_service import generate_ats_report_pdf

SAMPLE_RESUME = """
RAM BANDARU
ramudubandaru987@gmail.com | +91 8688726584 | linkedin.com/in/ram-bandaru | github.com/Ram-Source-Web

SUMMARY
Software QA Automation Engineer with 3+ years of experience in Python, Selenium, PyTest, and SQL.
Worked on manual testing and writing python scripts for the web app.

EXPERIENCE
Project Engineer - Wipro Technologies
- Worked on regression testing and test framework design using Python and PyTest.
- Automated 150+ test cases, reducing execution time by 40%.
- Integrated Jenkins CI/CD pipeline and Git version control.

EDUCATION
B.Tech in Computer Science - 2022

SKILLS
Python, Java, Selenium, PyTest, SQL, Git, Docker, Postman, Linux, REST API
"""

SAMPLE_JOB_DESC = """
Senior Test Automation Engineer (SDET)
Requirements:
- 3+ years experience with Python and Selenium test automation.
- Hands-on experience with PyTest, REST API testing, and SQL.
- Strong knowledge of CI/CD pipelines (Jenkins/Docker).
- Experience leading regression testing cycles.
"""

def test_extract_skills():
    skills = AIResumeAnalyzer.extract_skills(SAMPLE_RESUME)
    skill_names = [s["skill"] for s in skills]
    assert "Python" in skill_names
    assert "Selenium" in skill_names
    assert "SQL" in skill_names
    assert "Docker" in skill_names

def test_analyze_resume_semantic():
    result = AIResumeAnalyzer.analyze_resume(SAMPLE_RESUME, SAMPLE_JOB_DESC)
    assert result["candidate_name"] == "RAM BANDARU"
    assert result["score"] >= 65
    assert "Python" in result["matched_skills"]
    assert len(result["recommendations"]) > 0
    assert "before_bullet" in result
    assert "after_bullet" in result
    assert "optimized_sections" in result
    assert "summary" in result["optimized_sections"]

def test_pdf_generation():
    result = AIResumeAnalyzer.analyze_resume(SAMPLE_RESUME, SAMPLE_JOB_DESC)
    scan_mock = {
        "candidate_name": "RAM BANDARU",
        "created_at": "2026-10-20 22:00:00",
        "score": result["score"],
        "skills_found": ", ".join(result["detected_skills"]),
        "missing_skills": ", ".join(result["missing_skills"])
    }
    pdf_bytes = generate_ats_report_pdf(scan_mock, result)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")
