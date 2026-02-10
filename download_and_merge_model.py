"""
Download model chunks from GitHub release and merge them.
Works through workplace proxies since GitHub is accessible.
"""
import sys
import urllib.request
import json
from pathlib import Path
import ssl
import shutil

def download_file(url, output_path):
    """Download file with progress indicator."""
    try:
        context = ssl._create_unverified_context()
        
        def reporthook(block_num, block_size, total_size):
            if total_size > 0:
                percent = min(block_num * block_size * 100 / total_size, 100)
                downloaded_mb = block_num * block_size / (1024 * 1024)
                total_mb = total_size / (1024 * 1024)
                print(f"\r    Progress: {percent:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", end='', flush=True)
        
        urllib.request.urlretrieve(url, output_path, reporthook=reporthook, context=context)
        print()  # New line after progress
        return True
        
    except Exception as e:
        print(f"\n    ✗ Failed: {e}")
        return False

def merge_chunks(chunk_files, output_file):
    """Merge chunk files into single model file."""
    print(f"\n{'='*70}")
    print("MERGING CHUNKS")
    print("="*70)
    
    with open(output_file, 'wb') as out_f:
        for i, chunk_file in enumerate(sorted(chunk_files), 1):
            print(f"  [{i}/{len(chunk_files)}] {chunk_file.name}... ", end='', flush=True)
            with open(chunk_file, 'rb') as chunk_f:
                out_f.write(chunk_f.read())
            print("✓")
    
    # Verify
    total_size = sum(f.stat().st_size for f in chunk_files)
    merged_size = output_file.stat().st_size
    
    if total_size == merged_size:
        print(f"\n✓ Merge successful! Size: {merged_size / (1024*1024):.2f} MB")
        return True
    else:
        print(f"\n✗ Merge failed! Size mismatch: {total_size} vs {merged_size}")
        return False

def download_from_github_release(repo, tag, base_filename):
    """
    Download model chunks from GitHub release and merge.
    
    Args:
        repo: GitHub repo (e.g., "username/repo-name")
        tag: Release tag (e.g., "model-v1.0")
        base_filename: Base model filename (e.g., "Meta-Llama-3-8B-Instruct.Q4_0.gguf")
    """
    models_dir = Path(__file__).parent / "models"
    models_dir.mkdir(exist_ok=True)
    
    output_file = models_dir / base_filename
    
    # Check if model already exists
    if output_file.exists():
        print(f"\n⚠ Model already exists: {output_file}")
        response = input("Re-download and overwrite? (y/n): ")
        if response.lower() != 'y':
            print("Download cancelled.")
            return False
    
    print("="*70)
    print("GITHUB MODEL DOWNLOADER")
    print("="*70)
    print(f"Repository: {repo}")
    print(f"Release: {tag}")
    print(f"Model: {base_filename}")
    print()
    
    # Get release info from GitHub API
    api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    print(f"Fetching release info...")
    
    try:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(api_url, context=context) as response:
            release_data = json.loads(response.read())
    except Exception as e:
        print(f"✗ Failed to get release info: {e}")
        print(f"\nManual download:")
        print(f"  1. Go to: https://github.com/{repo}/releases/tag/{tag}")
        print(f"  2. Download all .part files")
        print(f"  3. Run: python merge_model_chunks.py <download_folder>")
        return False
    
    # Find chunk files or single file
    assets = release_data.get('assets', [])
    
    # Check if it's a single file (no splitting)
    single_file = [a for a in assets if a['name'] == base_filename]
    if single_file:
        print(f"Found single model file (no chunks)")
        asset = single_file[0]
        size_mb = asset['size'] / (1024 * 1024)
        print(f"  {asset['name']} - {size_mb:.2f} MB")
        print()
        print(f"Downloading...")
        
        if download_file(asset['browser_download_url'], output_file):
            print(f"\n{'='*70}")
            print("SUCCESS!")
            print("="*70)
            print(f"Model saved to: {output_file}")
            print(f"\nReady to use! Run: python main.py OPC_TEST.xlsm")
            return True
        else:
            return False
    
    # Check for chunk files
    chunk_assets = [a for a in assets if base_filename in a['name'] and '.part' in a['name']]
    
    if not chunk_assets:
        print(f"✗ No files found for {base_filename}")
        print(f"\nAvailable files in release:")
        for asset in assets:
            print(f"  - {asset['name']}")
        return False
    
    print(f"Found {len(chunk_assets)} chunks:")
    for asset in sorted(chunk_assets, key=lambda x: x['name']):
        size_mb = asset['size'] / (1024 * 1024)
        print(f"  {asset['name']} - {size_mb:.2f} MB")
    
    # Download chunks
    temp_dir = models_dir / "temp_chunks"
    temp_dir.mkdir(exist_ok=True)
    
    print(f"\n{'='*70}")
    print("DOWNLOADING CHUNKS")
    print("="*70)
    
    chunk_files = []
    for i, asset in enumerate(sorted(chunk_assets, key=lambda x: x['name']), 1):
        chunk_path = temp_dir / asset['name']
        print(f"\n  [{i}/{len(chunk_assets)}] {asset['name']}")
        
        if not download_file(asset['browser_download_url'], chunk_path):
            print(f"\n✗ Download failed.")
            print(f"Manual download: https://github.com/{repo}/releases/tag/{tag}")
            return False
        
        chunk_files.append(chunk_path)
    
    # Merge chunks
    if merge_chunks(chunk_files, output_file):
        # Cleanup
        print("\nCleaning up temporary files...")
        for chunk_file in chunk_files:
            chunk_file.unlink()
        temp_dir.rmdir()
        
        print(f"\n{'='*70}")
        print("SUCCESS!")
        print("="*70)
        print(f"Model saved to: {output_file}")
        print(f"\nNext steps:")
        print(f"1. Update config.py line 8:")
        print(f'   LLM_MODEL = "{base_filename}"')
        print(f"2. Run: python main.py OPC_TEST.xlsm")
        return True
    else:
        return False

def main():
    print("="*70)
    print("GITHUB MODEL DOWNLOADER & MERGER")
    print("="*70)
    print()
    
    # Default values for your project
    default_repo = "robertoriosr1998/project-robot-2"
    default_tag = "model-v1.0"
    default_model = "Meta-Llama-3-8B-Instruct.Q4_0.gguf"
    
    if len(sys.argv) == 4:
        # Command line mode
        repo = sys.argv[1]
        tag = sys.argv[2]
        model = sys.argv[3]
    else:
        # Interactive mode
        print("This will download the model from your GitHub release.")
        print()
        
        repo = input(f"GitHub repo [{default_repo}]: ").strip() or default_repo
        tag = input(f"Release tag [{default_tag}]: ").strip() or default_tag
        model = input(f"Model filename [{default_model}]: ").strip() or default_model
        print()
    
    success = download_from_github_release(repo, tag, model)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
