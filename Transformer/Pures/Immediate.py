# SPDX-FileCopyrightText: 2022 Rot127 <unisono@quyllur.org>
# SPDX-License-Identifier: LGPL-3.0-only

from Transformer.PluginInfo import isa_to_imm_fnc, isa_to_imm_args
from Transformer.Pures.LetVar import LetVar
from Transformer.Pures.Pure import ValueType


class Immediate(LetVar):
    def __init__(self, name: str, val: int, v_type: ValueType):
        self.name = name
        self.v_type = v_type
        super().__init__(name, val, v_type)

    def il_init_var(self, isa_to_imm_fcn=None):
        return f'RzILOpPure *{self.get_isa_name()} = {isa_to_imm_fnc}({", ".join(isa_to_imm_args)}, "{self.name}");'
