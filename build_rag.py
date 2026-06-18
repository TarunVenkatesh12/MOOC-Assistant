from pathlib import Path
import sys

# Make sure imports resolve even if run from project root
sys.path.insert(0, str(Path(__file__).parent))

from rag.ingest import build_index, COURSE_DIR, INDEX_PATH

if __name__ == "__main__":
    print("=" * 60)
    print("  MOOC RAG — Building Course Index")
    print("=" * 60)
    print(f"  Course dir : {COURSE_DIR}")
    print(f"  Output     : {INDEX_PATH}")
    print()

    try:
        index = build_index(COURSE_DIR, INDEX_PATH)
        n_chunks = len(index["chunks"])
        print()
        print("=" * 60)
        print(f"  Done!  {n_chunks:,} chunks indexed")
        print(f"  Index saved to: {INDEX_PATH}")
        print("=" * 60)
    except FileNotFoundError as e:
        print(f"\n  ERROR: {e}")
        print("\nMake sure you've extracted the course tar.gz into course_data/")
        print("Expected structure:  course_data/course/html/*.html")
        sys.exit(1)