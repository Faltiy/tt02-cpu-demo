# CPU_DEMO

All credit for the creation and some of the code goes to [noahgaertner](https://github.com/noahgaertner/tt02-verilog-demo). This repo contains fixes to the testbench, documentation and RTL cleanups (licensed under Apache 2.0, see LICENSE).

---

![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg)

# Basic 4-bit CPU (Tiny Tapeout 02)

A tiny programmable 4-bit accumulator CPU. You load a program and its data
through the input pins, then clock it and watch the program counter and
accumulator on the output pins.

> **Always reset first.** Reset is synchronous and active high. It clears the
> program counter, accumulator **and both memories**, and the memories are not
> initialised any other way. So the order is: **reset → load → run**. Resetting
> after loading erases your program.

## Pins

| Pin     | Dir | Function                              |
|---------|-----|---------------------------------------|
| IN[0]   | in  | clock                                 |
| IN[1]   | in  | reset (synchronous, active high)      |
| IN[3:2] | in  | mode (see below)                      |
| IN[7:4] | in  | 4-bit data bus (`IN[7]` is the MSB)   |
| OUT[3:0]| out | program counter (`OUT[0]` = LSB)     |
| OUT[7:4]| out | accumulator value (`OUT[4]` = LSB)   |

## Modes (IN[3:2])

| Value | Name       | What happens on the rising clock edge                         |
|-------|------------|---------------------------------------------------------------|
| 0     | `LOADPROG` | `prog[pc] <= IN[7:4]`, `pc <= pc + 1`                         |
| 1     | `LOADDATA` | `data[pc] <= IN[7:4]`, `pc <= pc + 1`                         |
| 2     | `SETRUNPT` | `pc <= IN[7:4]`                                               |
| 3     | `RUNPROG`  | execute the instruction at `prog[pc]` (see ISA)               |

## Programming model

- 16 × 4-bit program memory (`prog`) and 16 × 4-bit data memory (`data`).
- Both are indexed by the **same** program counter. The instruction at
  `prog[i]` always uses `data[i]` as its operand (called *datac* below).
  There is no separate immediate field.
- The program counter is 4 bits and wraps from 15 to 0.
- `STORE` writes to `data[datac]`. Since operands live in `data`, a program can
  store a value into the operand slot of a later instruction (self-modifying
  code). This is how you get "variable" operands.

### Loading a program

1. Pulse reset (hold `IN[1]` high for one clock edge).
2. Mode `LOADPROG`: clock in 16 opcodes (one per clock). `pc` wraps back to 0.
3. Mode `LOADDATA`: clock in 16 operands. `pc` wraps back to 0.
4. Mode `SETRUNPT`: put the start address on `IN[7:4]` and clock once.
5. Mode `RUNPROG`: each clock executes one instruction.

If you load fewer than 16 entries, use `SETRUNPT` to move `pc` back (e.g. to 0)
before the next load. Unused entries are 0 after reset, which is `LOAD 0`.

## ISA

All arithmetic is modulo 16. "datac" is `data[pc]`. Every instruction except
`JUMPTOIF` advances `pc` by 1.

| Op | Name       | Effect                                                           |
|----|------------|------------------------------------------------------------------|
| 0  | `LOAD`     | `acc <= datac`                                                   |
| 1  | `STORE`    | `data[datac] <= acc`                                             |
| 2  | `ADD`      | `acc <= acc + datac`                                             |
| 3  | `MUL`      | `acc <= acc * datac` (low 4 bits)                                |
| 4  | `SUB`      | `acc <= acc - datac`                                             |
| 5  | `SHIFTL`   | `acc <= acc << min(datac, 3)`                                    |
| 6  | `SHIFTR`   | `acc <= acc >> min(datac, 3)`                                    |
| 7  | `JUMPTOIF` | `pc <= datac` if the jump flag is 1, else `pc + 1`; `acc` unchanged |
| 8  | `LOGICAND` | `acc <= (acc != 0) && (datac != 0)` (result is 0 or 1)           |
| 9  | `LOGICOR`  | `acc <= (acc != 0) \|\| (datac != 0)` (result is 0 or 1)         |
| 10 | `EQUALS`   | `acc <= (acc == datac)` (0 or 1)                                 |
| 11 | `NEQ`      | `acc <= (acc != datac)` (0 or 1)                                 |
| 12 | `BITAND`   | `acc <= acc & datac`                                             |
| 13 | `BITOR`    | `acc <= acc \| datac`                                            |
| 14 | `LOGICNOT` | `acc <= (acc == 0)` (operand ignored)                            |
| 15 | `BITNOT`   | `acc <= ~acc` (operand ignored)                                  |

Notes:

- **Shift amounts are clamped to 3.** A shift by 4 or more behaves like a shift
  by 3 (it does not clear the register).
- **Jump condition and timing.** The condition is the external pin `IN[7]`,
  *sampled on the previous clock edge* (a one-cycle delay). To take a jump,
  `IN[7]` must be 1 during the clock cycle *before* the `JUMPTOIF` executes.
  The jump target is the operand `data[pc]` of the `JUMPTOIF` itself.
- There is no unconditional jump and no halt. Holding `IN[7]` high while running
  makes every `JUMPTOIF` taken, which gives you an unconditional jump.
- `SETRUNPT` with a value of 8 or more also samples `IN[7] = 1` into the jump
  flag, because the flag is sampled on every non-reset clock edge.

## Example: one of every opcode

Load `prog[i] = i` for i = 0..15 and this data:

```
data = 0 0 5 2 11 5 1 0 3 11 11 0 15 15 10 0
```

Then `SETRUNPT 0`, hold `IN[7]` low, and run 16 cycles. The accumulator (OUT[7:4])
after each instruction is:

```
0 0 5 10 15 8 4 4 1 1 0 0 0 15 0 15
```

## Simulation

Requires [cocotb](https://www.cocotb.org/) and Icarus Verilog.

```sh
cd src
make
! grep -E "<(failure|error)" results.xml   # no output means all tests passed
```

`src/test.py` compares the DUT against a Python reference model every cycle and
also checks a few hand-computed values (all opcodes, jump timing, reset wiping
the memories, `STORE` into a later operand slot, and randomized programs).
`src/tb.sv` is just a wrapper that exposes the pins and dumps `tb.vcd`; cocotb
supplies the clock and stimulus.

Target clock is 50 kHz or lower.

# What is Tiny Tapeout?

TinyTapeout is an educational project that aims to make it easier and cheaper
than ever to get your digital designs manufactured on a real chip!

Go to https://tinytapeout.com for instructions!

## How to enable the GitHub actions to build the ASIC files

Please see the instructions for:

* [Enabling GitHub Actions](https://tinytapeout.com/faq/#when-i-commit-my-change-the-gds-action-isnt-running)
* [Enabling GitHub Pages](https://tinytapeout.com/faq/#my-github-action-is-failing-on-the-pages-part)

## How does the build work?

The [GitHub Action](.github/workflows/gds.yaml) uses the open source ASIC tool
[OpenLane](https://www.zerotoasiccourse.com/terminology/openlane/) to turn the
sources listed in `info.yaml` into the files needed to fabricate an ASIC.

## Resources

* [FAQ](https://tinytapeout.com/faq/)
* [Digital design lessons](https://tinytapeout.com/digital_design/)
* [Join the community](https://discord.gg/rPK2nSjxy8)
