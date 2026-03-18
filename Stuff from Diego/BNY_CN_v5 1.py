# -*- coding: utf-8 -*-
"""
Split y parse de PDFs 'combined' (BNY):
- Detecta cada operación por 'TRADE DETAILS' y agrupa páginas del bloque (SUB/RED/RE-REG).
- SUB: MISMA MANERA QUE TU CÓDIGO (etiquetas Value/Price/Units) + encabezado 'Value Price Units' multi-línea.
- SELL / RE-REG:
    • Units EXACTAMENTE como SUB (buscar línea con 'Units' y extraer tras etiqueta).
    • NAV (Price) y Series desde la TABLA de Lot Detail (pdfplumber).
    • Lot Count: número de filas válidas en la tabla de Lot Detail (por orden).
- Class: guarda la LÍNEA COMPLETA donde aparece 'Class'.
- Renombrado EXACTO: {Action}_{Class}_{Account[0:15]}_{GrossAmount}({i}).pdf
- Crea carpeta por trade: '{FundShort}_{TodayISO}' y guarda ahí los PDFs y un Excel (openpyxl).
- Acorta nombres para evitar rutas > 260 caracteres en Windows.

Autor: Diego AF605690
Fecha: 2025-12-11
"""

import os
import re
import datetime as dt
import pdfplumber
import pandas as pd
from PyPDF2 import PdfReader, PdfWriter

# ======== CONFIG ========
FOLDER = r"C:\Users\af605690\OneDrive - ALLFUNDS BANK, S.A.U\Escritorio\Nueva Carpeta\BNY"

# ======== HELPERS ========
def sanitize_filename(name: str) -> str:
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        name = name.replace(ch, '-')
    return name.strip()

def safe_shorten(s: str, max_len: int) -> str:
    s = sanitize_filename(s)
    if len(s) <= max_len:
        return s
    cut = s.rfind(' ', 0, max_len)
    if cut == -1 or cut < max_len * 0.6:
        cut = max_len
    return s[:cut].strip()

def extract_after_label(line, label):
    if label in line:
        return line.split(label, 1)[-1].strip()
    return None

def extract_float_after_label(line, label):
    val = extract_after_label(line, label)
    if val:
        try:
            return float(val.replace(',', ''))
        except ValueError:
            return None
    return None

def to_float(s: str):
    try:
        return float(s.replace(',', ''))
    except Exception:
        return None

NUM_RE = r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+\.[0-9]+)"
SERIES_LETTER_RE  = re.compile(r"\bSeries\s+([A-Za-z])\b", re.I)
SERIES_DATE_RE    = re.compile(r"\b(?:0?[1-9]|1[0-2])/\d{4}\b")

# ======== LOT DETAIL via pdfplumber (TABLA) ========
TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "intersection_tolerance": 5,
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 20,
    "min_words_vertical": 1,
    "min_words_horizontal": 1,
}

def _norm(s):  # normaliza cabecera de columna
    return (s or "").strip().lower()

def extract_lot_table_rows(block_pages):
    """
    Devuelve lista de dicts por fila de la tabla de Lot Detail:
    [{'series_letter': 'C'|'A'|..., 'series_date': 'mm/yyyy'|'', 'price': float, 'units': float, 'value': float}, ...]
    Fallback regex si no se detecta tabla.
    """
    rows = []
    # 1) Intentar tablas con líneas
    for page in block_pages:
        try:
            tables = page.extract_tables(TABLE_SETTINGS) or []
        except Exception:
            tables = []
        for tbl in tables:
            if not tbl or len(tbl) < 2:
                continue
            header_row_idx = None
            for idx, r in enumerate(tbl[:3]):  # primeras filas
                hdr = [_norm(c) for c in r]
                if ("price" in hdr) and (("lot units" in hdr) or ("units" in hdr)):
                    header = hdr
                    header_row_idx = idx
                    break
            if header_row_idx is None:
                continue
            def col_idx(names):
                for n in names:
                    if n in header:
                        return header.index(n)
                return None
            i_price = col_idx(["price"])
            i_units = col_idx(["lot units", "units"])
            i_value = col_idx(["lot value", "value"])
            i_series= col_idx(["series", "lot series"])
            for r in tbl[header_row_idx+1:]:
                def cell(i):
                    if i is None or i >= len(r): return ""
                    return (r[i] or "").strip()
                series_cell = cell(i_series)
                series_letter = None
                series_date   = None
                if series_cell:
                    m_letter = SERIES_LETTER_RE.search(series_cell)
                    if m_letter:
                        series_letter = m_letter.group(1).upper()
                    else:
                        m_date = SERIES_DATE_RE.search(series_cell)
                        if m_date:
                            series_date = m_date.group(0)
                        elif len(series_cell) == 1 and series_cell.isalpha():
                            series_letter = series_cell.upper()
                price = to_float(cell(i_price))
                units = to_float(cell(i_units))
                value = to_float(cell(i_value))
                rows.append({
                    "series_letter": series_letter,
                    "series_date":   series_date,
                    "price":         price,
                    "units":         units,
                    "value":         value,
                })
    # 2) Fallback regex si no hay filas
    if not rows:
        LOT_LINE_RE = re.compile(
            rf"(\d{{3,}})\s+(Series\s+[A-Za-z]|[0-1]?\d/\d{{4}}|[A-Za-z]{{3}}/\d{{4}})\s+{NUM_RE}\s+{NUM_RE}\s+{NUM_RE}"
        )
        for page in block_pages:
            txt = page.extract_text() or ""
            for m in LOT_LINE_RE.finditer(txt):
                _, series_tok, price_s, units_s, value_s = m.groups()
                series_letter = None
                series_date   = None
                ml = SERIES_LETTER_RE.search(series_tok)
                if ml:
                    series_letter = ml.group(1).upper()
                else:
                    md = SERIES_DATE_RE.search(series_tok)
                    if md:
                        series_date = md.group(0)
                rows.append({
                    "series_letter": series_letter,
                    "series_date":   series_date,
                    "price":         to_float(price_s),
                    "units":         to_float(units_s),
                    "value":         to_float(value_s),
                })
    return rows

# ======== LECTURA Y AGRUPACIÓN ========
def read_all_pages(pdf_path):
    pages = []
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page)
            pages_text.append(page.extract_text() or "")
    return pages, pages_text

def group_pages_into_trades(pages_text):
    starts = []
    for i, txt in enumerate(pages_text):
        if re.search(r"\bTRADE DETAILS\b", txt, re.I):
            starts.append(i)
    if not starts:
        return [(i, i) for i in range(len(pages_text))]
    ranges = []
    for k, s in enumerate(starts):
        e = (starts[k+1] - 1) if (k + 1) < len(starts) else len(pages_text) - 1
        ranges.append((s, e))
    return ranges

# ======== PARSE BLOQUE ========
def parse_trade_block(pages, pages_text, start_idx, end_idx):
    lines = []
    for i in range(start_idx, end_idx + 1):
        lines += (pages_text[i] or "").splitlines()
    text_joined = " ".join(lines)

    row = {
        "Account Name": None,
        "Fund Name": None,
        "Class": None,
        "Series": None,
        "Action": None,
        "Currency": None,
        "Dealing Date": None,
        "Gross Amount": None,
        "NAV": None,
        "Units": None,
        # "Initial Value": None,
        "Redemption Fee": None,
        "Settlement Amount": None,
        "Lot Count": None,   # <--- NUEVO
        "Transfer From Class": None,
        "Transfer From Price": None,
        "Transfer From Units": None,
        "Transfer To Class":None,
        "Transfer To Price": None,
        "Transfer To Units": None

    }
    
    
    tj = text_joined.lower()
    if re.search(r"\btransfer\b", tj) or "lot detail before transfer" in tj or "transfer from" in tj:
        row["Action"] = "Switch"
    elif re.search(r"\bbuy\b", tj):
        row["Action"] = "SUB"
    elif re.search(r"\bsell\b", tj):
        row["Action"] = "RED"
    elif re.search(r"re-?registration\s+in", tj):
        row["Action"] = "Re-Registration In"
    elif re.search(r"re-?registration\s+out", tj):
        row["Action"] = "Re-Registration Out"

    

    # --- Etiquetas (tu estilo) ---
    for line in lines:
        if "request of" in line and row["Account Name"] is None:
            row["Account Name"] = extract_after_label(line, "request of")
        elif "AFB/BNPPLUX/BNP PARIBAS SUISSE SA" in line and row["Account Name"] is None:
            row["Account Name"] = "BNP Paribas"
        if ("Fund" in line or "iCapital" in line) and ("SP" in line or "Fund" in line) and row["Fund Name"] is None:
            row["Fund Name"] = line.strip()
        if "Class" in line and "Lot" not in line and row["Class"] is None:
            row["Class"] = line.strip()   # línea completa
        elif "In accordance with your instructions, the Administrator confirms the following trade." in line and row["Class"] is None:
            # Get the next line if available
            idx = lines.index(line)
            if idx + 1 < len(lines):
                row["Class"] = lines[idx + 1].strip()
        elif row["Action"] == "Switch" and "Transfer From" in line:
            row["Class"]="Switch"
            row["Transfer From Class"]=extract_after_label(line, "Transfer From")
            
                
        if row["Action"] == "Switch" and "Transfer To" in line:
            row["Transfer To Class"]=extract_after_label(line, "Transfer To")


        if "Series" in line and "Lot" not in line and row["Series"] is None:
            ser = extract_after_label(line, "Series")
            if ser: row["Series"] = ser
        if "Currency" in line and row["Currency"] is None:
            cur = extract_after_label(line, "Currency")
            if cur and len(cur) >= 3:
                tok = cur.split()[0]
                if len(tok) == 3 and tok.isupper():
                    row["Currency"] = tok
            else:
                m = re.search(r"\b([A-Z]{3})\s+Currency\b", line)
                if m: row["Currency"] = m.group(1)
        if "Dealing Date" in line and row["Dealing Date"] is None:
            dd = extract_after_label(line, "Dealing Date")
            m = re.search(r"\b\d{2}-[A-Za-z]{3}-\d{4}\b", dd or "")
            if m: row["Dealing Date"] = m.group(0)
        # Etiquetas sueltas (SUB a tu manera)
        if "Value" in line and ("Price" not in line or "Units" not in line):
            v = extract_float_after_label(line, "Value")
            if v is not None: row["Gross Amount"] = v
        if "Price" in line and ("Value" not in line or "Units" not in line):
            nav = extract_float_after_label(line, "Price")
            if nav is not None: row["NAV"] = nav
        if "Units" in line and ("Value" not in line or "Price" not in line):
            u = extract_float_after_label(line, "Units")
            if u is not None: row["Units"] = u
            
    
        # m = re.search(r"Transfer\s+From\s+(.*?)\s+Transfer\s+To\s+(.*)", text_joined, re.I)
        # if m:
        #     row["Transfer From Class"] = m.group(1).strip()
        #     row["Transfer To Class"] = m.group(2).strip()
    

    # Encabezado SUB 'Value Price Units' multi-línea
    header_idx = next((i for i, l in enumerate(lines) if ("Value" in l and "Price" in l and "Units" in l)), None)
    header_units = None
    header_nav   = None
    header_val   = None
    if header_idx is not None:
        nums_header = re.findall(NUM_RE, lines[header_idx])
        if nums_header:
            header_val = to_float(nums_header[0])  # Value
            row["Gross Amount"] = header_val
            row["Settlement Amount"] = header_val
        for j in range(header_idx + 1, min(header_idx + 6, len(lines))):
            if re.search(r"[A-Za-z]", lines[j]):  # saltar líneas con texto
                continue
            nums_next = re.findall(NUM_RE, lines[j])
            if len(nums_next) >= 2:
                header_nav   = to_float(nums_next[0])    # Price
                header_units = to_float(nums_next[1])    # Units
                break

    # === LOT DETAIL como TABLA ===
    block_pages = [pages[i] for i in range(start_idx, end_idx + 1)]
    lot_rows = extract_lot_table_rows(block_pages)

    # Lot Count (filas válidas con algún dato numérico relevante)
    row["Lot Count"] = sum(
        1 for r in lot_rows
        if (r["price"] is not None) or (r["units"] is not None) or (r["value"] is not None)
    ) if lot_rows else 0

    # Series (limpia)
    series_letters = sorted({r["series_letter"] for r in lot_rows if r["series_letter"]})
    series_dates   = sorted({r["series_date"]   for r in lot_rows if r["series_date"]})
    if series_letters:
        row["Series"] = ", ".join(series_letters)
    elif (not row["Series"]) and series_dates:
        row["Series"] = ", ".join(series_dates)


    # NAV (Price): promedio ponderado si hay varios; sino, único; sino header_nav
    price_units = [(r["price"], r["units"]) for r in lot_rows if r["price"] is not None]
    
    # ===== NUEVO: si es 'Switch', mapear From/To desde las dos primeras filas =====
    if (row.get("Action") == "Switch") and price_units:
        # Transfer From (primera fila)
        row["Transfer From Price"] = price_units[0][0]
        row["Transfer From Units"] = price_units[0][1]
    
        # Transfer To (segunda fila, si existe)
        if len(price_units) >= 2:
            row["Transfer To Price"] = price_units[1][0]
            row["Transfer To Units"] = price_units[1][1]
        else:
            # Si no hay segunda fila, deja To en None (o copia From si así lo prefieres)
            row["Transfer To Price"] = None
            row["Transfer To Units"] = None
    
        # Opcional: si quieres que NAV y Units principales se queden como estaban, no toques nada.
        # Si prefieres que reflejen el 'From':
        # if row.get("NAV") is None: row["NAV"] = row["Transfer From Price"]
        # if row.get("Units") is None: row["Units"] = row["Transfer From Units"]
    
    # ===== LÓGICA ORIGINAL (se mantiene) =====

    if price_units:
        total_u = 0.0
        total_val = 0.0
        for p, u in price_units:
            u_eff = u if (u is not None and u > 0) else (header_units if header_units else 1.0)
            total_u += u_eff
            total_val += p * u_eff
    
        if total_u > 0 and row.get("NAV") is None:
            if row.get("Action") == "Switch":
                # Si es Switch, forzamos NAV a None (NaN en Excel)
                row["NAV"] = None
            else:
                row["NAV"] = round(total_val / total_u, 4)
    
    elif header_nav is not None and row.get("NAV") is None:
        if row.get("Action") == "Switch":
            # Si es Switch, forzamos NAV a None (NaN en Excel)
            row["NAV"] = None
        else:
            row["NAV"] = header_nav
    # Units: EXACTAMENTE como en SUB → buscar línea que contenga 'Units' y extraer tras la etiqueta
    units_from_label = None
    for line in lines:
        if "Units" in line:
            u = extract_float_after_label(line, "Units")
            if u is not None:
                units_from_label = u
                break
    
    if units_from_label is not None:
        row["Units"] = units_from_label
    else:
        if header_units is not None and row.get("Units") is None:
            row["Units"] = header_units
        else:
            lot_units_sum = sum(r["units"] or 0.0 for r in lot_rows if r["units"] is not None)

    # Gross Amount (Sell): si hay Final Value (ajustes), usar neto; si no, usar Value por etiqueta; si falta, suma de lotes
    if row["Action"] == "Sell":
        m = re.search(rf"Initial Value\s+{NUM_RE}", text_joined, re.I)
        if m: 
            row["Gross Amount"] = to_float(m.group(1))
            # row["Settlement Amount"] = row["Gross Amount"]
        m = re.search(rf"Sales Charge\s*\(({NUM_RE})\)", text_joined, re.I)
        if m: row["Redemption Fee"] = to_float(m.group(1))        
        else:
            row["Settlement Amount"] = row["Gross Amount"]

        m = re.search(rf"Final Value\s+{NUM_RE}", text_joined, re.I)
        if m: row["Settlement Amount"] = to_float(m.group(1))
        if row["Gross Amount"] is None and header_val is not None:
            row["Gross Amount"] = header_val
            row["Settlement Amount"] = row["Gross Amount"]
            row["Redemption Fee"] = None
        # elif row["Gross Amount"] is None and header_val is not None:
        #     row["Gross Amount"] = header_val
        # elif row["Gross Amount"] is None:
        #     lot_value_sum = sum(r["value"] or 0.0 for r in lot_rows if r["value"] is not None)
        #     if lot_value_sum > 0:
        #         row["Gross Amount"] = round(lot_value_sum, 2)

    # Fallbacks
    if (row["Fund Name"] is None or str(row["Fund Name"]).strip() == ""):
        # intenta coger una línea media como fallback
        for l in lines[5:20]:
            if "Fund" in l and "SP" in l:
                row["Fund Name"] = l.strip()
                break
    if (row["Dealing Date"] is None):
        for l in lines:
            if "COPY" in l or "Date:" in l: continue
            m = re.search(r"\b\d{2}-[A-Za-z]{3}-\d{4}\b", l)
            if m:
                row["Dealing Date"] = m.group(0)
                break

    return row

# ======== SAVE SPLIT ========
def save_pages_range_to_pdf(src_pdf, start_page, end_page, dest_pdf):
    reader = PdfReader(src_pdf)
    writer = PdfWriter()
    for i in range(start_page, end_page + 1):
        writer.add_page(reader.pages[i])
    with open(dest_pdf, "wb") as f_out:
        writer.write(f_out)

# ======== MAIN ========
def main():
    groups = {}  # key = out_folder_path, value = list[rows]
    i_counter_global = 0
    today_iso = dt.date.today().isoformat()

    for file in os.listdir(FOLDER):
        if not file.lower().endswith(".pdf"):
            continue
        src_pdf = os.path.join(FOLDER, file)

        # Leer todas las páginas + textos
        try:
            pages, pages_text = read_all_pages(src_pdf)
        except Exception as e:
            print(f"[WARN] No se pudo leer {file}: {e}")
            continue

        # Agrupar por TRADE DETAILS
        ranges = group_pages_into_trades(pages_text)
        if not ranges:
            ranges = [(p, p) for p in range(len(pages_text))]

        for (s, e) in ranges:
            row = parse_trade_block(pages, pages_text, s, e)

            # Carpeta por trade: {FundShort}_{todayISO}
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

            # Renombrado EXACTO
            action = row.get("Action") or "UNK"
            cls    = row.get("Class") or "Class-NA"
            acc    = (row.get("Account Name") or "Account-NA")[0:15]
            gross  = row.get("Gross Amount")
            gross_s = str(gross) if gross is not None else "0"
            new_name = f"{action}_{cls}_{acc}_{gross_s}({i_counter_global})"
            i_counter_global += 1

            new_name = sanitize_filename(new_name)
            new_name = safe_shorten(new_name, 120) + ".pdf"
            new_pdf_path = os.path.join(out_folder_path, new_name)

            try:
                save_pages_range_to_pdf(src_pdf, s, e, new_pdf_path)
                print(f"[OK] {file} :: páginas {s+1}-{e+1} → {os.path.join(out_folder_name, new_name)}")
            except Exception as ex:
                print(f"[ERR] Guardando split de {file} páginas {s+1}-{e+1}: {ex}")

    # Excel por carpeta
    for out_folder_path, rows in groups.items():
        if not rows:
            continue
    
        # Asegura que la carpeta exista en el momento de escribir (importante en OneDrive)
        os.makedirs(out_folder_path, exist_ok=True)
    
        df = pd.DataFrame(rows)
        
        CANONICAL_COLUMNS = [
            # Identificación
            "Source File", "Block Pages", "Account Name", "Fund Name", "Class", "Series", "ISIN",
            # Operación
            "Action", "Currency", "Dealing Date", "Reference",
            # Métricas principales
            "Gross Amount", "Redemption Fee", "Settlement Amount", "NAV", "Units",
            # Auxiliares
            "Aux1", "Aux2",
            # Extendidas (mantener todo lo tuyo)
            # "Initial Value", "Final Value",
            "Lot Count", "Transfer From Class", "Transfer From Price", "Transfer From Units",
            "Transfer To Class", "Transfer To Price", "Transfer To Units",
        ]

        

        

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

        # Asegurar y reordenar columnas
        for c in CANONICAL_COLUMNS:
            if c not in df.columns:
                df[c] = None
        df = df.reindex(columns=CANONICAL_COLUMNS)
        # return df
        
        
        base_folder = os.path.basename(out_folder_path)
    
        # NO pisar la variable global today_iso; usa un nombre distinto
        if '_' in base_folder:
            fund_short, today_iso_folder = base_folder.rsplit('_', 1)
        else:
            fund_short = base_folder
            # si no hay fecha en el nombre de carpeta, usa la fecha de ejecución
            today_iso_folder = today_iso
    
        # Construye un nombre de archivo robusto
        excel_name = f"{fund_short[:15]}_Trade_Confirmations_{today_iso_folder}.xlsx"
        excel_name = sanitize_filename(excel_name)   # <- nuevo: limpia caracteres problemáticos
        excel_name = safe_shorten(excel_name, 120)   # mantiene longitud razonable
    
        excel_path = os.path.join(out_folder_path, excel_name)
    
        # Manejo opcional de rutas largas en Windows
        excel_path_to_write = excel_path
        if os.name == 'nt' and len(excel_path) > 240:
            excel_path_to_write = r"\\?\{}".format(excel_path)
    
        try:
            df.to_excel(excel_path_to_write, index=False, engine="openpyxl")
            print(f"[DONE] Excel → {os.path.join(os.path.basename(out_folder_path), excel_name)}")
        except FileNotFoundError as e:
            # Error típico: carpeta no existe en ese instante o ruta inválida
            print(f"[ERR] Exportando Excel en {out_folder_path}: {e}")
            print(f"[HINT] Existe la carpeta? {os.path.isdir(out_folder_path)}  |  Ruta length={len(excel_path)}")
        except Exception as e:
            # Reintento con nombre aún más corto
            print(f"[WARN] Primer intento falló: {e}. Reintentando con nombre más corto...")
            excel_name_short = safe_shorten(excel_name, 60)
            excel_name_short = sanitize_filename(excel_name_short)
            excel_path_short = os.path.join(out_folder_path, excel_name_short)
            excel_path_short_write = excel_path_short
            if os.name == 'nt' and len(excel_path_short) > 240:
                excel_path_short_write = r"\\?\{}".format(excel_path_short)
            try:
                df.to_excel(excel_path_short_write, index=False, engine="openpyxl")
                print(f"[DONE] Excel (short) → {os.path.join(os.path.basename(out_folder_path), excel_name_short)}")
            except Exception as e2:
                print(f"[ERR] Exportando Excel (retry) en {out_folder_path}: {e2}")

if __name__ == "__main__":
    main()
