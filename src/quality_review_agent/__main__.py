import sys

from .cli import main
from .interactive import main as interactive_main
from .webapp import serve


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        serve()
    elif len(sys.argv) > 1 and sys.argv[1] == "interactive":
        raise SystemExit(interactive_main(sys.argv[2:]))
    else:
        raise SystemExit(main())
