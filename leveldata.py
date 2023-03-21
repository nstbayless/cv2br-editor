# this script reads the map entity data from ROM, writes to an assembly file.

import enum
import sys
import rom
from rom import readword, readbyte

def array_to_hx(a):
    return ", ".join(list(map(lambda x: f"${x:02X}", a)))

if len(sys.argv) < 2:
    print(f"usage: {sys.argv[0]} romfile.gb")
    sys.exit()
    
with open(sys.argv[1], "rb") as f:
    rom.readrom(f.read())

############################################################
def idname(id):
    if id in rom.Entities:
        return "ENT_" + rom.Entities[id]
    else:
        return f"${id:02x}"
    
I = " " * 4
    
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
    write(f"org ${rom.LEVTAB_TILES4x4_BANK2:04X}")
    write(f"banksk{rom.BANK2:X}")
    write("level_tile_chunks_table:")
    for i, level in enumerate(rom.LEVELS):
        if level is None:
            write(f"    dw Plant_Tile_Chunks ; spurious entry")
        else:
            write(f"    dw {level}_Tile_Chunks")
    
    write("")
    write(f"org ${rom.LEVTAB_TILES_BANK2:04X}")
    write(f"banksk{rom.BANK2:X}")
    write("level_tiles_table:")
    for i, level in enumerate(rom.LEVELS):
        if level is None:
            write(f"    dw Plant_Tiles ; spurious entry")
        else:
            write(f"    dw {level}_Tiles")
            
    tiles_s = [""]
    def writeti(s):
        tiles_s[0] += s + "\n"
    First = True
    tilechunkmaxid = [0 for l in rom.LEVELS]
    for i, level in enumerate(rom.LEVELS):
        if level is not None:
            write("")
            addr = readword(rom.BANK2, rom.LEVTAB_TILES_BANK2 + i*2)
            write(f"org ${addr:04X}")
            write(f"banksk{rom.BANK2:X}")
            write(f"{level}_Tiles:")
            for substage in range(rom.SUBSTAGECOUNT[i]):
                addr2 = readword(rom.BANK2, addr + substage*2)
                write(f"    dw {level}_{substage}_Tiles")
                writeti("")
                if First:
                    writeti(f"org ${addr2:04X}")
                    writeti(f"banksk{rom.BANK6:X}")
                    First = False
                writeti(f"{level}_{substage}_Tiles:")
                tiles = rom.get_entry_end(rom.LEVTAB_TILES_BANK2, rom.BANK2, i, substage) - addr2
                if tiles <= 0:
                    breakpoint()
                assert tiles > 0
                assert tiles % 20 == 0
                for t in range(tiles//5):
                    if t % 4 == 0:
                        writeti(f"    ; screen {t//4}")
                    rowdata = [readbyte(rom.BANK6, addr2 + t*5 + i) for i in range(5)]
                    writeti("    db " +array_to_hx(rowdata))
                    lvi = i if level != "Drac3" else i-1
                    tilechunkmaxid[lvi] = max([tilechunkmaxid[lvi]] + rowdata)

    write("")
    write(f"org ${rom.LEVEL_TILESET_TABLE:04X}")
    write(f"banksk{rom.LEVEL_TILESET_TABLE_BANK:X}")
    write("level_tileset_table:")
    for i, level in enumerate(rom.LEVELS):
        addr = rom.readtableword(rom.LEVEL_TILESET_TABLE_BANK, rom.LEVEL_TILESET_TABLE, i)
        if level is not None:
            write(f"    dw ${addr:04X} ; {level}")
        else:
            write(f"    dw ${addr:04X}")

    write("")
    write(f"org ${rom.TILES4x4_BEGIN:04X}")
    write(f"banksk{rom.BANK2:X}")
    write(f" ds $10, $0 ; blank 4x4 tile chunk")
    
    for i, level in enumerate(rom.LEVELS):
        if level in [None, "Drac3"]:
            continue
        addr = readword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2 + 2*i)
        write("")
        #write(f"org ${addr:04X}")
        #write(f"banksk{BANK2:X}")
        write(f"{level}_Tile_Chunks:")
        if level == "Drac2":
            write(f"Drac3_Tile_Chunks:")
            tilec = 0x82 * 0x10 # this is a guess
        else:
            #tilec = (tilechunkmaxid[i]-3) * 0x10 #
            tilec = rom.get_entry_end(rom.LEVTAB_TILES4x4_BANK2, rom.BANK2, i) - addr
        assert tilec % 0x10 == 0
        
        for i in range(1, tilec//0x10+1):
            s = "    db"
            first = True
            for j in range(0x10):
                a = readbyte(rom.BANK2, addr + (i-1) * 0x10 + j)
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
    for id in rom.Entities:
        write(f"ENT_{rom.Entities[id]+':': <20} equ ${id:02x}")
    for i in range(8):
        write(f"SLOT{i}: equ ${i:02x}")
    
    for table_addr, table_name in [(rom.LEVTAB_A, "Misc"), (rom.LEVTAB_B, "Enemies"), (rom.LEVTAB_C, "Items")]:
        write("")
        write(f"""
org ${table_addr:04X}
banksk{rom.BANK:X}
table_level_{table_name}:""")
        
        leveldata = [""]
        leveltables = ""
        def writeld(s):
            leveldata[0] += s + "\n"
        for i, level in enumerate(rom.LEVELS):
            stagetable_C = readword(rom.BANK, table_addr + 2*i)
            if not level:
                write(f"    dw Plant_{table_name} ; spurious entry")
            else:
                write(f"    dw {level}_{table_name}")
                leveltables += f"\n{level}_{table_name}:\n"
                for substage in range(rom.SUBSTAGECOUNT[i]):
                    writeld("")
                    substagetable_C = readword(rom.BANK, stagetable_C + 2*substage)
                    leveltables += f"    dw Lvl{level}_{substage}_{table_name}\n"
                    
                    writeld(f"Lvl{level}_{substage}_{table_name}:")
                    writeld(f";   screen,   b,  slot, entity,                  x,   y")
                    read_substage_data(level, substage, rom.BANK, substagetable_C, writeld)
        
        write(leveltables)
        write(leveldata[0])