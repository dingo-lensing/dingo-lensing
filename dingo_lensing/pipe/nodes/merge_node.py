from bilby_pipe.job_creation.nodes import MergeNode as BilbyMergeNode

from dingo.pipe.utils import _strip_unwanted_submission_keys
from dingo.pipe.nodes.merge_node import MergeNode

class LensedMergeNode(MergeNode):
    @property
    def executable(self):
        return self._get_executable_path("dingo_lensing_result")
