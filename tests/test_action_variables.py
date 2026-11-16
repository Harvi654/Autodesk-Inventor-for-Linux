"""Unknown %VARIABLES% in a custom action's parameters skip the action with
a warning instead of passing the text on (docs/installer-completeness-
review.md, "Needed" 6); what is left out of MSI properties, install
parameters and action types is listed too. Synthetic step dicts, dry run."""
import os
import shlex
import tempfile
import unittest
from pathlib import Path

import image_fixture as fx


def step(actions=(), params="", msi=None, name="Pkg"):
    return {"name": name, "type": "EXE", "display": name, "version": "1", "file": "x64/pkg/setup.exe",
            "params": params, "installLocation": None, "msiProperties": msi or {}, "properties": {},
            "actions": [{"type": t, "path": p, "params": a} for t, p, a in actions]}


class ActionVariables(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="inventor-action-vars-")
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        (t / "image").mkdir()
        (t / "prefix").mkdir()
        saved = os.environ.get("INV_LOGDIR")
        self.addCleanup(lambda: os.environ.pop("INV_LOGDIR", None) if saved is None
                        else os.environ.__setitem__("INV_LOGDIR", saved))
        self.mod, self.inst = fx.installer(t / "image", t / "prefix", t / "logs")
        self.seen = []
        # the command as logged: an msiexec line with a space runs through a batch file
        self.inst.run = lambda argv, logname, timeout=None, show=None: \
            self.seen.append(shlex.split(show) if show else argv) or 0

    def log(self):
        return Path(self.inst.logdir, "install.log").read_text()

    def test_unknown_parameter_skips_the_action(self):
        s = step([("postInstall", r"%PROGRAMFILES%\Tool\InvAcNGEN.exe", r'install "%INV_INSTALL_PATH%Bin"')])
        self.assertTrue(self.inst.do_actions(s, "x.log"))
        self.assertEqual(self.seen, [])
        self.assertIn(r'WARN skip action postInstall %PROGRAMFILES%\Tool\InvAcNGEN.exe install '
                      r'"%INV_INSTALL_PATH%Bin": unknown %INV_INSTALL_PATH%', self.log())

    def test_known_parameters_run(self):
        self.inst.vars["inv_install_path"] = "C:\\Program Files\\Autodesk\\Inventor 2027\\"
        s = step([("postInstall", r"%PROGRAMFILES%\Tool\InvAcNGEN.exe", r'install "%INV_INSTALL_PATH%Bin"')])
        self.assertTrue(self.inst.do_actions(s, "x.log"))
        self.assertEqual(self.seen[0][1:], [r"C:\Program Files\Tool\InvAcNGEN.exe", "install",
                                            r"C:\Program Files\Autodesk\Inventor 2027\Bin"])

    def test_a_percent_sign_that_is_no_variable_runs(self):
        s = step([("postInstall", r"C:\Tool\t.exe", "--progress 50% --quiet")])
        self.inst.do_actions(s, "x.log")
        self.assertEqual(self.seen[0][2:], ["--progress", "50%", "--quiet"])

    def test_unknown_path_is_still_skipped(self):
        s = step([("preInstall", r"%SOMEWHERE%\t.exe", "")])
        self.inst.do_actions(s, "x.log")
        self.assertEqual(self.seen, [])
        self.assertIn(r"WARN skip action preInstall %SOMEWHERE%\t.exe : unknown %SOMEWHERE%", self.log())

    def test_action_types_never_run_are_listed(self):
        s = step([("preUninstall", r"C:\Tool\u.exe", "/remove"), ("postInstall", r"C:\Tool\p.exe", "")])
        self.inst.log_unrun_actions(s)
        log = self.log()
        self.assertIn(r"skip action preUninstall C:\Tool\u.exe /remove: action type not run by this installer", log)
        self.assertNotIn("p.exe", log)

    def test_install_parameters_with_unknown_variables_are_said(self):
        self.inst.do_exe(step(params="/quiet LANG=%LANGUAGE_CODE%"), "x.log")
        self.assertEqual(self.seen[0][2:], ["/quiet", "LANG=%LANGUAGE_CODE%"])
        self.assertIn("WARN install parameters of Pkg keep unknown %LANGUAGE_CODE%: /quiet LANG=%LANGUAGE_CODE%",
                      self.log())

    def test_msi_properties_left_out_are_listed(self):
        s = dict(step(msi={"UNITS": "%UNITS%", "ADSK_LANG": "en-US", "SERIAL": "%ACADSERIALNUMBER%"}), type="MSI",
                 file="x64/pkg/p.msi")
        self.inst.do_msi(s, "x.log")
        self.assertIn("ADSK_LANG=en-US", self.seen[0])
        self.assertIn("MSI properties left out (unknown variable): UNITS (%UNITS%), SERIAL (%ACADSERIALNUMBER%)",
                      self.log())


if __name__ == "__main__":
    unittest.main()
