# SPDX-FileCopyrightText: 2022 Rot127 <unisono@quyllur.org>
# SPDX-License-Identifier: LGPL-3.0-only

from Transformer.Effects.Effect import Effect
from Transformer.Pures.Pure import Pure, PureType


def singleton(cls, *args, **kw):
    instances = {}

    def _singleton(*args, **kw):
        if cls not in instances:
            instances[cls] = cls(*args, **kw)
        return instances[cls]

    return _singleton


@singleton
class ILOpsHolder(object):
    read_ops: dict
    exec_ops: dict
    write_ops: dict
    let_ops: dict  # immutable LET vars.

    def __init__(self):
        self.read_ops = dict()
        self.exec_ops = dict()
        self.write_ops = dict()
        self.let_ops = dict()

    def add_pure(self, pure: Pure):
        if pure.type == PureType.GLOBAL:
            self.read_ops[pure.get_name()] = pure
        elif pure.type == PureType.EXEC or pure.type == PureType.LOCAL:
            self.exec_ops[pure.get_name()] = pure
        elif pure.type == PureType.LET:
            self.read_ops[pure.get_name()] = pure
        else:
            raise NotImplementedError('')

    def add_effect(self, effect: Effect):
        self.write_ops[effect.get_name()] = effect