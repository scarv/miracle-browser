
# Registers Experiment

## Purpose

To identify if there are registers in the memory hierarchy which 
might only be updated in-frequently, or on a per-request basis.
This might lead to un-expected hamming distance leakages.

**Method:**

- Create an array of 32-bit values in a part of the memory space
  *not accessed by instructions*.
  - This is essential. As instructions are constantly being fetched and
    will destroy the effect we are looking for.
  - Ideally, we should be accessing entirely separate devices.
  - For the target platforms used here, we can run instructions out of
    flash memory, and data out of the SRAM.
- The 0'th word of the array is kept constant and is the "key".
- The remaining words of the array are randomised with each trace.
- In each trace:
  - Clear two registers, `A` and `B`.
  - First, load a randomised word into register `A`.
  - Execute some `NOP`s as a barrier.
  - Next, load the "key" into register `B`.
  - Load another, different randomised word into register B.
    - This is to prevent hamming distance leakage occuring between traces.
  - Clear the `A` and `B` registers ready for the next trace.
  - `A` and `B` *must* be different registers.

**Expectation:**

- Given that the "key" is never used to overwrite the known random data in
  a CPU register, we should never see hamming distance leakage between the
  two. Unless...
- There is a register in the memory hierarchy which is only updated when
  a load is performed to that *device*, even if the *address* is different.
- If such a register exists, we should see *hamming distance* leakage, using
  the distance between the key and random value as our estimate.
- Distinguishing between hamming weight and distance will be a matter of
  plotting simple CPA style attacks over one another to check if the
  corrolation peaks appear in the same places.
