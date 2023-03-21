# this script reads the map entity data from ROM, writes to an assembly file.

import enum
import sys

def array_to_hx(a):
    return ", ".join(list(map(lambda x: f"${x:02X}", a)))

# bank2
LEVTAB_TILES4x4_BANK2 = 0x42a5
LEVTAB_TILES_BANK2 = 0x42C4
TILES4x4_BEGIN = 0x44c0

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
    0x0F: "ENM_PANAGUCHI_0F",
    
    0x08: "WALL_1UP",
    0x09: "ENM_RAT_09",
    
    0x0B: "WALL_MEAT",
    0x0C: "ENM_PANAGUCHI_0C",
    0x0D: "ENM_PANAGUCHI_0D",
    0x0E: "ENM_RAT_0E",
    
    0x1C: "ENM_SKELETON_1C",
    0x1E: "ENM_FORNEUS",
    0x1F: "ENM_BAT_1F",
    
    0x20: "ENM_SKELETON_20",
    0x21: "ENM_MUDMAN",
    0x22: "BOSS_TWIN_TRIDENT",
    0x24: "BG_ANIM",
    0x25: "SPAWNEYE_RIGHT",
    0x26: "SPAWNEYE_LEFT",
    
    0x33: "ENM_KNIGHT",
    0x34: "ENM_RAVEN",
    0x35: "ITM_WHIP_CHAIN",
    0x37: "ENM_WATER_CREEP",
    0x3C: "SPAWNEYE_ABOVE",
    
    0x41: "ENM_DAGGER",
    0x45: "BOSS_DARKSIDE",
    0x4E: "BGFLAME",
    
    0x53: "BOSS_ANGEL_MUMMY",
    0x5D: "ENM_BEATLE",
    
    0x60: "BOSS_IRON_DOLL",
    
    0x69: "BOSS_BONE_SERPENT",
    
    0x72: "BOSS_SOLEIL",
    0x73: "BOSS_DRACULA",
}

if len(sys.argv) < 2:
    print(f"usage: {sys.argv[0]} romfile.gb")
    sys.exit()

romfile = sys.argv[1]
    
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

def get_entry_end(table, bank, level, substage, drac3_size):
    if substage is not None:
        substage += 1
        if substage >= SUBSTAGECOUNT[level]:
            substage = 0
            level += 1
        if level >= len(SUBSTAGECOUNT):
            level = len(SUBSTAGECOUNT) - 1
            substage = SUBSTAGECOUNT[level] - 1
        else:
            drac3_size = 0
    else:
        level += 1
        if level >= len(SUBSTAGECOUNT):
            level -= 1
        else:
            drac3_size = 0
        
    addr2 = readword(bank, table + 2*level)
    if substage is not None:
        addr2 = readword(bank, addr2 + 2*substage)
    return addr2 + drac3_size
    
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
                out(f"{I}db           SLOT{slot:x}, {idname(id) + ',': <22} ${x:02x}, ${y:02x}")
                addr += 4
        if b == 0xFD:
            addr += 1
            out(f"{I}ENDROOMS")
            break
        else:
            while readbyte(bank, addr) < 0xFD:
                a = readbyte(bank, addr+0) # which screen in this room it appears at
                b = readbyte(bank, addr+1)
                slot = readbyte(bank, addr+2)
                id = readbyte(bank, addr+3)
                x = readbyte(bank, addr+4)
                y = readbyte(bank, addr+5)
                out(f"{I}db ${a:02x}, ${b:02x}, SLOT{slot:x}, {idname(id) + ',': <22} ${x:02x}, ${y:02x}")
                addr += 6

with open("leveldata.asm", "w") as f:
    def write(t):
        f.write(t)
        f.write("\n")
    
    write(f"org ${LEVTAB_TILES4x4_BANK2:04X}")
    write("banksk2")
    write("level_tile_chunks_table:")
    for i, level in enumerate(LEVELS):
        if level is None:
            write(f"    dw Plant_Tile_Chunks ; spurious entry")
        else:
            write(f"    dw {level}_Tile_Chunks")
    
    write("")
    write(f"org ${LEVTAB_TILES_BANK2:04X}")
    write("banksk2")
    write("level_tiles_table:")
    for i, level in enumerate(LEVELS):
        if level is None:
            write(f"    dw Plant_Tiles ; spurious entry")
        else:
            write(f"    dw {level}_Tiles")
            
    tiles_s = [""]
    def writeti(s):
        tiles_s[0] += s + "\n"
    First = True
    tilechunkmaxid = [0 for l in LEVELS]
    for i, level in enumerate(LEVELS):
        if level is not None:
            write("")
            addr = readword(2, LEVTAB_TILES_BANK2 + i*2)
            write(f"org ${addr:04X}")
            write(f"banksk2")
            write(f"{level}_Tiles:")
            for substage in range(SUBSTAGECOUNT[i]):
                addr2 = readword(2, addr + substage*2)
                write(f"    dw {level}_{substage}_Tiles")
                writeti("")
                if First:
                    writeti(f"org ${addr2:04X}")
                    writeti("banksk6")
                    First = False
                writeti(f"{level}_{substage}_Tiles:")
                tiles = get_entry_end(LEVTAB_TILES_BANK2, 2, i, substage, 5*20) - addr2
                assert tiles > 0
                assert tiles % 20 == 0
                for t in range(tiles//5):
                    if t % 4 == 0:
                        writeti(f"    ; screen {t//4}")
                    rowdata = [readbyte(6, addr2 + t*5 + i) for i in range(5)]
                    writeti("    db " +array_to_hx(rowdata))
                    lvi = i if level != "Drac3" else i-1
                    tilechunkmaxid[lvi] = max([tilechunkmaxid[lvi]] + rowdata)

    write("")
    write(f"org ${TILES4x4_BEGIN:04X}")
    write("banksk2")
    write(f" ds $10, $0 ; blank 4x4 tile chunk")
    
    for i, level in enumerate(LEVELS):
        if level in [None, "Drac3"]:
            continue
        addr = readword(2, LEVTAB_TILES4x4_BANK2 + 2*i)
        write("")
        #write(f"org ${addr:04X}")
        #write(f"banksk2")
        write(f"{level}_Tile_Chunks:")
        if level == "Drac2":
            write(f"Drac3_Tile_Chunks:")
            tilec = 0x6500 + 0x82 * 0x10 - addr
        else:
            #tilec = (tilechunkmaxid[i]-3) * 0x10 #
            tilec = get_entry_end(LEVTAB_TILES4x4_BANK2, 2, i, None, None) - addr
        assert tilec % 0x10 == 0
        
        for i in range(1, tilec//0x10+1):
            s = "    db"
            first = True
            for j in range(0x10):
                a = readbyte(2, addr + (i-1) * 0x10 + j)
                if first:
                    first = False
                else:
                    s += ","
                s += f" ${a:02x}"
            write(f"{s}   ; tile ${i:02X}")
        
    write(tiles_s[0])

with open("levelobjects.asm", "w") as f:
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
    # macro definitions
    for id in Entities:
        write(f"ENT_{Entities[id]+':': <20} equ ${id:02x}")
    for i in range(8):
        write(f"SLOT{i}: equ ${i:02x}")
    
    for table_addr, table_name in [(LEVTAB_A, "Misc"), (LEVTAB_B, "Enemies"), (LEVTAB_C, "Items")]:
        write("")
        write(f"""
org ${table_addr:04X}
banksk{BANK}
table_level_{table_name}:""")
        
        leveldata = [""]
        leveltables = ""
        def writeld(s):
            leveldata[0] += s + "\n"
        for i, level in enumerate(LEVELS):
            stagetable_C = readword(BANK, table_addr + 2*i)
            if not level:
                write(f"    dw Plant_{table_name} ; spurious entry")
            else:
                write(f"    dw {level}_{table_name}")
                leveltables += f"\n{level}_{table_name}:\n"
                for substage in range(SUBSTAGECOUNT[i]):
                    writeld("")
                    substagetable_C = readword(BANK, stagetable_C + 2*substage)
                    leveltables += f"    dw Lvl{level}_{substage}_{table_name}\n"
                    
                    writeld(f"Lvl{level}_{substage}_{table_name}:")
                    writeld(f";   screen,   b,  slot, entity,                  x,   y")
                    read_substage_data(level, substage, BANK, substagetable_C, writeld)
        
        write(leveltables)
        write(leveldata[0])