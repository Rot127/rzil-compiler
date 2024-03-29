# SPDX-FileCopyrightText: 2022 Rot127 <unisono@quyllur.org>
# SPDX-License-Identifier: LGPL-3.0-only
import re
from enum import Enum

from rzilcompiler.Exceptions import OverloadException
from rzilcompiler.Transformer.Pures.Parameter import Parameter
from rzilcompiler.Transformer.Hybrids.Hybrid import Hybrid, HybridType, HybridSeqOrder
from rzilcompiler.Transformer.PluginInfo import hexagon_c_call_prefix
from rzilcompiler.Transformer.Pures.Pure import Pure
from rzilcompiler.Transformer.ValueType import ValueType, VTGroup


class SubRoutineInitType(Enum):
    DECL = 0
    DEF = 1
    CALL = 2


class SubRoutine(Hybrid):
    """
    Represents a sub routine.
    """

    def __init__(
        self, name: str, ret_type: ValueType, params: list[Parameter], body: str
    ):
        self.routine_name = name
        # Precompiled subroutine's body.
        self.body = self.check_for_bundle_usage(body)
        self.op_type = HybridType.SUB_ROUTINE
        if ret_type.group & VTGroup.VOID:
            self.seq_order = HybridSeqOrder.EXEC_ONLY
        else:
            self.seq_order = HybridSeqOrder.EXEC_THEN_SET_VAL

        Hybrid.__init__(self, name, params, ret_type)

    def check_for_bundle_usage(self, code: str) -> str:
        if re.search(r"\Wpkt\W", code):
            code = "HexPkt *pkt = bundle->pkt;\n" + code
        if re.search(r"\Whi\W", code):
            code = "const HexInsn *hi = bundle->insn;\n" + code
        return "{\n" + code + "\n}"

    def get_parameter_value_types(self) -> list[ValueType]:
        """Returns the parameter value types as ordered list (left to right)."""
        return [p.value_type for p in self.ops]

    def il_init(self, sub_init_type=SubRoutineInitType.CALL) -> str:
        """
        Either as definition, declaration or call.
        Call is for initializations within another body statement and returns nothing.
        """
        if sub_init_type == SubRoutineInitType.CALL:
            return ""

        decl = (
            f"RZ_OWN RzILOpEffect *{hexagon_c_call_prefix.lower()}{self.routine_name}("
        )
        decl += ", ".join([p.get_rzi_decl() for p in self.ops])
        decl += ")"
        if sub_init_type == SubRoutineInitType.DECL:
            return decl
        decl += self.body
        return decl

    def il_write(self):
        raise OverloadException(
            "Must be overloaded with the knowledge about args used."
        )

    def il_exec(self):
        return ""

    def il_read(self):
        # The value of the sub-routine is always stored in "ret_val"
        tmp = "SIGNED(" if self.value_type.signed else "UNSIGNED("
        tmp += (
            f"{self.value_type.bit_width}" if self.value_type.bit_width != 0 else "32"
        )
        return f'{tmp}, VARL("ret_val"))'


class SubRoutineCall(Hybrid):
    """
    Represents a call to a sub-routine.
    The operands passed to a SubRoutineCall are arguments instead of parameters.
    """

    def __init__(self, sub_routine: SubRoutine, args: list[Pure]):
        self.inlined = True  # Calls are always inlined.
        self.sub_routine = sub_routine
        self.args: list[Pure] = args
        self.seq_order = HybridSeqOrder.EXEC_THEN_SET_VAL
        self.op_type = HybridType.SCALL

        Hybrid.__init__(
            self, sub_routine.get_name() + "_call", args, sub_routine.value_type
        )

    def il_exec(self):
        return ""

    def il_init(self):
        """No initialization needed."""
        return ""

    def il_read(self):
        return self.sub_routine.il_read()

    def il_write(self):
        if len(self.args) != len(self.sub_routine.get_parameter_value_types()):
            raise ValueError(
                f"The number of arguments ({len(self.args)}) does not match number of the parameters.\n"
                f"{self.sub_routine.name} needs: {[str(t) for t in self.sub_routine.get_parameter_value_types()]}"
            )
        code = f"{hexagon_c_call_prefix.lower() + self.sub_routine.get_name()}("
        code += build_arg_list(self.args, self.sub_routine.get_parameter_value_types())
        code += ")"
        return code

    def __str__(self):
        return (
            f"{self.sub_routine.get_name()}({', '.join([str(op) for op in self.ops])})"
        )


def build_arg_list(arguments: list[Pure], param_types: list[ValueType]) -> str:
    from rzilcompiler.Transformer.Pures.Macro import MacroInvocation

    if len(arguments) != len(param_types):
        raise ValueError("Length of argument and parameter list does not match")
    code = ""
    for i, (arg, ptype) in enumerate(zip(arguments, param_types)):
        if i > 0:
            code += ", "
        if ptype.group & VTGroup.EXTERNAL or isinstance(arg, MacroInvocation):
            # Parameter passed from outer scope
            if isinstance(arg, Parameter):
                code += arg.get_name()
                continue
            # The argument should be of an external type. So only the variable name is printed.
            if "get_op_var" not in dir(arg):
                if isinstance(arg, str):
                    code += arg
                    continue
                raise ValueError(
                    f"{arg} as no method to get it's operand holding variable name."
                )
            code += arg.get_op_var()
        elif (
            ptype.group & VTGroup.PURE
            or ptype.group & VTGroup.FLOAT
            or ptype.group & VTGroup.DOUBLE
        ):
            # Normal pure.
            code += arg.il_read()
        else:
            raise ValueError(
                f"{ptype.group} not handled to initialize a sub-routine arguments."
            )
    return code
