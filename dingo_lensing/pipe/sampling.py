#!/usr/bin/env python
""" Script to sample from a Dingo model. Based on bilby_pipe data analysis script. """
import sys
from pathlib import Path
import os

from bilby_pipe.input import Input
from bilby_pipe.utils import parse_args, logger, convert_string_to_dict

from dingo.core.posterior_models.build_model import build_model_from_kwargs
from dingo.gw.data.event_dataset import EventDataset
from dingo.gw.inference.gw_samplers import GWSampler, GWSamplerGNPE
from dingo.gw.inference.inference_utils import prepare_log_prob
from dingo.pipe.default_settings import DENSITY_RECOVERY_SETTINGS
from dingo.pipe.parser import create_parser
from dingo.pipe.sampling import (
    SamplingInput,
    create_sampling_parser
)

logger.name = "dingo_lensing_pipe"

class LensedSamplingInput(SamplingInput):
    pass


def main():
    """Data analysis main logic"""
    args, unknown_args = parse_args(sys.argv[1:], create_sampling_parser())
    # log_version_information()
    analysis = SamplingInput(args, unknown_args)
    analysis.run_sampler()
    sys.exit(0)
