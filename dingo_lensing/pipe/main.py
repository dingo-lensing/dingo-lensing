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

from .dag_creator import (
    generate_dag
)

logger.name = "dingo_lensing_pipe"

class LensedMainInput(MainInput):
    pass

def main():
    parser = create_parser(top_level=True)
    args, unknown_args = parse_args(get_command_line_arguments(), parser)

    importance_sampling_updates, model_args = fill_in_arguments_from_model(args)
    inputs = LensedMainInput(args, unknown_args, importance_sampling_updates)
    write_complete_config_file(parser, args, inputs)

    # TODO: Use two sets of inputs! The first must match the network; the second is
    #  used in importance sampling.

    generate_dag(inputs, model_args)

    if len(unknown_args) > 0:
        print(f"Unrecognized arguments {unknown_args}")
