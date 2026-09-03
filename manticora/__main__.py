from rich.markup import escape

from manticora.app import cli
from manticora.core import Error, err


def main() -> None:
    try:
        cli()
    except Error as e:
        err.print(e)
        raise SystemExit(1)
    except Exception as e:
        err.print(f"[red bold]Unexpected error:[/red bold] {escape(str(e))}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
