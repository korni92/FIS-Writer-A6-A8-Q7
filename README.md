# Audi A8 DIS (Instrument Cluster)

**Tested / observed on:** Audi A8 4E (D3) with MMI 2G / 2G High with PeakCan. Code is for PeakCan

<img width="997" height="771" alt="cluster" src="https://github.com/user-attachments/assets/94657e35-08e7-4df5-9fb7-f312ba62fa5d" />

**CAN Bus:** Cluster **500 kbps**

**CAN IDs used:**
- `0x490` → MMI / Injector → Cluster (sends data + ACKs)
- `0x491` → Cluster → MMI / Injector (sends ACKs + confirmations)

## 1. Packet Structure

Every CAN frame uses **8 bytes**:

- **Byte 0** = Protocol Header 
- **Bytes 1–7** = Payload
Only Open Request, Heartbeat / Keep-Alive and Ping-Pong doesn't have this specific Byte 0 Protocol Header
In the further documentation the Byte 0 is not added to the paiload for easier writing. 

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

| Step | Direction | Payload (after header)         | Notes                                                |
|------|-----------|--------------------------------|------------------------------------------------------|
| 1    | → MMI     | 00 02 4D 02                    | Param Request 1 (Seq 0)                              |
|      | ← Cluster | BX                             | ACK from Cluster (Seq 1)                             |
|      | ← Cluster | 01 03 48 02 02                 | Param Response (Seq 0)                               |
|      | → MMI     | BX                             | ACK from MMI (Seq 1)                                 |
| Delay| ← Cluster | A3                             | Cluster pauses to process. Keep responding to PINGs! |
| Delay| → MMI     | A1 0F 8A FF 4A FF              | send PONG                                            |
| 2    | → MMI     | 00 02 4D 02                    | Param Request 2 (Seq 1)                              |
|      | ← Cluster | BX                             | ACK from Cluster (Seq 2)                             |
|      | ← Cluster | 01 03 48 02 02                 | Param Response (Seq 1)                               |
|      | → MMI     | BX                             | ACK from MMI (Seq 2)                                 |
| 3    | → MMI     | 00 02 4D 01                    | Param Request 3 (Seq 2)                              |
|      | ← Cluster | BX                             | ACK from Cluster (Seq 3)                             |
|      | ← Cluster | 01 03 48 02 01                 | Param Response (Seq 2)                               |
|      | → MMI     | BX                             | ACK from MMI (Seq 3)                                 |
| 4    | → MMI     | 02 01 48                       | Param Request 4 (Seq 3)                              |
|      | ← Cluster | BX                             | ACK from Cluster (Seq 4)                             |
|      | ← Cluster | 03 10 48 0B 50 08 0C           | Final Burst: BODY Frame 1 (Seq 3)                    |
|      | ← Cluster | 45 30 39 00 00 01 00           | Final Burst: BODY Frame 2 (Seq 4)                    |
|      | ← Cluster | 02 01 01 10                    | Final Burst: END Frame (Seq 5)                       | 
|      | → MMI     | BX                             | Final ACK from MMI (Seq 6)                           |
| 6    | → Cluster | A3                             | Channel Open PING                                    |
|      | → MMI     | A1 0F 8A FF 4A FF              | Channel Open PONG                                    |

Now needing to claim the desired screens

| Step | Direction | Payload (after header)         | Notes                                                |
|------|-----------|--------------------------------|------------------------------------------------------|
| 7    | → MMI     | 30 01 01                       | Claim Area 1 (Seq 4)                                 |
|      | ← Cluster | BX                             | ACK from Cluster (Seq 5)                             |
|      | ← Cluster | 31 03 01 01 04                 | Param Response (Seq 6)                               |
|      | → MMI     | BX                             | ACK from MMI (Seq 7)                                 |
|      | → MMI     | 30 01 02                       | Claim Area 2 (Seq 5)                                 |
|      | ← Cluster | BX                             | ACK from Cluster (Seq 6)                             |
|      | ← Cluster | 31 03 02 01 04                 | Param Response (Seq 7)                               |
|      | → MMI     | BX                             | ACK from MMI (Seq 8)                                 |
|      | → MMI     | 30 01 03                       | Claim Area 3 (Seq 6)                                 |
|      | ← Cluster | BX                             | ACK from Cluster (Seq 7)                             |
|      | ← Cluster | 31 03 03 01 04                 | Param Response (Seq 8)                               |
|      | → MMI     | BX                             | ACK from MMI (Seq 9)                                 |

* BX: the X is for the sequenz number
  
8. **Channel is now OPEN** – ready to write data

## 3. Messages
Claim Area:
36 01 01 -> Top Line of the cluster (where Radio Station is displayed)
36 01 02 -> To write to the middle section
to clear an entire area write 30 instead of 36

Write Data:
`E0 AA BB 00 XX XX XX
XX XX XX XX XX XX XX`

`E0: command to write
AA: 02 + lenght for the Text to show
BB: Line to write to
XX: Data in ASCII`

Text can also be nested, instead of writing each line indiviually. But each line needs to prepared in the way described above. 
Usually it looks like this when the whole content is replaced:

| Dir     | Message                          | Description                              |
|---------|----------------------------------|------------------------------------------|
|→ MMI    | `36 01 01`                       | Claim top line                           |
|← Cluster| `ACK`                            | ACK                                      |
|→ MMI    | `E0 AA BB 00 XX XX XX`           | write top line                           |
|← Cluster| `ACK`                            | ACK                                      |
|→ MMI    | `36 01 02`                       | Clear entire zone                        |
|← Cluster| `ACK`                            | ACK                                      |
|→ MMI    | `E0 AA 05 00 XX XX XX`           | Middle header                            |
|← Cluster| `ACK`                            | ACK                                      |
|→ MMI    | `E0 AA 06 00 XX XX XX`           | Middle body 1                            |
|← Cluster| `ACK`                            | ACK                                      |
|→ MMI    | `E0 AA 07 00 XX XX XX`           | Middle body 2                            |
|← Cluster| `ACK`                            | ACK                                      |
|→ MMI    | `E0 AA 08 00 XX XX XX`           | Middle body 3                            |
|← Cluster| `ACK`                            | ACK                                      |
|→ MMI    | `E0 AA 09 00 XX XX XX`           | Middle body 4                            |
|← Cluster| `ACK`                            | ACK                                      |
|→ MMI    | `E4 02 01 02`                    | Menu/highlight control (when needed)     |
|← Cluster| `ACK`                            | ACK                                      |
|→ MMI    | `32 01 02`                       | commit to top line                       |
|← Cluster| `ACK`                            | ACK                                      |
|← Cluster| `3B 02 02 03`                    | cluster confirms that it shows middle    |
|→ MMI    | `ACK`                            | ACK                                      |
|→ MMI    | `32 01 01.`                      | comit to middle part                     |
|← Cluster| `ACK`                            | ACK                                      |
|← Cluster| `3B 02 01 03`                    | cluster confirms that it shows top line  |
|→ MMI    | `ACK`                            | ACK                                      |


## 4. Important Opcodes

| Opcode | Example                          | Description                                                 |
|--------|----------------------------------|-------------------------------------------------------------|
| `30`   | `30 01 AA`                       | Initialize / Subscribe to Zone                              |
| `31`   | `31 03 AA 01 04`                 | Answere to claim                                            |
| `32`   | `32 01 AA`                       | Release / Commit transaction                                |
| `34`   | `34 01 AA`                       | unknown, might something to display, gets responded with 3B |
| `36`   | `36 01 AA`                       | Claim / Start transaction (Zone)                            |
| `E0`   | `E0 DD CC 00 ...`                | Write text (Len + Line + 00 + data)                         |
| `E4`   | `E4 ...`                         | Menu/highlight control                                      |
| `E2`   | `E2 01 BB`                       | Force source (Phone=01, Media=06, ...)                      |
| `3B`   | `3B 02 AA EE`                    | Cluster confirmation after Release and Status Code          |
| `09`   | `09 ...`                         | Error from Cluster                                          |

- `AA` → Zone ID
- `BB` → Screen Display Option
- `CC` → Text Line ID
- `DD` → Text Length
- `EE` Status Code
  
### Zone IDs
- `01` → Top line
- `02` → Middle area
- `03` → Nav screen

### Screen Display Option
- `01` → Telephone
- `06` → Media

### Text Line IDs (for opcode `E0`)
- `01` Top line
- `05` Middle header
- `06` Middle body 1
- `07` Middle body 2
- `08` Middle body 3
- `09` Middle body 4

### Status Code (for opcode `3B`)
- `00` Error
- `03` Showing

### Text Length Calculation
Len = 2 + number_of_characters
↑   └───────────────┘
(Line ID + 00 separator)


Example: `"Hello"` (5 chars) → `E0 07 01 00 48 65 6C 6C 6F`

### Indicator/Highlight (for opcode `E4`)
E4 AA BB CC
- `AA` Line 1-4 (00 for no line, 01 for line at 06, 02 for line at 07, ...)
- `BB` Arrow control (00 no arrow, 01 arrow up, 02 arrow down, 03 arrow up and down)
- `CC` unknown

## 5. Typical Transaction 

Just Top Line
```text
1. Claim     → 36 01 01    → wait ACK
2. Write     → E0 ...      → wait ACK (multi-frame: 20 → 20 → 10)
3. Release   → 32 01 01    → wait ACK
4. Confirm   ← 3B ...      → send ACK
````

Nested Update whole screen
```text
1. Claim     → 36 01 01    → wait ACK
2. Write     → E0 ...      → wait ACK (multi-frame: 20 → 20 → 10)
3. Claim     → 36 01 02    → wait ACK
4. Write     → E0 ...      → wait ACK (multi-frame: 20 → 20 → 10)
5. Indicator → E4 ...      → wait ACK
6. Release   → 32 01 02    → wait ACK
7. Confirm   ← 3B 02 02 03 → send ACK
8. Release   → 32 01 01    → wait ACK
9. Confirm   ← 3B 02 01 03 → send ACK
````

It's also possible to just replace one line or more in the middle part by sending `Write E0` for the wanted line and `Release` if you don't switch the screen between radio, telephone or gave it to the cluster before. This works as long as just the middle part content is update, when top part needs an update, for the next middle part write, it needs to be claimed again with `36`.
For example: The middle area was already claimed for the mode and the lines 05 - 09 need to be updated, just sending the lines that should be updated and release it.

Updating line or lines on the active middle part
```text
1. Write     → E0 ...      → wait ACK (multi-frame: 20 → 20 → 10)
2. Release   → 32 01 02    → wait ACK
3. Confirm   ← 3B 02 02 03 → send ACK
````

Updating just Indicator/Highlight
```text
1. Indicator → E4 ...      → wait ACK
2. Release   → 32 01 02    → wait ACK
3. Confirm   ← 3B 02 02 03 → send ACK
```
Just updating the `Indicator/Highlight` is possible, by sending the Opcode `E4` with needed configuration and after ACK from cluster, just send write command `32 01 02` and this will be confirmed by the cluster. 

If a line needs to be cleared, just send empty Data for it, otherwise the content stays there
till it's overwritten. 
