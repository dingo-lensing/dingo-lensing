#!/usr/bin/env python3
"""Pack DINGO's source at one commit into a tarball that jobs run DINGO from.

DINGO is pure Python, so a job can import it straight from an unpacked source
tree, and the image needs no DINGO of its own (container/dingo-deps.def). The
tarball holds `git archive` of the commit under the folder dingo_<commit10>/,
plus two files that git does not track:

* COMMIT.json: The full commit, `git describe` and the version below. guard.py
  checks it before a script uses DINGO.
* dingo/_version.py: The file setuptools_scm writes when DINGO is installed.
  Without it DINGO stamps its outputs "dingo=None", which reads back as version
  0.0.0 and sets off its backward-compatibility warning.

The version follows setuptools_scm's default scheme: The tag's version at a
tagged commit, otherwise the next patch release as a development release, e.g.
0.10.4.dev1+gdd481d98 one commit after v0.10.3.

The same commit always gives byte-identical output, so the .sha256 file next to
the tarball identifies it.

    python -I pack_dingo.py --repo ~/dingo-effeciency --commit dd481d98 --output-dir DIR

Standard library and git only.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Tuple, Union

DESCRIBE = re.compile(r"^v(?P<tag>\d+(?:\.\d+)*)-(?P<distance>\d+)-g(?P<node>[0-9a-f]+)$")
COMMIT_FILE = "COMMIT.json"
VERSION_FILE = "dingo/_version.py"


class PackError(RuntimeError):
    """The commit cannot be packed; the message says why and what to do."""


@dataclass
class Packed:
    path: str
    sha256: str
    commit: str
    describe: str
    version: str
    reused: bool


def git(repo: Path, *args: str, binary: bool = False) -> Union[str, bytes]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip()
        raise PackError(f"git {' '.join(args)} failed in {repo}: {message}")
    return result.stdout if binary else result.stdout.decode().strip()


def version_from_describe(describe: str) -> Tuple[str, tuple]:
    """The version and version tuple setuptools_scm gives a `git describe --long` string."""
    match = DESCRIBE.match(describe)
    if match is None:
        raise PackError(
            f"Cannot read a version from 'git describe' output {describe!r}: "
            "Expected v<release>-<distance>-g<hash>, e.g. v0.10.3-1-gdd481d98"
        )
    release = [int(part) for part in match["tag"].split(".")]
    distance = int(match["distance"])
    if distance == 0:
        return ".".join(map(str, release)), tuple(release)
    release[-1] += 1
    node = "g" + match["node"]
    version = f"{'.'.join(map(str, release))}.dev{distance}+{node}"
    return version, (*release, f"dev{distance}", node)


def version_file_text(version: str, version_tuple: tuple) -> str:
    return (
        "# Written by pack_dingo.py, as setuptools_scm writes it when DINGO is installed.\n"
        f"__version__ = version = {version!r}\n"
        f"__version_tuple__ = version_tuple = {version_tuple!r}\n"
    )


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def add_file(archive: tarfile.TarFile, name: str, text: str, mtime: int) -> None:
    data = text.encode()
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = mtime
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    archive.addfile(info, io.BytesIO(data))


def pack(repo: Union[str, Path], ref: str, output_dir: Union[str, Path]) -> Packed:
    repo = Path(repo).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if not repo.is_dir():
        raise PackError(f"{repo} is not a folder")
    commit = git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if commit == git(repo, "rev-parse", "HEAD") and git(
        repo, "status", "--porcelain", "--untracked-files=no"
    ):
        raise PackError(
            f"{repo} has uncommitted changes, and {ref} is its checked-out commit: "
            "Commit them first, so the tarball and the commit agree"
        )
    try:
        describe = git(repo, "describe", "--tags", "--long", "--match", "v[0-9]*", commit)
    except PackError as error:
        raise PackError(
            f"{error}. The version comes from DINGO's release tags, which a clone of the "
            "fork may lack: Run git -C REPO fetch upstream --tags"
        ) from None
    version, version_tuple = version_from_describe(describe)
    mtime = int(git(repo, "show", "-s", "--format=%ct", commit))

    name = f"dingo_{commit[:10]}"
    target = output_dir / f"{name}.tar.gz"
    with tempfile.TemporaryDirectory() as scratch:
        tar_path = Path(scratch) / f"{name}.tar"
        tar_path.write_bytes(
            git(repo, "archive", "--format=tar", f"--prefix={name}/", commit, binary=True)
        )
        with tarfile.open(tar_path) as archive:
            members = set(archive.getnames())
        if f"{name}/dingo/__init__.py" not in members:
            raise PackError(f"Commit {commit} has no dingo/__init__.py: Is {repo} DINGO?")
        for extra in (COMMIT_FILE, VERSION_FILE):
            if f"{name}/{extra}" in members:
                raise PackError(f"Commit {commit} already tracks {extra}, which pack_dingo.py writes")

        record = {"commit": commit, "describe": describe, "version": version}
        with tarfile.open(tar_path, "a") as archive:
            add_file(archive, f"{name}/{COMMIT_FILE}", json.dumps(record, indent=2) + "\n", mtime)
            add_file(archive, f"{name}/{VERSION_FILE}", version_file_text(version, version_tuple), mtime)

        # gzip without a file name or time stamp in its header, so the bytes depend
        # only on the commit.
        packed = Path(scratch) / target.name
        with open(packed, "wb") as raw, gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, mtime=0
        ) as compressed:
            compressed.write(tar_path.read_bytes())
        digest = sha256_of(packed)

        reused = target.exists()
        if reused:
            if sha256_of(target) != digest:
                raise PackError(
                    f"{target} exists but differs from a fresh pack of {commit}: "
                    "Remove it, or pack into another folder"
                )
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(packed), str(target))
        with open(f"{target}.sha256", "w", newline="\n") as handle:
            handle.write(f"{digest}  {target.name}\n")
    return Packed(str(target), digest, commit, describe, version, reused)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True, help="A clone of DINGO (our fork)")
    parser.add_argument("--commit", default="HEAD", help="Commit, tag or branch to pack (default HEAD)")
    parser.add_argument("--output-dir", default=".", help="Where to write the tarball (default .)")
    args = parser.parse_args(argv)
    try:
        packed = pack(args.repo, args.commit, args.output_dir)
    except PackError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(packed), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
