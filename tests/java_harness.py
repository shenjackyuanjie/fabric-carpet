"""Compile actual changed Java classes with minimal, explicit host/API stand-ins.

These are isolated behavior tests, not a Minecraft server or a Mixin runtime test.
The normal Gradle build additionally compiles against the real 1.16.5 dependencies.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run_java(main_class, sources, stubs, resources=None):
    if not shutil.which('javac') or not shutil.which('java'):
        raise unittest.SkipTest('The isolated Java regression tests require a JDK 9 or later')
    with tempfile.TemporaryDirectory(prefix='carpet-1165-test-') as folder:
        folder = Path(folder)
        source_dir = folder / 'src'
        classes = folder / 'classes'
        classes.mkdir()
        for name, content in stubs.items():
            target = source_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        for relative in sources:
            target = source_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'src/main/java' / relative, target)
        for relative, content in (resources or {}).items():
            target = classes / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        compile_result = subprocess.run(
            ['javac', '--release', '8', '-encoding', 'UTF-8', '-d', str(classes)]
            + [str(p) for p in source_dir.rglob('*.java')],
            text=True, capture_output=True, timeout=60,
        )
        if compile_result.returncode:
            raise AssertionError(compile_result.stdout + compile_result.stderr)
        run_result = subprocess.run(
            ['java', '-ea', '-cp', str(classes), main_class],
            text=True, capture_output=True, timeout=30,
        )
        if run_result.returncode:
            raise AssertionError(run_result.stdout + run_result.stderr)
        return run_result.stdout
