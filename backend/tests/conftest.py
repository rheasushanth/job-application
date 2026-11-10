from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SAMPLE_RESUME_TEXT = """ANANYA SHARMA
Bengaluru, Karnataka | ananya.sharma@example.com | +91 98765 43210
github.com/ananyash | linkedin.com/in/ananyash

CAREER OBJECTIVE
Final-year Computer Science student seeking a software engineering internship
where I can apply my backend and machine learning project experience.

EDUCATION
B.Tech in Computer Science and Engineering
PES University, Bengaluru
2022 - 2026 (Pursuing) | CGPA: 8.7/10

Higher Secondary, Narayana PU College
2020 - 2022 | Percentage: 94%

TECHNICAL SKILLS
Languages: Python, Java, JavaScript, SQL, C++
Frameworks: Django, FastAPI, React, Flask
Tools & Platforms: Docker, Git, PostgreSQL, Redis, AWS
Libraries: Pandas, NumPy, scikit-learn, PyTorch
Concepts: Data Structures, Algorithms, REST APIs, OOP, DBMS

PROJECTS
Resume Ranking Engine - Python, FastAPI, scikit-learn
- Built a semantic resume-to-job matching service using sentence embeddings
- Exposed a FastAPI service with PostgreSQL persistence, served 2000+ requests
- Achieved 0.82 F1 on a hand-labelled relevance set

Campus Marketplace - Django, PostgreSQL, Docker
- Full-stack marketplace for student listings with JWT authentication
- Containerised with Docker and deployed on AWS EC2

Traffic Sign Classifier - PyTorch, OpenCV
- CNN achieving 97.3% accuracy on the GTSRB dataset

INTERNSHIPS
Backend Developer Intern - Zeta Technologies
Jun 2025 - Dec 2025
- Developed REST APIs in Django serving 50k daily requests
- Reduced p95 query latency 40% by adding Redis caching and query indexes

Machine Learning Intern, Nova Analytics
May 2024 - Jul 2024
- Built data pipelines in Pandas and trained gradient boosting models

CERTIFICATIONS
AWS Certified Cloud Practitioner - Amazon Web Services (2025)
Machine Learning Specialization - Coursera (2024)

ACHIEVEMENTS
- Winner, PES Hackathon 2025 among 180 teams
- Solved 600+ problems on LeetCode; contest rating 1842
- Published a paper on resume parsing at a student research symposium
"""
