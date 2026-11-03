#!/usr/bin/env python3
"""Pack build_lal.sh's LAL and LALSimulation into a tarball that jobs run them from.

Execute nodes have no /home, so a job cannot reach the environment build_lal.sh installs into.
The tarball, lal_<patch10>.tar.gz, holds under the folder lal_<patch10>/:

* python/: The lal and lalsimulation Python packages, to go first on sys.path.
* lib/: The shared libraries those packages load from the environment, as ldd finds them: LAL's
  own and their dependencies (GSL, FFTW and so on), under the names they are asked for by. The
  files are the build's own, unmodified. Their run paths still name the environment on /home, so
  a job finds them through LD_LIBRARY_PATH (xphm_job.py).
* BUILT.txt and MANIFEST.json: What was built, and the sha256 of each library.

    python -I pack_lal.py --env ENV --built BUILT.txt --output-dir DIR

Prints a JSON record of the tarball. Standard library and ldd only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Callable, Dict, List

LDD_LINE = re.compile(r"^\s*(\S+)\s+=>\s+(\S*/\S+)(\s+\(0x[0-9a-f]+\))?\s*$")


def parse_ldd(text: str) -> Dict[str, str]:
    """{name asked for: path} from ldd's output. A library ldd cannot find is an error."""
    found = {}
    for line in text.splitlines():
        if "not found" in line:
            raise ValueError(f"ldd cannot find {line.split()[0]}")
        match = LDD_LINE.match(line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def run_ldd(path: Path) -> str:
    return subprocess.run(["ldd", str(path)], check=True, stdout=subprocess.PIPE, universal_newlines=True).stdout


def libraries_in_env(extensions: List[Path], env: Path, ldd: Callable[[Path], str] = run_ldd) -> Dict[str, Path]:
    """The libraries the extension modules load from the environment. ldd lists what they load
    directly and indirectly, so this is the whole closure; the rest (libc, libm) is the image's."""
    env = env.resolve()
    libraries = {}
    for extension in extensions:
        for name, path in parse_ldd(ldd(extension)).items():
            if env in Path(path).resolve().parents:
                libraries[name] = Path(path)
    return libraries


def patch_hash(built: Path) -> str:
    for line in built.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(" ")
        if key == "patch_sha256" and value:
            return value.strip()
    raise ValueError(f"{built} has no patch_sha256")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def without_bytecode(info: tarfile.TarInfo):
    return None if "__pycache__" in info.name.split("/") else info


def pack(env: Path, built: Path, output_dir: Path, ldd: Callable[[Path], str] = run_ldd) -> dict:
    sites = sorted(env.glob("lib/python3.*/site-packages"))
    if len(sites) != 1:
        raise ValueError(f"Expected one site-packages in {env}, found {len(sites)}")
    site = sites[0]
    extensions = sorted(site.glob("lal/_lal*.so")) + sorted(site.glob("lalsimulation/_lalsimulation*.so"))
    if len(extensions) != 2:
        raise ValueError(f"Expected the lal and lalsimulation extension modules in {site}, found {extensions}")
    libraries = libraries_in_env(extensions, env, ldd)
    # Both extension modules load liblal; liblalsimulation can be linked into _lalsimulation itself
    # (conda-forge's packages are), so it is not required.
    if not any(name.startswith("liblal.so") for name in libraries):
        raise ValueError(f"ldd did not find liblal.so in {env}")

    patch = patch_hash(built)
    top = f"lal_{patch[:10]}"
    output_dir.mkdir(parents=True, exist_ok=True)
    tarball = output_dir / f"{top}.tar.gz"
    hashes, packed = {}, {}
    with tarfile.open(tarball, "w:gz") as archive:
        archive.add(site / "lal", f"{top}/python/lal", filter=without_bytecode)
        archive.add(site / "lalsimulation", f"{top}/python/lalsimulation", filter=without_bytecode)
        archive.add(built, f"{top}/BUILT.txt")
        for name, library in sorted(libraries.items()):
            real = library.resolve()
            hashes[name] = sha256(real)
            if real in packed:  # one file under two names, such as libcblas and libopenblas
                link = tarfile.TarInfo(f"{top}/lib/{name}")
                link.type = tarfile.SYMTYPE
                link.linkname = packed[real]
                archive.addfile(link)
            else:
                archive.add(real, f"{top}/lib/{name}")
                packed[real] = name
        manifest = json.dumps({"patch_sha256": patch, "libraries": hashes}, indent=2).encode("utf-8")
        info = tarfile.TarInfo(f"{top}/MANIFEST.json")
        info.size = len(manifest)
        archive.addfile(info, io.BytesIO(manifest))
    return {
        "path": str(tarball),
        "top": top,
        "patch_sha256": patch,
        "libraries": sorted(libraries),
        "bytes": tarball.stat().st_size
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", required=True, type=Path, help="The environment build_lal.sh installed into")
    parser.add_argument("--built", required=True, type=Path, help="Its BUILT.txt")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        record = pack(args.env, args.built, args.output_dir)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
