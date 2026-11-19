"""把仓库根加入 ``sys.path``，保证 ``python -m pytest tests -q`` 能导入 render。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
