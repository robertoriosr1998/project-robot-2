# -*- coding: utf-8 -*-
"""
APEX_CNs_v3.py
Refactorizado completamente siguiendo la arquitectura del sistema BNY.
Cambios clave vs v2:
- Corrige la extracción de UNITS para APEX:
  * Soporta "Number of Units Issued/Redemed" además de "Shares".
  * Fallback por regex que detecta valor ANTES o DESPUÉS de la etiqueta.
- "Dealing Date" se extrae por etiqueta, no desde fechas del encabezado.
- Añade "Reference" al Excel.
- Extracción de tabla más robusta (todas las páginas + limpieza).
- Pequeñas mejoras de saneado y orden de columnas.

*** Actualización solicitada (2026-02-25):
- Añadidas dos nuevas columnas y su parseo:
  * "Redemption Fee"
  * "Settlement Amount"
"""

import os
import re
import datetime as dt
import pdfplumber
import pandas as pd
from PyPDF2 import PdfReader, PdfWriter

# ===================== CONFIG =====================
# FOLDER = r"C:\Users\af605690\OneDrive - ALLFUNDS BANK, S.A.U\Escritorio\cn_analysis\apex"
# FOLDER = r"C:\Users\af605690\OneDrive - ALLFUNDS BANK, S.A.U\Escritorio\macros\outlook"
FOLDER = r"C:\Users\af605299\OneDrive - ALLFUNDS BANK, S.A.U\Escritorio\Nueva Carpeta\APEX"

# ===================== HELPERS =====================
def sanitize_filename(name: str) -> str:
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '\n']:
        name = name.replace(ch, '-')
    return name.strip()

def safe_shorten(s: str, max_len: int):
    s = sanitize_filename(s or "")
    if len(s) <= max_len:
        return s
    cut = s.rfind(" ", 0, max_len)
    if cut == -1 or cut < max_len * 0.6:
        cut = max_len
    return s[:cut].strip()

def to_float(s: str):
    if s is None:
        return None
    s = str(s)
    # Quitar moneda y separadores, admitir "." decimal y "," de miles
    s = s.replace("USD", "").replace("EUR", "").replace("GBP", "")
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except:
        return None

def clean_label(s: str):
    # Normaliza etiquetas de tabla/linea para match robusto
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def capture_numeric_near_label(text: str, label: str):
    """
    Devuelve un float si encuentra un número cerca de la etiqueta.
    - Caso A: 'Label : 123.45'
    - Caso B: '123.45 Label' (muy común en APEX)
    """
    if not text:
        return None
    lbl = re.escape(label)
    num = r"[-+]?\d[\d,]*\.?\d*"
    # Label seguido de valor
    m = re.search(rf"{lbl}\s*[:\-]?\s*(USD\s*)?({num})", text, re.IGNORECASE)
    if m:
        return to_float(m.group(2))
    # Valor seguido de Label
    m = re.search(rf"({num})\s*(USD\s*)?{lbl}", text, re.IGNORECASE)
    if m:
        return to_float(m.group(1))
    return None

def capture_text_after_label(text: str, label: str, max_chars=50):
    """
    Extrae texto corto tras una etiqueta: 'Label value...'
    """
    lbl = re.escape(label)
    m = re.search(rf"{lbl}\s*[:\-]?\s*([^\n\r]{{1,{max_chars}}})", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Intento inverso (valor-antes-etiqueta) no aplica bien a texto libre para Reference
    return None

# ===================== APEX-SPECIFIC: Mapping =====================
def classify_action(text_block: str):
    """
    Mapping APEX -> Actions
    SUB = Subscriptions
    RED = Redemptions
    TRA = Transfers/Switch
    """
    t = (text_block or "").lower()
    if ("subscription" in t) or ("number of shares issued" in t) or ("number of units issued" in t):
        return "SUB"
    if ("redemption" in t) or ("number of shares redeemed" in t) or ("number of units redeemed" in t):
        return "RED"
    if ("transfer" in t) or ("switch" in t):
        return "TRA"
    return "UNK"

# ===================== LECTURA COMPLETA =====================
def read_all_pages(pdf_path):
    pages = []
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            pages.append(p)
            pages_text.append(p.extract_text() or "")
    return pages, pages_text

# ===================== AGRUPACIÓN (APEX) =====================
def group_pages_into_trades(pages_text):
    """
    APEX: cada PDF suele ser un único bloque.
    """
    return [(0, len(pages_text) - 1)]

# ===================== PARSEO BLOQUE APEX =====================
def parse_apex_block(pages, pages_text, start_idx, end_idx):
    # Reunir texto de todas las páginas del bloque
    lines = []
    for i in range(start_idx, end_idx + 1):
        lines += (pages_text[i] or "").splitlines()
    text_joined = "\n".join(lines)

    row = {
        "Action": None,
        "Fund Name": None,
        "Class": None,
        "Series": None,
        "ISIN": "",  # Siempre vacío
        "Client Account": None,
        "Currency": "USD",
        "Dealing Date": None,
        "Reference": None,  # << NUEVO (v3)
        "Gross Amount": None,
        "NAV": None,
        "Units": None,
        # << NUEVO (solicitado)
        "Redemption Fee": None,
        "Settlement Amount": None,
    }

    # ACTION
    row["Action"] = classify_action(text_joined)

    # FUND NAME (heurística: buscar nombres de gestoras comunes)
    for l in lines:
        l_low = l.lower()
        if any(x in l_low for x in ["north haven", "blackrock", "blue owl", "icapital"]):
            row["Fund Name"] = l.strip()
            break

    # CLIENT ACCOUNT (heurística: buscar patrón común de AFB-/AFN- ...)
    acc = None
    for l in lines[:8]:  # suele estar arriba
        if re.search(r"\bAF[BN]-", l) or "_" in l:
            acc = l.strip()
            break
    if not acc and len(lines) > 1:
        acc = lines[1].strip()
    row["Client Account"] = acc

    # ===== CLASS + SERIES =====
    row["Series"] = ""  # por defecto
    RE_MMYYYY = re.compile(r"(0?[1-9]|1[0-2])\s*/\s*\d{4}$")  # 05/2025
    RE_SERIESWORD = re.compile(r"-\s*Series\s+(.+)$", re.IGNORECASE)  # - Series C
    RE_END_SHARES = re.compile(r"\s*Shares\s*$", re.IGNORECASE)  # ... Shares

    def _extract_class_series_from_line(raw_line: str):
        clean = " ".join((raw_line or "").split())
        lower = clean.lower()
        if "class" not in lower:
            return (None, None)
        # Muchos encabezados incluyen 'of Unit'/'of Share' o similar
        idx_class = lower.rfind("class ")
        if idx_class == -1:
            return (None, None)
        rest = clean[idx_class + len("class "):].strip()
        if not rest:
            return (None, None)
        # 1) '- Series X'
        m_word = RE_SERIESWORD.search(rest)
        if m_word:
            class_txt = rest[:m_word.start()].strip(" -")
            series_txt = m_word.group(1).strip()
            return ((class_txt or None), (series_txt or ""))
        # 2) '... MM/YYYY'
        m_date = RE_MMYYYY.search(rest)
        if m_date:
            class_txt = rest[:m_date.start()].strip(" -")
            series_txt = m_date.group(0).replace(" ", "")
            return ((class_txt or None), (series_txt or ""))
        # 3) Termina en 'Shares' -> limpiar
        rest_wo_shares = RE_END_SHARES.sub("", rest).strip()
        if rest_wo_shares:
            return (rest_wo_shares, "")
        return (None, None)

    for l in lines:
        c, s = _extract_class_series_from_line(l)
        if c is not None:
            row["Class"] = c
            row["Series"] = s or ""
            break

    # ===== Dealing Date (por etiqueta) =====
    # Buscar 'Dealing Date' explícito; si no, usar primer patrón de fecha
    m = re.search(
        r"Dealing Date\s*[:\-]?\s*("
        r"\d{1,2}\s+[A-Za-z]{3,}\s+\d{4}"
        r"|\d{1,2}/\d{1,2}/\d{4}"
        r")",
        text_joined,
        re.IGNORECASE,
    )
    if m:
        row["Dealing Date"] = m.group(1).strip()
    else:
        m2 = re.search(r"\b\d{1,2}\s?[A-Za-z]{3,}\s?\d{4}\b", text_joined)
        if m2:
            row["Dealing Date"] = m2.group(0)

    # ===== Reference =====
    ref = capture_text_after_label(text_joined, "Reference", max_chars=30)
    if ref:
        # coge solo el 1er token útil (números o alfanumérico corto)
        ref_m = re.search(r"[A-Za-z0-9\-\./]+", ref)
        row["Reference"] = ref_m.group(0) if ref_m else ref.strip()

    # ===== TABLE DATA (todas las páginas) =====
    table_data = {}
    for pi in range(start_idx, end_idx + 1):
        try:
            tables = pages[pi].extract_tables() or []
        except:
            tables = []
        for tbl in tables:
            # Normalmente columnas: [Label, Value]
            for r in (tbl or []):
                if not r or len(r) < 1:
                    continue
                key = clean_label(r[0]) if r[0] else None
                if not key:
                    continue
                val_raw = ""
                if len(r) > 1 and r[1]:
                    val_raw = str(r[1])
                val_raw = val_raw.replace("USD", "").strip()
                # Guarda numérico si aplica, si no, texto crudo
                val_num = to_float(val_raw)
                table_data[key] = val_num if val_num is not None else val_raw

    # ===== NAV / UNITS / GROSS AMOUNT con prioridad y fallbacks =====
    # --- NAV ---
    for k in ["Offering Price", "Share Value", "NAV", "Price per Unit", "Price per Share"]:
        if k in table_data and table_data[k] not in (None, ""):
            row["NAV"] = to_float(str(table_data[k]))
            break
    if row["NAV"] is None:
        row["NAV"] = (
            capture_numeric_near_label(text_joined, "Offering Price")
            or capture_numeric_near_label(text_joined, "Share Value")
        )

    # --- UNITS ---
    unit_keys = [
        "Number of Units Issued", "Number of Units Redeemed",
        "Units Issued", "Units Redeemed",
        "Number of Shares Issued", "Number of Shares Redeemed",
        "Shares Issued", "Shares Redeemed",
        "Number of Units", "Number of Shares"
    ]
    for k in unit_keys:
        if k in table_data and table_data[k] not in (None, ""):
            row["Units"] = to_float(str(table_data[k]))
            break
    if row["Units"] is None:
        row["Units"] = (
            capture_numeric_near_label(text_joined, "Number of Units Issued") or
            capture_numeric_near_label(text_joined, "Number of Units Redeemed") or
            capture_numeric_near_label(text_joined, "Units Issued") or
            capture_numeric_near_label(text_joined, "Units Redeemed") or
            capture_numeric_near_label(text_joined, "Number of Shares Issued") or
            capture_numeric_near_label(text_joined, "Number of Shares Redeemed")
        )

    # --- GROSS AMOUNT ---
    # Preferimos el importe de la operación (Subscription/Redemption) sobre Settlement.
    amount_keys_priority = [
        "Subscription Amount", "Redemption Amount", "Switch Amount",
        "Settlement Amount", "Trade Amount"
    ]
    for k in amount_keys_priority:
        if k in table_data and table_data[k] not in (None, ""):
            row["Gross Amount"] = to_float(str(table_data[k]))
            break
    if row["Gross Amount"] is None:
        row["Gross Amount"] = (
            capture_numeric_near_label(text_joined, "Subscription Amount") or
            capture_numeric_near_label(text_joined, "Redemption Amount") or
            capture_numeric_near_label(text_joined, "Settlement Amount")
        )

    # --- NUEVOS CAMPOS: Redemption Fee & Settlement Amount ---
    # Settlement Amount explícito
    if "Settlement Amount" in table_data and table_data["Settlement Amount"] not in (None, ""):
        row["Settlement Amount"] = to_float(str(table_data["Settlement Amount"]))
    else:
        row["Settlement Amount"] = capture_numeric_near_label(text_joined, "Settlement Amount")

    # Redemption Fee explícito
    if "Redemption Fee" in table_data and table_data["Redemption Fee"] not in (None, ""):
        row["Redemption Fee"] = to_float(str(table_data["Redemption Fee"]))
    else:
        row["Redemption Fee"] = capture_numeric_near_label(text_joined, "Redemption Fee")

    return row

# ===================== SAVE SPLIT =====================
def save_pages_range_to_pdf(src_pdf, start_page, end_page, dest_pdf):
    reader = PdfReader(src_pdf)
    writer = PdfWriter()
    for i in range(start_page, end_page + 1):
        writer.add_page(reader.pages[i])
    with open(dest_pdf, "wb") as fh:
        writer.write(fh)

# ===================== MAIN =====================
def main():
    groups = {}
    i_global = 0
    today_iso = dt.date.today().isoformat()

    for file in os.listdir(FOLDER):
        if not file.lower().endswith(".pdf"):
            continue

        pdf_path = os.path.join(FOLDER, file)
        try:
            pages, pages_text = read_all_pages(pdf_path)
        except Exception as e:
            print(f"[WARN] No se pudo leer {file}: {e}")
            continue

        ranges = group_pages_into_trades(pages_text)

        for (s, e) in ranges:
            row = parse_apex_block(pages, pages_text, s, e)
            fund_full = (row.get("Fund Name") or "Fund-NA").strip()
            fund_short = safe_shorten(fund_full, 85)
            out_folder_name = sanitize_filename(f"{fund_short}_{today_iso}")
            out_folder_path = os.path.join(FOLDER, out_folder_name)
            os.makedirs(out_folder_path, exist_ok=True)

            if out_folder_path not in groups:
                groups[out_folder_path] = []
            groups[out_folder_path].append({
                "Source File": file,
                "Block Pages": f"{s+1}-{e+1}",
                **row
            })

            # Nombre de archivo (estilo BNY)
            action = row.get("Action") or "UNK"
            cls = row.get("Class") or "Class-NA"
            acc = (row.get("Client Account") or "ACC-NA")[:15]
            gross = row.get("Gross Amount")
            gross_s = str(gross) if gross is not None else "0"

            new_name = f"{action}_{cls}_{acc}_{gross_s}({i_global})"
            i_global += 1
            new_name = sanitize_filename(new_name)
            new_name = safe_shorten(new_name, 120) + ".pdf"
            new_pdf_path = os.path.join(out_folder_path, new_name)
            try:
                save_pages_range_to_pdf(pdf_path, s, e, new_pdf_path)
                print(f"[OK] {file} → {os.path.join(out_folder_name, new_name)}")
            except Exception as ex:
                print(f"[ERR] Guardando split de {file}: {ex}")

    # Crear Excel por carpeta
    for out_folder_path, rows in groups.items():
        if not rows:
            continue
        df = pd.DataFrame(rows)

        # --------------------------------------------------
        # REMOVE DUPLICATE REFERENCES (keep first occurrence)
        # --------------------------------------------------
        if "Reference" in df.columns:
            df = df.drop_duplicates(subset=["Reference"], keep="first")

        # --------------------------------------------------
        # Orden de columnas (incluye Reference + nuevos campos)
        # --------------------------------------------------
        # preferred_cols = [
        #     "Source File", "Block Pages", "Client Account", "Fund Name", "Class", "Series",
        #     "ISIN", "Action", "Currency",
        #     "Gross Amount", "NAV", "Units",
        #     "Redemption Fee", "Settlement Amount",   # << NUEVOS CAMPOS
        #     "Dealing Date", "Reference"
        # ]
        # rest_cols = [c for c in df.columns if c not in preferred_cols]
        # df = df.reindex(columns=preferred_cols + rest_cols)

        # excel_name = "APEX_Confirmations.xlsx"
        # excel_path = os.path.join(out_folder_path, excel_name)
        # try:
        #     df.to_excel(excel_path, index=False, engine="openpyxl")
        #     print(f"[DONE] Excel → {os.path.basename(out_folder_path)}/{excel_name}")
        # except Exception as e:
        #     print(f"[ERR] Exportando Excel en {out_folder_path}: {e}")

        # (El bloque siguiente aparece duplicado en el script original: lo mantenemos sin más cambios)
        
        
        
        # Auxiliares
        def _aux1(row):
            if row.get("Action") in ("SUB", "RED") and (row.get("Gross Amount") is not None) and (row.get("NAV") is not None):
                return f"{row['Gross Amount']:.2f}|{row['NAV']:.4f}".replace('.',',')
            return ""
        def _aux2(row):
            if row.get("Action") in ("SUB", "RED") and (row.get("NAV") is not None) and (row.get("Units") is not None):
                return f"{row['NAV']:.4f}|{row['Units']:.4f}".replace('.',',')
            return ""
        df["Aux1"] = df.apply(_aux1, axis=1)
        df["Aux2"] = df.apply(_aux2, axis=1)
        
        
        preferred_cols = [
            "Source File", "Block Pages", "Client Account", "Fund Name", "Class", "Series",
            "ISIN", "Action", "Currency", "Dealing Date", "Reference", 
            "Gross Amount","Redemption Fee", "Settlement Amount", "NAV", "Units", "Aux1", "Aux2"
        ]
        # Reindex con columnas preferidas primero
        rest_cols = [c for c in df.columns if c not in preferred_cols]
        df = df.reindex(columns=preferred_cols + rest_cols)
        excel_name = f"{fund_short[:15]}_Trade_Confirmations_{dt.date.today().isoformat()}.xlsx"
        excel_name = sanitize_filename(excel_name)
        excel_path = os.path.join(out_folder_path, excel_name)
        try:
            df.to_excel(excel_path, index=False, engine="openpyxl")
            print(f"[DONE] Excel → {os.path.join(os.path.basename(out_folder_path), excel_name)}")
        except Exception as e:
            print(f"[ERR] Exportando Excel en {out_folder_path}: {e}")

# =====================
if __name__ == "__main__":
    main()
