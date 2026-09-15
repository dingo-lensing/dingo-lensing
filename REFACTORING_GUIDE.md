# Refactoring Guide: Model-Agnostic Amplification Dispatch

This describes the redesign of how `LensedWaveformGenerator` resolves sample
parameters and computes the amplification factor for a given lens model, and
how to add a new lens model (or a whole new lens code, e.g. Gravelamps) under
it.

## The contract

A lens model is any object with two methods:

```python
def resolve(self, parameters: dict, lens_model_defaults: dict) -> dict:
    """Pop whatever this model needs out of `parameters` (falling back to
    `lens_model_defaults`, and applying any model-specific fallback logic),
    and return the resolved values as a flat dict."""

def compute(self, frequency_array, resolved: dict):
    """Turn the resolved values into the amplification factor array."""
```

That's it. `AmplificationModel` in `modwaveforms_amplification.py` is a base
class that raises `NotImplementedError` for both methods, but subclassing it
is optional documentation, not a requirement; a lens-code module elsewhere
can define a plain class with `resolve`/`compute` methods and nothing else
needs to know about it.

`resolve()` is called once per sample, before the base (unlensed) waveform is
generated, and it `pop`s the keys it consumes out of `parameters` in place.
That's how the leak bug is now structurally prevented: any key `resolve()`
doesn't pop is left in `parameters` and reaches the base generator; any key
it does pop is gone. Getting this right for a new model is entirely that
model's own responsibility, and a mistake in it cannot leak into any other
model's behaviour.

`get_model(amplification_factor_function, **lens_model_settings)` in each
lens-code module is a small factory: look up the class for the requested
function name, construct it, return it. `lens_code_loader.py` is the one
layer above that: it maps a `lens_model_code` string (e.g. `"modwaveforms"`)
to the Python module implementing it, imports that module lazily and only
once (so a cluster job using only `modwaveforms` never has to import
Gravelamps or vice versa), and calls its `get_model()`.

## Two kinds of per-model configuration

There are two YAML settings, and they answer different questions:

- **`lens_model_defaults`**: per-sample fallback values. If a sample doesn't
  include a value a model needs (e.g. `mu_rel` wasn't sampled per-event),
  `resolve()` falls back to this dict. Resolved fresh on every sample.
- **`lens_model_settings`**: fixed, generator-construction-time
  configuration, forwarded straight to the model class's `__init__`. For
  anything that should be built once and reused across every sample in a
  run, most obviously a lookup table or interpolator loaded from a file.

Concretely: `ML`/`y` for `pointlens` are per-sample values, so they belong in
`lens_model_defaults` if you want a fallback for them. A lookup table file
path is not a per-sample value at all, it's identical for every sample in
the run, so it belongs in `lens_model_settings` and gets consumed once, in
the model's constructor.

## Adding a new lens model within an existing lens code

Add one class to that lens code's `_amplification.py` module and register it
in that module's `_AMPLIFICATION_MODEL_CLASSES` dict. Nothing else in the
package needs to change; see any of the five models already in
`modwaveforms_amplification.py` (`OneImageBBH`, `TwoImagesBBH`,
`FoldCaustic`, `CuspCaustic`, `PointLens`) for the pattern.

## Adding a whole new lens code: Gravelamps as a worked example

Gravelamps is a real sibling package with its own amplification functions,
and its own real parameter names (`lens_mass`, `lens_fractional_distance`,
`source_position`), so it's a good test of whether this design actually
holds up outside modwaveforms. Here's what integrating its O3 point-mass
microlensing model (`gravelamps.models.microlensing_o3`) would look like.

Reading `gravelamps/models/microlensing_o3.py`, the function to call is:

```python
def amplification(dimensionless_frequency, source_position, lookup_table=None):
    ...
```

`dimensionless_frequency` is not the waveform's frequency array directly,
Gravelamps needs it converted first via
`microlensing_o3.frequency_to_dimensionless_frequency(frequency_array,
redshifted_lens_mass)`. And `lookup_table` is a `microlensing_o3.LookUpTable`
object, built once from an HDF5 file path (`LookUpTable.__init__` raises
`FileNotFoundError` if the path doesn't exist), covering the wave-optics
regime below a frequency cutoff; above that cutoff `amplification()` falls
back to geometric optics on its own and needs no table at all. That table is
exactly the "construction-time setting" case: it doesn't come from a sample,
it's identical for the whole run, and building it means opening a file, so
it should happen once, not on every sample.

**Step 1: add `dingo_lensing/gravelamps_amplification.py`**

```python
from gravelamps.models import microlensing_o3
from gravelamps.core.conversion import (
    lens_mass_source_to_lens_mass,
    solar_mass_to_natural_mass,
)


def _resolve_with_default(name, parameters, lens_model_defaults):
    # Deliberately duplicated from modwaveforms_amplification.py rather than
    # imported: this module has zero import-time coupling to any other lens
    # code's module, by design.
    value = parameters.pop(name, None)
    if value is None:
        value = lens_model_defaults.get(name)
    return value


class MicrolensingO3:
    def __init__(self, lookup_table_path=None):
        self._lookup_table = (
            microlensing_o3.LookUpTable(lookup_table_path)
            if lookup_table_path is not None
            else None
        )

    def resolve(self, parameters, lens_model_defaults):
        return {
            "lens_mass": _resolve_with_default(
                "lens_mass", parameters, lens_model_defaults
            ),
            "lens_fractional_distance": _resolve_with_default(
                "lens_fractional_distance", parameters, lens_model_defaults
            ),
            "source_position": _resolve_with_default(
                "source_position", parameters, lens_model_defaults
            ),
            # luminosity_distance is a source parameter the *base* (unlensed)
            # waveform model also needs, so unlike the three keys above, it
            # must be read here, not popped, or the base generator loses it.
            # This is exactly the kind of mistake the original ML/y leak bug
            # was: get this line wrong for a new model and only *this*
            # model's samples break, nothing else's.
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

**Step 2: register the lens code in `lens_code_loader.py`**

```python
_LENS_CODE_MODULES = {
    "modwaveforms": "dingo_lensing.modwaveforms_amplification",
    "gravelamps": "dingo_lensing.gravelamps_amplification",
}
```

One line. `modwaveforms_amplification.py`, `waveform_generator.py`, and every
existing model are untouched.

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

## What you get for free

- `LensedWaveformGenerator` doesn't change at all, whether you're adding a
  model to an existing lens code or an entirely new lens code.
- `modwaveforms_amplification.py` and every other lens code's module are
  untouched; a bug in `MicrolensingO3.resolve()` cannot affect `PointLens` or
  any other model.
- The lookup table (or any other construction-time setting) is loaded once
  per generator, not once per sample, and two generators with different
  `lens_model_settings` never share a model instance (`load_amplification_model`
  is deliberately not cached, unlike the module import step above it).
- Nothing needs an allowlist or denylist to protect the base waveform
  generator from lensing-specific parameters: `resolve()`'s `pop()` already
  strips exactly what it consumes, and dingo-gw's own parameter conversion
  does targeted key lookups rather than blindly unpacking the whole dict, so
  leftover unrelated keys in `parameters` are harmless.
