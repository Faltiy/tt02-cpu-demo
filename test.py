"""Self-checking cocotb tests for the 4-bit CPU (noahgaertner_cpu).

Every cycle the DUT outputs (pc, accumulator) are compared against a small
Python reference model of the ISA, plus a few hand-computed expectations so
the model itself is not trusted blindly.

Timing convention: inputs are driven on the falling edge, the DUT samples on
the following rising edge, and outputs are read on the next falling edge once
they have settled.
"""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

# pin modes (IN[3:2])
LOADPROG, LOADDATA, SETRUNPT, RUNPROG = 0, 1, 2, 3

# opcodes
(LOAD, STORE, ADD, MUL, SUB, SHIFTL, SHIFTR, JUMPTOIF,
 LOGICAND, LOGICOR, EQUALS, NEQ, BITAND, BITOR, LOGICNOT, BITNOT) = range(16)


class CpuModel:
    """Cycle-accurate reference model of the ISA."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.pc = 0
        self.reg = 0
        self.last = 0  # IN[7] sampled on the previous edge
        self.prog = [0] * 16
        self.data = [0] * 16

    def step(self, mode, d):
        d &= 0xF
        npc = (self.pc + 1) & 0xF
        if mode == LOADPROG:
            self.prog[self.pc] = d
            self.pc = npc
        elif mode == LOADDATA:
            self.data[self.pc] = d
            self.pc = npc
        elif mode == SETRUNPT:
            self.pc = d
        else:
            op = self.prog[self.pc]
            dc = self.data[self.pc]
            r = self.reg
            if op == LOAD:
                self.reg = dc
            elif op == STORE:
                self.data[dc] = r
            elif op == ADD:
                self.reg = (r + dc) & 0xF
            elif op == SUB:
                self.reg = (r - dc) & 0xF
            elif op == MUL:
                self.reg = (r * dc) & 0xF
            elif op == SHIFTL:
                self.reg = (r << min(dc, 3)) & 0xF
            elif op == SHIFTR:
                self.reg = r >> min(dc, 3)
            elif op == LOGICAND:
                self.reg = int(r != 0 and dc != 0)
            elif op == LOGICOR:
                self.reg = int(r != 0 or dc != 0)
            elif op == EQUALS:
                self.reg = int(r == dc)
            elif op == NEQ:
                self.reg = int(r != dc)
            elif op == BITAND:
                self.reg = r & dc
            elif op == BITOR:
                self.reg = r | dc
            elif op == LOGICNOT:
                self.reg = int(r == 0)
            elif op == BITNOT:
                self.reg = (~r) & 0xF
            if op == JUMPTOIF:
                self.pc = dc if self.last else npc
            else:
                self.pc = npc
        # sampled on every non-reset cycle, used by the NEXT cycle's jump
        self.last = (d >> 3) & 1


# ------------------------------------------------------------------ helpers
def read_outputs(dut):
    v = int(dut.outputs.value)  # raises ValueError if X/Z, which is a failure
    return v & 0xF, (v >> 4) & 0xF  # (pc, regval)


async def boot(dut):
    """Start the clock exactly once per test and park the inputs."""
    dut.reset.value = 1
    dut.instruction.value = 0
    dut.data.value = 0
    cocotb.start_soon(Clock(dut.clock, 10, units="us").start())
    await FallingEdge(dut.clock)


async def fresh(dut):
    """Apply a clean reset; returns a freshly reset reference model."""
    model = CpuModel()
    await drive(dut, model, 0, 0, rst=1)
    assert read_outputs(dut) == (0, 0), "outputs must be 0 after reset"
    return model


async def start(dut):
    """boot + fresh, for tests that only need one clean start."""
    await boot(dut)
    return await fresh(dut)


async def drive(dut, model, mode, d, rst=0):
    """Apply one clock cycle, update the model, compare outputs."""
    dut.reset.value = rst
    dut.instruction.value = mode
    dut.data.value = d
    await RisingEdge(dut.clock)
    await FallingEdge(dut.clock)
    if rst:
        model.reset()
    else:
        model.step(mode, d)
    got = read_outputs(dut)
    exp = (model.pc, model.reg)
    assert got == exp, (
        f"mismatch after mode={mode} d={d} rst={rst}: "
        f"DUT (pc,reg)={got}, model={exp}"
    )
    return got


async def load(dut, model, prog, data, start_pc=0):
    """LOADPROG x16, LOADDATA x16 (pc wraps to 0 each time), SETRUNPT."""
    assert len(prog) == 16 and len(data) == 16
    for op in prog:
        await drive(dut, model, LOADPROG, op)
    assert model.pc == 0, "pc should wrap after 16 loads"
    for d in data:
        await drive(dut, model, LOADDATA, d)
    await drive(dut, model, SETRUNPT, start_pc)


# -------------------------------------------------------------------- tests
@cocotb.test()
async def test_reset_clears_state(dut):
    """Reset zeroes pc/acc AND wipes both memories."""
    model = await start(dut)
    # fill program with ADD and data with 7, run a bit so reg != 0
    await load(dut, model, [ADD] * 16, [7] * 16)
    for _ in range(3):
        await drive(dut, model, RUNPROG, 0)
    assert read_outputs(dut)[1] != 0
    # reset, then run: memories cleared => opcode 0 (LOAD) with operand 0
    await drive(dut, model, 0, 0, rst=1)
    assert read_outputs(dut) == (0, 0)
    for _ in range(4):
        pc, reg = await drive(dut, model, RUNPROG, 0)
        assert reg == 0, "memory was not cleared by reset"


@cocotb.test()
async def test_all_opcodes_demo(dut):
    """One of every opcode, with hand-computed expected accumulator values."""
    model = await start(dut)
    prog = list(range(16))  # prog[i] = opcode i
    data = [0, 0, 5, 2, 11, 5, 1, 0, 3, 11, 11, 0, 15, 15, 10, 0]
    await load(dut, model, prog, data)
    # expected accumulator after each of the 16 instructions
    expected = [0, 0, 5, 10, 15, 8, 4, 4, 1, 1, 0, 0, 0, 15, 0, 15]
    for i, exp in enumerate(expected):
        pc, reg = await drive(dut, model, RUNPROG, 0)
        assert reg == exp, f"opcode {i}: reg={reg}, expected {exp}"
        assert pc == (i + 1) & 0xF, f"opcode {i}: pc={pc}"


@cocotb.test()
async def test_jump_timing(dut):
    """JUMPTOIF uses IN[7] as sampled on the PREVIOUS clock edge."""
    prog = [ADD, JUMPTOIF, ADD, ADD] + [LOAD] * 12
    data = [1, 3, 2, 0] + [0] * 12  # JUMPTOIF target = data[1] = 3

    # (pin7 during the cycle before the jump, pin7 during the jump, taken?)
    cases = [(1, 0, True), (0, 1, False), (0, 0, False), (1, 1, True)]
    await boot(dut)
    for prev, cur, taken in cases:
        model = await fresh(dut)
        await load(dut, model, prog, data, start_pc=0)
        await drive(dut, model, RUNPROG, prev << 3)  # ADD, pc -> 1
        pc, _ = await drive(dut, model, RUNPROG, cur << 3)  # JUMPTOIF
        assert pc == (3 if taken else 2), (
            f"prev={prev} cur={cur}: pc={pc}, taken expected={taken}"
        )


@cocotb.test()
async def test_store_and_self_modifying_operand(dut):
    """STORE writes data[operand]; storing into a later operand slot works."""
    model = await start(dut)
    # pc0: LOAD 9 ; pc1: STORE ->data[3] ; pc2: LOAD 0 (clobber reg) ;
    # pc3: ADD (operand is the value STOREd by pc1)
    prog = [LOAD, STORE, LOAD, ADD] + [LOAD] * 12
    data = [9, 3, 0, 0] + [0] * 12
    await load(dut, model, prog, data)
    await drive(dut, model, RUNPROG, 0)  # reg = 9
    await drive(dut, model, RUNPROG, 0)  # data[3] = 9
    await drive(dut, model, RUNPROG, 0)  # reg = 0
    pc, reg = await drive(dut, model, RUNPROG, 0)  # reg = 0 + 9
    assert (pc, reg) == (4, 9)


@cocotb.test()
async def test_random_programs(dut):
    """Random programs, random pin activity, compared every cycle."""
    rng = random.Random(1234)
    await boot(dut)
    for trial in range(25):
        model = await fresh(dut)
        prog = [rng.randrange(16) for _ in range(16)]
        data = [rng.randrange(16) for _ in range(16)]
        await load(dut, model, prog, data, start_pc=rng.randrange(8))
        for _ in range(150):
            # mostly run, occasionally poke the other modes
            mode = RUNPROG if rng.random() < 0.9 else rng.randrange(3)
            await drive(dut, model, mode, rng.randrange(16))
        # sprinkle in a mid-run reset
        await drive(dut, model, rng.randrange(4), rng.randrange(16), rst=1)
        for _ in range(5):
            await drive(dut, model, RUNPROG, rng.randrange(16))
