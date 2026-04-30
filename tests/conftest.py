import sys
from pathlib import Path

# Put apps/api on the path so test imports resolve (core.*, db.*, config.*)
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))
