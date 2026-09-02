import sys
from pathlib import Path

# Add tests/aeo_writer to path
tests_path = Path(__file__).parent / "tests" / "aeo_writer"
sys.path.insert(0, str(tests_path))

# Import and re-export test data from subdirectory conftest
import importlib.util
spec = importlib.util.spec_from_file_location("aeo_conftest", tests_path / "conftest.py")
aeo_conftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aeo_conftest)

AI_GENERATED_TEXT = aeo_conftest.AI_GENERATED_TEXT
HUMAN_WRITTEN_TEXT = aeo_conftest.HUMAN_WRITTEN_TEXT
