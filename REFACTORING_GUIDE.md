# Refactoring Guide: Integrating a New Lens Model

This is a guide for adding a new lens model to DINGO-Lensing: either a new
amplification function for a lens code we already support (`modwaveforms`),
or an entirely new lens code (e.g. Gravelamps). It covers the general logic
just enough to work with it, then walks through exactly what to do, using
Gravelamps as a worked example.

## How it works, briefly

`LensedWaveformGenerator` doesn't hardcode anything about any specific lens
model. Every model is a small object with two methods:

```python
def resolve(self, parameters: dict, lens_model_defaults: dict) -> dict:
    """Pull whatever this model needs out of a sample's parameters."""

def compute(self, frequency_array, resolved: dict):
    """Turn those values into the amplification factor array."""
```

`resolve()` runs once per sample. It pops the values it needs out of
`parameters` (so they never reach the base, unlensed waveform code),
falling back to a configured default if a value isn't in the sample.
`compute()` then turns whatever `resolve()` returned into the actual
amplification factor.

Two pieces of bookkeeping every model does, on top of those two methods:

- **`PARAMETER_NAMES`**: a dict mapping every value this model reads to the
  DINGO-Lensing standard name it should be found under in a sample. This is
  required, and checked automatically when a model is loaded. Get a name
  wrong here and `resolve()` will look for something that isn't there and
  quietly fall back to a default instead. That's the main thing to get
  right when integrating a new model.
- **Fallback logging**: every time `resolve()` falls back to a default
  (either `lens_model_defaults` or a model's own built-in one) it logs it at
  `logging.DEBUG`, silent unless you turn it on. Worth doing once while
  testing a new model, to confirm it's actually reading real values and not
  quietly defaulting everything:
  ```python
  logging.getLogger("dingo_lensing.<your_code>_amplification").setLevel(logging.DEBUG)
  ```

And two separate places a value can come from beyond the sample itself:

- **`lens_model_defaults`**: per-sample fallback values, set once when the
  generator is configured, used whenever a sample doesn't include that
  value.
- **`lens_model_settings`**: fixed configuration built once at generator
  construction, forwarded straight to your model class's `__init__`. Use
  this for anything that isn't a per-sample value at all, like a lookup
  table loaded from a file.

## What you need to do

1. **Write your model class**, with `resolve()`, `compute()`, and
   `PARAMETER_NAMES`. If it needs one-time setup (a file to load, etc.),
   take that as an `__init__` argument, it'll arrive via
   `lens_model_settings`.
2. **If your lens code doesn't exist yet**, add a
   `dingo_lensing/<code>_amplification.py` module holding your model
   class(es), an `_AMPLIFICATION_MODEL_CLASSES` dict mapping amplification
   function names to classes, and a
   `get_model(amplification_factor_function, **lens_model_settings)`
   factory. (If you're adding a model to a lens code that already exists,
   this step is just adding a class and a dict entry to its existing
   module.)
3. **Register the lens code** by adding one entry to `_LENS_CODE_MODULES` in
   `lens_code_loader.py`.
4. **Point a dataset settings YAML at it**: set `lens_model_code`,
   `amplification_factor_function`, and, if you need them,
   `lens_model_settings` and/or `lens_model_defaults`.

That's it. Nothing else in the package needs to change: not
`waveform_generator.py`, not any other model's file, not the loader beyond
that one registration line.

## Worked example: Gravelamps

Gravelamps is a real sibling package with its own amplification functions
and its own established parameter names (`lens_mass`,
`lens_fractional_distance`, `source_position`). Here's what integrating its
O3 point-mass microlensing model (`gravelamps.models.microlensing_o3`) looks
like, step by step.

Reading `gravelamps/models/microlensing_o3.py`, the function to call is:

```python
def amplification(dimensionless_frequency, source_position, lookup_table=None):
    ...
```

`dimensionless_frequency` isn't the waveform's frequency array directly,
Gravelamps needs it converted first via
`microlensing_o3.frequency_to_dimensionless_frequency(frequency_array,
redshifted_lens_mass)`. And `lookup_table` is a `microlensing_o3.LookUpTable`
object, built once from an HDF5 file path, covering the wave-optics regime
below a frequency cutoff (above it, `amplification()` falls back to
geometric optics on its own and needs no table). That table is exactly a
`lens_model_settings` case: it doesn't come from a sample, it's identical
for the whole run, and building it means opening a file, so it should
happen once, not on every sample.

**Step 1: write the model class, in `dingo_lensing/gravelamps_amplification.py`**

```python
import logging

from gravelamps.models import microlensing_o3
from gravelamps.core.conversion import (
    lens_mass_source_to_lens_mass,
    solar_mass_to_natural_mass,
)


logger = logging.getLogger(__name__)


def _resolve_with_default(name, parameters, lens_model_defaults):
    # Deliberately duplicated from modwaveforms_amplification.py rather than
    # imported: this module has zero import-time coupling to any other lens
    # code's module, by design.
    value = parameters.pop(name, None)
    if value is None:
        value = lens_model_defaults.get(name)
        logger.debug(
            "Parameter '%s' not found in sample parameters; falling back to "
            "lens_model_defaults value %r.", name, value,
        )
    return value


class MicrolensingO3:
    # Standard name -> standard name for the three values this model reads
    # from a sample. If the team later decides source_position is the same
    # physical quantity as PointLens's own "y" and wants one shared standard
    # name for it, this is the only line that would change, to
    # {"source_position": "y"}; nothing else in this class would need to.
    PARAMETER_NAMES = {
        "lens_mass": "lens_mass",
        "lens_fractional_distance": "lens_fractional_distance",
        "source_position": "source_position",
    }

    def __init__(self, lookup_table_path=None):
        self._lookup_table = (
            microlensing_o3.LookUpTable(lookup_table_path)
            if lookup_table_path is not None
            else None
        )

    def resolve(self, parameters, lens_model_defaults):
        names = self.PARAMETER_NAMES
        return {
            "lens_mass": _resolve_with_default(
                names["lens_mass"], parameters, lens_model_defaults
            ),
            "lens_fractional_distance": _resolve_with_default(
                names["lens_fractional_distance"], parameters, lens_model_defaults
            ),
            "source_position": _resolve_with_default(
                names["source_position"], parameters, lens_model_defaults
            ),
            # luminosity_distance is a source parameter the *base* (unlensed)
            # waveform model also needs, so unlike the three keys above, it
            # must be read here, not popped, or the base generator loses it.
            "luminosity_distance": parameters["luminosity_distance"],
        }

    def compute(self, frequency_array, resolved):
        redshifted_lens_mass = solar_mass_to_natural_mass(
            lens_mass_source_to_lens_mass(
                resolved["lens_mass"],
                resolved["lens_fractional_distance"],
                resolved["luminosity_distance"],
            )
        )
        dimensionless_frequency = microlensing_o3.frequency_to_dimensionless_frequency(
            frequency_array, redshifted_lens_mass
        )
        return microlensing_o3.amplification(
            dimensionless_frequency,
            resolved["source_position"],
            lookup_table=self._lookup_table,
        )


_AMPLIFICATION_MODEL_CLASSES = {"microlensing_o3": MicrolensingO3}
SUPPORTED_AMPLIFICATION_FUNCTIONS = tuple(_AMPLIFICATION_MODEL_CLASSES)


def get_model(amplification_factor_function, **lens_model_settings):
    try:
        model_class = _AMPLIFICATION_MODEL_CLASSES[amplification_factor_function]
    except KeyError:
        raise ValueError(
            f"Unsupported lensing amplification function "
            f"'{amplification_factor_function}'. Available functions are: "
            f"{', '.join(SUPPORTED_AMPLIFICATION_FUNCTIONS)}."
        ) from None
    return model_class(**lens_model_settings)
```

**Step 2: register the lens code, in `lens_code_loader.py`**

```python
_LENS_CODE_MODULES = {
    "modwaveforms": "dingo_lensing.modwaveforms_amplification",
    "gravelamps": "dingo_lensing.gravelamps_amplification",
}
```

**Step 3: use it from a dataset settings YAML**

```yaml
lens_model_code: gravelamps
amplification_factor_function: microlensing_o3
lens_model_settings:
  lookup_table_path: /path/to/lookuptable.h5
lens_model_defaults:
  lens_fractional_distance: 0.5
```

`lens_model_settings` reaches `MicrolensingO3.__init__` (which builds the
`LookUpTable` once, at generator construction). `lens_model_defaults` is a
per-sample fallback exactly like the modwaveforms models already have; drop
it if `lens_fractional_distance` is always sampled per-event instead.
