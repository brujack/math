import argparse
import array
import io
import os
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

from collatz import (
    collatz_next,
    collatz_length,
    generate_records,
    get_exponent,
    main,
    parse_args,
)


if __name__ == "__main__":
    unittest.main()
