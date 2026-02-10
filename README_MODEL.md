# Model Management

## Current Setup

**Model:** Meta-Llama-3-8B-Instruct.Q4_0.gguf  
**Location:** `./models/Meta-Llama-3-8B-Instruct.Q4_0.gguf`  
**GitHub Release:** https://github.com/robertoriosr1998/project-robot-2/releases/tag/model-v1.0

---

## Download Model on New Machine

If you need to download the model on another machine (e.g., at work):

### Option 1: Automatic Download & Merge (Recommended)

```bash
python download_and_merge_model.py
```

The script will:
- Prompt for GitHub repo, release tag, and model name (with defaults)
- Download all chunks from GitHub
- Merge them automatically
- Save to `./models/` folder

### Option 2: Manual Download & Merge

1. Download chunks from: https://github.com/robertoriosr1998/project-robot-2/releases/tag/model-v1.0
2. Save all `.part` files to a folder
3. Run merge script:

```bash
python merge_model_chunks.py <folder_with_parts>
```

---

## Usage

Once the model is in `./models/`, just run:

```bash
python main.py OPC_TEST.xlsm
```

The script automatically loads the model from the local folder.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `merge_model_chunks.py` | Merge `.part` files into complete model |
| `download_and_merge_model.py` | Download from GitHub and merge automatically |

---

## Configuration

Model is configured in `config.py`:

```python
LLM_MODEL = "Meta-Llama-3-8B-Instruct.Q4_0.gguf"
```

Change this line if using a different model.

---

## Model Storage

- **Local:** `./models/Meta-Llama-3-8B-Instruct.Q4_0.gguf` (4.3 GB)
- **GitHub:** Split into 3 chunks (~1.5 GB each) in release
- **Chunks:** `.part01`, `.part02`, `.part03`

---

## Troubleshooting

**"Model not found" error:**
- Run `download_and_merge_model.py` to download from GitHub
- Or check that model exists in `./models/` folder

**Download fails:**
- Check internet connection
- Verify GitHub release exists
- Try manual download from browser

**Merge fails:**
- Re-download the chunks
- Check all `.part` files downloaded completely
- Verify disk space (need ~8 GB free during merge)
