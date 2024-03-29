# SPDX-FileCopyrightText: 2022 Rot127 <unisono@quyllur.org>
# SPDX-License-Identifier: LGPL-3.0-only

from rzilcompiler.Transformer.Pures.LocalVar import LocalVar
from rzilcompiler.Transformer.ValueType import ValueType


class ReturnValue(LocalVar):
    """This class represents a returned value."""

    def __init__(self, val_type: ValueType):
        LocalVar.__init__(self, "ret_val", value_type=val_type)

    def il_init_var(self):
        # Return values are not initialized.
        # They are initialized when an assignment to them happens via SETL.
        return ""

    def __str__(self):
        return f"{self.get_name()}_{self.value_type}"
