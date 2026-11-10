"""Curated skill ontology.

This is deliberately hand-maintained rather than LLM-generated: skill matching
feeds the match percentage, so it has to be deterministic, inspectable and
diffable. Each entry carries aliases (for normalisation), a category (for the
category sub-scores) and `related` skills (for transferable-skill credit, which
is awarded at a discount rather than as a full match).
"""

from __future__ import annotations

from typing import Iterable

# canonical -> (category, aliases, related)
SKILL_ONTOLOGY: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    # ---- programming languages -------------------------------------
    "Python": ("language", ("py", "python3", "python 3"), ("Django", "Flask", "FastAPI", "Pandas")),
    "JavaScript": ("language", ("js", "ecmascript", "es6", "es2015"), ("TypeScript", "Node.js", "React")),
    "TypeScript": ("language", ("ts",), ("JavaScript", "React", "Angular")),
    "Java": ("language", ("core java", "java se", "j2ee", "jee"), ("Spring", "Hibernate", "Kotlin")),
    "C": ("language", ("c language", "ansi c"), ("C++", "Embedded C")),
    "C++": ("language", ("cpp", "c plus plus", "cplusplus"), ("C", "Rust")),
    "C#": ("language", ("csharp", "c sharp", "dotnet c#"), (".NET", "ASP.NET")),
    "Go": ("language", ("golang",), ("Docker", "Kubernetes")),
    "Rust": ("language", (), ("C++", "Go")),
    "Ruby": ("language", (), ("Ruby on Rails",)),
    "PHP": ("language", (), ("Laravel", "MySQL")),
    "Swift": ("language", (), ("iOS", "Objective-C")),
    "Kotlin": ("language", (), ("Java", "Android")),
    "Scala": ("language", (), ("Spark", "Java")),
    "R": ("language", ("r language", "rlang"), ("Statistics", "Pandas")),
    "MATLAB": ("language", ("matlab/simulink",), ("Signal Processing",)),
    "Dart": ("language", (), ("Flutter",)),
    "Perl": ("language", (), ("Bash",)),
    "Objective-C": ("language", ("objc",), ("Swift", "iOS")),
    "SQL": ("language", ("structured query language",), ("PostgreSQL", "MySQL", "MS SQL Server")),
    "Bash": ("language", ("shell", "shell scripting", "bash scripting", "sh", "zsh"), ("Linux", "DevOps")),
    "PowerShell": ("language", (), ("Windows", "Azure")),
    "Solidity": ("language", (), ("Blockchain", "Ethereum")),
    "Assembly": ("language", ("asm", "x86 assembly"), ("C", "Embedded Systems")),
    "VHDL": ("language", (), ("Verilog", "FPGA")),
    "Verilog": ("language", ("systemverilog",), ("VHDL", "FPGA")),

    # ---- frontend ---------------------------------------------------
    "React": ("framework", ("react.js", "reactjs", "react js"), ("Next.js", "Redux", "JavaScript")),
    "Next.js": ("framework", ("nextjs", "next js"), ("React", "TypeScript", "Vercel")),
    "Vue.js": ("framework", ("vue", "vuejs", "vue 3", "nuxt"), ("JavaScript", "React")),
    "Angular": ("framework", ("angularjs", "angular 2+"), ("TypeScript", "RxJS")),
    "Svelte": ("framework", ("sveltekit",), ("JavaScript", "React")),
    "HTML": ("framework", ("html5",), ("CSS", "JavaScript")),
    "CSS": ("framework", ("css3",), ("Tailwind CSS", "SASS", "HTML")),
    "Tailwind CSS": ("framework", ("tailwind", "tailwindcss"), ("CSS", "React")),
    "SASS": ("framework", ("scss", "sass/scss"), ("CSS",)),
    "Bootstrap": ("framework", (), ("CSS", "HTML")),
    "Redux": ("framework", ("redux toolkit", "rtk"), ("React",)),
    "jQuery": ("framework", (), ("JavaScript",)),
    "React Native": ("framework", ("react-native",), ("React", "Mobile Development")),
    "Flutter": ("framework", (), ("Dart", "Mobile Development")),
    "Android": ("framework", ("android development", "android sdk"), ("Kotlin", "Java")),
    "iOS": ("framework", ("ios development",), ("Swift", "Objective-C")),

    # ---- backend ----------------------------------------------------
    "Node.js": ("framework", ("nodejs", "node", "node js"), ("Express.js", "JavaScript")),
    "Express.js": ("framework", ("express", "expressjs"), ("Node.js",)),
    "Django": ("framework", ("django rest framework", "drf"), ("Python", "PostgreSQL")),
    "Flask": ("framework", (), ("Python", "FastAPI")),
    "FastAPI": ("framework", ("fast api",), ("Python", "Pydantic", "Flask")),
    "Spring": ("framework", ("spring boot", "springboot", "spring mvc"), ("Java", "Hibernate")),
    "Hibernate": ("framework", ("jpa",), ("Java", "Spring")),
    ".NET": ("framework", ("dotnet", ".net core", "net core"), ("C#", "ASP.NET")),
    "ASP.NET": ("framework", ("asp.net core", "aspnet"), ("C#", ".NET")),
    "Laravel": ("framework", (), ("PHP", "MySQL")),
    "Ruby on Rails": ("framework", ("rails", "ror"), ("Ruby",)),
    "GraphQL": ("framework", ("apollo graphql",), ("REST API", "Node.js")),
    "REST API": ("concept", ("rest", "restful", "restful api", "rest apis"), ("GraphQL", "Microservices")),
    "gRPC": ("framework", (), ("Microservices", "Protocol Buffers")),
    "Microservices": ("concept", ("microservice architecture",), ("Docker", "Kubernetes", "REST API")),
    "WebSockets": ("concept", ("websocket", "socket.io"), ("Node.js",)),

    # ---- data / ML --------------------------------------------------
    "Machine Learning": ("ml", ("ml", "machine-learning"), ("Python", "scikit-learn", "Deep Learning")),
    "Deep Learning": ("ml", ("dl", "neural networks"), ("TensorFlow", "PyTorch", "Machine Learning")),
    "TensorFlow": ("ml", ("tf", "keras", "tensorflow 2"), ("Deep Learning", "Python")),
    "PyTorch": ("ml", ("torch",), ("Deep Learning", "Python")),
    "scikit-learn": ("ml", ("sklearn", "scikit learn"), ("Machine Learning", "Python", "Pandas")),
    "Pandas": ("ml", ("pandas dataframe",), ("Python", "NumPy", "Data Analysis")),
    "NumPy": ("ml", ("numpy array",), ("Python", "Pandas")),
    "NLP": ("ml", ("natural language processing", "text mining"), ("Machine Learning", "Transformers")),
    "Computer Vision": ("ml", ("cv", "opencv", "image processing"), ("Deep Learning", "PyTorch")),
    "Transformers": ("ml", ("hugging face", "huggingface", "bert", "llm"), ("NLP", "PyTorch")),
    "LLM": ("ml", ("large language model", "large language models", "genai", "generative ai"), ("Transformers", "NLP", "Prompt Engineering")),
    "Prompt Engineering": ("ml", ("prompting",), ("LLM",)),
    "Data Analysis": ("ml", ("data analytics", "analytics"), ("Pandas", "SQL", "Excel")),
    "Data Science": ("ml", ("datascience",), ("Machine Learning", "Statistics", "Python")),
    "Statistics": ("ml", ("statistical analysis", "statistical modeling"), ("R", "Data Analysis")),
    "Data Visualization": ("ml", ("dataviz", "matplotlib", "seaborn", "visualisation"), ("Tableau", "Power BI")),
    "Tableau": ("tool", (), ("Power BI", "Data Visualization")),
    "Power BI": ("tool", ("powerbi", "microsoft power bi"), ("Tableau", "Excel")),
    "Excel": ("tool", ("microsoft excel", "ms excel", "advanced excel"), ("Data Analysis",)),
    "Spark": ("tool", ("apache spark", "pyspark"), ("Scala", "Hadoop", "Big Data")),
    "Hadoop": ("tool", ("hdfs", "mapreduce"), ("Spark", "Big Data")),
    "Big Data": ("concept", (), ("Spark", "Hadoop", "Kafka")),
    "Kafka": ("tool", ("apache kafka",), ("Big Data", "Microservices")),
    "Airflow": ("tool", ("apache airflow",), ("ETL", "Python")),
    "ETL": ("concept", ("etl pipelines", "elt", "data pipelines"), ("Airflow", "SQL")),
    "dbt": ("tool", (), ("SQL", "ETL")),

    # ---- databases --------------------------------------------------
    "PostgreSQL": ("database", ("postgres", "psql"), ("SQL", "MySQL")),
    "MySQL": ("database", ("mariadb",), ("SQL", "PostgreSQL")),
    "MongoDB": ("database", ("mongo", "mongoose"), ("NoSQL", "Node.js")),
    "Redis": ("database", (), ("Caching", "NoSQL")),
    "SQLite": ("database", (), ("SQL",)),
    "MS SQL Server": ("database", ("sql server", "mssql", "t-sql"), ("SQL",)),
    "Oracle": ("database", ("oracle db", "pl/sql"), ("SQL",)),
    "Elasticsearch": ("database", ("elastic", "opensearch"), ("NoSQL",)),
    "NoSQL": ("database", (), ("MongoDB", "DynamoDB")),
    "DynamoDB": ("database", (), ("AWS", "NoSQL")),
    "Cassandra": ("database", (), ("NoSQL", "Big Data")),
    "Neo4j": ("database", ("graph database",), ("NoSQL",)),
    "Vector Database": ("database", ("pinecone", "weaviate", "pgvector", "faiss", "chroma"), ("LLM", "Embeddings")),
    "Embeddings": ("ml", ("sentence transformers", "word embeddings", "vector embeddings"), ("NLP", "Vector Database")),

    # ---- cloud / devops --------------------------------------------
    "AWS": ("cloud", ("amazon web services", "ec2", "s3", "lambda"), ("Cloud Computing", "DevOps")),
    "Azure": ("cloud", ("microsoft azure",), ("Cloud Computing", "DevOps")),
    "GCP": ("cloud", ("google cloud", "google cloud platform"), ("Cloud Computing", "Kubernetes")),
    "Cloud Computing": ("cloud", ("cloud",), ("AWS", "Azure", "GCP")),
    "Docker": ("devops", ("containerization", "containers"), ("Kubernetes", "DevOps")),
    "Kubernetes": ("devops", ("k8s", "eks", "gke"), ("Docker", "DevOps", "Helm")),
    "Helm": ("devops", (), ("Kubernetes",)),
    "Terraform": ("devops", ("iac", "infrastructure as code"), ("AWS", "DevOps")),
    "Ansible": ("devops", (), ("DevOps", "Linux")),
    "Jenkins": ("devops", (), ("CI/CD", "DevOps")),
    "CI/CD": ("devops", ("ci cd", "continuous integration", "continuous deployment", "github actions", "gitlab ci"), ("Jenkins", "Docker", "DevOps")),
    "DevOps": ("devops", ("sre", "site reliability"), ("Docker", "Kubernetes", "CI/CD")),
    "Linux": ("devops", ("unix", "ubuntu", "centos", "rhel"), ("Bash", "DevOps")),
    "Nginx": ("devops", ("reverse proxy",), ("Linux", "DevOps")),
    "Git": ("tool", ("github", "gitlab", "version control", "bitbucket"), ("CI/CD",)),
    "Monitoring": ("devops", ("prometheus", "grafana", "datadog", "observability"), ("DevOps",)),
    "Caching": ("concept", ("cache",), ("Redis",)),

    # ---- testing / quality -----------------------------------------
    "Unit Testing": ("testing", ("unit tests", "pytest", "jest", "junit", "mocha"), ("Test Automation", "TDD")),
    "Test Automation": ("testing", ("automation testing", "qa automation", "automated testing"), ("Selenium", "Unit Testing")),
    "Selenium": ("testing", ("selenium webdriver",), ("Test Automation", "Python")),
    "Cypress": ("testing", ("playwright",), ("Test Automation", "JavaScript")),
    "Manual Testing": ("testing", ("qa", "quality assurance", "software testing"), ("Test Automation",)),
    "TDD": ("testing", ("test driven development",), ("Unit Testing",)),
    "Postman": ("tool", ("api testing",), ("REST API",)),
    "JMeter": ("testing", ("performance testing", "load testing"), ("Test Automation",)),

    # ---- CS fundamentals -------------------------------------------
    "Data Structures": ("concept", ("dsa", "data structures and algorithms"), ("Algorithms", "Problem Solving")),
    "Algorithms": ("concept", ("algorithm design", "competitive programming"), ("Data Structures",)),
    "Problem Solving": ("soft", ("analytical skills",), ("Data Structures",)),
    "OOP": ("concept", ("object oriented programming", "object-oriented design", "oops"), ("Java", "Design Patterns")),
    "Design Patterns": ("concept", (), ("OOP", "System Design")),
    "System Design": ("concept", ("high level design", "hld", "lld", "software architecture"), ("Microservices", "Design Patterns")),
    "Operating Systems": ("concept", ("os",), ("Linux",)),
    "Computer Networks": ("concept", ("networking", "tcp/ip"), ("Linux",)),
    "DBMS": ("concept", ("database management systems",), ("SQL",)),
    "Compiler Design": ("concept", (), ("C", "Algorithms")),

    # ---- security --------------------------------------------------
    "Cybersecurity": ("security", ("information security", "infosec", "security"), ("Penetration Testing", "Network Security")),
    "Penetration Testing": ("security", ("pentesting", "ethical hacking", "vapt"), ("Cybersecurity",)),
    "Network Security": ("security", (), ("Cybersecurity", "Computer Networks")),
    "Cryptography": ("security", ("encryption",), ("Cybersecurity",)),
    "OAuth": ("security", ("oauth2", "openid connect", "sso", "jwt"), ("Authentication",)),
    "Authentication": ("security", ("authorization", "authn", "authz"), ("OAuth",)),

    # ---- product / process -----------------------------------------
    "Agile": ("process", ("scrum", "kanban", "sprint planning"), ("Jira", "Project Management")),
    "Jira": ("tool", ("atlassian jira",), ("Agile",)),
    "Project Management": ("soft", ("program management",), ("Agile", "Stakeholder Management")),
    "Figma": ("tool", ("adobe xd", "sketch"), ("UI/UX")),
    "UI/UX": ("design", ("ui/ux design", "user experience", "user interface", "ux"), ("Figma", "CSS")),
    "Technical Writing": ("soft", ("documentation",), ("Communication",)),
    "Communication": ("soft", ("verbal communication", "written communication"), ("Teamwork",)),
    "Teamwork": ("soft", ("collaboration", "team player"), ("Communication",)),
    "Leadership": ("soft", ("team leadership", "mentoring"), ("Communication",)),
    "Stakeholder Management": ("soft", ("client management",), ("Communication",)),

    # ---- business / analyst ----------------------------------------
    "Business Analysis": ("business", ("business analyst", "requirement gathering"), ("Data Analysis", "SQL")),
    "Digital Marketing": ("business", ("seo", "sem", "social media marketing"), ("Content Writing",)),
    "Content Writing": ("business", ("copywriting", "content creation"), ("Technical Writing",)),
    "Accounting": ("business", ("bookkeeping", "tally"), ("Excel",)),
    "Sales": ("business", ("business development", "bd", "inside sales"), ("Communication",)),
    "Human Resources": ("business", ("hr", "recruitment", "talent acquisition"), ("Communication",)),
    "Customer Support": ("business", ("customer service", "customer success"), ("Communication",)),
    "Operations": ("business", ("operations management",), ("Project Management",)),
    "Finance": ("business", ("financial analysis", "fp&a"), ("Excel", "Accounting")),
}


# ---------------------------------------------------------------------------
# Derived lookups, built once at import.
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").replace("_", " ").split())


ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canon, (_cat, _aliases, _rel) in SKILL_ONTOLOGY.items():
    ALIAS_TO_CANONICAL[_norm(_canon)] = _canon
    for _alias in _aliases:
        ALIAS_TO_CANONICAL[_norm(_alias)] = _canon

# Keep punctuation-sensitive forms reachable: "c++", "c#", ".net", "ci/cd".
for _canon in ("C++", "C#", ".NET", "CI/CD", "UI/UX", "Node.js", "Next.js", "Vue.js", "Express.js"):
    ALIAS_TO_CANONICAL[_canon.lower()] = _canon

SKILL_CATEGORY: dict[str, str] = {k: v[0] for k, v in SKILL_ONTOLOGY.items()}
SKILL_RELATED: dict[str, tuple[str, ...]] = {k: v[2] for k, v in SKILL_ONTOLOGY.items()}

# Terms too ambiguous to recognise from running prose.
#
# Free-text scanning cannot tell the programming language Go from the verb
# "go", or the Operations function from "day-to-day operations". Matching these
# bare forms produced real false positives — a senior backend posting listing
# "Operations", "Human Resources" and "Go" as required skills, which then
# polluted the skill-gap analysis with advice to learn Sales and Communication.
#
# These strings are excluded from *text scanning* only. They remain fully
# matchable via `canonicalise()`, so they still work when a candidate lists
# them explicitly in a skills section, and their unambiguous aliases
# ("golang", "r language", "ansi c") are still scanned normally.
# The bar for inclusion is "this token appears in job-posting prose more often
# as an ordinary word than as the skill". Language names like Rust, Swift,
# Scala and Spring do *not* meet it — in a software posting they essentially
# always mean the technology, and excluding them loses real matches. Only
# tokens that genuinely collide are listed.
PROSE_AMBIGUOUS_TERMS: frozenset[str] = frozenset({
    # Single letters and two-letter words, unusable as bare tokens. Their
    # unambiguous aliases ("golang", "r language", "ansi c") still scan.
    "go", "r", "c",
    # Tool names that are far more common as verbs.
    "excel", "access",
    # Generic business and soft-skill nouns that live in boilerplate
    # ("day-to-day operations", "security is everyone's responsibility").
    "operations", "sales", "finance", "accounting", "analytics",
    "communication", "teamwork", "collaboration", "leadership",
    "security", "testing", "qa", "hr", "it",
})

# Longest-first so "machine learning" wins over "learning" during text scanning.
# Ambiguous bare terms are dropped from the scan set.
SCAN_TERMS: list[tuple[str, str]] = sorted(
    (
        (term, canonical)
        for term, canonical in ALIAS_TO_CANONICAL.items()
        if term not in PROSE_AMBIGUOUS_TERMS
    ),
    key=lambda kv: len(kv[0]),
    reverse=True,
)

TECHNICAL_CATEGORIES = {
    "language", "framework", "ml", "database", "cloud", "devops",
    "testing", "concept", "security", "tool", "design",
}

STOP_SKILL_WORDS = {
    "experience", "knowledge", "skills", "good", "strong", "excellent",
    "ability", "work", "team", "years", "year", "plus", "etc", "and", "or",
    "the", "with", "in", "of", "a", "an", "to", "for", "on", "using",
}


def is_technical(canonical: str) -> bool:
    return SKILL_CATEGORY.get(canonical, "other") in TECHNICAL_CATEGORIES


def related_skills(canonical: str) -> Iterable[str]:
    return SKILL_RELATED.get(canonical, ())
