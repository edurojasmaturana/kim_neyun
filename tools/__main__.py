"""
Permite ejecutar el paquete como script:
    python -m tools <command> [--config CONFIG] [options]

Simplemente delega a tools.cli.main().
"""
import sys

from .cli import main

if __name__ == '__main__':
    sys.exit(main())
