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
| `34`   | `34 01 AA`                       | Stop displaying content                                     |
| `36`   | `36 01 AA`                       | Claim / Start transaction (Zone)                            |
| `E0`   | `E0 DD CC LL ...`                | Write text (Len + Line + Text color + data)                 |
| `E4`   | `E4 ...`                         | Menu/highlight control                                      |
| `E2`   | `E2 01 BB`                       | Force source (Phone=01, Media=06, ...)                      |
| `3B`   | `3B 02 AA EE`                    | Cluster confirmation after Release and Status Code          |
| `09`   | `09 ...`                         | Error from Cluster                                          |
| `DC`   | `DC FF GG HH`                    | Draw Navigation Arrow (Length + Group + Data)               |
| `DE`   | `DE JJ KK.`                      | Draw Navigation Distance Bar (01 + Fill level, 00 hides)    |

- `AA` → Zone ID
- `BB` → Screen Display Option
- `CC` → Text Line ID
- `DD` → Text Length
- `EE` → Status Code
- `FF` → amount of following bytes
- `GG` → Group of Arrows
- `HH` → Arrow configuration
- `JJ` → 00 = status bar off | 01 = status bar on
- `KK` → FF - 00 full - empty
- `LL` → Text color 00 = 01 Color inversion
  
### AA Zone IDs
- `01` → Top line
- `02` → Middle area
- `03` → Nav screen

### BB Screen Display Option
- `01` → Telephone (Green)
- `02` → Radio (Red)
- `06` → Media (Red)

### CC Text Line IDs (for opcode `E0`)
- `01` Top line complete
- `02` Top line left
- `03` Top line middle
- `04` Top line right side
- `05` Middle header
- `06` Middle body 1
- `07` Middle body 2
- `08` Middle body 3
- `09` Middle body 4

### CC Navigation screen (Only for clamimed Screen Zone ID 03 wirh opcode `E0`)
- `0A` Headline (Street name)
- `0B` Top left (Distance/Turn info)
- `0C` Bottom left (Distance till Destination)
- `0D` Bottom right (Time at arrival)

### EE Status Code (for opcode `3B`)
- `00` → Back to Trip Computer
- `01` → Ready (Cluster screen is free again after showing a warning)
- `02` → Busy (Cluster is actively displaying a vehicle warning/info. Must retry 32 release later)
- `03` → Showing (Success)
- `04` → Stops showing (Success)
- `E0` → FATAL ERROR (needs Hardware Restart)

### Hardware Busy/ Error
Just giving `9X` means we need to try again after X x 10 millisecond with the same message and same seq counter.
If you get 0x09 02 03 E0, you have violated the transaction state machine (e.g., trying to write to Zone 0x03 without first sending a 32 Release for Zone 0x02). This causes a fatal crash requiring a hardware restart.

### DD Text Length Calculation
Len = 2 + number_of_characters
 ↑         └───────────────┘

Example: `"Hello"` (5 chars) → `E0 07 01 00 48 65 6C 6C 6F`

### LL Text color
Line ID 06-09:
Can be inverted between white 01 and Display Screen Option color 00

Line ID 01 - 05
Can be inverted between white 00 and red 01


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

## 6. Navigation Screen (Zone 0x03)

The Navigation screen is handled completely separately from the Media/Telephone views. It utilizes Zone 0x03 and introduces unique graphical opcodes for drawing turn arrows and distance bars.
Navigation Graphics

### Distance Bar (Opcode DE)
Draws the vertical progress bar on the right side of the screen (typically used for distance to next turn).
```text
Show Bar: DE 01 XX (Where XX ranges from 0x00 empty to 0xF9 full).
Hide Bar: DE 00
```

### Turn Arrows (Opcode DC)
Draws the graphical arrows. The structure is: DC AA BB CC CC...
```text
- AA = Length of following bytes
- BB = Arrow Group (Acts like a directory/category)
- CC = Data (Specific arrow modifier/angle. Can be multiple bytes)
```

### Known Arrow Groups (BB):
```text
- 0A: Standard turn arrows (Data 00 = Straight, 10 = 20° left, 80 = 180° U-turn left, etc.)
- 0B: Highway/Autobahn arrows (Data FF = Long straight from bottom)
- 0C: Highway Exits (Data C0 = Exit right, 40 = Exit left)
- 0D: Complex junctions / overlapping streets
- 0F: Lane merges (Data 00 = Merge right)
```

### Navigation Transaction Flows
The cluster state machine is very strict when transitioning between standard modes (Zone 02) and Nav mode (Zone 03). You must explicitly flush the active zone before claiming the other, otherwise the cluster will crash (0x09 E0).

Entering Nav Mode (From Media/Phone)
To enter Nav mode, you must first clear the middle section of the standard screen, release it, and then claim the Nav zone.
```text
1. Claim Standard   → 36 01 02       → wait ACK
2. Write Empty      → E0 02 05 00    → wait ACK (Clear headline)
3. Release Standard → 32 01 02       → wait ACK
4. Confirm Flush    ← 3B 02 02 00    → send ACK (Cluster acknowledges 02 is flushed)
5. Claim Nav        → 36 01 03       → wait ACK
6. Write Texts      → E0 ... 0A/0B/0C→ wait ACK
7. Draw Arrow       → DC ...         → wait ACK
8. Draw Bar         → DE ...         → wait ACK
9. Release Nav      → 32 01 03       → wait ACK
10. Confirm Show    ← 3B 02 03 03    → send ACK
```

### Updating Active Nav Mode
Once Zone `03` is active, you can update it just like Zone `02`.
```text
1. Claim Nav        → 36 01 03       → wait ACK
2. Write/Draw       → E0 / DC / DE   → wait ACK
3. Release Nav      → 32 01 03       → wait ACK
4. Confirm Show     ← 3B 02 03 03    → send ACK
```

### Exiting Nav Mode (Back to Media/Phone)
Just claiming Zone `02` is not enough to force the cluster to leave the Nav screen. You must send a source switch command `E2`, followed by a dummy Claim/Release of Zone `02` to force the UI to redraw.
```text
1. Force Source     → E2 01 06       → wait ACK (06 = Media, 01 = Phone)
2. Claim Standard   → 36 01 02       → wait ACK
3. Release Standard → 32 01 02       → wait ACK
4. Confirm Flush    ← 3B 02 03 00    → send ACK (Cluster acknowledges 03 is flushed)
5. Confirm Show     ← 3B 02 02 03    → send ACK (Cluster confirms 02 is now showing)
```

## 7. Phone Screen Option (E2 01 01)

Specialities of Phone screen option. It has some extra line options and signs.
In Top Line `36 01 01`, lets show an signal strenght indicator in top line with a second message for write to line 4 `E0 DD 04`. If Top line is split, the middle part is adressed with Text Line ID `03` and the right side with Text Line ID `04`

### Phone signal strenght handled for quick update

EE 80 8X

- `X` for filled signal bars 0-5

```text
1. Claim              → 36 01 01                → wait ACK
2. Write middle part  → E0 DD 03 00 ...         → wait ACK (multi-frame: 20 → 20 → 10)
3. Write right part   → E0 DD 04 00 EE 80 8X    → wait ACK 
4. Release            → 32 01 02                → wait ACK
5. Confirm            ← 3B 02 03 03             → send ACK
```

Signal strengh is handled like all other, it can be updated indivdually. 

## 9. Giving screen back to cluster (stop displaying)
If Trip Computer should be displayed again, the Opcode `34` is used for this. I have just seen it in combination with middle part (34 01 02) and after stopping navigation (34 01 03), so the Nav screen cant be reaced when not active. 
The cluster will confirm this with Opcode `3B` with matching zone ID and Status `04` at the end. (3B 02 AA EE).
It's important to keep Heartbeat / Keep-Alive active, so the screen can always be reclaimed. 

## GOOD TO KNOW:

### After using split Top Line
When split Top line (line ID `03` `04` was used and it should be used the whole top line (line ID `01`), the MMI sends claim `36 01 01`, sends empty data for line IDs `03` `04`, releases and after getting confirm `3B`, it claims top line `36 01 01` again and sends data to line ID `01`
Opposite when using split top line, `01` needs to be cleared.
If the previous content is not cleared, when switching, it shows old content underneath the new.

```text
1. Claim              → 36 01 01                → wait ACK
2. Clear Line ID 03   → E0 02 03 00             → wait ACK
3. Clear Line ID 04   → E0 02 04 00             → wait ACK
4. Release            → 32 01 01                → wait ACK
5. Confirm            ← 3B 02 03 03             → send ACK
6. Claim              → 36 01 01                → wait ACK
7. Writes Line ID 01  → E0 DD 01 00 ...         → wait ACK (multi-frame: 20 → 20 → 10)
8. Release            → 32 01 01                → wait ACK
9. Confirm            ← 3B 02 01 03             → send ACK
```
### Special letters

Are treated as letters. Here are the HEX data to send to show the special ones, Audi an own format
| Sign         | Hex Data      | Describtion             |
|--------------|---------------|-------------------------|
| `!`          | EE 80 21      |                         |
| `"`          | EE 80 22      |                         |
| `#`          | EE 80 23      |                         |
| `$`          | EE 80 24      |                         |
| `%`          | EE 80 25      |                         |
| `&`          | EE 80 26      |                         |
| `(`          | EE 80 28      |                         |
| `0`          | EE 80 30      |                         |
| `1`          | EE 80 31      |                         |
| `2`          | EE 80 32      |                         |
| `3`          | EE 80 33      |                         |
| `4`          | EE 80 34      |                         |
| `5`          | EE 80 35      |                         |
| `6`          | EE 80 36      |                         |
| `7`          | EE 80 37      |                         |
| `8`          | EE 80 38      |                         |
| `9`          | EE 80 39      |                         |
| `:`          | EE 80 3A      |                         |
| `;`          | EE 80 3B      |                         |
| `<`          | EE 80 3C      |                         |
| `=`          | EE 80 3D      |                         |
| `>`          | EE 80 3E      |                         |
| `?`          | EE 80 3F      |                         |
| `@`          | EE 80 40      |                         |
| `A`          | EE 80 40 - 5A | Big letters A to Z      |
| `[`          | EE 80 5B      |                         |
| `\`          | EE 80 5C      |                         |
| `]`          | EE 80 5D      |                         |
| `^`          | EE 80 5E      |                         |
| `_`          | EE 80 5F      |                         |
| `            | EE 80 60      |                         |
| `a`          | EE 80 61 - 7A | Small letters a to z    |
| `{`          | EE 80 7B      |                         |
| straight bar | EE 80 7C      |                         |
| `}`          | EE 80 7D      |                         |
| `~`          | EE 80 7E      |                         |
| `Signal 0/5` | EE 80 80      |                         |
| `Signal 1/5` | EE 80 81      |                         |
| `Signal 2/5` | EE 80 82      |                         |
| `Signal 3/5` | EE 80 83      |                         |
| `Signal 4/5` | EE 80 84      |                         |
| `Signal 5/5` | EE 80 85      |                         |
| Phone Pickup | EE 80 88      |                         |
| `...`        | EE 80 89      |                         |
|Antenna symbl | EE 80 9A      |                         |
|Speaker crossed| EE 80 9B      |                         |
| `→`          | EE 80 9C      |                         |
| Time AM Logo | EE 80 9D      |                         |
| Time PM Logo | EE 80 9E      |                         |
| Speaker      | EE 80 9F      |                         |
| Play logo    | EE 80 A0      |                         |
| TP logo      | EE 80 A1      |                         |
| TMC logo     | EE 80 A2      |                         |
|Speaker corssed| EE 80 A3      |                         |
| Factory symbol| EE 80 A4      |                         |
| House symbol | EE 80 A5      |                         |
| Phone symbol | EE 80 A6      |                         |
| Mobil symbol | EE 80 A7      |                         |
| Fax symbol   | EE 80 A8      |                         |
| Pager symbol | EE 80 A9      |                         |
| Car symbol   | EE 80 AA      |                         |
| thick `?`    | EE 80 AB      |                         |
| Simc. symbol | EE 80 AC      |                         |
| `▼`          | EE 80 AD      |                         |
| `►`          | EE 80 AE      |                         |
| Folder symbol| EE 80 AF      |                         |
| Big Space    | EE 80 BE      |                         |

