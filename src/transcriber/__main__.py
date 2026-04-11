"""``python -m transcriber`` で起動するためのエントリポイント.

実装は :mod:`transcriber.cli` の ``main`` に委譲する. パッケージ外部からは
``uv run python -m transcriber transcribe <url>`` のように呼び出される.
"""

from transcriber.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
