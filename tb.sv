`default_nettype none
`timescale 1ns / 1ps

// Thin wrapper around the CPU. All stimulus and checking lives in test.py
// (cocotb); this file only exposes convenient signals and dumps a VCD for
// GTKWave. Do NOT add a clock generator or stimulus here, cocotb drives
// `clock`, `reset`, `instruction` and `data`.
module tb ();
  logic       clock;
  logic       reset;
  logic [1:0] instruction;
  logic [3:0] data;

  initial begin
    clock       = 1'b0;
    reset       = 1'b1;
    instruction = 2'd0;
    data        = 4'd0;
  end

  initial begin
    $dumpfile("tb.vcd");
    $dumpvars(0, tb);
    #1;
  end

  wire [7:0] inputs = {data, instruction, reset, clock};
  wire [7:0] outputs;
  wire [3:0] pc = outputs[3:0];
  wire [3:0] regval = outputs[7:4];

  noahgaertner_cpu cpu_dut (
      .io_in (inputs),
      .io_out(outputs)
  );
endmodule
