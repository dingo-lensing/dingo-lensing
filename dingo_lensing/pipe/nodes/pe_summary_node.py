import os 
from bilby_pipe.job_creation.nodes import PESummaryNode as BilbyPESummaryNode
from bilby_pipe.utils import BilbyPipeError, logger

from dingo.pipe.nodes.pe_summary_node import PESummaryNode

logger.name = "dingo_pipe"

class LensedPESummaryNode(PESummaryNode):
    pass