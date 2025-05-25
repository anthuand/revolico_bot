"""
Groq Client Utility Module
-------------------------
Provides functions to interact with Groq LLM for HTML analysis and general responses.
All code is documented and follows PEP8 and best practices.
"""

import os
from groq import Groq
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SCRAPING_LLM = os.environ.get("SCRAPPING_LLM")
RESPONSES_LLM = os.environ.get("RESPONSES_LLM")

client = Groq(api_key=GROQ_API_KEY)

def groq_chat_completion(messages: List[Dict[str, Any]], model: Optional[str] = None, **kwargs) -> str:
    """
    Sends a chat completion request to Groq LLM and returns the response content.
    """
    if not model:
        model = RESPONSES_LLM
    response = client.chat.completions.create(
        messages=messages,
        model=model,
        **kwargs
    )
    return response.choices[0].message.content

def analyze_html_with_llm(html: str, query: str) -> str:
    """
    Uses the scraping LLM to analyze HTML and answer a query.
    """
    messages = [
        {"role": "system", "content": "You are an expert in scraping and HTML analysis."},
        {"role": "user", "content": f"Analyze the following HTML and answer the query: {query}\n\nHTML:\n{html}"}
    ]
    return groq_chat_completion(messages, model=SCRAPING_LLM)

def general_response_llm(prompt: str) -> str:
    """
    Uses the responses LLM to answer a general prompt.
    """
    messages = [
        {"role": "user", "content": prompt}
    ]
    return groq_chat_completion(messages, model=RESPONSES_LLM) 