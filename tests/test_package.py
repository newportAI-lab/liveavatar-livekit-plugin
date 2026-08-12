import subprocess
import sys
import tarfile
import zipfile

import pytest

from livekit.plugins import facemarket


def test_public_package_identity():
    assert facemarket.__version__ == "0.1.0"
    error = facemarket.APIError(1001, "avatar not found")
    assert error.code == 1001
    assert error.message == "avatar not found"
    assert "1001" in str(error)


def test_import_does_not_require_typing_self_added_in_python_311():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import builtins,httpx,livekit.api;"
                "original_import=builtins.__import__;"
                "guarded=lambda name,globals=None,locals=None,fromlist=(),level=0: "
                "(_ for _ in ()).throw(ImportError('typing.Self unavailable')) "
                "if name=='typing' and fromlist and 'Self' in fromlist else "
                "original_import(name,globals,locals,fromlist,level);"
                "builtins.__import__=guarded;"
                "from livekit.plugins import facemarket;"
                "print(facemarket.__version__)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.1.0"


@pytest.fixture(scope="module")
def built_distributions(tmp_path_factory):
    output = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    return next(output.glob("*.whl")), next(output.glob("*.tar.gz"))


def test_wheel_preserves_documented_namespace_package(built_distributions):
    wheel, _ = built_distributions
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())

    assert "livekit/plugins/facemarket/__init__.py" in names
    assert "facemarket/__init__.py" not in names


def test_fresh_target_wheel_install_imports_documented_path(built_distributions, tmp_path):
    wheel, _ = built_distributions
    target = tmp_path / "target"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(target),
            str(wheel),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import pathlib,sys;"
                f"target=pathlib.Path({str(target)!r}).resolve();"
                "sys.path.insert(0,str(target));"
                "from livekit.plugins import facemarket;"
                "module=pathlib.Path(facemarket.__file__).resolve();"
                "assert module.is_relative_to(target),(module,target);"
                "print(facemarket.__version__)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "0.1.0"


def test_sdist_excludes_internal_workflow_artifacts(built_distributions):
    _, sdist = built_distributions
    with tarfile.open(sdist) as archive:
        names = archive.getnames()

    assert not any("/.superpowers/" in name for name in names)
    assert not any("/docs/superpowers/" in name for name in names)
    assert any(name.endswith("/tests/test_package.py") for name in names)
