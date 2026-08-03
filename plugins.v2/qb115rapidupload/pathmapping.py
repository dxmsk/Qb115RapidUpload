import re
from pathlib import Path
from typing import Callable, Iterable, List, Sequence, Tuple


PathMapping = Tuple[str, str]


def parse_path_mappings(value) -> List[PathMapping]:
    """Parse one qB-to-local path mapping per line."""
    if isinstance(value, (list, tuple, set)):
        lines = [str(item or "") for item in value]
    else:
        lines = re.split(r"[\r\n]+", str(value or ""))
    mappings: List[PathMapping] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        parts = re.split(r"\s*(?:=>|=|\|)\s*", text, maxsplit=1)
        if len(parts) != 2:
            continue
        source, target = (part.strip() for part in parts)
        if source and target and (source, target) not in mappings:
            mappings.append((source, target))
    return mappings


class LocalPathMapper:
    """Map qB container paths to paths visible inside MoviePilot."""

    def __init__(
        self,
        mappings: Sequence[PathMapping] = (),
        roots_getter: Callable[[], Iterable[str]] = lambda: (),
    ):
        self.mappings = list(mappings or ())
        self.roots_getter = roots_getter

    @staticmethod
    def _tokens(path: Path) -> List[str]:
        anchor = path.anchor
        return [part for part in path.parts if part and part != anchor]

    @staticmethod
    def _same(left: str, right: str) -> bool:
        return left.casefold() == right.casefold()

    def _explicit(self, path: Path) -> Path | None:
        for source_text, target_text in self.mappings:
            source = Path(source_text).expanduser()
            try:
                relative = path.relative_to(source)
            except ValueError:
                continue
            return Path(target_text).expanduser() / relative
        return None

    def map(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        path = Path(text).expanduser()
        try:
            if path.exists():
                return str(path)
        except OSError:
            pass

        explicit = self._explicit(path)
        if explicit is not None:
            return str(explicit)

        source_tokens = self._tokens(path)
        if not source_tokens:
            return text
        matches = []
        for root_text in self.roots_getter() or ():
            root_value = str(root_text or "").strip()
            if not root_value:
                continue
            root = Path(root_value).expanduser()
            root_tokens = self._tokens(root)
            if not root_tokens:
                continue

            direct = root.joinpath(*source_tokens)
            try:
                if direct.exists():
                    matches.append((len(source_tokens), direct))
            except OSError:
                pass

            max_overlap = min(len(root_tokens), len(source_tokens))
            for overlap in range(max_overlap, 0, -1):
                root_tail = root_tokens[-overlap:]
                found = False
                for start in range(0, len(source_tokens) - overlap + 1):
                    source_slice = source_tokens[start : start + overlap]
                    if not all(self._same(a, b) for a, b in zip(root_tail, source_slice)):
                        continue
                    candidate = root.joinpath(*source_tokens[start + overlap :])
                    try:
                        exists = candidate.exists()
                    except OSError:
                        exists = False
                    if exists:
                        matches.append((overlap, candidate))
                        found = True
                        break
                if found:
                    break

        if not matches:
            return text
        matches.sort(key=lambda item: item[0], reverse=True)
        return str(matches[0][1])
