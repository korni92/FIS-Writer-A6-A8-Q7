# Audi A8 DIS (Instrument Cluster) – DDP Protocol Documentation

Reverse-engineered protocol for injecting custom text/data into the 2003–2010 Audi A8 (D3) instrument cluster (DIS/Kombi) using the Display Data Protocol (DDP).

**Tested / observed on:** Audi A8 4E (D3) with MMI 2G / 2G High and aftermarket CAN injectors.

**CAN Bus:** Cluster **500 kbps**

**CAN IDs used:**
- `0x490` → MMI / Injector → Cluster (sends data + ACKs)
- `0x491` → Cluster → MMI / Injector (sends ACKs + confirmations)

## 1. Packet Structure

Every CAN frame uses **8 bytes**:

- **Byte 0** = Protocol Header
- **Bytes 1–7** = Payload

### Byte 0 Format
High Nibble (4 bits) = Packet Type
Low  Nibble  (4 bits) = Sequence Counter (0–15)


| Type   | Name       | Description                                          | Example     |
|--------|------------|------------------------------------------------------|-------------|
| `0x10` | DATA END   | Single frame **or** last frame of multi-frame msg. Expects ACK. | `0x15`      |
| `0x20` | DATA BODY  | Intermediate frame of multi-frame message. Usually no immediate ACK. | `0x25`      |
| `0xB0` | ACK        | Acknowledgment – contains the sequence number acked   | `0xB5`      |

**Sequence Counter rules**
- Sender always increments modulo 16: next frame = (current + 1) % 16
- After receiving ACK(N) → next send must use (N+1) % 16
- After receiving DATA(N) → next send must use (N+1) % 16

### Heartbeat / Keep-Alive
Both sides must keep sending heartbeats or the channel dies after ~5 seconds silence from cluster (`0x491`).

- Ping: `A3` (sent by both sides)
- Pong: `A1 0F 8A FF 4A FF` (typical response)

## 2. Handshake & Reconnection Sequence (Critical!)

This full sequence **must** be performed after power-on, after >5s silence, or after receiving error frame (e.g. `0xA8`).

### Step-by-step Handshake

1. **Open Request**
→ MMI:   A0 0F 8A FF 4A FF
← Cluster: A1 0F 8A FF 4A FF

2. **Ping-Pong Stabilization** (~1 second)
← Cluster: A3 ...
→ MMI:     A1 0F 8A FF 4A FF
(repeat until stable)

3. **Parameter Exchange** (strictly sequential – wait for ACK after each!)

| Step | Direction | Payload (after header)         | Notes                       |
|------|-----------|--------------------------------|-----------------------------|
| 1    | → MMI     | 00 02 4D 02                    | Param 10                    |
|      | ← Cluster | 01 03 48 01 02                 | → send ACK                  |
| 2    | → MMI     | 00 02 4D 02                    | Param 11                    |
|      | ← Cluster | 01 03 48 02 02                 | → send ACK                  |
| 3    | → MMI     | 00 02 4D 01                    | Param 12                    |
|      | ← Cluster | 01 03 48 02 01                 | → send ACK                  |
| 4    | → MMI     | 02 01 48                       | Param 13                    |
|      | ← Cluster | (ACK expected)                 |                             |

4. **Final Burst from Cluster** (receive & ACK each frame)
← [2x] 03 10 48 0B 50 08 0C
← [2x] 45 30 39 00 00 01 00
← [1x] 02 01 01 10             ← last frame – send final ACK


5. **Channel is now OPEN** – ready to claim zones and write data

## 3. Important Opcodes

| Opcode | Example                          | Description                              |
|--------|----------------------------------|------------------------------------------|
| `36`   | `36 01 01`                       | Claim / Start transaction (Zone)         |
| `32`   | `32 01 02`                       | Release / Commit transaction             |
| `30`   | `30 01 02`                       | Clear entire zone                        |
| `E0`   | `E0 0D 01 00 48 65 6C ...`       | Write text (Len + Line + 00 + data)      |
| `E4`   | `E4 02 ...`                      | Menu/highlight control                   |
| `E2`   | `E2 01 01`                       | Force source (Phone=01, Media=06, ...)   |
| `3B`   | `3B ...`                         | Cluster confirmation after Release       |

### Zone IDs
- `01` → Top line (yellow/red/orange bar)
- `02` → Middle area (trip computer / menu / navigation)

### Text Line IDs (for opcode `E0`)
- `01` Top line
- `05` Middle header
- `06` Middle body 1
- `07` Middle body 2
- `08` Middle body 3
- `09` Middle footer

### Text Length Calculation
Len = 2 + number_of_characters
↑   └───────────────┘
(Line ID + 00 separator)


Example: `"Hello"` (5 chars) → `E0 07 01 00 48 65 6C 6C 6F`

## 4. Typical Transaction (Atomic Update – Top Line)

```text
1. Claim     → 36 01 01    → wait ACK
2. Write     → E0 ...      → wait ACK (multi-frame: 20 → 20 → 10)
3. Release   → 32 01 01    → wait ACK
4. Confirm   ← 3B ...      → send ACK


