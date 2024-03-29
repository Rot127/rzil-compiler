# SPDX-FileCopyrightText: 2022 Rot127 <unisono@quyllur.org>
# SPDX-License-Identifier: LGPL-3.0-only
from rzilcompiler.Transformer.Pures.Pure import Pure, PureType
from rzilcompiler.Transformer.ValueType import (
    ValueType,
    get_value_type_by_c_type,
    split_var_decl,
    VTGroup,
)


class Parameter(Pure):
    """
    This class represents a parameter of a sub-routine.
    It is in general treated immutable, never initialized and only referenced by its name.
    """

    def __init__(self, name: str, value_type: ValueType):
        Pure.__init__(self, name, PureType.LET, value_type)

    def get_val(self):
        raise ValueError("Parameters have no explicit value.")

    def get_rzil_val(self) -> str:
        """Returns the value as the name of the variable holding the Pure."""
        return self.get_name()

    def il_init_var(self):
        raise ValueError("Parameters should not be initialized!")

    def il_read(self):
        """Returns the code to read the let variable for the VM."""
        self.reads += 1
        if self.reads <= 1 or not self.value_type.group & VTGroup.PURE:
            return self.get_rzil_val()
        return f"DUP({self.get_rzil_val()})"

    def vm_id(self):
        return self.get_rzil_val()

    def get_rzi_decl(self):
        param_type = self.value_type.get_param_decl_type()
        space = "" if param_type[-1] == "*" else " "  # No space after *
        return f"{param_type}{space}{self.get_name()}"

    def __str__(self):
        return f"{self.get_name()}"


def get_parameter_by_decl(decl: str) -> Parameter:
    """
    Returns a Parameter object as defined in the declaration string.

    :param decl: The declaration of the for "<c_type> <id>"
    :return: And initialized Parameter object with the type and name of the declaration.
    """
    ptype, name = split_var_decl(decl)
    return Parameter(name, get_value_type_by_c_type(ptype))
