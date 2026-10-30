#GWLENS integration will be done here
##Work in progress

import numpy as np
from gwlens import solver1d
import logging
import inspect
from typing import Dict

logger = logging.getLogger(__name__)



def _resolve_with_default(name,parameters, lens_model_defaults):
    """
    TBW docstrings...
    """
    value= parameters.po(name,None)

    if value is None:
        value = lens_model_defaults.get(name)
    return value


#Initializing here
point = solver1d.point_mass()
sis = solver1d.sis()
cis = solver1d.cis()
nfw = solver1.nfw()

#Collecting all implemented lenses here
#Implementing only the 1d lenses now, but can be extended when needed...
LENSES = {
    "gwlens_point":("1d", point,()),
    "gwlens_sis" : ("1d", sis,()),
    "gwlens_cis" : ("1d", cis,("rc",)),
    "gwlens_nfw": ("1d", nfw, ("kappa_s",))
}

SUPPORTED_GWLENS_MODELS = tuple(LENSES)


def get__model():
    """
    A function to return F after checking the paramerters and available list lens models
    """

    return F


class GWLENSmodel:

    """
    Main solver class which calls gwlens and performs the amplification factor calculation
    


    Raise:
    -------
    Value error for a not accepted solver
    """

    def __init__(self,solver,MLz_range=None,y_range=None,f_min=20.0,f_max=1024.0,time_origin="first_image",**kwargs):

        #Currently restricting to solver1d...
        if solver not in ("1d"):
            raise ValueError(f"solver must be valid, the input  {solver} is not valid")

        self.solver = solver
        self.build = build
        self.shape = tuple(shape_parameters)
        self.position("y")
        names = ("MLz", ) + self.position + self.shape
        self.PARAMETER_NAMES = {n: n for n in names}
        self.y_ranges = [y_range]
        self.f_min = float(f_min)
        self.f_max = float(f_max)





    def resolve(self, parameters:Dict[str,float], lens_model_defaults: Dict[str,float]) -> Dict[str,float]:
        """ 
        TBW 
        """
        out = {}

        self.shape_sampled = any(parameters.get(p) is not None for p in self.shape)

        for internal, standard in self.PARAMETER_NAMES.items():
            value = _resolve_with_default(standard, parameters, lens_model_defaults)

            if value is None:
                raise ValueError("....")

            out[internal] = float(value)

        return out

    def compute():

        return
    
