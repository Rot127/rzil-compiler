// SPDX-FileCopyrightText: 2022 Rot127 <unisono@quyllur.org>
// SPDX-License-Identifier: LGPL-3.0-only

// Macros in this file fill replace the qualcomm macros from the Qemu source.

#define MEM_LOAD1s(VA) (mem_load_s8(VA))
#define MEM_LOAD1u(VA) (mem_load_u8(VA))
#define MEM_LOAD2s(VA) (mem_load_s16(VA))
#define MEM_LOAD2u(VA) (mem_load_u16(VA))
#define MEM_LOAD4s(VA) (mem_load_s32(VA))
#define MEM_LOAD4u(VA) (mem_load_u32(VA))
#define MEM_LOAD8s(VA) (mem_load_s64(VA))
#define MEM_LOAD8u(VA) (mem_load_u64(VA))

#define MEM_STORE1(VA, DATA, SLOT) mem_store_u8(VA, DATA)
#define MEM_STORE2(VA, DATA, SLOT) mem_store_u16(VA, DATA)
#define MEM_STORE4(VA, DATA, SLOT) mem_store_u32(VA, DATA)
#define MEM_STORE8(VA, DATA, SLOT) mem_store_u64(VA, DATA)

#define CANCEL cancel_slot

#define fPART1(WORK) __COMPOUND_PART1__{ WORK; }__COMPOUND_PART1__

#define fIMMEXT(IMM)

#define fREAD_GP() \
    (insn->extension_valid ? 0 : READ_REG(HEX_REG_GP))

#define fWRITE_NPC(A) JUMP(A)

#define READ_REG(NUM)                    NUM
#define READ_PREG(NUM)                   P##NUM

#define HEX_REG_LR   HEX_REG_ALIAS_LR
#define HEX_REG_R31   HEX_REG_ALIAS_R31
#define HEX_REG_SA0   HEX_REG_ALIAS_SA0
#define HEX_REG_LC0   HEX_REG_ALIAS_LC0
#define HEX_REG_SA1   HEX_REG_ALIAS_SA1
#define HEX_REG_LC1   HEX_REG_ALIAS_LC1
#define HEX_REG_P3_0   HEX_REG_ALIAS_P3_0
#define HEX_REG_M0   HEX_REG_ALIAS_M0
#define HEX_REG_M1   HEX_REG_ALIAS_M1
#define HEX_REG_USR   HEX_REG_ALIAS_USR
#define HEX_REG_PC   HEX_REG_ALIAS_PC
#define HEX_REG_UGP   HEX_REG_ALIAS_UGP
#define HEX_REG_GP   HEX_REG_ALIAS_GP
#define HEX_REG_CS0   HEX_REG_ALIAS_CS0
#define HEX_REG_CS1   HEX_REG_ALIAS_CS1
#define HEX_REG_UPCYCLELO   HEX_REG_ALIAS_UPCYCLELO
#define HEX_REG_UPCYCLEHI   HEX_REG_ALIAS_UPCYCLEHI
#define HEX_REG_FRAMELIMIT   HEX_REG_ALIAS_FRAMELIMIT
#define HEX_REG_FRAMEKEY   HEX_REG_ALIAS_FRAMEKEY
#define HEX_REG_PKTCNTLO   HEX_REG_ALIAS_PKTCNTLO
#define HEX_REG_PKTCNTHI   HEX_REG_ALIAS_PKTCNTHI
#define HEX_REG_UTIMERLO   HEX_REG_ALIAS_UTIMERLO
#define HEX_REG_UTIMERHI   HEX_REG_ALIAS_UTIMERHI
/* Use reserved control registers for qemu execution counts */
// HEX_REG_QEMU_PKT_CNT      = 52,
// HEX_REG_QEMU_INSN_CNT     = 53,
// HEX_REG_QEMU_HVX_CNT      = 54,
