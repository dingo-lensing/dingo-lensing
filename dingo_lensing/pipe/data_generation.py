import sys

from bilby_pipe.main import parse_args
from bilby_pipe.utils import logger
from dingo.pipe.data_generation import (
    DataGenerationInput,
    create_generation_parser
)

logger.name = "dingo_lensing_pipe"

class LensedDataGenerationInput(DataGenerationInput):
    pass

def main():
    """Data generation main logic"""
    args, unknown_args = parse_args(sys.argv[1:], create_generation_parser())
    # log_version_information()
    data = LensedDataGenerationInput(args, unknown_args)
    data.save_hdf5()
    logger.info("Completed data generation")
