#!/usr/bin/env python
""" Script to importance sample based on Dingo lensing samples. Based on dingo_pipe data
analysis script. """
import sys

from bilby_pipe.utils import (
    parse_args, 
    logger
)

from dingo.gw.data.event_dataset import EventDataset
from dingo.pipe.parser import create_parser
from dingo_lensing.result import LensedGWResult as Result
from dingo.pipe.importance_sampling import (
    ImportanceSamplingInput,
    create_sampling_parser
)

logger.name = "dingo_lensing_pipe"

class LensedImportanceSamplingInput(ImportanceSamplingInput):
    def  _load_proposal(self):
        super()._load_proposal()
        self.result = Result(file_name=self.proposal_samples_file)

def main():
    """Lensing Data analysis main logic"""
    args, unknown_args = parse_args(sys.argv[1:], create_sampling_parser())
    analysis = LensedImportanceSamplingInput(args, unknown_args)
    analysis.run_sampler()
    sys.exit(0)