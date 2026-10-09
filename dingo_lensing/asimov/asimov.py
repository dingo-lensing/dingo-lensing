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
import re
import subprocess
from configparser import RawConfigParser
from pathlib import Path
from typing import ClassVar

# Commonly used Python libraries
# GW specific Python libraries
from asimov import config
from asimov.pipeline import Pipeline, PipelineException, PipelineLogger

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

    def detect_completion(self) -> bool:
        """
        Checks for the production of the posterior file to signal that the job
        has completed.

        Returns
        -------
        bool
            True if run is complete
        """

        self.logger.info("Checking if the DINGO-lensing job has completed.")
        return isinstance(self.samples(), Path) and self.samples().is_file() 

    def build_dag(self, dryrun=False):
        """
        Construct a DAG for submittion to the HTCondor scheduler using pipe
        functionality.

        Parameters
        ----------
        dryrun: bool, optional
            If true, commands will not be run but will instead be printed to
            standard output. Default is False.

        Raises
        ------
        PipelineException
            If constructino of the DAG fails for any reason.
        """

        cwd = Path.cwd()
        self.logger.info(f"Working in {cwd}")
        config_path = self._get_config_fp()

        command = [
            str(
                Path(
                    config.get("pipelines", "environment"),
                    "bin",
                    "dingo_lensing_pipe"
                )
            ),
            str(config_path)
        ]

        if dryrun:
            print(" ".join(command))
        else:
            self.logger.info(" ".join(command))
            pipe = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            out, err = pipe.communicate()
            self.logger.info(out)

        if err or "DAG generation complete, to submit jobs" not in str(out):
            self.logger.error(err)
            raise PipelineException(
                f"DAG could not be generated.\n{command}\n{out}\n\n{err}",
                production=self.production.name
            )
        
        return PipelineLogger(message=out, production=self.production.name)

    def _get_config_fp(self) -> Path:
        """
        Retrieves the DINGO-lensing configuration file for the production.

        Returns
        -------
        config_fp: Path
            Path to the DINGO-lensing config file.

        Raises
        ------
        FileNotFoundError
            If the config file cannot be found.
        """

        cwd = Path.cwd()

        if self.production.event.repository:
            config_fp = self.production.event.repository.find_prods(
                self.production.name, self.category
            )[0]
            config_fp = cwd.joinpath(config_fp)
        else:
            config_fp = Path(f"{self.production.name}.ini")

        if not config_fp.is_file():
            raise FileNotFoundError(
                f"Did not find config file at expected: {config_fp}"
            )

        return config_fp

    def samples(self) -> Path | None:
        """
        Retrieves the final importance samples for the production if they
        exist.

        Returns
        -------
        samples_fp: Path | None
            Path to final importance samples if they exist. Will be None if
            they do not yet exist.

        Raises
        ------
        ValueError
            If there are too many final result files.
        """
        
        # TODO: Main DINGO requires a hack to deal with
        # MultibandedFrequencyDomain and PESummary. Need to know if this is
        # something that we must contend with also.

        rundir = Path(self.production.rundir).joinpath("result")
        samples_fp = rundir.glob("*importance_sampling.hdf5")

        if len(samples_fp) == 0:
            return None
        if len(samples_fp) == 1:
            return samples_fp[0]

        raise ValueError(
            f"Found {len(samples_fp)} result files. Investigate further."
        )

    def collect_assets(self) -> dict:
        """
        Gather the result assets for this job.

        Returns
        -------
        dict
            Contains the samples in the `samples` key if thye exist.
        """

        return {"samples": self.samples()}

    def upload_assets(self):
        """
        Upload the samples from the job.
        """

        asset = self.collect_assets()["samples"]
        if asset:
            self.production.event.repository.add_file(
                str(asset),
                "posterior_samples.hdf5",
                commit_message="Added DINGO-lensing posterior samples."
            )

    def submit_dag(self, dryrun=False):
        """
        Submit a generated DAG to the HTCondor scheduler.

        Parameters
        ----------
        dryrun: bool
            If true, will not do anything but print the commands to standard
            out. Default is False.

        Raises
        ------
        PipelineException
            If submission fails.
        """

        cwd = Path.cwd()
        self.logger.info(f"Working in {cwd}")

        self.before_submit()

        if "job label" in self.production.meta:
            job_label = self.production.meta["job label"]
        else:
            job_label = self.production.name
        
        dag_filename = f"dag_{job_label}.submit"
        command = [
            "condor_submit_dag",
            "-batch-name",
            f"DINGO-Lensing/{self.production.event.name}/{self.production.name}",
            str(Path(self.production.rundir).joinpath("submit", dag_filename))
        ]

        if dryrun:
            print(" ".join(command))
        else:
            dagman = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.logger.info(" ".join(command))
            stdout, stderr = dagman.communicate()

            if "submitted to cluster" in str(stdout):
                cluster = re.search(
                    r"submitted to cluster ([\d]_)", str(stdout)
                ).groups()[0]
                self.logger.info(
                    "Submitted successfully. Running with job id "
                    f"{int(cluster)}"
                )

                self.production.status = "running"
                self.production.job_id = int(cluster)
            else:
                self.logger.info("Failed to submit to scheduler")
                self.logger.info(stdout)
                self.logger.error(stderr)

                self.production.status = "stuck"

                raise PipelineException(
                    "Failed to submit DINGO-lensing DAG to scheduler"
                )

    def resurrect(self):
        """
        Attempt to resurrect a failed job.
        """

        if "resurrections" in self.production.meta:
            count = self.production.meta["resurrections"]
        else:
            count = 0

        if count < 5:
            self.submit_dag()

    @classmethod
    def read_ini(cls, fp: str) -> RawConfigParser:
        """
        Read and parse a DINGO-Lensing configuration file.

        Parameters
        ----------
        fp: str
            Path to the configuration file.

        Returns
        -------
        parsed_config: RawConfigParser
            Configuration parser for the file.
        """

        with open(fp, "r", encoding="utf-8") as f:
            file_content = f.read()

        parsed_config = RawConfigParser()
        parsed_config.read_string(file_content)

        return parsed_config
