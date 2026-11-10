"""Role catalogue for alternative-role recommendations.

Each role declares the skills that genuinely define it, split into core (you
cannot do the job without these) and supporting. Fit is computed from actual
skill coverage against this catalogue, so a suggestion is always backed by
evidence rather than an LLM free-associating job titles.

`search_terms` are what the discovery engine actually queries the portals with.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoleDefinition:
    key: str
    title: str
    family: str
    core_skills: tuple[str, ...]
    supporting_skills: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()
    # Degree level this role typically expects (0 = none stated, 3 = bachelor).
    typical_degree_level: int = 3
    # Seniority bands this role is offered at.
    levels: tuple[str, ...] = ("internship", "entry")
    blurb: str = ""
    related_roles: tuple[str, ...] = field(default_factory=tuple)


ROLE_CATALOGUE: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        key="sde_intern",
        title="Software Development Engineer Intern",
        family="software_engineering",
        core_skills=("Data Structures", "Algorithms", "OOP"),
        supporting_skills=("Python", "Java", "C++", "Git", "SQL", "Problem Solving"),
        search_terms=("software engineer intern", "software development intern"),
        levels=("internship",),
        blurb="General-purpose software engineering internship; graded mostly on "
              "fundamentals and one strong language.",
        related_roles=("backend_intern", "fullstack_intern"),
    ),
    RoleDefinition(
        key="backend_intern",
        title="Backend Developer Intern",
        family="software_engineering",
        core_skills=("REST API", "SQL"),
        supporting_skills=("Python", "Java", "Node.js", "Django", "Flask", "FastAPI",
                           "Spring", "PostgreSQL", "MySQL", "MongoDB", "Docker", "Git"),
        search_terms=("backend developer intern", "backend engineer intern"),
        levels=("internship",),
        blurb="Server-side development: APIs, data models and persistence.",
        related_roles=("sde_intern", "fullstack_intern", "devops_intern"),
    ),
    RoleDefinition(
        key="frontend_intern",
        title="Frontend Developer Intern",
        family="software_engineering",
        core_skills=("JavaScript", "HTML", "CSS"),
        supporting_skills=("React", "Vue.js", "Angular", "TypeScript", "Tailwind CSS",
                           "Next.js", "Redux", "Git", "UI/UX"),
        search_terms=("frontend developer intern", "front end developer intern"),
        levels=("internship",),
        blurb="Browser-side development: components, state and styling.",
        related_roles=("fullstack_intern", "ui_engineer"),
    ),
    RoleDefinition(
        key="fullstack_intern",
        title="Full Stack Developer Intern",
        family="software_engineering",
        core_skills=("JavaScript", "REST API"),
        supporting_skills=("React", "Node.js", "Python", "Django", "Express.js", "SQL",
                           "PostgreSQL", "MongoDB", "HTML", "CSS", "Git", "Docker"),
        search_terms=("full stack developer intern", "fullstack intern"),
        levels=("internship",),
        blurb="Both halves of a web application, from database to interface.",
        related_roles=("backend_intern", "frontend_intern"),
    ),
    RoleDefinition(
        key="python_developer",
        title="Python Developer",
        family="software_engineering",
        core_skills=("Python",),
        supporting_skills=("Django", "Flask", "FastAPI", "SQL", "PostgreSQL", "REST API",
                           "Pandas", "Git", "Docker", "Unit Testing"),
        search_terms=("python developer", "python engineer"),
        levels=("internship", "entry", "mid"),
        blurb="Python-centred engineering across web services, tooling and automation.",
        related_roles=("backend_intern", "data_engineer"),
    ),
    RoleDefinition(
        key="java_developer",
        title="Java Developer",
        family="software_engineering",
        core_skills=("Java", "OOP"),
        supporting_skills=("Spring", "Hibernate", "SQL", "REST API", "Git", "Maven",
                           "Unit Testing", "Microservices"),
        search_terms=("java developer", "java backend developer"),
        levels=("entry", "mid"),
        blurb="Enterprise backend development on the JVM.",
        related_roles=("backend_intern",),
    ),
    RoleDefinition(
        key="mobile_developer",
        title="Mobile App Developer",
        family="software_engineering",
        core_skills=("Mobile Development",),
        supporting_skills=("React Native", "Flutter", "Android", "iOS", "Kotlin", "Swift",
                           "Dart", "Java", "REST API", "Git"),
        search_terms=("mobile app developer", "android developer intern", "ios developer intern"),
        levels=("internship", "entry"),
        blurb="Native or cross-platform application development.",
    ),
    RoleDefinition(
        key="data_analyst",
        title="Data Analyst",
        family="data",
        core_skills=("SQL", "Data Analysis"),
        supporting_skills=("Excel", "Python", "Pandas", "Tableau", "Power BI",
                           "Statistics", "Data Visualization", "R"),
        search_terms=("data analyst", "data analyst intern"),
        levels=("internship", "entry"),
        blurb="Turning data into reporting and decisions; SQL-heavy.",
        related_roles=("business_analyst", "data_scientist"),
    ),
    RoleDefinition(
        key="data_scientist",
        title="Data Science Intern",
        family="data",
        core_skills=("Python", "Statistics", "Machine Learning"),
        supporting_skills=("Pandas", "NumPy", "scikit-learn", "SQL", "Data Visualization",
                           "Jupyter", "Data Analysis"),
        search_terms=("data science intern", "data scientist"),
        levels=("internship", "entry"),
        blurb="Statistical modelling and experimentation on real datasets.",
        related_roles=("ml_intern", "data_analyst"),
    ),
    RoleDefinition(
        key="ml_intern",
        title="Machine Learning Intern",
        family="ai_ml",
        core_skills=("Machine Learning", "Python"),
        supporting_skills=("scikit-learn", "TensorFlow", "PyTorch", "Pandas", "NumPy",
                           "Deep Learning", "Statistics", "NLP", "Computer Vision"),
        search_terms=("machine learning intern", "ml engineer intern"),
        levels=("internship",),
        blurb="Training, evaluating and shipping models.",
        related_roles=("ai_engineer_intern", "data_scientist"),
    ),
    RoleDefinition(
        key="ai_engineer_intern",
        title="AI Engineer Intern",
        family="ai_ml",
        core_skills=("Python", "Machine Learning"),
        supporting_skills=("LLM", "Transformers", "NLP", "PyTorch", "TensorFlow",
                           "Embeddings", "Vector Database", "Prompt Engineering", "REST API"),
        search_terms=("ai engineer intern", "ai intern", "generative ai intern"),
        levels=("internship", "entry"),
        blurb="Applied AI: building products on top of models, often LLMs.",
        related_roles=("ml_intern",),
    ),
    RoleDefinition(
        key="data_engineer",
        title="Data Engineer Intern",
        family="data",
        core_skills=("SQL", "Python", "ETL"),
        supporting_skills=("Airflow", "Spark", "Kafka", "PostgreSQL", "Big Data",
                           "Docker", "AWS", "dbt"),
        search_terms=("data engineer intern", "data engineering intern"),
        levels=("internship", "entry"),
        blurb="Pipelines and warehouses that make data usable downstream.",
        related_roles=("backend_intern", "data_analyst"),
    ),
    RoleDefinition(
        key="cloud_intern",
        title="Cloud Engineer Intern",
        family="infrastructure",
        core_skills=("Cloud Computing",),
        supporting_skills=("AWS", "Azure", "GCP", "Linux", "Docker", "Kubernetes",
                           "Terraform", "Bash", "Monitoring"),
        search_terms=("cloud engineer intern", "cloud intern"),
        levels=("internship", "entry"),
        blurb="Provisioning and operating cloud infrastructure.",
        related_roles=("devops_intern",),
    ),
    RoleDefinition(
        key="devops_intern",
        title="DevOps Intern",
        family="infrastructure",
        core_skills=("CI/CD", "Linux"),
        supporting_skills=("Docker", "Kubernetes", "Git", "AWS", "Terraform", "Ansible",
                           "Jenkins", "Bash", "Monitoring", "Nginx"),
        search_terms=("devops intern", "devops engineer intern", "sre intern"),
        levels=("internship", "entry"),
        blurb="Build, deploy and observability pipelines.",
        related_roles=("cloud_intern", "backend_intern"),
    ),
    RoleDefinition(
        key="qa_automation_intern",
        title="QA Automation Intern",
        family="quality",
        core_skills=("Test Automation",),
        supporting_skills=("Selenium", "Cypress", "Unit Testing", "Python", "Java",
                           "JavaScript", "Postman", "REST API", "Manual Testing", "JMeter"),
        search_terms=("qa automation intern", "sdet intern", "test automation intern"),
        levels=("internship", "entry"),
        blurb="Automated test suites and release confidence.",
        related_roles=("sde_intern",),
    ),
    RoleDefinition(
        key="security_intern",
        title="Cybersecurity Intern",
        family="security",
        core_skills=("Cybersecurity",),
        supporting_skills=("Penetration Testing", "Network Security", "Linux",
                           "Computer Networks", "Python", "Cryptography"),
        search_terms=("cyber security intern", "security analyst intern"),
        levels=("internship", "entry"),
        blurb="Finding and closing security weaknesses.",
    ),
    RoleDefinition(
        key="business_analyst",
        title="Business Analyst",
        family="business",
        core_skills=("Business Analysis",),
        supporting_skills=("SQL", "Excel", "Data Analysis", "Power BI", "Tableau",
                           "Communication", "Agile", "Jira"),
        search_terms=("business analyst", "business analyst intern"),
        levels=("internship", "entry"),
        blurb="Translating business needs into specifications and analysis.",
        related_roles=("data_analyst", "product_intern"),
    ),
    RoleDefinition(
        key="product_intern",
        title="Product Management Intern",
        family="business",
        core_skills=("Project Management", "Communication"),
        supporting_skills=("Agile", "Jira", "Data Analysis", "SQL", "UI/UX",
                           "Stakeholder Management", "Figma"),
        search_terms=("product management intern", "associate product manager intern"),
        levels=("internship",),
        blurb="Specifying and sequencing what gets built.",
        related_roles=("business_analyst",),
    ),
    RoleDefinition(
        key="ui_engineer",
        title="UI/UX Designer",
        family="design",
        core_skills=("UI/UX",),
        supporting_skills=("Figma", "HTML", "CSS", "Design Patterns", "Communication"),
        search_terms=("ui ux designer intern", "product designer intern"),
        levels=("internship", "entry"),
        blurb="Interface and interaction design.",
        related_roles=("frontend_intern",),
    ),
    RoleDefinition(
        key="technical_writer",
        title="Technical Writer",
        family="content",
        core_skills=("Technical Writing",),
        supporting_skills=("Communication", "Git", "REST API", "Content Writing"),
        search_terms=("technical writer intern", "documentation intern"),
        levels=("internship", "entry"),
        blurb="Documentation for technical products and APIs.",
    ),
)

ROLES_BY_KEY: dict[str, RoleDefinition] = {r.key: r for r in ROLE_CATALOGUE}


def roles_for_level(seniority: str) -> list[RoleDefinition]:
    """Roles plausibly open to a candidate at this seniority."""
    wanted = {
        "student": {"internship"},
        "intern": {"internship"},
        "fresher": {"internship", "entry"},
        "entry_level": {"entry", "mid"},
        "experienced": {"entry", "mid"},
    }.get(seniority, {"internship", "entry"})
    return [r for r in ROLE_CATALOGUE if set(r.levels) & wanted]
