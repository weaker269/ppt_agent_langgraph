import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "src.agent" not in sys.modules:
    agent_pkg = types.ModuleType("src.agent")
    agent_pkg.__path__ = [str(PROJECT_ROOT / "src" / "agent")]
    sys.modules["src.agent"] = agent_pkg

if "faiss" not in sys.modules:
    fake_faiss = types.ModuleType("faiss")

    class _FakeIndex:
        def __init__(self, *args, **kwargs):
            self.args = args

        def add(self, *args, **kwargs):  # pragma: no cover - 仅用于占位
            return None

    def _fake_read_index(*args, **kwargs):
        return _FakeIndex()

    def _fake_write_index(*args, **kwargs):
        return None

    fake_faiss.IndexFlatIP = _FakeIndex
    fake_faiss.read_index = _fake_read_index
    fake_faiss.write_index = _fake_write_index
    sys.modules["faiss"] = fake_faiss

if "jieba" not in sys.modules:
    fake_jieba = types.ModuleType("jieba")

    def _fake_lcut(text, *args, **kwargs):
        return list(text)

    fake_jieba.lcut = _fake_lcut
    sys.modules["jieba"] = fake_jieba
