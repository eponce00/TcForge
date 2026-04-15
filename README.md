# TwinCAT State Machine Library

A structured approach to implementing industrial automation sequences in TwinCAT PLC using state-based control with integrated safety permissions and HMI interface.

## What It Is

This library provides a framework for building robust automation sequences that follow a clear state machine pattern. Instead of writing complex ladder logic or unstructured code, you define your machine's behavior through distinct states (Homing, Running, Stopping, etc.) and individual steps within each state.

The system handles common industrial automation needs like safety interlocks, operator permissions, fault recovery, and step-by-step sequence execution with timeouts.

## How It Works

The library centers around three main concepts:

**State Machine Controller** (`FB_StateMachine`) - Manages overall machine states and transitions. It knows when your machine should be homing, running, stopping, or handling faults, and ensures proper state transitions based on commands and conditions.

**Sequence Steps** (`FB_SequenceStep`) - Each state contains a series of numbered steps that execute in order. Each step can have its own timeout, safety permissions, and fault handling. Steps use even numbers (1000, 1002) for normal execution and odd numbers (1001, 1003) for fault conditions.

**Permission System** (`FB_Permissives`) - Validates safety conditions and interlocks before allowing operations. Supports bypass functionality for maintenance and troubleshooting while maintaining safety integrity.

## Implementation Example

The included code example demonstrates a typical implementation with four main states:

- **Homing** (steps 1000-1999) - Machine initialization and reference positioning
- **Running** (steps 2000-2999) - Normal production operation
- **Stopping** (steps 3000-3999) - Controlled shutdown sequence  
- **Aborting** (steps 4000-4999) - Emergency stop and safe state

Each state has its own program (PRG_Homing, PRG_Running, etc.) that manages the step sequence for that particular operation. The main program coordinates between states and handles the overall state transitions.

## Repository Layout

The active TwinCAT source now lives under a single cleaned host project:

- `TwinCAT/Core.sln` - unified solution entry point
- `TwinCAT/Core.tsproj` - shared TwinCAT project configuration
- `TwinCAT/CoreExample` - example PLC application
- `TwinCAT/Core` - library PLC source used to build the reusable state machine library

This keeps the example PLC and the library PLC in one TwinCAT project instead of maintaining separate solutions or duplicate folder trees.

## Key Benefits

- **Predictable Behavior** - Clear state definitions eliminate unexpected machine behavior
- **Maintainable Code** - Structured approach makes troubleshooting and modifications easier
- **Safety Integration** - Built-in permission checking ensures safe operation
- **Operator Interface** - Ready-made HMI structures for complete operator control
- **Fault Recovery** - Automatic fault detection with retry capabilities

## Getting Started

1. Open `TwinCAT/Core.sln` in TwinCAT XAE
2. Use `CoreExample` as the reference example for how the library is consumed
3. Use `Core` as the source PLC for the reusable library objects
4. Build the unified solution and adapt the example state programs to your machine
5. Configure safety permissions and HMI interface for your application

This library transforms complex automation sequences into manageable, structured code that's easier to develop, debug, and maintain.
