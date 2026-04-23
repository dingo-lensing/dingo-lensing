#
#  Adapted from dingo_pipe. In particular, uses the dingo_pipe data generation code.
#

from bilby_pipe.utils import (
    get_command_line_arguments,
    logger,
    parse_args,
)

from dingo.pipe.main import (
    MainInput, 
    fill_in_arguments_from_model, 
    write_complete_config_file
)

from dingo.pipe.parser import create_parser


from pathlib import Path
import os
import copy
from tqdm.auto import tqdm 


logger.name = "dingo_batch"

def main():
    parser = create_parser(top_level=True)
    args, unknown_args = parse_args(get_command_line_arguments(), parser)
    #breakpoint()

    importance_sampling_updates, model_args = fill_in_arguments_from_model(args)
    has_lensing = ( "lensing_delta_t" in (model_args['prior_dict']) )or ("mu_rel" in (model_args['prior_dict']))
    if has_lensing:
        from .dag_creator import generate_dag
    else:
        from dingo.pipe.dag_creator import generate_dag
    batchdir = Path("run")
    cwd=Path.cwd()
    paths = sorted(batchdir.iterdir())
    for path in tqdm(paths, desc="Generating DAGs", unit="run"):
        rundir = cwd / path
        os.chdir(rundir)
        args_i = copy.deepcopy(args)
        inputs = MainInput(args_i, unknown_args, importance_sampling_updates)

        write_complete_config_file(parser, args_i, inputs)

    # TODO: Use two sets of inputs! The first must match the network; the second is
    #  used in importance sampling.
        inputs.outdir = args.outdir
        if has_lensing:
            generate_dag(inputs, model_args)
        else:
            generate_dag(inputs)

        del inputs, rundir

    if len(unknown_args) > 0:
        print(f"Unrecognized arguments {unknown_args}")