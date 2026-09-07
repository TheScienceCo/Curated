"""Normalised skill ontology, alias resolution and text-based skill mining.

Everything here is deterministic. The LLM may *propose* skills, but they are
always funnelled through `normalize_skill` so downstream scoring compares
apples to apples ("ReactJS", "React.js" and "React" are one skill).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.enums import ProofabilityTier


@dataclass(frozen=True)
class Skill:
    """One node in the skill taxonomy."""

    slug: str
    label: str
    category: str
    #: How quickly a competent engineer can *demonstrate* this without formal
    #: years of experience. Drives the Proofability score.
    proofability: float  # 0.0 (hard gate) .. 1.0 (trivially demonstrable)
    aliases: tuple[str, ...] = ()
    #: Rough market value signal used by the Career Capital score.
    career_capital: float = 0.5
    #: Suggested way to prove it in an interview loop.
    proof_project: str | None = None
    learning_difficulty: str = "moderate"  # low | moderate | high | gated


CATEGORY_SOFTWARE = "software"
CATEGORY_AI = "ai"
CATEGORY_CYBER = "cyber"
CATEGORY_INTELLIGENCE = "intelligence"
CATEGORY_SCIENCE = "science"
CATEGORY_BUSINESS = "business"
CATEGORY_CREDENTIAL = "credential"


def _s(
    slug: str,
    label: str,
    category: str,
    proofability: float,
    aliases: tuple[str, ...] = (),
    career_capital: float = 0.5,
    proof_project: str | None = None,
    learning_difficulty: str = "moderate",
) -> Skill:
    return Skill(
        slug=slug,
        label=label,
        category=category,
        proofability=proofability,
        aliases=aliases,
        career_capital=career_capital,
        proof_project=proof_project,
        learning_difficulty=learning_difficulty,
    )


SKILLS: tuple[Skill, ...] = (
    # --- Software ---------------------------------------------------------
    _s(
        "python",
        "Python",
        CATEGORY_SOFTWARE,
        0.95,
        ("py", "python3"),
        0.8,
        "Ship a typed FastAPI service with tests and CI.",
        "low",
    ),
    _s(
        "typescript",
        "TypeScript",
        CATEGORY_SOFTWARE,
        0.9,
        ("ts", "type script"),
        0.75,
        "Port a JS project to strict TypeScript; publish the diff.",
        "low",
    ),
    _s(
        "javascript",
        "JavaScript",
        CATEGORY_SOFTWARE,
        0.9,
        ("js", "ecmascript", "node.js", "nodejs", "node"),
        0.6,
        "Build a small SPA without a framework.",
        "low",
    ),
    _s(
        "react",
        "React",
        CATEGORY_SOFTWARE,
        0.88,
        ("reactjs", "react.js"),
        0.7,
        "Build a data-dense dashboard with hooks and suspense.",
        "low",
    ),
    _s(
        "nextjs",
        "Next.js",
        CATEGORY_SOFTWARE,
        0.85,
        ("next", "next.js", "nextjs app router"),
        0.7,
        "Deploy an App-Router site with server components and auth.",
        "low",
    ),
    _s(
        "fastapi",
        "FastAPI",
        CATEGORY_SOFTWARE,
        0.92,
        ("fast api",),
        0.65,
        "Expose a typed REST API with Pydantic validation and OpenAPI docs.",
        "low",
    ),
    _s(
        "c",
        "C",
        CATEGORY_SOFTWARE,
        0.6,
        (),
        0.6,
        "Write a small parser or allocator with fuzzing.",
        "high",
    ),
    _s(
        "cpp",
        "C++",
        CATEGORY_SOFTWARE,
        0.6,
        ("c++", "cplusplus", "c plus plus"),
        0.75,
        "Implement a performance-sensitive data structure with benchmarks.",
        "high",
    ),
    _s(
        "rust",
        "Rust",
        CATEGORY_SOFTWARE,
        0.65,
        (),
        0.75,
        "Rewrite a hot path in Rust and publish the benchmark.",
        "high",
    ),
    _s(
        "go",
        "Go",
        CATEGORY_SOFTWARE,
        0.8,
        ("golang",),
        0.65,
        "Build a concurrent service with graceful shutdown.",
        "low",
    ),
    _s("java", "Java", CATEGORY_SOFTWARE, 0.75, (), 0.5, None, "moderate"),
    _s(
        "sql",
        "SQL",
        CATEGORY_SOFTWARE,
        0.9,
        ("postgres", "postgresql", "mysql", "sqlite"),
        0.55,
        "Model a schema and optimise a slow analytical query with EXPLAIN.",
        "low",
    ),
    _s(
        "apis",
        "API design",
        CATEGORY_SOFTWARE,
        0.88,
        ("api", "rest", "rest api", "restful", "graphql"),
        0.6,
        "Publish a versioned API with an OpenAPI contract.",
        "low",
    ),
    _s(
        "system_design",
        "System design",
        CATEGORY_SOFTWARE,
        0.75,
        ("architecture", "distributed systems", "technical architecture"),
        0.8,
        "Write a design doc for a system you actually built.",
        "moderate",
    ),
    _s(
        "algorithms",
        "Algorithms & data structures",
        CATEGORY_SOFTWARE,
        0.85,
        ("data structures", "dsa"),
        0.5,
        "Interview-style practice plus one non-trivial implementation.",
        "low",
    ),
    _s("git", "Git", CATEGORY_SOFTWARE, 0.95, ("github", "version control"), 0.35, None, "low"),
    _s(
        "cicd",
        "CI/CD",
        CATEGORY_SOFTWARE,
        0.85,
        ("ci", "cd", "ci/cd", "continuous integration", "github actions", "gitlab ci", "jenkins"),
        0.5,
        "Wire a repo to lint + test + build + deploy on every push.",
        "low",
    ),
    _s(
        "docker",
        "Docker",
        CATEGORY_SOFTWARE,
        0.9,
        ("containers", "containerization"),
        0.5,
        "Containerise a multi-service app with compose.",
        "low",
    ),
    _s(
        "kubernetes",
        "Kubernetes",
        CATEGORY_SOFTWARE,
        0.7,
        ("k8s", "eks", "gke"),
        0.65,
        "Deploy a stateful workload with health checks and autoscaling.",
        "moderate",
    ),
    _s(
        "cloud",
        "Cloud architecture",
        CATEGORY_SOFTWARE,
        0.75,
        ("aws", "azure", "gcp", "google cloud", "cloud deployment", "cloud infrastructure"),
        0.7,
        "Deploy a production-shaped stack with IaC.",
        "moderate",
    ),
    _s(
        "terraform",
        "Terraform / IaC",
        CATEGORY_SOFTWARE,
        0.8,
        ("iac", "infrastructure as code", "pulumi", "cloudformation"),
        0.55,
        None,
        "low",
    ),
    _s(
        "fullstack",
        "Full-stack engineering",
        CATEGORY_SOFTWARE,
        0.8,
        (
            "full stack",
            "full-stack",
            "full stack engineering",
            "full-stack engineering",
            "frontend and backend",
        ),
        0.75,
        "Ship an end-to-end product: schema, API, UI, deploy.",
        "moderate",
    ),
    _s(
        "data_engineering",
        "Data engineering",
        CATEGORY_SOFTWARE,
        0.75,
        ("etl", "elt", "data pipelines", "airflow", "spark"),
        0.6,
        None,
        "moderate",
    ),
    # --- AI ---------------------------------------------------------------
    _s(
        "llms",
        "LLMs",
        CATEGORY_AI,
        0.9,
        ("llm", "large language models", "genai", "gen ai", "generative ai", "foundation models"),
        0.95,
        "Ship an evaluated LLM feature with guardrails.",
        "low",
    ),
    _s(
        "rag",
        "RAG",
        CATEGORY_AI,
        0.9,
        ("retrieval augmented generation", "retrieval-augmented generation", "retrieval augmented"),
        0.85,
        "Build a grounded retrieval system with citation accuracy metrics.",
        "low",
    ),
    _s(
        "embeddings",
        "Embeddings",
        CATEGORY_AI,
        0.9,
        ("vector embeddings", "semantic search"),
        0.7,
        "Build semantic search with recall@k measured.",
        "low",
    ),
    _s(
        "vector_databases",
        "Vector databases",
        CATEGORY_AI,
        0.9,
        ("vector db", "vector database", "pgvector", "pinecone", "weaviate", "qdrant", "chroma"),
        0.6,
        "Benchmark two vector stores on the same corpus.",
        "low",
    ),
    _s(
        "prompt_engineering",
        "Prompt engineering",
        CATEGORY_AI,
        0.95,
        ("prompting", "prompt design"),
        0.5,
        "Publish a prompt suite with an eval harness.",
        "low",
    ),
    _s(
        "fine_tuning",
        "Fine-tuning",
        CATEGORY_AI,
        0.7,
        ("finetuning", "fine tuning", "sft", "lora", "peft"),
        0.8,
        "Fine-tune a small open model and report eval deltas.",
        "moderate",
    ),
    _s(
        "agents",
        "Agentic systems",
        CATEGORY_AI,
        0.85,
        (
            "agent",
            "agents",
            "agentic",
            "agentic ai",
            "agentic systems",
            "ai agents",
            "multi-agent",
            "multi agent",
        ),
        0.95,
        "Build a tool-calling agent with traces and failure analysis.",
        "low",
    ),
    _s(
        "tool_calling",
        "Tool calling",
        CATEGORY_AI,
        0.9,
        ("function calling", "tool use", "structured outputs"),
        0.7,
        "Implement schema-validated tool calls with retries.",
        "low",
    ),
    _s(
        "evaluation",
        "Model evaluation",
        CATEGORY_AI,
        0.85,
        ("evals", "eval", "llm evaluation", "benchmarking models"),
        0.85,
        "Build an offline eval set with regression tracking.",
        "moderate",
    ),
    _s(
        "grounding",
        "Grounding & citation",
        CATEGORY_AI,
        0.85,
        ("hallucination mitigation",),
        0.7,
        None,
        "moderate",
    ),
    _s(
        "human_in_the_loop",
        "Human-in-the-loop systems",
        CATEGORY_AI,
        0.85,
        ("hitl", "human in the loop"),
        0.7,
        None,
        "low",
    ),
    _s(
        "pytorch",
        "PyTorch",
        CATEGORY_AI,
        0.8,
        ("torch",),
        0.8,
        "Train and profile a model end to end.",
        "moderate",
    ),
    _s("tensorflow", "TensorFlow", CATEGORY_AI, 0.75, ("tf", "keras"), 0.55, None, "moderate"),
    _s(
        "scikit_learn",
        "scikit-learn",
        CATEGORY_AI,
        0.9,
        ("sklearn", "scikit learn"),
        0.5,
        None,
        "low",
    ),
    _s(
        "machine_learning",
        "Machine learning",
        CATEGORY_AI,
        0.75,
        ("ml", "applied ml", "applied machine learning", "deep learning", "dl", "ai/ml", "ai"),
        0.9,
        "Ship a model with measured business impact.",
        "moderate",
    ),
    _s("nlp", "NLP", CATEGORY_AI, 0.8, ("natural language processing",), 0.7, None, "moderate"),
    _s(
        "computer_vision",
        "Computer vision",
        CATEGORY_AI,
        0.7,
        ("cv", "image recognition"),
        0.7,
        None,
        "moderate",
    ),
    _s(
        "mlops",
        "MLOps",
        CATEGORY_AI,
        0.8,
        ("ml ops", "model deployment", "model serving"),
        0.7,
        None,
        "moderate",
    ),
    # --- Cyber ------------------------------------------------------------
    _s(
        "ghidra",
        "Ghidra",
        CATEGORY_CYBER,
        0.8,
        (),
        0.75,
        "Publish a write-up reversing a crackme or real sample.",
        "moderate",
    ),
    _s(
        "ida",
        "IDA Pro",
        CATEGORY_CYBER,
        0.75,
        ("ida pro", "binary ninja", "binaryninja"),
        0.7,
        None,
        "moderate",
    ),
    _s(
        "x86",
        "x86/x64 assembly",
        CATEGORY_CYBER,
        0.65,
        ("x86/x64", "x64", "assembly", "asm"),
        0.7,
        "Hand-analyse a small binary and document the control flow.",
        "high",
    ),
    _s(
        "malware_analysis",
        "Malware analysis",
        CATEGORY_CYBER,
        0.7,
        ("malware", "malware analyst", "static analysis", "dynamic analysis"),
        0.85,
        "Analyse a public sample end to end and publish IOCs.",
        "high",
    ),
    _s(
        "reverse_engineering",
        "Reverse engineering",
        CATEGORY_CYBER,
        0.7,
        ("re", "binary analysis", "reversing"),
        0.85,
        "Reverse a protocol or binary and publish the notes.",
        "high",
    ),
    _s(
        "vulnerability_research",
        "Vulnerability research",
        CATEGORY_CYBER,
        0.55,
        ("vuln research", "vr", "exploit development", "bug hunting", "fuzzing"),
        0.95,
        "Find and responsibly disclose a real bug; a CVE is the proof.",
        "high",
    ),
    _s(
        "yara",
        "YARA",
        CATEGORY_CYBER,
        0.9,
        ("yara rules",),
        0.5,
        "Write and validate detection rules against a sample corpus.",
        "low",
    ),
    _s(
        "windows_internals",
        "Windows internals",
        CATEGORY_CYBER,
        0.6,
        ("win32", "windows kernel"),
        0.75,
        None,
        "high",
    ),
    _s(
        "packet_analysis",
        "Packet analysis",
        CATEGORY_CYBER,
        0.85,
        ("wireshark", "pcap", "network forensics"),
        0.5,
        None,
        "low",
    ),
    _s(
        "mitre_attack",
        "MITRE ATT&CK",
        CATEGORY_CYBER,
        0.9,
        ("attack framework", "att&ck"),
        0.5,
        None,
        "low",
    ),
    _s(
        "threat_intelligence",
        "Threat intelligence",
        CATEGORY_CYBER,
        0.8,
        ("cti", "cyber threat intelligence", "threat intel"),
        0.75,
        None,
        "moderate",
    ),
    _s(
        "incident_response",
        "Incident response",
        CATEGORY_CYBER,
        0.7,
        ("ir", "dfir", "forensics"),
        0.65,
        None,
        "moderate",
    ),
    _s(
        "appsec",
        "Application security",
        CATEGORY_CYBER,
        0.8,
        ("application security", "secure coding", "sast", "pentesting", "penetration testing"),
        0.7,
        None,
        "moderate",
    ),
    _s(
        "ai_security",
        "AI/ML security",
        CATEGORY_CYBER,
        0.85,
        ("ai security", "prompt injection", "model security", "red teaming llms"),
        0.9,
        "Publish a red-team eval of an LLM app.",
        "moderate",
    ),
    # --- Intelligence ------------------------------------------------------
    _s(
        "humint",
        "HUMINT",
        CATEGORY_INTELLIGENCE,
        0.3,
        ("human intelligence", "source operations"),
        0.7,
        None,
        "gated",
    ),
    _s(
        "osint",
        "OSINT",
        CATEGORY_INTELLIGENCE,
        0.85,
        ("open source intelligence",),
        0.6,
        "Publish a sourced OSINT analysis product.",
        "low",
    ),
    _s("docex", "DOCEX", CATEGORY_INTELLIGENCE, 0.4, ("document exploitation",), 0.5, None, "high"),
    _s(
        "all_source",
        "All-source intelligence",
        CATEGORY_INTELLIGENCE,
        0.4,
        ("all source", "all-source analysis", "intelligence analysis"),
        0.65,
        None,
        "high",
    ),
    _s(
        "targeting",
        "Targeting",
        CATEGORY_INTELLIGENCE,
        0.35,
        ("target development",),
        0.7,
        None,
        "gated",
    ),
    _s(
        "link_analysis",
        "Link analysis",
        CATEGORY_INTELLIGENCE,
        0.7,
        ("network analysis", "graph analysis", "analyst notebook"),
        0.55,
        None,
        "moderate",
    ),
    _s(
        "intel_reporting",
        "Intelligence reporting",
        CATEGORY_INTELLIGENCE,
        0.45,
        ("reporting", "intelligence writing"),
        0.5,
        "Write a finished analytic product to standard on an unclassified topic.",
        "high",
    ),
    _s(
        "mandarin",
        "Mandarin",
        CATEGORY_INTELLIGENCE,
        0.2,
        ("chinese", "mandarin chinese", "putonghua"),
        0.8,
        None,
        "high",
    ),
    # --- Science ----------------------------------------------------------
    _s("biochemistry", "Biochemistry", CATEGORY_SCIENCE, 0.3, (), 0.55, None, "high"),
    _s(
        "stem_cells", "Stem cell biology", CATEGORY_SCIENCE, 0.2, ("stem cell",), 0.55, None, "high"
    ),
    _s("tissue_engineering", "Tissue engineering", CATEGORY_SCIENCE, 0.2, (), 0.55, None, "high"),
    _s(
        "molecular_biology",
        "Molecular biology",
        CATEGORY_SCIENCE,
        0.3,
        ("molbio",),
        0.55,
        None,
        "high",
    ),
    _s("peptide_chemistry", "Peptide chemistry", CATEGORY_SCIENCE, 0.2, (), 0.5, None, "high"),
    _s(
        "analytical_chemistry",
        "Analytical chemistry",
        CATEGORY_SCIENCE,
        0.25,
        (),
        0.5,
        None,
        "high",
    ),
    _s(
        "lcms",
        "LC-MS",
        CATEGORY_SCIENCE,
        0.2,
        ("lc-ms", "lc/ms", "liquid chromatography"),
        0.5,
        None,
        "high",
    ),
    _s("gcms", "GC-MS", CATEGORY_SCIENCE, 0.2, ("gc-ms", "gc/ms"), 0.5, None, "high"),
    _s(
        "biomedical_engineering",
        "Biomedical engineering",
        CATEGORY_SCIENCE,
        0.3,
        ("bme",),
        0.55,
        None,
        "high",
    ),
    _s(
        "computational_biology",
        "Computational biology",
        CATEGORY_SCIENCE,
        0.6,
        ("bioinformatics", "comp bio", "compbio"),
        0.85,
        "Reproduce a published analysis on public data.",
        "moderate",
    ),
    _s(
        "drug_discovery",
        "Drug discovery",
        CATEGORY_SCIENCE,
        0.4,
        ("pharma research", "medicinal chemistry"),
        0.75,
        None,
        "high",
    ),
    _s("biosecurity", "Biosecurity", CATEGORY_SCIENCE, 0.5, ("biodefense",), 0.8, None, "high"),
    # --- Business / customer ----------------------------------------------
    _s(
        "customer_facing",
        "Customer-facing technical delivery",
        CATEGORY_BUSINESS,
        0.7,
        (
            "customer facing",
            "client facing",
            "client-facing",
            "customer-facing technical delivery",
            "stakeholder management",
            "customer engagement",
        ),
        0.85,
        "Own a deployment with a named external customer.",
        "moderate",
    ),
    _s(
        "solutions_engineering",
        "Solutions engineering",
        CATEGORY_BUSINESS,
        0.7,
        ("sales engineering", "pre-sales", "presales", "solution architecture"),
        0.8,
        None,
        "moderate",
    ),
    _s(
        "technical_sales",
        "Technical sales",
        CATEGORY_BUSINESS,
        0.6,
        ("enterprise sales", "quota carrying", "revenue ownership"),
        0.8,
        None,
        "moderate",
    ),
    _s(
        "product_management",
        "Product management",
        CATEGORY_BUSINESS,
        0.6,
        ("product ownership", "pm", "product strategy"),
        0.75,
        None,
        "moderate",
    ),
    _s(
        "program_management",
        "Program management",
        CATEGORY_BUSINESS,
        0.65,
        ("project management", "technical program management", "tpm"),
        0.6,
        None,
        "moderate",
    ),
    _s(
        "leadership",
        "Technical leadership",
        CATEGORY_BUSINESS,
        0.5,
        ("team lead", "tech lead", "engineering management", "people management"),
        0.85,
        None,
        "high",
    ),
    _s(
        "business_development",
        "Business development",
        CATEGORY_BUSINESS,
        0.6,
        ("bd", "partnerships", "strategic partnerships", "capture management"),
        0.75,
        None,
        "moderate",
    ),
    _s(
        "govt_contracting",
        "Government contracting",
        CATEGORY_BUSINESS,
        0.5,
        ("federal contracting", "govcon", "far", "dfars", "seta"),
        0.5,
        None,
        "moderate",
    ),
    # --- Credentials (hard gates) ------------------------------------------
    _s(
        "phd",
        "PhD",
        CATEGORY_CREDENTIAL,
        0.0,
        ("doctorate", "ph.d", "ph.d.", "doctoral"),
        0.7,
        None,
        "gated",
    ),
    _s(
        "md_license",
        "Medical license",
        CATEGORY_CREDENTIAL,
        0.0,
        ("medical license", "board certification", "board certified", "md", "licensed physician"),
        0.6,
        None,
        "gated",
    ),
    _s(
        "bar_license",
        "Legal bar license",
        CATEGORY_CREDENTIAL,
        0.0,
        ("bar admission", "jd required"),
        0.5,
        None,
        "gated",
    ),
    _s(
        "pe_license",
        "Professional Engineer license",
        CATEGORY_CREDENTIAL,
        0.0,
        ("pe license",),
        0.4,
        None,
        "gated",
    ),
    _s("cissp", "CISSP", CATEGORY_CREDENTIAL, 0.3, (), 0.4, None, "high"),
    _s(
        "security_plus",
        "Security+",
        CATEGORY_CREDENTIAL,
        0.7,
        ("comptia security+", "sec+"),
        0.25,
        "Sit the exam; ~4-6 weeks of study.",
        "low",
    ),
    _s(
        "aws_cert",
        "AWS certification",
        CATEGORY_CREDENTIAL,
        0.7,
        ("aws certified", "solutions architect associate"),
        0.3,
        None,
        "low",
    ),
)


SKILLS_BY_SLUG: dict[str, Skill] = {s.slug: s for s in SKILLS}

#: alias (lowercased) -> canonical slug. Built once at import time.
_ALIAS_INDEX: dict[str, str] = {}
for _skill in SKILLS:
    _ALIAS_INDEX[_skill.slug.replace("_", " ")] = _skill.slug
    _ALIAS_INDEX[_skill.slug] = _skill.slug
    _ALIAS_INDEX[_skill.label.lower()] = _skill.slug
    for _alias in _skill.aliases:
        _ALIAS_INDEX[_alias.lower()] = _skill.slug


#: Extra alias mappings that are phrases rather than skill names, e.g. the
#: clearance shorthand the spec calls out ("CI Poly" -> Counterintelligence
#: Polygraph). These are resolved by `normalize_phrase` rather than
#: `normalize_skill` because they are not skills.
PHRASE_ALIASES: dict[str, str] = {
    "ci poly": "Counterintelligence Polygraph",
    "ci polygraph": "Counterintelligence Polygraph",
    "counterintelligence poly": "Counterintelligence Polygraph",
    "fsp": "Full Scope Polygraph",
    "full scope poly": "Full Scope Polygraph",
    "esp": "Expanded Scope Polygraph",
    "ts/sci": "Top Secret / SCI",
    "tssci": "Top Secret / SCI",
    "genai": "generative AI",
    "gen ai": "generative AI",
    "ml": "machine learning",
    "reactjs": "React",
    "fde": "Forward Deployed Engineer",
    "mts": "Member of Technical Staff",
    "yoe": "years of experience",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def normalize_skill(raw: str) -> str | None:
    """Resolve a free-text skill mention to a canonical slug, or None."""
    if not raw:
        return None
    candidate = _clean(raw)
    candidate = candidate.strip(" .,;:()[]{}\"'")
    if candidate in _ALIAS_INDEX:
        return _ALIAS_INDEX[candidate]
    # Try a few light morphological variants before giving up.
    for variant in (
        candidate.replace("-", " "),
        candidate.replace("-", ""),
        candidate.replace(".", ""),
        candidate.replace(" ", "_"),
        candidate.rstrip("s"),
        candidate + "s",
    ):
        if variant in _ALIAS_INDEX:
            return _ALIAS_INDEX[variant]
    # "5+ years of Python" -> python
    stripped = re.sub(
        r"^(?:\d+\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience\s*(?:in|with)?\s*)?)",
        "",
        candidate,
    ).strip()
    if stripped and stripped != candidate:
        return normalize_skill(stripped)
    return None


def normalize_phrase(raw: str) -> str:
    """Expand common domain shorthand into its full form for display."""
    return PHRASE_ALIASES.get(_clean(raw), raw)


def normalize_skills(raws: list[str]) -> list[str]:
    """Normalise a list of skill mentions, preserving order and de-duplicating."""
    out: list[str] = []
    for raw in raws:
        slug = normalize_skill(raw)
        if slug and slug not in out:
            out.append(slug)
    return out


def label_for(slug: str) -> str:
    skill = SKILLS_BY_SLUG.get(slug)
    return skill.label if skill else slug.replace("_", " ").title()


def get_skill(slug: str) -> Skill | None:
    return SKILLS_BY_SLUG.get(slug)


# --------------------------------------------------------------------------
# Free-text mining
# --------------------------------------------------------------------------

#: Short aliases that are real skill names but far too ambiguous to mine from
#: prose. They stay resolvable through `normalize_skill` (where the caller has
#: already asserted "this string is a skill") but are never matched against
#: free text. Learned the hard way: "MD" matched the state abbreviation in
#: "Annapolis Junction, MD", and "re" matched the tail of "We're".
MINING_DENYLIST = frozenset(
    {"re", "ir", "cv", "cd", "ci", "pm", "bd", "vr", "esp", "md", "tf", "ts", "dl", "tc", "sec+"}
)

#: Short aliases worth mining, but only in their canonical capitalisation.
#: "AI" is a skill; "ai" inside a lowercase word is noise. The value is the
#: exact form that must appear in the text.
CASE_SENSITIVE_MINING: dict[str, str] = {
    "c": "C",
    "c++": "C++",
    "ml": "ML",
    "ai": "AI",
    "js": "JS",
    "go": "Go",
    "ida": "IDA",
    "fsp": "FSP",
    "sql": "SQL",
}

#: Boundary that also rejects apostrophes, so "We're" cannot yield "re".
_LEFT_BOUNDARY = r"(?<![\w'\u2019])"


def _right_boundary(alias: str) -> str:
    """Reject a trailing word char, apostrophe, and - for plain-letter aliases
    - a trailing ``+`` or ``#`` so "C" does not match inside "C++" or "C#"."""
    extra = "" if any(ch in alias for ch in "+#") else "+#"
    return r"(?!['\u2019" + extra + r"]?[\w])" if not extra else r"(?![\w'\u2019+#])"


def _mention_pattern(alias: str) -> re.Pattern[str] | None:
    """Compile a free-text matcher for one alias, or None if it is unminable."""
    if alias in MINING_DENYLIST:
        return None
    canonical = CASE_SENSITIVE_MINING.get(alias)
    if len(alias) < 2 and canonical is None:
        return None
    if len(alias) <= 3 and canonical is None and alias.isalpha():
        # Any other very short alphabetic alias is too noisy to mine.
        return None
    body = re.escape(canonical if canonical else alias)
    body = body.replace("\\ ", "[\\s\\-/]+").replace(" ", "[\\s\\-/]+")
    flags = 0 if canonical else re.IGNORECASE
    return re.compile(_LEFT_BOUNDARY + body + _right_boundary(alias), flags)


# Longest-first so "machine learning" wins over "ml" inside the same span, and
# so multi-word aliases are matched before their single-word substrings.
_MENTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = []
for _alias, _slug in sorted(_ALIAS_INDEX.items(), key=lambda kv: -len(kv[0])):
    _pattern = _mention_pattern(_alias)
    if _pattern is not None:
        _MENTION_PATTERNS.append((_slug, _pattern))


def extract_skills_from_text(text: str) -> list[str]:
    """Mine canonical skill slugs from free text.

    Deterministic and order-preserving: skills come back in the order they
    first appear, which keeps explanations readable.
    """
    if not text:
        return []
    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    for slug, pattern in _MENTION_PATTERNS:
        if slug in seen:
            continue
        match = pattern.search(text)
        if match:
            seen.add(slug)
            hits.append((match.start(), slug))
    return [slug for _, slug in sorted(hits)]


#: Holding a skill on the left implies competence in the skills on the right.
#: Without this, a candidate with LLMs, RAG and agents on their profile reads
#: as "missing machine learning", which is nonsense.
IMPLIES: dict[str, tuple[str, ...]] = {
    "llms": ("machine_learning", "nlp"),
    "rag": ("embeddings", "llms", "vector_databases", "machine_learning"),
    "agents": ("llms", "tool_calling", "prompt_engineering", "machine_learning"),
    "fine_tuning": ("machine_learning", "pytorch"),
    "pytorch": ("machine_learning",),
    "tensorflow": ("machine_learning",),
    "scikit_learn": ("machine_learning",),
    "nlp": ("machine_learning",),
    "computer_vision": ("machine_learning",),
    "mlops": ("machine_learning", "cicd"),
    "prompt_engineering": ("llms",),
    "tool_calling": ("llms", "apis"),
    "evaluation": ("machine_learning",),
    "nextjs": ("react", "javascript", "fullstack"),
    "react": ("javascript",),
    "typescript": ("javascript",),
    "fastapi": ("python", "apis"),
    "kubernetes": ("docker", "cloud"),
    "terraform": ("cloud",),
    "malware_analysis": ("reverse_engineering",),
    "ghidra": ("reverse_engineering",),
    "ida": ("reverse_engineering",),
    "vulnerability_research": ("reverse_engineering", "appsec"),
    "computational_biology": ("molecular_biology",),
    "solutions_engineering": ("customer_facing",),
    "technical_sales": ("customer_facing",),
    "all_source": ("intel_reporting",),
}


def expand_skills(slugs: set[str] | list[str]) -> set[str]:
    """Close a skill set over the implication map.

    Applied once (not transitively to a fixed point) - the map is shallow by
    design, and one hop covers every relationship worth asserting.
    """
    expanded = set(slugs)
    for slug in list(expanded):
        expanded.update(IMPLIES.get(slug, ()))
    return expanded


@dataclass
class SkillGap:
    """One requirement the candidate does not currently hold."""

    slug: str
    label: str
    tier: ProofabilityTier
    proofability: float
    learning_difficulty: str
    how_to_demonstrate: str | None = None
    suggested_project: str | None = None
    interview_readiness: str = "unknown"
    notes: list[str] = field(default_factory=list)


#: Above this a gap is considered closable by demonstration alone.
PROOFABLE_THRESHOLD = 0.55
#: At or below this it is a hard gate (credentials, licences, polygraphs).
HARD_GATE_THRESHOLD = 0.15


def classify_gap(slug: str) -> SkillGap:
    """Bucket a missing skill into demonstrated / proofable / hard gate."""
    skill = SKILLS_BY_SLUG.get(slug)
    if skill is None:
        # Unknown skills are assumed moderately proofable: an unrecognised
        # technology is far more often a library than a licence.
        return SkillGap(
            slug=slug,
            label=label_for(slug),
            tier=ProofabilityTier.PROOFABLE,
            proofability=0.6,
            learning_difficulty="moderate",
            how_to_demonstrate="Build a small public project exercising this and link it.",
            interview_readiness="2-4 weeks",
        )
    if skill.proofability <= HARD_GATE_THRESHOLD:
        tier = ProofabilityTier.HARD_GATE
    elif skill.proofability >= PROOFABLE_THRESHOLD:
        tier = ProofabilityTier.PROOFABLE
    else:
        # The awkward middle: possible, but not on interview-loop timescales.
        # "gated" here means an external body controls access (a cleared
        # program, a licensing board) - not merely "this takes a long time".
        tier = (
            ProofabilityTier.HARD_GATE
            if skill.learning_difficulty == "gated"
            else ProofabilityTier.PROOFABLE
        )
    return SkillGap(
        slug=skill.slug,
        label=skill.label,
        tier=tier,
        proofability=skill.proofability,
        learning_difficulty=skill.learning_difficulty,
        how_to_demonstrate=skill.proof_project,
        suggested_project=skill.proof_project,
        interview_readiness=_readiness(skill),
    )


def _readiness(skill: Skill) -> str:
    if skill.learning_difficulty == "gated":
        return "not achievable by demonstration"
    if skill.proofability >= 0.85:
        return "1-2 weeks of focused work"
    if skill.proofability >= 0.7:
        return "2-6 weeks of focused work"
    if skill.proofability >= 0.55:
        return "1-3 months of focused work"
    return "6+ months"


__all__ = [
    "Skill",
    "SKILLS",
    "SKILLS_BY_SLUG",
    "SkillGap",
    "PHRASE_ALIASES",
    "normalize_skill",
    "normalize_skills",
    "normalize_phrase",
    "extract_skills_from_text",
    "classify_gap",
    "label_for",
    "get_skill",
    "IMPLIES",
    "expand_skills",
    "PROOFABLE_THRESHOLD",
    "HARD_GATE_THRESHOLD",
    "MINING_DENYLIST",
    "CASE_SENSITIVE_MINING",
]
