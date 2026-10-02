import os

FORBIDDEN_WORDS = ["thrilled", "esteemed", "testament", "beacon", "delve", "spearhead", "passionate", "pleased to apply"]

def generate_human_cover_note(role_title: str, company: str, jd_excerpt: str, model: str | None = None) -> str:
    """
    Generates a concise 60-85 words cover note for LinkedIn/Indeed Easy Apply forms.
    Guaranteed free from AI cliches and buzzwords.
    Supports Google Gemini (preferred) or OpenAI.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    prompt = f"""Role: {role_title} | Company: {company} | JD Context: {jd_excerpt[:1500]}
Candidate: Arya Maulana Nugroho, ITIL (Senior Telecom & Data Engineer, Tokyo)

Tuliskan pesan ringkas (maksimal 60–85 kata, 1 paragraf pendek) dalam Bahasa Inggris untuk Hiring Manager / Recruiter:
ATURAN WAJIB:
1. DILARANG menggunakan kata-kata klise khas AI: "thrilled", "esteemed", "testament", "beacon", "delve", "spearhead", "passionate", "I am writing to express my enthusiasm".
2. Tulis seperti seorang senior engineer yang berbicara langsung secara profesional: sebutkan relevansi di Open RAN/RIC atau Big Data Telecom, dan cantumkan 1 pencapaian kuantitatif nyata (misal: Rakuten MVP hemat 15% energi jaringan atau data pipeline 10M subscribers).
3. Tanpa subject line formal, tanpa salam pembuka berbunga-bunga, langsung ke intisari, dan akhiri ringkas dengan "Best, Arya".
"""

    text = ""

    # 1. Use Google Gemini if GEMINI_API_KEY is available
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            models_to_try = [model, "gemini-3-flash-preview", "gemini-flash-latest"] if model else ["gemini-3-flash-preview", "gemini-flash-latest"]
            for m in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=m,
                        contents=prompt,
                    )
                    text = response.text.strip()
                    if text:
                        break
                except Exception as inner_e:
                    continue
        except Exception as e:
            print(f"[Writer Error] Gemini cover note failed: {e}. Trying fallback...")

    # 2. Fallback to OpenAI
    if not text and openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            chosen_model = model or "gpt-4o"
            response = client.chat.completions.create(
                model=chosen_model,
                messages=[
                    {"role": "system", "content": "You write concise, authentic, senior-level professional engineering communications without generic AI tropes."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4
            )
            text = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Writer Error] OpenAI cover note failed: {e}")

    # Fallback template if no LLM returned valid response
    if not text:
        return (
            f"Hi team, I noticed your opening for {role_title} at {company}. "
            "With over 10 years in Telecom & Data Engineering—most recently architecting Non-RT RIC rApps at Rakuten Mobile "
            "where our team achieved a 15% network energy reduction (Rakuten Group MVP)—I would love to bring this expertise to your team. "
            "My resume is attached for your review. Best, Arya"
        )

    # Post-check filter
    for word in FORBIDDEN_WORDS:
        if word in text.lower():
            return (
                f"Hi team, I noticed your opening for {role_title} at {company}. "
                "With over 10 years in Telecom & Data Engineering—most recently architecting Non-RT RIC rApps at Rakuten Mobile "
                "where our team achieved a 15% network energy reduction (Rakuten Group MVP)—I would love to bring this expertise to your team. "
                "My resume is attached for your review. Best, Arya"
            )

    return text
