"""The compatibility verifier fails closed without opening a database."""

import json
from pathlib import Path
import subprocess
import sys


def test_retired_verifier_returns_documented_exit_code() -> None:
    script = Path(__file__).parents[1] / "scripts" / "verify_real_data.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True,
                            text=True, check=False)
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "LEGACY_BFF_VERIFIER_RETIRED"
    assert result.stderr == ""
