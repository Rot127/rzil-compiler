# SPDX-FileCopyrightText: 2022 Rot127 <unisono@quyllur.org>
# SPDX-License-Identifier: LGPL-3.0-only

from rzilcompiler.Transformer.Pures.Pure import Pure
from rzilcompiler.Transformer.Pures.PureExec import PureExec
from rzilcompiler.Transformer.Pures.BooleanOp import BooleanOp
from rzilcompiler.Transformer.Pures.CompareOp import CompareOp


class Ternary(PureExec):
    def __init__(self, name: str, cond: Pure, then_p: Pure, else_p: Pure):
        PureExec.__init__(self, name, [cond, then_p, else_p], then_p.value_type)

    def il_exec(self):
        if isinstance(self.ops[0], BooleanOp) or isinstance(self.ops[0], CompareOp):
            cond = self.ops[0].il_read()
        else:
            cond = f"NON_ZERO({self.ops[0].il_read()})"
        return f"ITE({cond}, {self.ops[1].il_read()}, {self.ops[2].il_read()})"

    def __str__(self):
        return f"({self.ops[0]} ? {self.ops[1]} : {self.ops[2]})"
