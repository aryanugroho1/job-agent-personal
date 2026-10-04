import re
from rapidfuzz import fuzz

LEGAL_SUFFIXES = [
    r"\bpt\b", r"\binc\b", r"\bltd\b", r"\bllc\b", r"\bcorp\b", 
    r"\bkk\b", r"\bkabushiki kaisha\b", r"\bgmbh\b", r"\bpte\b", r"\bco\b"
]

def normalize_text(text: str) -> str:
    """
    Normalizes string by lowering case, removing legal suffixes and punctuation.
    """
    if not text:
        return ""
    cleaned = text.lower()
    for suffix in LEGAL_SUFFIXES:
        cleaned = re.sub(suffix, "", cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())

def calculate_jaccard(text1: str, text2: str) -> float:
    """
    Calculates Jaccard similarity of two texts based on word token sets.
    """
    set1 = set(normalize_text(text1).split())
    set2 = set(normalize_text(text2).split())
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return (intersection / union) * 100.0

def is_duplicate(
    job1: dict, 
    job2: dict, 
    company_threshold: int = 85, 
    role_threshold: int = 80, 
    jaccard_threshold: int = 75
) -> bool:
    """
    Evaluates if two job postings represent the same vacancy across platforms.
    """
    c1 = normalize_text(job1.get("company", ""))
    c2 = normalize_text(job2.get("company", ""))
    
    r1 = normalize_text(job1.get("role_title", ""))
    r2 = normalize_text(job2.get("role_title", ""))

    if not c1 or not c2 or not r1 or not r2:
        return False

    comp_ratio = fuzz.token_sort_ratio(c1, c2)
    role_ratio = fuzz.token_sort_ratio(r1, r2)

    if comp_ratio >= company_threshold and role_ratio >= role_threshold:
        # Check description similarity if both have JD excerpt
        jd1 = job1.get("description", "")
        jd2 = job2.get("description", "")
        if jd1 and jd2:
            jaccard = calculate_jaccard(jd1, jd2)
            if jaccard >= jaccard_threshold:
                return True
        else:
            return True

    return False
