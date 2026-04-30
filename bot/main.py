from __future__ import annotations

from bot.app import run_cli
from bot.cli import build_parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_cli(args, parser)


if __name__ == "__main__":
    main()
