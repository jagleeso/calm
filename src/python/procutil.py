import logging
import subprocess
from StringIO import StringIO

import logconfig
logger = logging.getLogger(__name__)

class WrappedCalledProcessError(Exception):
    pass

def call(cmd):
    try:
        return subprocess.check_output(cmd)
    except subprocess.CalledProcessError as e:
        cmd_str = " ".join(cmd)
        exit_code = e.returncode
        stderr_str = e.output
        raise WrappedCalledProcessError("Failed to execute \"{cmd_str}\" (exit code {exit_code}).  Standard error was:\n{stderr_str}".format(**locals()))
