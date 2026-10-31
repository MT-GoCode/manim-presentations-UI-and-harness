from .closing import Outcomes, Questions
from .evaluation import Evaluation
from .kernels import Kernels
from .machine import Machine
from .opening import Context, OneJob, Title
from .workflows import OldSwarm
from .zephon_overview import ZephonSingle

SCENES = [
    Title,
    Context,
    OneJob,
    Evaluation,
    Kernels,
    ZephonSingle,
    OldSwarm,
    Machine,
    Outcomes,
    Questions,
]
