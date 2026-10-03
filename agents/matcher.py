import os
import json

def evaluate_job_match(master_cv: dict, job_post: dict, model: str | None = None) -> dict:
    """
    Evaluates job description against Master CV using LLM (Gemini or OpenAI).
    Returns:
      - match_score (0-100)
      - reasoning
      - tailored_role_title
      - tailored_summary
      - ats_keywords
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    prompt = f"""
You are an expert ATS & Telecom/Data Engineering Career Advisor.
Evaluate the fit between the Candidate Profile and the Job Posting.

CANDIDATE PROFILE:
Name: {master_cv['candidate']['name']}
Baseline Summary: {master_cv['summary']['baseline']}
Core Competencies: {json.dumps(master_cv['competencies'])}
Experience Highlights: {json.dumps([{'role': exp['role'], 'company': exp['company'], 'highlights': exp['highlights'][:3]} for exp in master_cv['experience'][:3]])}

JOB POSTING:
Company: {job_post.get('company')}
Title: {job_post.get('role_title')}
Description:
{job_post.get('description', '')[:3000]}

OUTPUT INSTRUCTIONS:
Return STRICTLY valid JSON with no markdown wrapping:
{{
  "match_score": <integer from 0 to 100>,
  "reasoning": "<short concise reasoning of match score>",
  "tailored_role_title": "<aligned title for resume header, e.g. Senior Open RAN Engineer or Lead Telecom Data Engineer>",
  "tailored_summary": "<compelling 3-4 sentence professional summary tailored to this exact JD, integrating real candidate metrics like 15% energy reduction or 10M subscribers, without buzzwords>",
  "ats_keywords": ["keyword1", "keyword2", "keyword3"]
}}
"""

    # 1. Use Google Gemini if GEMINI_API_KEY is available
    if gemini_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=gemini_key)
            models_to_try = [model] if model else []
            for default_m in ["gemini-flash-lite-latest", "gemini-3.1-flash-lite-preview", "gemini-flash-latest", "gemini-3-flash-preview"]:
                if default_m not in models_to_try:
                    models_to_try.append(default_m)
            for m in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.2
                        )
                    )
                    return json.loads(response.text)
                except Exception as inner_e:
                    continue
        except Exception as e:
            print(f"[Matcher Error] Gemini evaluation failed: {e}. Trying fallback...")

    # 2. Fallback to OpenAI
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            chosen_model = model or "gpt-4o-mini"
            response = client.chat.completions.create(
                model=chosen_model,
                messages=[
                    {"role": "system", "content": "You are an automated career evaluation engine outputting raw JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[Matcher Error] OpenAI evaluation failed: {e}")

    # Fallback default
    return {
        "match_score": 0,
        "reasoning": "No valid LLM response received",
        "tailored_role_title": job_post.get("role_title", "Senior Telecom & Data Engineer"),
        "tailored_summary": master_cv["summary"]["baseline"],
        "ats_keywords": []
    }
