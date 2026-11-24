from pathlib import Path

import pytest

from monitor.folder import FolderAmbiguous, FolderNotFound, resolve_folder

MR = "https://gitlab.com/skillcorner/software/wilson/-/merge_requests/2860"


def write_state(cache: Path, slug: str, text: str) -> Path:
    folder = cache / slug
    folder.mkdir(parents=True)
    (folder / "state.md").write_text(text)
    return folder


def test_session_folder_wins(tmp_path: Path):
    session = tmp_path / "session-feature"
    session.mkdir()
    assert resolve_folder(session, None, tmp_path) == session


def test_mr_url_matches_single_state_file(tmp_path: Path):
    folder = write_state(tmp_path, "competition", f"- MR {MR} (draft)\n")
    write_state(tmp_path, "other", "- MR https://gitlab.com/x/y/-/merge_requests/1\n")
    assert resolve_folder(None, MR, tmp_path) == folder


def test_two_matches_are_ambiguous(tmp_path: Path):
    write_state(tmp_path, "a", f"{MR}\n")
    write_state(tmp_path, "b", f"{MR}\n")
    with pytest.raises(FolderAmbiguous):
        resolve_folder(None, MR, tmp_path)


def test_no_match_is_not_found(tmp_path: Path):
    write_state(tmp_path, "a", "nothing here\n")
    with pytest.raises(FolderNotFound):
        resolve_folder(None, MR, tmp_path)


def test_shorter_mr_url_does_not_match_longer_one(tmp_path: Path):
    write_state(tmp_path, "long", f"{MR}0\n")
    with pytest.raises(FolderNotFound):
        resolve_folder(None, MR[:-1], tmp_path)
