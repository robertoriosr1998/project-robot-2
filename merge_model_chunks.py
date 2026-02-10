"""
Merge model chunk files into a complete model file.
Use this after downloading chunks from GitHub release.
"""
import sys
from pathlib import Path

def merge_chunks(chunks_dir: str, output_filename: str = None):
    """
    Merge .part files in a directory into a single file.
    
    Args:
        chunks_dir: Directory containing .part01, .part02, etc. files
        output_filename: Name for output file (optional, auto-detected from parts)
    
    Returns:
        Path to merged file, or None if failed
    """
    chunks_path = Path(chunks_dir)
    
    if not chunks_path.exists():
        print(f"Error: Directory not found: {chunks_dir}")
        return None
    
    # Find all .part files
    part_files = sorted(chunks_path.glob("*.part*"))
    
    if not part_files:
        print(f"Error: No .part files found in {chunks_dir}")
        return None
    
    print(f"Found {len(part_files)} chunk files:")
    total_size = 0
    for pf in part_files:
        size_mb = pf.stat().st_size / (1024 * 1024)
        total_size += size_mb
        print(f"  {pf.name} - {size_mb:.2f} MB")
    
    print(f"\nTotal size: {total_size:.2f} MB")
    
    # Determine output filename
    if output_filename is None:
        # Extract base filename from first part (remove .part01, etc.)
        base_name = part_files[0].name
        if '.part' in base_name:
            output_filename = base_name.split('.part')[0] + '.gguf'
        else:
            output_filename = "merged_model.gguf"
    
    # Output to models/ folder
    models_dir = Path(__file__).parent / "models"
    models_dir.mkdir(exist_ok=True)
    output_path = models_dir / output_filename
    
    print(f"\nMerging into: {output_path}")
    
    # Check if output already exists
    if output_path.exists():
        response = input(f"\nFile already exists: {output_path}\nOverwrite? (y/n): ")
        if response.lower() != 'y':
            print("Merge cancelled.")
            return None
    
    # Merge chunks
    print("\nMerging chunks...")
    try:
        with open(output_path, 'wb') as out_f:
            for i, part_file in enumerate(part_files, 1):
                print(f"  [{i}/{len(part_files)}] {part_file.name}... ", end='', flush=True)
                with open(part_file, 'rb') as part_f:
                    chunk_data = part_f.read()
                    out_f.write(chunk_data)
                print("✓")
        
        # Verify merged file size
        output_size_mb = output_path.stat().st_size / (1024 * 1024)
        
        print(f"\n{'='*70}")
        print("SUCCESS!")
        print("="*70)
        print(f"Merged file: {output_path}")
        print(f"Size: {output_size_mb:.2f} MB")
        
        # Verify size matches
        if abs(output_size_mb - total_size) < 0.1:  # Allow small difference due to rounding
            print("✓ Size verification passed")
        else:
            print(f"⚠ Warning: Size mismatch (expected {total_size:.2f} MB, got {output_size_mb:.2f} MB)")
        
        print(f"\nNext steps:")
        print(f"1. Update config.py line 8:")
        print(f'   LLM_MODEL = "{output_filename}"')
        print(f"2. Run: python main.py OPC_TEST.xlsm")
        
        return output_path
        
    except Exception as e:
        print(f"\n✗ Merge failed: {e}")
        if output_path.exists():
            output_path.unlink()  # Clean up partial file
        return None

def main():
    print("="*70)
    print("MODEL CHUNK MERGER")
    print("="*70)
    print()
    
    # Check command line arguments
    if len(sys.argv) >= 2:
        chunks_dir = sys.argv[1]
        output_filename = sys.argv[2] if len(sys.argv) >= 3 else None
    else:
        # Interactive mode
        print("This script merges .part files into a complete model file.")
        print()
        chunks_dir = input("Enter path to directory with .part files: ").strip()
        if not chunks_dir:
            print("Error: Directory path required")
            return 1
        
        output_filename = input("Enter output filename (or press Enter for auto-detect): ").strip()
        if not output_filename:
            output_filename = None
        
        print()
    
    result = merge_chunks(chunks_dir, output_filename)
    
    return 0 if result else 1

if __name__ == "__main__":
    sys.exit(main())
