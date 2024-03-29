# SPDX-FileCopyrightText: 2022 Rot127 <unisono@quyllur.org>
# SPDX-License-Identifier: LGPL-3.0-only
from enum import Enum, auto

from lark import Transformer, Token

from rzilcompiler.Transformer.Hybrids.GCCStmtDeclExpr import GCCStmtDeclExpr
from rzilcompiler.Transformer.Pures.Macro import Macro, MacroInvocation
from rzilcompiler.Transformer.Pures.Bool import Bool
from rzilcompiler.Transformer.Hybrids.SubRoutine import SubRoutine, SubRoutineCall
from rzilcompiler.Transformer.Pures.ReturnValue import ReturnValue
from rzilcompiler.Transformer.Pures.Parameter import Parameter
from rzilcompiler.ArchEnum import ArchEnum
from rzilcompiler.Transformer.Effects.Branch import Branch
from rzilcompiler.Transformer.Effects.Effect import Effect
from rzilcompiler.Transformer.Effects.Empty import Empty
from rzilcompiler.Transformer.Effects.ForLoop import ForLoop
from rzilcompiler.Transformer.Effects.Jump import Jump
from rzilcompiler.Transformer.Effects.MemStore import MemStore
from rzilcompiler.Transformer.Effects.NOP import NOP
from rzilcompiler.Transformer.Effects.Sequence import Sequence
from rzilcompiler.HexagonExtensions import (
    HexagonTransformerExtension,
    get_fcn_param_types,
)
from rzilcompiler.Transformer.Hybrids.Hybrid import Hybrid, HybridType, HybridSeqOrder
from rzilcompiler.Transformer.Hybrids.PostfixIncDec import PostfixIncDec
from rzilcompiler.Transformer.ILOpsHolder import ILOpsHolder
from rzilcompiler.Transformer.Pures.BitOp import BitOperationType, BitOp
from rzilcompiler.Transformer.Pures.BooleanOp import BooleanOpType, BooleanOp
from rzilcompiler.Transformer.Hybrids.Call import Call
from rzilcompiler.Transformer.Pures.Cast import Cast
from rzilcompiler.Transformer.Pures.CompareOp import CompareOp, CompareOpType
from rzilcompiler.Transformer.Pures.LetVar import LetVar
from rzilcompiler.Transformer.Pures.LocalVar import LocalVar
from rzilcompiler.Transformer.Pures.MemLoad import MemAccessType, MemLoad
from rzilcompiler.Transformer.Pures.Number import Number
from rzilcompiler.Transformer.Pures.Pure import Pure, PureType
from rzilcompiler.Transformer.ValueType import (
    ValueType,
    c11_cast,
    get_value_type_by_c_number,
    VTGroup,
    promoted_type,
)
from rzilcompiler.Transformer.Effects.Assignment import Assignment, AssignmentType
from rzilcompiler.Transformer.Pures.ArithmeticOp import ArithmeticOp, ArithmeticType
from rzilcompiler.Transformer.Pures.Register import Register, RegisterAccessType
from rzilcompiler.Transformer.Pures.Sizeof import Sizeof
from rzilcompiler.Transformer.Pures.Ternary import Ternary
from rzilcompiler.Transformer.Pures.Variable import Variable
from rzilcompiler.Transformer.helper import flatten_list
from rzilcompiler.Transformer.helper_hexagon import (
    get_num_base_by_token,
)


class CodeFormat(Enum):
    EXEC_CLASSES = auto()  # Emits READ / EXEC / WRITE blocks
    READ_STATEMENTS = auto()  # Emits READ / stmt, stmt, stmt... blocks


class RZILTransformer(Transformer):
    """
    Transforms the tree into Pures and Effects.
    The classes do the actual code generation.
    """

    def __init__(
        self,
        arch: ArchEnum,
        sub_routines: dict[str:SubRoutine] = None,
        parameters: list[Parameter] = None,
        return_type: ValueType = None,
        code_format: CodeFormat = CodeFormat.READ_STATEMENTS,
        macros: dict[str:Macro] = None,
    ):
        self.code_format = code_format
        # Classes of Pures which should not be initialized in the C code.
        self.inlined_pure_classes = (Number, Sizeof, Cast, Bool)
        self.imm_set_effect_list = list()

        self.arch = arch
        self.sub_routines: dict[str:SubRoutine] = (
            dict() if not sub_routines else sub_routines
        )
        self.macros: dict[str:Macro] = dict() if not macros else macros

        # Return type of this Transfomer. This is set if a sub-routine is transformed.
        self.return_type = return_type
        # List of parameters this transformer can take as given from outer scope.
        self.parameters: dict[str:Parameter] = (
            dict() if not parameters else {p.get_name(): p for p in parameters}
        )
        if (self.return_type and not self.parameters) or (
            not self.return_type and self.parameters
        ):
            raise ValueError(
                "If parameters and return type must be set or unset. But never just one of them."
            )

        self.il_ops_holder = ILOpsHolder()

        if self.arch == ArchEnum.HEXAGON:
            self.ext = HexagonTransformerExtension(self)
        else:
            raise NotImplementedError(
                f"Architecture {self.arch} has not Transformer extension."
            )
        super().__init__()

    def reset(self):
        self.ext.reset_flags()
        self.il_ops_holder.hybrid_effect_dict.clear()
        self.imm_set_effect_list.clear()
        self.il_ops_holder.clear()

    def update_sub_routines(self, new_routines: dict[str:SubRoutine]) -> None:
        self.sub_routines.update(new_routines)

    def update_macros(self, macro: dict[str:Macro]):
        self.macros.update(macro)

    def get_op_id(self) -> int:
        return self.il_ops_holder.get_op_count()

    def add_op(self, op):
        if op.get_name() in self.parameters:
            raise ValueError(f"Operand {op.get_name()} already defined as parameter.")
        elif self.il_ops_holder.has_op(op.get_name()):
            return self.il_ops_holder.get_op_by_name(op.get_name())

        num_id = self.il_ops_holder.get_op_count()
        op.set_num_id(num_id)
        if isinstance(op, self.inlined_pure_classes):
            if not hasattr(op, "inlined"):
                NotImplementedError(f"{op} can not be inlined yet.")
            op.inlined = True

        if (
            not isinstance(op, Variable)
            and not isinstance(op, Register)
            and not isinstance(op, ReturnValue)
            and not (
                isinstance(op, LocalVar) and op.value_type.group & VTGroup.HYBRID_LVAR
            )
        ):
            # Those have already a unique name
            op.set_name(f"{op.get_name()}_{num_id}")
        self.il_ops_holder.add_op(op)
        return op

    def fbody(self, items):
        self.ext.set_token_meta_data("fbody")
        # We are at the top. Generate code.

        holder = self.il_ops_holder
        if holder.is_empty():
            return f"return NOP();"

        res = ""

        if self.code_format in [CodeFormat.EXEC_CLASSES, CodeFormat.READ_STATEMENTS]:
            res = self.emit_read_block(holder, res)

        if self.code_format in [CodeFormat.EXEC_CLASSES]:
            res = self.emit_exec_block(holder, res)

        if self.code_format in [CodeFormat.EXEC_CLASSES]:
            res = self.emit_write_block(holder, res)

        if self.code_format == CodeFormat.READ_STATEMENTS:
            res = self.emit_stmt_blocks(holder, res)

        res = self.emit_final_seq_return(items, res)
        return res

    def emit_final_seq_return(self, items, res):
        # Hybrids which have no parent in the AST
        left_hybrids = [
            self.il_ops_holder.hybrid_effect_dict.pop(hid)
            for hid in [k for k in self.il_ops_holder.hybrid_effect_dict.keys()]
        ]
        # Assign all effects without parent in the AST to the final instruction sequence.
        instruction_sequence = Sequence(
            f"instruction_sequence",
            [
                op
                for op in self.imm_set_effect_list + left_hybrids + flatten_list(items)
                if isinstance(op, Effect)
            ],
        )

        if self.code_format == CodeFormat.READ_STATEMENTS:
            # The instruction sequence belongs logically more to the
            # return in this formatting.
            res += "\n"
            res += instruction_sequence.il_init_var() + "\n"
        elif self.code_format == CodeFormat.EXEC_CLASSES:
            res += instruction_sequence.il_init_var() + "\n\n"

        res += f"return {instruction_sequence.effect_var()};"
        return res

    def emit_stmt_blocks(self, holder, res):
        statements = list()
        for effect in holder.write_ops.values():
            statements.append(sorted(effect.get_exec_op_list(), key=lambda x: x.num_id))
            statements[-1].append(effect)

        for stmt in statements:
            effect = stmt[-1]
            effect_init = effect.il_init_var()
            if not effect_init:
                continue

            res += f"\n// {stmt[-1]};\n"
            # Emit each statement
            for op in stmt[:-1]:
                op_init = op.il_init_var()
                if not op_init:
                    continue
                res += op_init + "\n"
            res += effect_init + "\n"
        return res

    def emit_write_block(self, holder, res):
        res += "\n// WRITE\n"
        for op in holder.write_ops.values():
            if isinstance(op, Hybrid):
                hybrid_init = op.il_init_var()
                if not hybrid_init:
                    continue
                res += hybrid_init + "\n"
                continue
            write_op = op.il_init_var()
            if not write_op:
                continue
            res += write_op + "\n"
        return res

    def emit_exec_block(self, holder, res):
        res += "\n// EXEC\n"
        for op in holder.exec_ops.values():
            if isinstance(op, Hybrid):
                continue
            exec_op = op.il_init_var()
            if not exec_op:
                continue
            res += exec_op + "\n"
        return res

    def emit_read_block(self, holder, res):
        res += "\n// READ\n"
        for op in holder.read_ops.values():
            read_op = op.il_init_var()
            if not read_op:
                continue
            res += read_op + "\n"
        return res

    def jump_stmt(self, items):
        if items[0] == "return":
            # Set result of the expression.
            if self.il_ops_holder.has_op("ret_val"):
                ret_val = self.il_ops_holder.get_op_by_name("ret_val")
            else:
                ret_val = self.add_op(ReturnValue(self.return_type))
            src: Pure = items[1]
            if src.value_type.bit_width > 64:
                raise ValueError(
                    "The return value of current sub-routines is currently only 64bit wide."
                )
            if src.value_type.bit_width != 64:
                src = self.init_a_cast(ValueType(False, 64), src)
            return self.add_op(
                Assignment("set_return_val", AssignmentType.ASSIGN, ret_val, src)
            )
        return items  # Pass them upwards

    def relational_expr(self, items):
        self.ext.set_token_meta_data("relational_expr")
        return self.compare_op(items)

    def equality_expr(self, items):
        self.ext.set_token_meta_data("equality_expr")
        return self.compare_op(items)

    def reg_alias(self, items):
        self.ext.set_token_meta_data("reg")

        return self.add_op(self.ext.reg_alias(items))

    # SPECIFIC FOR: Hexagon
    def new_reg(self, items):
        self.ext.set_token_meta_data("new_reg")

        return self.add_op(self.ext.hex_reg(items, True))

    def explicit_reg(self, items):
        name = items[0]
        new = items[1] is not None
        self.ext.set_token_meta_data("explicit_reg", is_new=new)
        return self.add_op(
            self.ext.hex_reg(
                [
                    Token("REG_TYPE", name[0]),
                    Token("SRC_DEST_REG", str(name[1:])),
                    name,
                ],
                is_new=new,
                is_explicit=True,
            )
        )

    def reg(self, items):
        self.ext.set_token_meta_data("reg")

        return self.add_op(self.ext.reg(items))

    def imm(self, items):
        self.ext.set_token_meta_data("imm")
        name = items[0]
        if name in self.il_ops_holder.read_ops:
            return self.il_ops_holder.read_ops[name]

        imm = self.ext.imm(items)
        assignment = self.add_op(
            Assignment(
                f"imm_assign",
                AssignmentType.ASSIGN,
                imm,
                imm,
            )
        )
        self.imm_set_effect_list.append(assignment)
        return self.add_op(imm)

    def jump(self, items):
        self.ext.set_token_meta_data("jump")
        ta: Pure = items[1]
        if ta.value_type.bit_width != 32:
            # Enforce 32bit values for now.
            ta = self.init_a_cast(ValueType(False, 32), ta)
        return self.chk_hybrid_dep(self.add_op(Jump(f"jump_{ta.pure_var()}", ta)))

    def nop(self, items):
        return self.add_op(NOP("nop"))

    def specifier_qualifier_list(self, items):
        self.ext.set_token_meta_data("specifier_qualifier_list")
        if items[0] != ValueType(False, 32) or items[1] != ValueType(True, 32):
            raise ValueError(
                f"Handling specifier qualifier lists only rudimentary implemented. Can't process {items}"
            )
        # unsigned int case
        return ValueType(False, 32)

    def type_specifier(self, items):
        self.ext.set_token_meta_data("data_type")
        return self.ext.get_value_type_by_resource_type(items)

    def init_a_cast(
        self, target_type: ValueType, pure: Pure, cast_name: str = ""
    ) -> Pure:
        """
        Initializes and returns a Cast if the val_types and the pure.val_type
        mismatch. Otherwise, it simply returns the pure.
        """
        if target_type.group & (
            VTGroup.FLOAT | VTGroup.DOUBLE
        ) or pure.value_type.group & (VTGroup.FLOAT | VTGroup.DOUBLE):
            raise ValueError(
                "Floats or doubles should not be casted. They get (de)coded via fUNFLOAT()"
            )
        if target_type == pure.value_type:
            return pure
        if not cast_name:
            cast_name = f"cast_{target_type}"
        if (
            pure.value_type.group & VTGroup.BOOL
            and not target_type.group & VTGroup.BOOL
        ):
            # Can't use a normal cast.
            true = Number("true", 1, target_type)
            true.inlined = True
            false = Number("false", 0, target_type)
            false.inlined = True
            return self.add_op(Ternary(f"ite_cast_{target_type}", pure, true, false))
        return self.add_op(Cast(cast_name, target_type, pure))

    def cast_expr(self, items):
        self.ext.set_token_meta_data("cast_expr")
        val_type = items[0]
        data = items[1]
        if data.value_type == val_type:
            return data

        return self.init_a_cast(val_type, data)

    def number(self, items):
        self.ext.set_token_meta_data("number")

        v_type = get_value_type_by_c_number(items)
        num_str = str(items[0])
        name = f'const_{items[0]}{items[1] if items[1] else ""}'

        holder = self.il_ops_holder
        if name in holder.read_ops:
            return holder.read_ops[name]
        return self.add_op(
            Number(name, int(num_str, get_num_base_by_token(items[0])), v_type)
        )

    def declaration_specifiers(self, items):
        self.ext.set_token_meta_data("declaration_specifiers")
        specifier: str = items[0]
        t: ValueType = items[1]
        if isinstance(specifier, ValueType):
            # Allow only unsigned int for now
            if not (specifier == ValueType(False, 32)) and (t == ValueType(True, 32)):
                raise NotImplementedError(
                    f"Type specifier {specifier} currently not supported."
                )
            t.signed = False
            return t
        if isinstance(specifier, str) and specifier == "const":
            t.group |= VTGroup.CONST
            return t
        raise NotImplementedError(
            f"Type specifier {specifier} currently not supported."
        )

    def set_dest_type(self, assig: Assignment, t: ValueType) -> None:
        """For "<type> Assignment" declarations the Assignment gets parsed first.
        Afterwards the type. Here we update the type of the destination variable.
        """
        if assig.dest.type != PureType.LOCAL and assig.dest.type != PureType.LET:
            raise NotImplementedError(
                f"Updating the type of a {assig.dest.type} is not allowed."
            )
        assig.dest.set_value_type(t)
        dest_casted, src_casted = self.cast_operands(
            a=assig.dest, b=assig.src, immutable_a=True
        )
        assig.set_src(src_casted)
        assig.set_dest(dest_casted)

    def declaration(self, items):
        self.ext.set_token_meta_data("declaration")

        if len(items) != 2:
            raise NotImplementedError(
                f"Declarations without exactly two tokens are not supported."
            )
        if hasattr(items[0], "type") and items[0].type != "IDENTIFIER":
            # Declarations like: "TYPE <id>;" are only added to the ILOpholder list.
            # They get initialize when they first get set.
            self.add_op(Variable(items[1], items[0]))
            return self.chk_hybrid_dep(self.add_op(Empty(f"empty")))
        t: ValueType = items[0]
        if isinstance(items[1], Assignment):
            assg: Assignment = items[1]
            self.set_dest_type(assg, t)
            return assg
        elif isinstance(items[1], Sequence):
            # This is an assignment which has a hybrid dependency. Iterate over sequence ops and find Assignment.
            items[1]: Sequence
            for e in items[1].effects:
                if isinstance(e, Assignment):
                    self.set_dest_type(e, t)
                    return items[1]
            raise NotImplementedError(
                "declaration without Assignment are not implemented."
            )
        elif isinstance(items[1], str):
            if items[1] in self.il_ops_holder.read_ops:
                return self.il_ops_holder.read_ops[items[1]]
            return self.add_op(Variable(items[1], t))
        raise NotImplementedError(f"Declaration with items {items} not implemented.")

    def init_declarator(self, items):
        self.ext.set_token_meta_data("init_declarator")

        if len(items) != 2:
            raise NotImplementedError(
                f"Can not initialize an Init declarator with {len(items)} tokens."
            )
        if items[0] in self.il_ops_holder.read_ops:
            # variable was declared before.
            dest = self.il_ops_holder.read_ops[items[0]]
        else:
            # Variable was not declared before. The type is unknown.
            # Type is updated in declaration handler.
            dest = Variable(items[0], None)
            self.add_op(dest)
        op_type = AssignmentType.ASSIGN
        src: Pure = items[1]
        name = f"op_{op_type.name}"
        dest, src = self.cast_operands(a=dest, b=src, immutable_a=True)
        return self.chk_hybrid_dep(self.add_op(Assignment(name, op_type, dest, src)))

    def selection_stmt(self, items):
        self.ext.set_token_meta_data("selection_stmt")
        cond = items[1]
        then_seq = self.chk_hybrid_dep(
            self.add_op(Sequence(f"seq_then", flatten_list(items[2])))
        )
        name = f"branch"
        if items[0] == "if" and len(items) == 3:
            return self.chk_hybrid_dep(
                self.add_op(Branch(name, cond, then_seq, Empty(f"empty")))
            )
        elif items[0] == "if" and len(items) > 3 and items[3] == "else":
            else_seq = self.chk_hybrid_dep(
                self.add_op(Sequence(f"seq_else", flatten_list(items[4])))
            )
            return self.chk_hybrid_dep(
                self.add_op(Branch(name, cond, then_seq, else_seq))
            )
        else:
            raise NotImplementedError(f'"{items[0]}" branch not implemented.')

    def conditional_expr(self, items):
        self.ext.set_token_meta_data("conditional_expr")
        result = self.simplify_conditional_expr(items)
        if result:
            return result
        then_p = items[1]
        else_p = items[2]

        if (
            then_p.value_type.group & VTGroup.HYBRID_LVAR
            and hasattr(then_p, "hybrid_owner")
            and isinstance(then_p.hybrid_owner, GCCStmtDeclExpr)
        ):
            # The if/elif cases mean that the then/else expression are produced by an
            # GCC-stmt-decl-expression.
            # (See: https://gcc.gnu.org/onlinedocs/gcc-2.95.3/gcc_4.html#SEC62)
            # The statements in this expression must be executed conditionally as well.
            # So we update the corresponding GCCStmtDeclExpr statements with a BRANCH here.
            hybrid = then_p.hybrid_owner
            hybrid: GCCStmtDeclExpr
            hybrid.update_stmt(
                Branch("branch", cond=items[0], then=hybrid.stmt, otherwise=Empty(""))
            )
        if (
            else_p.value_type.group & VTGroup.HYBRID_LVAR
            and hasattr(else_p, "hybrid_owner")
            and isinstance(else_p.hybrid_owner, GCCStmtDeclExpr)
        ):
            hybrid = else_p.hybrid_owner
            hybrid: GCCStmtDeclExpr
            hybrid.update_stmt(
                Branch("branch", cond=items[0], then=Empty(""), otherwise=hybrid.stmt)
            )

        then_p, else_p = self.cast_operands(a=then_p, b=else_p, immutable_a=False)
        return self.add_op(Ternary(f"cond", items[0], then_p, else_p))

    def update_assign_src(self, assign: Assignment):
        """
        For Assignment expressions, we need to add a PureExec for the
        corresponding expressions. So Add for +=, SUB for -= etc.
        """
        if assign.assign_type == AssignmentType.ASSIGN:
            return
        elif assign.assign_type == AssignmentType.ASSIGN_ADD:
            assign.set_src(
                ArithmeticOp(
                    f"op_ADD",
                    self.promotion_cast(assign.dest),
                    self.promotion_cast(assign.src),
                    ArithmeticType.ADD,
                )
            )
        elif assign.assign_type == AssignmentType.ASSIGN_SUB:
            assign.set_src(
                ArithmeticOp(
                    f"op_SUB",
                    self.promotion_cast(assign.dest),
                    self.promotion_cast(assign.src),
                    ArithmeticType.SUB,
                )
            )
        elif assign.assign_type == AssignmentType.ASSIGN_MUL:
            assign.set_src(
                ArithmeticOp(
                    f"op_MUL",
                    self.promotion_cast(assign.dest),
                    self.promotion_cast(assign.src),
                    ArithmeticType.MUL,
                )
            )
        elif assign.assign_type == AssignmentType.ASSIGN_MOD:
            assign.set_src(
                ArithmeticOp(
                    f"op_MOD",
                    assign.dest,
                    assign.src,
                    ArithmeticType.MOD,
                )
            )
        elif assign.assign_type == AssignmentType.ASSIGN_DIV:
            assign.set_src(
                ArithmeticOp(
                    f"op_DIV",
                    self.promotion_cast(assign.dest),
                    self.promotion_cast(assign.src),
                    ArithmeticType.DIV,
                )
            )
        elif assign.assign_type == AssignmentType.ASSIGN_RIGHT:
            assign.set_src(
                BitOp(
                    f"op_SHIFTR",
                    self.promotion_cast(assign.dest),
                    self.promotion_cast(assign.src),
                    BitOperationType.RSHIFT,
                )
            )
        elif assign.assign_type == AssignmentType.ASSIGN_LEFT:
            assign.set_src(
                BitOp(
                    f"op_SHIFTL",
                    self.promotion_cast(assign.dest),
                    self.promotion_cast(assign.src),
                    BitOperationType.LSHIFT,
                )
            )
        elif assign.assign_type == AssignmentType.ASSIGN_AND:
            assign.set_src(
                BitOp(
                    f"op_AND",
                    assign.dest,
                    assign.src,
                    BitOperationType.AND,
                )
            )
        elif assign.assign_type == AssignmentType.ASSIGN_OR:
            assign.set_src(
                BitOp(
                    f"op_OR",
                    assign.dest,
                    assign.src,
                    BitOperationType.OR,
                )
            )
        elif assign.assign_type == AssignmentType.ASSIGN_XOR:
            assign.set_src(
                BitOp(
                    f"op_XOR",
                    assign.dest,
                    assign.src,
                    BitOperationType.XOR,
                )
            )
        else:
            raise NotImplementedError(f"Assign type {assign.assign_type} not handled.")
        self.add_op(assign.src)

    def assignment_expr(self, items):
        self.ext.set_token_meta_data("assignment_expr")

        dest: Pure = items[0]
        if isinstance(dest, Register) and dest.get_isa_name()[0] == "P":
            dname = dest.get_isa_name().upper()
            # Predicates need special handling.
            self.ext.set_token_meta_data(
                "pred_write",
                pred_num=(
                    dest.get_pred_num() if dname[1] in ["0", "1", "2", "3"] else -1
                ),
            )
        op_type = AssignmentType(items[1])
        if isinstance(items[2], Assignment):
            # a = b = 0 case
            src = items[2].src
        else:
            src: Pure = items[2]
        name = f"op_{op_type.name}"
        if op_type not in [
            AssignmentType.ASSIGN_MOD,
            AssignmentType.ASSIGN_RIGHT,
            AssignmentType.ASSIGN_LEFT,
        ]:
            dest, src = self.cast_operands(a=dest, b=src, immutable_a=True)
        assignment = Assignment(name, op_type, dest, src)
        self.update_assign_src(assignment)
        assignment = self.chk_hybrid_dep(self.add_op(assignment))
        if isinstance(items[2], Assignment):
            return self.chk_hybrid_dep(
                self.add_op(Sequence("seq", [assignment, items[2]]))
            )
        return assignment

    def additive_expr(self, items):
        result = self.simplify_arithmetic_expr(items)
        if result:
            return self.add_op(result)
        self.ext.set_token_meta_data("additive_expr")

        a = items[0]
        b = items[2]
        op_type = ArithmeticType(items[1])
        name = f"op_{op_type.name}"
        if op_type != ArithmeticType.MOD:
            # Modular operations don't need matching types.
            a = self.promotion_cast(a)
            b = self.promotion_cast(b)
            a, b = self.cast_operands(a=a, b=b, immutable_a=False)
        return self.add_op(ArithmeticOp(name, a, b, op_type))

    def multiplicative_expr(self, items):
        result = self.simplify_arithmetic_expr(items)
        if result:
            return self.add_op(result)
        self.ext.set_token_meta_data("multiplicative_expr")

        a = items[0]
        b = items[2]
        op_type = ArithmeticType(items[1])
        name = f"op_{op_type.name}"
        if op_type != ArithmeticType.MOD:
            # Modular operations don't need matching types.
            a = self.promotion_cast(a)
            b = self.promotion_cast(b)
            a, b = self.cast_operands(a=a, b=b, immutable_a=False)
        v = ArithmeticOp(name, a, b, op_type)
        return self.add_op(v)

    def and_expr(self, items):
        self.ext.set_token_meta_data("and_expr")

        return self.bit_operations(items, BitOperationType.AND)

    def inclusive_or_expr(self, items):
        self.ext.set_token_meta_data("inclusive_or_expr")

        return self.bit_operations(items, BitOperationType.OR)

    def exclusive_or_expr(self, items):
        self.ext.set_token_meta_data("exclusive_or_expr")

        return self.bit_operations(items, BitOperationType.XOR)

    def logical_and_expr(self, items):
        self.ext.set_token_meta_data("logical_and_expr")
        return self.boolean_expr(items)

    def logical_or_expr(self, items):
        self.ext.set_token_meta_data("logical_or_expr")
        return self.boolean_expr(items)

    def boolean_expr(self, items):
        if items[0] == "!":
            t = BooleanOpType(items[0])
            name = f"op_INV"
            v = BooleanOp(name, items[1], None, t)
        else:
            t = BooleanOpType(items[1])
            name = f"op_{t.name}"
            a = items[0]
            b = items[2] if len(items) == 3 else None
            if a and b:
                # No need to check for single operand operations.
                a, b = self.cast_operands(a=a, b=b, immutable_a=False)
            v = BooleanOp(name, a, b, t)
        return self.add_op(v)

    def shift_expr(self, items):
        self.ext.set_token_meta_data("shift_expr")
        return self.bit_operations(items, BitOperationType(items[1]))

    def unary_expr(self, items):
        self.ext.set_token_meta_data("unary_expr")
        result: Number = self.simplify_unary_expr(items)
        if result:
            return self.add_op(result)
        if items[0] == "~":
            v = self.bit_operations(items, BitOperationType.NOT)
        elif items[0] == "-":
            v = self.bit_operations(items, BitOperationType.NEG)
        elif items[0] == "!":
            v = self.boolean_expr(items)
        else:
            raise NotImplementedError(f"Unary expression {items[0]} not handler.")
        return v

    def argument_expr_list(self, items):
        self.ext.set_token_meta_data("argument_expr_list")
        return flatten_list(items)

    def sub_routine(self, items):
        routine_name = items[0]
        if routine_name == "fatal":
            return Empty("fatal")
        elif routine_name == "MEM_STORE0":
            return self.add_op(NOP("nop"))
        if routine_name not in self.sub_routines:
            # Handle it in legacy c_call handler.
            return self.c_call(items)
        args = items[1:]
        sub_routine: SubRoutine = self.sub_routines[routine_name]
        casted_args = self.cast_sub_routine_args(
            sub_routine.get_name(), args, sub_routine.get_parameter_value_types()
        )

        return self.resolve_hybrid(
            self.add_op(SubRoutineCall(self.sub_routines[routine_name], casted_args))
        )

    def postfix_expr(self, items):
        self.ext.set_token_meta_data("postfix_expr")
        t = HybridType(items[1])
        name = f"op_{HybridType(items[1]).name}"
        if t == HybridType.INC or t == HybridType.DEC:
            op: LocalVar = items[0]
            return self.resolve_hybrid(
                self.add_op(PostfixIncDec(name, op, op.value_type, t))
            )
        else:
            raise NotImplementedError(f"Postfix expression {t} not handled.")

    def bit_operations(self, items: list, op_type: BitOperationType):
        self.ext.set_token_meta_data("bit_operations")

        if len(items) < 3:
            # Single operand bit operation e.g. ~
            a = self.promotion_cast(items[1])
            name = f"op_{op_type.name}"
            v = BitOp(name, a, None, op_type)
            return self.add_op(v)
        a = items[0]
        b = items[2]
        name = f"op_{op_type.name}"
        if (a and b) and not (
            op_type == BitOperationType.RSHIFT or op_type == BitOperationType.LSHIFT
        ):
            a = self.promotion_cast(a)
            b = self.promotion_cast(b)
            a, b = self.cast_operands(a=a, b=b, immutable_a=False)
        v = BitOp(name, a, b, op_type)
        return self.add_op(v)

    def mem_store(self, items):
        self.ext.set_token_meta_data("mem_store")
        va = items[3]
        data: Pure = items[4]
        operation_value_type = ValueType(items[1] == "s", items[2])
        if operation_value_type != data.value_type:
            # STOREW determines from the data type how many bytes are written.
            # Cast the data type to the mem store type
            data = self.init_a_cast(operation_value_type, data)
        return self.chk_hybrid_dep(
            self.add_op(MemStore(f"ms_{data.get_name()}", va, data))
        )

    # SPECIFIC FOR: Hexagon
    def mem_load(self, items):
        self.ext.set_token_meta_data("mem_load")
        vt = ValueType(items[1] == "s", items[2])
        mem_acc_type = MemAccessType(vt, True)
        va = items[3]
        if not isinstance(va, Pure):
            va = self.il_ops_holder.get_op_by_name(va.value)

        return self.add_op(MemLoad(f"ml_{va.get_name()}", va, mem_acc_type))

    def macro_expr(self, items):
        self.ext.set_token_meta_data("macro_expr")
        macro_name = items[0]
        args = items[1:]
        if macro_name not in self.macros:
            raise ValueError(f"Macro {macro_name} is not defined.")
        macro = self.macros[macro_name]
        self.cast_arg_list(args, macro.param_types)
        return self.add_op(MacroInvocation(macro_name, args, macro))

    def cast_sub_routine_args(
        self, fcn_name: str, args: list[Pure], predefined_types: list[ValueType] = None
    ) -> list[Pure]:
        if predefined_types:
            param_types = predefined_types
        else:
            param_types = get_fcn_param_types(fcn_name)
        self.cast_arg_list(args, param_types)
        return args

    def cast_arg_list(self, args: list, param_types: list[ValueType]) -> None:
        if len(args) != len(param_types):
            raise ValueError(
                f"Argument and parameter count mismatch:\nargs: {args}\nparams: {param_types}"
            )

        for i, (arg, p_type) in enumerate(zip(args, param_types)):
            if not p_type or isinstance(arg, str):
                # Those sub-routines are not yet implemented properly and
                # get handled by Call.py
                continue
            if p_type.group & VTGroup.EXTERNAL:
                # Here we pass non Pures. So we can't cast them.
                continue
            if arg.value_type == p_type:
                continue

            args[i] = self.init_a_cast(p_type, arg, "param_cast")

    def c_call(self, items):
        self.ext.set_token_meta_data("c_call")
        prefix = items[0]
        if prefix == "sizeof":
            op = items[1]
            return self.add_op(Sizeof(f"op_sizeof_{op.get_name()}", op))
        val_type = self.ext.get_val_type_by_fcn(prefix)
        param = self.cast_sub_routine_args(prefix, items[1:])

        return self.resolve_hybrid(
            self.add_op(Call(f"c_call", val_type, [prefix] + param))
        )

    def identifier(self, items):
        self.ext.set_token_meta_data("identifier")
        # Hexagon shortcode can initialize certain variables without type.
        # Those are converted to a local var here.
        identifier = items[0].value
        if identifier in self.parameters:
            return self.parameters[identifier]

        holder = self.il_ops_holder
        if identifier in holder.read_ops:
            return holder.read_ops[identifier]
        if self.ext.is_special_id(identifier):
            return self.add_op(self.ext.special_identifier_to_local_var(identifier))
        # Return string. It could be a variable or a function call.
        return identifier

    def compare_op(self, items):
        self.ext.set_token_meta_data("compare_op")
        result = self.simplify_compare_expr(items)
        if result:
            return self.add_op(result)
        op_type = CompareOpType(items[1])
        a, b = self.cast_operands(a=items[0], b=items[2], immutable_a=False)
        return self.add_op(CompareOp(f"op_{op_type.name}", a, b, op_type))

    def for_loop(self, items):
        self.ext.set_token_meta_data("for_loop")
        if len(items) != 5:
            raise NotImplementedError(
                f"For loops with {len(items)} elements is not supported yet."
            )
        compound = self.chk_hybrid_dep(
            self.add_op(Sequence(f"seq", flatten_list(items[4]) + [items[3]])),
            HybridSeqOrder.SEQ_THEN_HYB,
        )
        return self.chk_hybrid_dep(
            self.add_op(
                Sequence(
                    f"seq",
                    [items[1], self.add_op(ForLoop(f"for", items[2], compound))],
                )
            )
        )

    def iteration_stmt(self, items):
        self.ext.set_token_meta_data("iteration_stmt")
        if items[0] == "for":
            return self.for_loop(items)
        else:
            raise NotImplementedError(f"{items[0]} loop not supported.")

    def compound_stmt(self, items):
        self.ext.set_token_meta_data("compound_stmt")
        # These are empty compound statements.
        return self.chk_hybrid_dep(self.add_op(Empty(f"empty")))

    def gcc_extended_expr(self, items):
        self.ext.set_token_meta_data("gcc_extended_expr")
        if isinstance(items[0], list) and isinstance(items[-1], Pure):
            raise NotImplementedError(
                "List of statements in gcc extended expressions not implemented."
            )
        elif isinstance(items[0], list) or not items[1]:
            # This is a compound statement.
            return items[0]
        p: Pure = items[1]
        e: Effect = items[0]
        return self.resolve_hybrid(
            self.add_op(GCCStmtDeclExpr("gcc_expr", e, p, p.value_type))
        )

    def expr_stmt(self, items):
        self.ext.set_token_meta_data("expr_stmt")
        # These are empty expression statements.
        return self.add_op(self.chk_hybrid_dep(self.add_op(Empty(f"empty"))))

    def cancel_slot_stmt(self, items):
        self.ext.set_token_meta_data("cancel_slot_stmt")
        return self.add_op(self.chk_hybrid_dep(self.add_op(NOP(f"nop"))))

    def block_item_list(self, items):
        self.ext.set_token_meta_data("block_item_list")
        return items

    def block_item(self, items):
        self.ext.set_token_meta_data("block_item")
        return items[0]

    def chk_hybrid_dep(
        self, effect: Effect, order: HybridSeqOrder = HybridSeqOrder.HYB_THEN_SEQ
    ) -> Effect:
        """Check hybrid dependency. Checks if a hybrid effect must be executed before the given effect and returns
        a sequence of Sequence(hybrid, given effect) if so. Otherwise, the original effect.
        """
        if len(self.il_ops_holder.hybrid_effect_dict) == 0:
            return effect
        hybrid_deps = list()
        for o in effect.get_op_list():
            if (
                not isinstance(o, str)
                and o.get_name() in self.il_ops_holder.hybrid_effect_dict
            ):
                hybrid_deps.append(
                    self.il_ops_holder.hybrid_effect_dict.pop(o.get_name())
                )

        if len(hybrid_deps) == 0:
            return effect
        if order == HybridSeqOrder.HYB_THEN_SEQ:
            return self.add_op(Sequence(f"seq", hybrid_deps + [effect]))
        elif order == HybridSeqOrder.SEQ_THEN_HYB:
            return self.add_op(Sequence(f"seq", [effect] + hybrid_deps))
        raise ValueError(f"Invalid HybridSeqOrder = {order}")

    def resolve_hybrid(self, hybrid: Hybrid) -> Pure | Hybrid:
        """Splits a hybrid in a Pure and Effect part.
        The Pure is assigned to a LocalVar. The LocalVar gets returned.
        The hybrids effect and the assignment of the LocalVar are saved to a list and used later when
        the dependent effect is created.

        If the hybrid is a sub-routine with a return type of void, this returns the hybrid.
        """
        if hybrid.value_type.group & VTGroup.VOID:
            return hybrid

        tmp_x_name = f"h_tmp{self.il_ops_holder.hybrid_op_count}"
        self.il_ops_holder.hybrid_op_count += 1
        if hybrid.seq_order == HybridSeqOrder.EXEC_ONLY:
            # Doesn't return anything. So no LocalVar for the return value has to be initialized.
            self.il_ops_holder.hybrid_effect_dict[tmp_x_name] = self.chk_hybrid_dep(
                hybrid
            )
            return Number("VOID_VALUE", 0xFFFFFFFF, ValueType(False, 32, VTGroup.VOID))
        h_tmp_type = hybrid.value_type
        h_tmp_type.group |= VTGroup.HYBRID_LVAR
        tmp_x = self.add_op(
            LocalVar(tmp_x_name, hybrid.value_type, hybrid_owner=hybrid)
        )
        tmp_x
        hybrid.references_set.add(tmp_x)

        # Assign the hybrid pure part to tmp_x.
        name = f"op_{AssignmentType.ASSIGN.name}_hybrid_tmp"
        tmp_x, hybrid = self.cast_operands(a=tmp_x, b=hybrid, immutable_a=True)
        set_tmp = self.add_op(Assignment(name, AssignmentType.ASSIGN, tmp_x, hybrid))

        # Add hybrid effect to the ILOpHolder in the Effect constructor.
        if hybrid.seq_order == HybridSeqOrder.SET_VAL_THEN_EXEC:
            h_seq = [set_tmp, hybrid]
        elif hybrid.seq_order == HybridSeqOrder.EXEC_THEN_SET_VAL:
            h_seq = [hybrid, set_tmp]
        else:
            raise NotImplementedError(
                f"Hybrid {hybrid} has no valid sequence order set."
            )

        seq = self.add_op(Sequence(f"seq", h_seq))
        seq = self.chk_hybrid_dep(seq)
        self.il_ops_holder.hybrid_effect_dict[tmp_x_name] = seq
        # Return local tX
        return tmp_x

    def simplify_unary_expr(self, items) -> Number | None:
        """
        Checks if the given unary expression can be simplified.
        Unary expressions on Numbers can be resolved to the resulting number,
        so we do not have to do it during IL runtime.
        """
        operation: str = items[0]
        a = items[1]
        if not isinstance(a, LetVar):
            return None

        if not isinstance(a.get_val(), int):
            return None

        val_a = a.get_val()
        match operation:
            case "~":
                result = ~val_a
                a_type = promoted_type(a.value_type)
            case "-":
                result = -val_a
                a_type = promoted_type(a.value_type)
                a_type.signed = True
            case "+":
                result = +val_a
                a_type = promoted_type(a.value_type)
            case _:
                return None

        self.il_ops_holder.rm_op_by_name(a.get_name())
        name = f'const_{"neg" if result < 0 else "pos"}_{result}'
        return Number(name, result, a_type)

    def simplify_arithmetic_expr(self, items) -> Pure:
        """
        Checks if the given arithmetic expression can be simplified.
        Simple arithmetic expressions can be resolved to a single number,
        so we do not have to do it during IL runtime.
        """
        a = items[0]
        operation: str = items[1]
        b = items[2]
        if not isinstance(a, LetVar) or not isinstance(b, LetVar):
            return None

        if not isinstance(a.get_val(), int) or not isinstance(b.get_val(), int):
            return None

        val_a = a.get_val()
        val_b = b.get_val()
        self.il_ops_holder.rm_op_by_name(a.get_name())
        self.il_ops_holder.rm_op_by_name(b.get_name())
        match operation:
            case "+":
                result = val_a + val_b
            case "-":
                result = val_a - val_b
            case "*":
                result = val_a * val_b
            case "/":
                result = val_a / val_b
            case _:
                raise NotImplementedError(f"Can not simplify '{operation}' expression.")
        a_type, b_type = c11_cast(a.value_type, b.value_type)

        name = f'const_{"neg" if items[0] == "-" else "pos"}{items[1]}{items[2] if items[2] else ""}'
        return Number(name, result, a_type)

    def simplify_compare_expr(self, items) -> Pure:
        """
        Checks if the given compare expression can be simplified.
        Simple compare expressions can be resolved to a truth value,
        so we do not have to do it during IL runtime.
        """
        a = items[0]
        operation: str = items[1]
        b = items[2]
        if not isinstance(a, LetVar) or not isinstance(b, LetVar):
            return None

        if not isinstance(a.get_val(), int) or not isinstance(b.get_val(), int):
            return None

        val_a = a.get_val()
        val_b = b.get_val()
        self.il_ops_holder.rm_op_by_name(a.get_name())
        self.il_ops_holder.rm_op_by_name(b.get_name())
        match operation:
            case "<":
                res = val_a < val_b
            case ">":
                res = val_a > val_b
            case "<=":
                res = val_a <= val_b
            case ">=":
                res = val_a >= val_b
            case "==":
                res = val_a == val_b
            case "!=":
                res = val_a != val_b
            case _:
                raise NotImplementedError(f"Can not simplify '{operation}' expression.")

        name = f"{'True' if res else 'False'}"
        return Bool(name, True if res else False)

    def simplify_conditional_expr(self, items) -> Pure | None:
        cond = items[0]
        if not isinstance(cond, LetVar):
            return None
        self.il_ops_holder.rm_op_by_name(cond.get_name())
        if cond.get_val():
            self.il_ops_holder.rm_op_by_name(items[2].get_name())
            return items[1]
        self.il_ops_holder.rm_op_by_name(items[1].get_name())
        return items[2]

    def cast_operands(self, immutable_a: bool, **ops) -> tuple[Pure, Pure]:
        """Casts two operands to a common type according to C11 standard.
        If immutable_op_a = True operand b is cast to the operand a type
        (Useful for assignments to global vars like registers).
        Operand are names in the order: a, b, c, ...
        """
        if "a" not in ops and "b" not in ops:
            raise NotImplementedError('At least operand "a" and "b" must be given.')
        a = ops["a"]
        b = ops["b"]
        if not a.value_type and not b.value_type:
            raise NotImplementedError("Cannot cast ops without value types.")
        if not a.value_type:
            a.value_type = b.value_type
            return a, b
        if not b.value_type:
            b.value_type = a.value_type
            return a, b

        if a.value_type == b.value_type:
            return a, b

        if immutable_a:
            return a, self.init_a_cast(a.value_type, b)

        casted_a, casted_b = c11_cast(a.value_type, b.value_type)

        if (
            casted_a.bit_width != a.value_type.bit_width
            or casted_a.signed != a.value_type.signed
        ):
            a = self.init_a_cast(casted_a, a)
        if (
            casted_b.bit_width != b.value_type.bit_width
            or casted_b.signed != b.value_type.signed
        ):
            b = self.init_a_cast(casted_b, b)

        return a, b

    def promotion_cast(self, pure: Pure) -> Pure:
        """Checks the type of the given Pure if it needs to be promoted to (unsigned) int.
        If so this returns a cast of the Pure to the given promoted type.
        Otherwise, it returns the Pure given.
        """
        p_type = promoted_type(pure.value_type)
        if p_type != pure.value_type:
            return self.init_a_cast(p_type, pure)
        return pure
