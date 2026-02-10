# Model Management

## Current Setup

**Model:** tinyllama-1.1b-chat-v1.0.Q4_0.gguf  
**Location:** `./models/tinyllama-1.1b-chat-v1.0.Q4_0.gguf`  
**Size:** ~700 MB (small enough to commit directly to GitHub)

---

## Download Model on New Machine

If you need to download the model on another machine:

### Option 1: Download from Hugging Face

```bash
# Create models directory if it doesn't exist
mkdir -p models

# Download directly from Hugging Face
curl -L "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_0.gguf" -o models/tinyllama-1.1b-chat-v1.0.Q4_0.gguf
```

### Option 2: Clone from Your Repository

If the model is committed to your GitHub repository, just clone/pull:

```bash
git clone https://github.com/robertoriosr1998/project-robot-2.git
cd project-robot-2
# Model should be in ./models/ folder
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
LLM_MODEL = "tinyllama-1.1b-chat-v1.0.Q4_0.gguf"
```

Change this line if using a different model.

---

## Model Storage

- **Local:** `./models/tinyllama-1.1b-chat-v1.0.Q4_0.gguf` (~700 MB)
- **GitHub:** Small enough to commit directly (no need for releases/chunks)
- **Speed:** ~7x faster than Llama-3-8B on CPU-only systems

---

## Troubleshooting

**"Model not found" error:**
- Download from Hugging Face: https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF
- Save to `./models/` folder
- Or pull from your GitHub repo if already committed

**Model runs too slow:**
- TinyLlama is optimized for CPU, but if still slow:
  - Close other applications
  - Check CPU usage in Task Manager
  - Consider upgrading to a system with more RAM

**Extraction quality issues:**
- TinyLlama is smaller and may miss some fields
- Consider testing with your PDFs first
- If quality is insufficient, upgrade to Phi-3-mini (2.3 GB) or Llama-3.2-3B (1.9 GB)
