from pathlib import Path

# OCR settings
OCR_LANGUAGES = ['en']
PDF_DPI = 300

# GPT4ALL model (will download on first run if not present)
LLM_MODEL = "Meta-Llama-3-8B-Instruct.Q4_0.gguf"

# Extraction prompt - CUSTOMIZE THIS for your CN documents
# Output maps to CN Database columns (3-14)
EXTRACTION_PROMPT = """
Extract the following fields from this Confirmation Note (CN) document:

- Is it a CN?: Boolean - Is this a Confirmation Note? (Yes/No/True/False)
- Operation Type: Type of transaction operation (e.g., Purchase, Redemption, Switch, Subscription)
- Is it a Multiseries?: Boolean - Is this a multiseries transaction? (Yes/No/True/False)
- Currency: Transaction currency code (e.g., USD, EUR, GBP, CHF)
- Gross Amount: Gross transaction amount (numeric value)
- Net Amount: Net transaction amount (numeric value)
- Units: Number of units/shares (numeric value)
- Equalization: Equalization amount (numeric value)
- Fees: Total fees charged (numeric value)
- NAV price: Net Asset Value price per unit (numeric value)
- NAV date: NAV date (format: YYYY-MM-DD or DD/MM/YYYY)
- Settlement Date: Settlement date (format: YYYY-MM-DD or DD/MM/YYYY)

Return as JSON with keys: is_cn, operation_type, is_multiseries, currency, gross_amount, 
net_amount, units, equalization, fees, nav_price, nav_date, settlement_date

If a field is not found, use null.
"""

# NOTE: No Python helper functions needed for config.py in new architecture
# - Parameters are read by VBA only (GetParameterValue, GetConfirmationEmail)
# - TIPS data retrieved by VBA GetTIPSInfoByNumber() per OPC row
# - Python reads passwords directly from CN Database temp columns (16-18)
