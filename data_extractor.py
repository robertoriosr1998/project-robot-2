import json
import re
from gpt4all import GPT4All

_model = None

def get_model(model_name: str = "Meta-Llama-3-8B-Instruct.Q4_0.gguf") -> GPT4All:
    """Get or create GPT4All model instance."""
    global _model
    if _model is None:
        _model = GPT4All(model_name)
    return _model

def extract_structured_data(text: str, extraction_prompt: str, model_name: str = None) -> dict:
    """Use LLM to extract specific fields from OCR text.
    
    Expected output fields (CN Database columns 3-14):
    - is_cn: Is this a Confirmation Note?
    - operation_type: Type of operation
    - is_multiseries: Is it a multiseries transaction?
    - currency: Transaction currency
    - gross_amount: Gross amount
    - net_amount: Net amount
    - units: Number of units
    - equalization: Equalization value
    - fees: Associated fees
    - nav_price: NAV price
    - nav_date: NAV date
    - settlement_date: Settlement date
    """
    model = get_model(model_name) if model_name else get_model()
    
    prompt = f"""{extraction_prompt}

Document text:
---
{text[:4000]}  # Limit context length
---

Respond with ONLY valid JSON, no other text:"""

    response = model.generate(prompt, max_tokens=500, temp=0.1)
    return parse_json_response(response)

def parse_json_response(response: str) -> dict:
    """Extract JSON from LLM response."""
    # Try to find JSON in response
    try:
        # Look for JSON object pattern
        match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group())
    except json.JSONDecodeError:
        pass
    
    return {"raw_response": response, "parse_error": True}
