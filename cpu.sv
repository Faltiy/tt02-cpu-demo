`default_nettype none
// Basic 4-bit CPU for Tiny Tapeout 02.
//
// Behaviour is intentionally identical to the original submission; this
// version only cleans up type-strictness (no implicit logic->enum
// assignments), replaces the hand-unrolled reset with loops, and makes the
// comments match what the hardware actually does.
//
// Programming model (see README.md for the full story):
//   * 16 x 4-bit program memory (prog) and 16 x 4-bit data memory (data).
//   * Both are indexed by the SAME program counter. The "operand" of the
//     instruction at prog[pc] is always data[pc]  (called datac below).
//   * Reset (synchronous, active high) clears pc, accumulator, jump flag AND
//     both memories, so reset BEFORE loading a program, not after.
module noahgaertner_cpu (
    input  logic [7:0] io_in,
    output logic [7:0] io_out
);
  logic clock, reset;
  assign clock = io_in[0];  // clock
  assign reset = io_in[1];  // synchronous reset, active high

  // ---------------------------------------------------------------- opcodes
  // Plain localparams (not enums) so Yosys / Verilator / Icarus all agree.
  localparam [3:0] LOAD     = 4'd0;   // reg <= datac
  localparam [3:0] STORE    = 4'd1;   // data[datac] <= reg
  localparam [3:0] ADD      = 4'd2;   // reg <= reg + datac        (mod 16)
  localparam [3:0] MUL      = 4'd3;   // reg <= reg * datac        (low 4 bits)
  localparam [3:0] SUB      = 4'd4;   // reg <= reg - datac        (mod 16)
  localparam [3:0] SHIFTL   = 4'd5;   // reg <= reg << min(datac,3)
  localparam [3:0] SHIFTR   = 4'd6;   // reg <= reg >> min(datac,3)
  localparam [3:0] JUMPTOIF = 4'd7;   // pc <= lastdata3 ? datac : pc+1
  localparam [3:0] LOGICAND = 4'd8;   // reg <= (reg != 0) && (datac != 0)
  localparam [3:0] LOGICOR  = 4'd9;   // reg <= (reg != 0) || (datac != 0)
  localparam [3:0] EQUALS   = 4'd10;  // reg <= (reg == datac)
  localparam [3:0] NEQ      = 4'd11;  // reg <= (reg != datac)
  localparam [3:0] BITAND   = 4'd12;  // reg <= reg & datac
  localparam [3:0] BITOR    = 4'd13;  // reg <= reg | datac
  localparam [3:0] LOGICNOT = 4'd14;  // reg <= (reg == 0)         (operand unused)
  localparam [3:0] BITNOT   = 4'd15;  // reg <= ~reg               (operand unused)

  // ------------------------------------------------------------ pin modes
  localparam [1:0] LOADPROG = 2'd0;  // prog[pc] <= IN[7:4]; pc <= pc+1
  localparam [1:0] LOADDATA = 2'd1;  // data[pc] <= IN[7:4]; pc <= pc+1
  localparam [1:0] SETRUNPT = 2'd2;  // pc <= IN[7:4]
  localparam [1:0] RUNPROG  = 2'd3;  // execute prog[pc] with operand data[pc]

  // ---------------------------------------------------------------- state
  logic [3:0] prog[15:0];  // program storage "file"
  logic [3:0] data[15:0];  // data storage "file"
  logic [3:0] pc;          // program counter
  logic [3:0] regval;      // accumulator
  logic       lastdata3;   // IN[7] as sampled on the previous rising edge

  // ------------------------------------------------------- derived signals
  logic [1:0] instruction;
  assign instruction = io_in[3:2];

  logic [3:0] inputdata;
  assign inputdata = io_in[7:4];

  logic [3:0] progc;  // opcode at pc
  logic [3:0] datac;  // operand at pc
  assign progc = prog[pc];
  assign datac = data[pc];

  logic [3:0] npc;
  assign npc = pc + 4'd1;

  assign io_out = {regval, pc};

  integer i;

  always_ff @(posedge clock) begin
    if (!reset) begin
      // Sampled every non-reset cycle. JUMPTOIF therefore sees the value
      // IN[7] had on the PREVIOUS clock edge (one-cycle delay).
      lastdata3 <= inputdata[3];
      case (instruction)
        LOADPROG: begin
          prog[pc] <= inputdata;
          pc <= npc;
        end
        LOADDATA: begin
          data[pc] <= inputdata;
          pc <= npc;
        end
        SETRUNPT: begin
          pc <= inputdata;
        end
        RUNPROG: begin
          case (progc)
            LOAD: begin
              regval <= datac;
              pc <= npc;
            end
            STORE: begin
              data[datac] <= regval;
              pc <= npc;
            end
            ADD: begin
              regval <= regval + datac;
              pc <= npc;
            end
            SUB: begin
              regval <= regval - datac;
              pc <= npc;
            end
            MUL: begin
              regval <= regval * datac;
              pc <= npc;
            end
            SHIFTL: begin
              // shift amount is clamped to 3
              regval <= (datac < 4) ? (regval << datac) : (regval << 3);
              pc <= npc;
            end
            SHIFTR: begin
              // shift amount is clamped to 3
              regval <= (datac < 4) ? (regval >> datac) : (regval >> 3);
              pc <= npc;
            end
            JUMPTOIF: begin
              // Conditional only (no unconditional jump) and the condition
              // comes from outside the chip: this design has no flags and
              // only one register. Target is the operand data[pc].
              pc <= lastdata3 ? datac : npc;
            end
            LOGICAND: begin
              regval <= (regval != 4'd0) && (datac != 4'd0);
              pc <= npc;
            end
            LOGICOR: begin
              regval <= (regval != 4'd0) || (datac != 4'd0);
              pc <= npc;
            end
            EQUALS: begin
              regval <= (regval == datac);
              pc <= npc;
            end
            NEQ: begin
              regval <= (regval != datac);
              pc <= npc;
            end
            BITAND: begin
              regval <= regval & datac;
              pc <= npc;
            end
            BITOR: begin
              regval <= regval | datac;
              pc <= npc;
            end
            LOGICNOT: begin
              regval <= (regval == 4'd0);
              pc <= npc;
            end
            BITNOT: begin
              regval <= ~regval;
              pc <= npc;
            end
          endcase
        end
      endcase
    end else begin
      pc        <= 4'd0;
      regval    <= 4'd0;
      lastdata3 <= 1'b0;
      for (i = 0; i < 16; i = i + 1) begin
        data[i] <= 4'd0;
        prog[i] <= 4'd0;
      end
    end
  end
endmodule
