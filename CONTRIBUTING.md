# Contributing to DINGO-lensing

Thank you for your interest in contributing to DINGO-lensing. Contributions of new features, lens models, bug fixes, documentation, tests, and other improvements are welcome.

To keep the codebase readable, maintainable, and scientifically reliable, all contributions should follow the guidelines below.

## Development setup

Clone the repository and create the DINGO-lensing environment:

```bash
git clone git@github.com:dingo-lensing/dingo-lensing.git
cd dingo-lensing

conda env create -f environment.yml
conda activate dingo-lensing
```

Install DINGO-lensing in editable mode:

```bash
pip install -e .
```

For development and testing, install `pytest` if it is not already available in your environment:

```bash
pip install pytest
```

We recommend developing new features on a separate branch rather than directly on `main`.

## Code style

DINGO-lensing follows the **PEP 8** style guide for Python code.

In particular:

- Use four spaces for indentation. Do not use tabs.
- Use descriptive variable, function, and class names.
- Use `snake_case` for functions and variables.
- Use `PascalCase` for classes.
- Organize imports according to PEP 8: standard-library imports, third-party imports, and local imports should be placed in separate groups.
- Keep functions focused on a well-defined task whenever possible.
- Avoid unnecessary duplication of code.
- Follow the PEP 8 recommendations for whitespace and line length.
- Prefer readable code over unnecessarily compact or clever implementations.

Small deviations from PEP 8 may occasionally be appropriate when they substantially improve readability, particularly for mathematical expressions. Such deviations should be intentional and easy to understand.

## Docstrings

**Every newly implemented function and method must include a docstring.**

This requirement applies to both public functions and internal helper functions. New classes should also include a docstring describing their purpose.

Docstrings should clearly explain:

- What the function does.
- The meaning of its arguments.
- The expected types, shapes, or units of arguments when these are not obvious.
- What the function returns.
- The meaning, type, shape, or units of the returned value when appropriate.
- Any important assumptions or conventions.
- Exceptions that may be raised when relevant.

For scientific routines, please document conventions carefully. For example, if a quantity is expected in detector-frame rather than source-frame units, or if an array has a particular frequency convention or shape, this should be stated explicitly.

We recommend using a consistent NumPy-style format. For example:

```python
def example_function(frequency_array, lens_mass):
    """Compute an example lensing quantity.

    Parameters
    ----------
    frequency_array : array-like
        Frequencies in Hz at which the quantity is evaluated.
    lens_mass : float
        Detector-frame lens mass in solar masses.

    Returns
    -------
    numpy.ndarray
        The computed quantity evaluated at each frequency.

    Raises
    ------
    ValueError
        If ``lens_mass`` is not positive.
    """
```

Sections that do not apply to a particular function may be omitted. However, the docstring should contain enough information for another contributor to understand and use the function without having to inspect its implementation.

Inline comments should be used to explain non-obvious implementation details, mathematical manipulations, or design choices. Comments should explain **why** something is being done rather than simply restating what the code does.

## Unit tests

**New functionality must be accompanied by unit tests.**

A contribution that adds a new function or changes existing behavior is generally not considered complete unless the corresponding behavior is tested.

Tests should be placed under the `tests/` directory and should follow the usual `pytest` naming conventions. For example,

```text
dingo_lensing/
    waveform_generator.py
    lens_code_loader.py
    ...

tests/
    test_waveform_generator.py
    test_lens_code_loader.py
    ...
```

Test files should be named `test_<module>.py`, and individual test functions should begin with `test_`.

Unit tests should, where applicable, cover:

- The expected behavior for representative inputs.
- Important edge cases.
- Invalid inputs and expected exceptions.
- Array shapes and data types.
- Numerically known or analytically understood limiting cases.
- Previously identified bugs.

For numerical calculations, avoid exact floating-point comparisons when they are not appropriate. Use tools such as

```python
numpy.testing.assert_allclose(...)
```

or

```python
pytest.approx(...)
```

with physically and numerically justified tolerances.

Tests should be deterministic whenever possible. Avoid tests whose result depends on network access, uncontrolled random numbers, or external state. If random samples are required, use a fixed random seed where appropriate.

For bug fixes, please include a **regression test** that demonstrates the incorrect behavior before the fix and verifies the correct behavior afterward.

Run the test suite before submitting a pull request:

```bash
python -m pytest
```

All tests should pass before a contribution is merged.

## Scientific correctness

DINGO-lensing is scientific software, so numerical correctness is as important as software correctness.

When implementing or modifying a scientific calculation:

- Clearly document the mathematical and physical conventions being used.
- Pay particular attention to units, reference frames, parameter definitions, and array conventions.
- Test known analytical results or limiting cases whenever possible.
- When implementing an equation from the literature, provide an appropriate reference in the docstring or nearby comments when useful.
- Avoid silently changing an existing convention or interpretation.
- Make numerical tolerances explicit when they affect the result.

When adding a new lens model or lensing implementation, contributors should also consult `REFACTORING_GUIDE.md` for the expected interface and organization.

## Backward compatibility

Changes should avoid unnecessarily breaking existing interfaces.

If a contribution changes the behavior or interface of an existing function, please explain the reason clearly in the pull request. Where practical, update existing code and tests to preserve compatibility.

Large API changes should be discussed with the maintainers before substantial implementation work is undertaken.

## Pull requests

Before opening a pull request, please make sure that:

- The code follows PEP 8.
- Every new function and method has an appropriate docstring.
- New functionality is covered by unit tests.
- Bug fixes include regression tests where appropriate.
- The complete test suite passes.
- Scientific conventions and assumptions are documented.
- Unrelated changes have not been included in the same pull request.

Please keep pull requests focused. A pull request that addresses one feature, bug, or well-defined refactoring is generally easier to review than one containing several unrelated changes.

The pull-request description should briefly explain:

1. What was changed.
2. Why the change was necessary.
3. How the change was tested.
4. Any scientific or API assumptions that reviewers should be aware of.

## Reporting issues

When reporting a bug, please provide enough information to reproduce the problem whenever possible, including:

- A minimal example demonstrating the issue.
- The expected behavior.
- The observed behavior.
- Relevant error messages or tracebacks.
- The Python and DINGO-lensing versions being used.
- Any relevant dependency versions or configuration settings.

For scientific issues, please also describe the physical or mathematical behavior you expected and, where appropriate, provide a reference.

## License

By contributing to DINGO-lensing, you agree that your contributions will be distributed under the license used by this repository.
