# Copyright (c) 2026 DINGO-Lensing Development Team
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTIBILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE

"""
Implementation of DINGO-Lensing Asimov pipeline class.
"""

# Python built-in libraries
import importlib.resources
from typing import ClassVar

# Commonly used Python libraries
# GW specific Python libraries
from asimov.pipeline import Pipeline, PipelineException

# DINGO internal imports


class DingoLensing(Pipeline):
    """
    DingoLensing Pipeline.

    Parameters
    ----------
    production: :class:`asimov.Production`
        The production object.
    category: str, optional
        The category of the job. Defaults to "C01_offline".
    """

    name = "dingo-lensing"
    STATUS: ClassVar = {
        "wait",
        "sutck",
        "stopped",
        "running",
        "finished",
        "uploaded",
        "processing"
    }

    config_template = str(
        importlib.resources.files(__package__).joinpath(
            "dingo-lensing.ini"
        )
    )

    def __init__(self, production, category=None):
        super().__init__(production, category)
        self.logger.info("Using the DINGO-Lensing pipeline")

        if not production.pipeline.lower() == "dingo-lensing":
            raise PipelineException(
                f"{production.pipeline} is not a DINGO-lensing pipeline."
            )

    def detect_completion(self):
        """
        Checks for the production of the posterior file to signal that the job
        has completed.
        """

        self.logger.info("Checking if the DINGO-lensing job has completed.")
