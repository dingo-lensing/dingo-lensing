import sys

import dingo.pipe.data_generation as dingo_data_generation
from bilby_pipe.main import parse_args
from bilby_pipe.utils import logger
from dingo.pipe.data_generation import (
    DataGenerationInput,
    create_generation_parser,
)

from dingo_lensing.injection import LensedInjection

logger.name = "dingo_lensing_pipe"


class LensedDataGenerationInput(DataGenerationInput):
    def _inject_dingo_signal(self, args):
        """Inject a lensed DINGO signal into the interferometer data.

        DINGO builds the signal with ``dingo.gw.injection.Injection``, whose
        waveform generator drops the lensing settings, so the injection would
        be unlensed. ``LensedInjection`` takes its place for this call.

        Parameters
        ----------
        args : argparse.Namespace
            Data generation arguments, passed on to DINGO.
        """
        injection_class = dingo_data_generation.Injection
        dingo_data_generation.Injection = LensedInjection
        try:
            super()._inject_dingo_signal(args)
        finally:
            dingo_data_generation.Injection = injection_class


def main():
    """Data generation main logic"""
    args, unknown_args = parse_args(sys.argv[1:], create_generation_parser())
    # log_version_information()
    data = LensedDataGenerationInput(args, unknown_args)
    data.save_hdf5()
    logger.info("Completed data generation")
