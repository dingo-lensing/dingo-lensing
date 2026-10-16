# local-tests-sync

A utility branch for test scripts, benchmarks, cluster tooling and results. Not for review or merge: It moves files between the local machine and the CIT cluster through git, and keeps tests out of the DINGO-Lensing branches that go to review.

## Layout

- `parallelisation/`: The DINGO-Lensing parallelisation investigation (option A tests T1 to T4, the container image tooling, analysis and results).
- `dingo_speedups/`: Speeding up importance sampling in the latest DINGO. Plan and log in `dingo_speedups/test_log.md`.
- `test_modwaveforms_amplification.py`: Unit tests from the waveform generator refactor.

Until 16 October 2026 the branch root also carried a copy of an old DINGO-Lensing commit (`dingo_lensing/`, `pyproject.toml`, `examples/`). It was removed because running Python or pip from here picked up that stale code. Code under test always comes from a real checkout or an installed package, never from this branch.

## Running the tests locally

```
cd parallelisation
python -m unittest discover -s tests
```

Tests that need DINGO are skipped locally and run on the cluster, in the image.
