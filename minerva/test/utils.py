import os
import shutil
import subprocess
import textwrap
import traceback
import unittest

from amaranth import *
from amaranth.back import rtlil


__all__ = ["FormalTestCase"]


# Taken from amaranth.test.utils.FHDLTestCase

class FormalTestCase(unittest.TestCase):
    def assertFormal(self, spec, mode="bmc", depth=1):
        caller, *_ = traceback.extract_stack(limit=2)
        spec_root, _ = os.path.splitext(caller.filename)
        spec_dir = os.path.dirname(spec_root)
        spec_name = "{}_{}".format(
            os.path.basename(spec_root).replace("test_", "spec_"),
            caller.name.replace("test_", "")
        )

        # The sby -f switch seems not fully functional when sby is reading from stdin.
        if os.path.exists(os.path.join(spec_dir, spec_name)):
            shutil.rmtree(os.path.join(spec_dir, spec_name))

        if mode == "hybrid":
            script = "setattr -unset init w:* a:amaranth.sample_reg %d"
            mode   = "bmc"
        else:
            script = ""

        config = textwrap.dedent("""\
        [options]
        mode {mode}
        depth {depth}
        wait on

        [engines]
        smtbmc

        [script]
        read_ilang top.il
        prep
        {script}

        [file top.il]
        {rtlil}
        """).format(
            mode=mode,
            depth=depth,
            script=script,
            rtlil=rtlil.convert(Fragment.get(spec, platform="formal"), ports=())
        )
        with subprocess.Popen(["sby", "-f", "-d", spec_name], cwd=spec_dir,
                              universal_newlines=True,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
            stdout, stderr = proc.communicate(config)
            if proc.returncode != 0:
                self.fail("Formal verification failed:\n" + stdout)
