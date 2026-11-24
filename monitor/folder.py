from pathlib import Path

STATE_NAME = "state.md"


class FolderNotFound(Exception):
    pass


class FolderAmbiguous(Exception):
    pass


def resolve_folder(session_folder: Path | None, mr_url: str | None, cache_root: Path) -> Path:
    if session_folder is not None:
        return session_folder
    if mr_url is None:
        raise FolderNotFound("no session folder and no MR URL")
    matches = _folders_citing(mr_url, cache_root)
    if not matches:
        raise FolderNotFound(f"no state.md cites {mr_url}")
    if len(matches) > 1:
        raise FolderAmbiguous(f"{len(matches)} state.md files cite {mr_url}")
    return matches[0]


def _folders_citing(mr_url: str, cache_root: Path) -> list[Path]:
    return [
        state.parent
        for state in sorted(cache_root.glob(f"*/{STATE_NAME}"))
        if mr_url in state.read_text()
    ]
