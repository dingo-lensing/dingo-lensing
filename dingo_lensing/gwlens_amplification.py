import numpy as np
import importlib
import inspect
import math
from typing import Dict
from gwlens import solver1d


TSUN = 4.925490947641267e-06        



#initialize the lens models
def _point():
    return solver1d.point_mass(1.0)

def _sis():
    return solver1d.sis(1.0)

def _cis(rc):
    return solver1d.cis(1.0, rc)

def _nfw(k):
    return solver1d.nfw(k=k)

_LENSES = {                                 
    "gwlens_point": (_point, ()),
    "gwlens_sis": (_sis, ()),
    "gwlens_cis": (_cis, ("rc",)),
    "gwlens_nfw": (_nfw, ("k",)),
}
SUPPORTED_GWLENS_MODELS = tuple(_LENSES) + ("gwlens_custom",)



class GWLENSmodels:
    """
    
    F(f) of an axisymmetric gwlens lens for one sample.
    
    """

    def __init__(self, build, shape_parameters=(), f_min=20.0, f_max=1024.0, time_origin="first_image",accuracy="pe"):

        """
      Doctstrings...
        """

        if accuracy not in ("pe", "high"):
            raise ValueError("accuracy must be 'pe' or 'high'")
        self.build = build
        self.shape = tuple(shape_parameters)
        self.PARAMETER_NAMES = {n: n for n in ("ML", "y") + self.shape}
        self.f_min = float(f_min)
        self.f_max = float(f_max)
        self.solver_kw = dict(time_origin=None if time_origin in (None, "none", "None") else str(time_origin), n_workers=1, interpolate="auto", interp_tol=1e-6 if accuracy == "pe" else 1e-10)
        if accuracy == "pe":
            self.solver_kw.update(solver1d.PE_SETTINGS)

    def resolve(self, parameters: Dict[str, float], lens_model_defaults: Dict[str, float]) -> Dict[str, float]:
        """
        Take the lens parameters out of the sample (falling back to lens_model_defaults).
        
        """
        out = {}
        for internal, standard in self.PARAMETER_NAMES.items():
            value = parameters.pop(standard, None)
            if value is None:
                value = lens_model_defaults.get(standard)
            if value is None:
                raise ValueError(f"GWLENS: no '{standard}' in the sample or in lens_model_defaults")
            out[internal] = float(value)
        return out

    def compute(self, frequency_array: np.ndarray, resolved: Dict[str, float]) -> np.ndarray:
   
        
        w = 8 * math.pi * TSUN * resolved["ML"] * frequency_array
        lens = self.build(*(resolved[p] for p in self.shape))
        F = solver1d.amplification(w, abs(resolved["y"]), lens, **self.solver_kw)
        return np.conj(F)


def get_model(amplification_factor_function: str, **lens_model_settings):
    """
    TBW
    """
    name = amplification_factor_function

    if name == "gwlens_custom":
        s = dict(lens_model_settings)
        path = s.pop("lens_function", None)
        if path is None:
            raise ValueError("gwlens_custom needs lens_model_settings.lens_function (dotted path of build(*shape))")
        
        module, attr = str(path).rsplit(".", 1)
        build = getattr(importlib.import_module(module), attr)
        shape = tuple(s.pop("shape_parameters", list(inspect.signature(build).parameters)))
        
        return GWLENSmodels(build, shape, **s)
    
    if name not in _LENSES:
        raise ValueError(f"Unsupported GWLENS model '{name}'. Available models: {', '.join(SUPPORTED_GWLENS_MODELS)}.")
    
    build, shape = _LENSES[name]
    return GWLENSmodels(build, shape, **lens_model_settings)