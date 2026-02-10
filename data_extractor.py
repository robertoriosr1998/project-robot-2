"""
Data extraction using GPT4All local LLM.

Model location: ./models/Meta-Llama-3-8B-Instruct.Q4_0.gguf
"""
import json
import re
from pathlib import Path
from gpt4all import GPT4All

_model = None

def get_model(model_name: str = "Meta-Llama-3-8B-Instruct.Q4_0.gguf") -> GPT4All:
    """Get or create GPT4All model instance.
    
    Loads model from ./models/ folder in project directory.
    """
    global _model
    if _model is None:
        local_model_path = Path(__file__).parent / "models" / model_name
        
        if not local_model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {local_model_path}\n"
                f"Expected: {model_name} in ./models/ folder\n"
                f"Current config.py setting: LLM_MODEL = '{model_name}'"
            )
        
        print(f"  Loading LLM model: {model_name}")
        _model = GPT4All(model_name, model_path=str(local_model_path.parent), allow_download=False)
        print(f"  Model loaded successfully!")
    
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
