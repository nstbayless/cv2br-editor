# this script reads the map entity data from ROM, writes to an assembly file.

import enum
import sys

BANK = 3
LEVTAB_A = 0x5242 # goes to D240
LEVTAB_B = 0x58AC # goes to D440
LEVTAB_C = 0x5D25 # goes to D640


LEVELS = [None, "Plant", "Crystal", "Cloud", "Rock", "Drac1", "Drac2", "Drac3"]
SUBSTAGECOUNT = [0, 6, 5, 5, 6, 5, 5, 1]
Entities = {
    0x00: "NONE",
    0x01: "ITM_CROSSAXE",
    0x02: "ITM_HOLYWATER",
    0x03: "ITM_COIN",
    0x04: "ITM_WHIP_FIRE",
    0x05: "ITM_HEARTSMALL",
    0x06: "ITM_HEARTBIG",
    
    0x08: "WALL_1UP",
    0x09: "ENM_RAT_09",
    
    0x0B: "WALL_MEAT",
    0x0C: "ENM_PANAGUCHI_0C",
    0x0D: "ENM_PANAGUCHI_0D",
    0x0E: "ENM_RAT_0E",
    
    0x1F: "ENM_BAT_1F",
    0x1F: "ENM_BAT_1F",
    
    0x22: "BOSS_22",
    
    0x25: "SPAWNEYE_RIGHT",
    0x26: "SPAWNEYE_LEFT",
    
    0x34: "ENM_RAVEN",
    0x35: "ITM_WHIP_CHAIN",
    
    0x3C: "SPAWNEYE_ABOVE",
    
    0x41: "ENM_DAGGER",
    
    0x45: "BOSS_55",
    
    0x4E: "BGFLAME",
    
    0x53: "BOSS_ANGEL_MUMMY",
    
    0x60: "BOSS_60",
    
    0x69: "BOSS_BONE_SERPENT",
    
    0x72: "BOSS_SOLEIL",
    0x73: "BOSS_DRACULA",
}

if len(sys.argv) < 3:
    print(f"usage: {sys.argv[0]} romfile out.asm")
    print(f"  e.g.: {sys.argv[0]} base-us.gb out.asm")
    sys.exit()

romfile = sys.argv[1]
outfile = sys.argv[2]
    
with open(romfile, "rb") as f:
    data = f.read()

if not data or len(data) <= 100:
    print(f"romfile {romfile} invalid?")
    sys.exit(1)
else:
    print(f"romfile has 0x{len(data):02x} bytes")

############################################################

def romaddr(bank, addr):
    return bank * 0x4000 + addr % 0x4000
    
def readbyte(bank, addr):
    return data[romaddr(bank, addr)]
    
def readword(bank, addr):
    return readbyte(bank, addr) + 0x100 * readbyte(bank, addr+1)

def idname(id):
    if id in Entities:
        return "ENT_" + Entities[id]
    else:
        return f"${id:02x}"

I = "    "

def read_substage_data(level, substage, bank, addr, out):
    while True:
        b = readbyte(bank, addr)
        if b == 0xFF:
            out(f"{I}ROOM")
            addr += 1
        if b == 0xFE:
            out(f"{I}ROOM_COMPRESSED")
            addr += 1
            while readbyte(bank, addr) < 0xFD:
                slot = readbyte(bank, addr)
                id = readbyte(bank, addr+1)
                x = readbyte(bank, addr+2)
                y = readbyte(bank, addr+3)
                out(f"{I}db           SLOT{slot:x}, {idname(id) + ',': <20} ${x:02x}, ${y:02x}")
                addr += 4
        if b == 0xFD:
            addr += 1
            out(f"{I}ENDROOMS")
            break
        else:
            while readbyte(bank, addr) < 0xFD:
                a = readbyte(bank, addr+0)
                b = readbyte(bank, addr+1)
                slot = readbyte(bank, addr+2)
                id = readbyte(bank, addr+3)
                x = readbyte(bank, addr+4)
                y = readbyte(bank, addr+5)
                out(f"{I}db ${a:02x}, ${b:02x}, SLOT{slot:x}, {idname(id) + ',': <20} ${x:02x}, ${y:02x}")
                addr += 6


with open(outfile, "w") as f:
    def write(t):
        f.write(t)
        f.write("\n")
    write("""; level data
ROOM: macro
    db $FF
endm
ROOM_COMPRESSED: macro
    db $FE
endm
ENDROOMS: macro
    db $FD
endm
""")
    for id in Entities:
        write(f"ENT_{Entities[id]+':': <20} equ ${id:02x}")
    write("")
    for i in range(4):
        write(f"SLOT{i}: equ ${i:02x}")
    for i, level in enumerate(LEVELS):
        if level:
            print(f"Decoding {level}")
            stagetable_C = readword(BANK, LEVTAB_C + 2*i)
            print(f"{level} entity table C: {stagetable_C:02x}")
            for substage in range(SUBSTAGECOUNT[i]):
                write("")
                substagetable_C = readword(BANK, stagetable_C + 2*substage)
                substagetable_C_Next = readword(BANK, stagetable_C + 2*substage + 2)
                print(f"{level}-{substage} entity table C: {substagetable_C:02x}")
                write(f"org ${substagetable_C:04x}")
                write(f"banksk{BANK}")
                write(f"Lvl{level}_{substage}_Items:")
                read_substage_data(level, substage, BANK, substagetable_C, write)
                