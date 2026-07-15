"""hub_lib — stdlib-only pure logic shared by hooks, workflows and tests.

Nothing here imports a third-party package: hooks run via `uv run --no-project`
and must not pay dependency-resolution cost. Keep it that way.
"""
