
from dingo.pipe.utils import _strip_unwanted_submission_keys
from dingo.pipe.nodes.generation_node import GenerationNode

class LensedGenerationNode(GenerationNode):
    @property
    def executable(self):
        return self._get_executable_path("dingo_lensing_pipe_generation")