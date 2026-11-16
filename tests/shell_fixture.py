"""Resolve test fixture shells and keep the caller's executable search path."""
import os
import shutil


def shell_script(text):
    header, body = text.split("\n", 1)
    if header not in ("#!/bin/bash", "#!/bin/sh"):
        raise ValueError("unexpected fixture shell: " + header)
    name = header.rsplit("/", 1)[-1]
    executable = shutil.which(name)
    if executable is None:
        raise RuntimeError("test fixture requires " + name + " in PATH")
    return "#!" + executable + "\n" + body


def fixture_path(*directories):
    return os.pathsep.join([os.fspath(directory) for directory in directories] + [os.environ["PATH"]])
