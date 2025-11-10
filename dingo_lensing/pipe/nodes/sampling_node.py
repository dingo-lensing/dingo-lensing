import os

from bilby_pipe.job_creation.nodes import AnalysisNode

from dingo.pipe.utils import _strip_unwanted_submission_keys
from dingo.pipe.nodes.sampling_node import SamplingNode

class LensedSamplingNode(SamplingNode):
    @property
    def executable(self):
        return self._get_executable_path("dingo_lensing_pipe_sampling")