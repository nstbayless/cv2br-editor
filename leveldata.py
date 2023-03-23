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

mapEntTableAddrToLabel = dict()

def writeLabelIfAddrInMap(addr, out):
    if addr in mapEntTableAddrToLabel:
        for label in mapEntTableAddrToLabel[addr]:
            out(f"{label}:")
        del mapEntTableAddrToLabel[addr]

def read_substage_data(level, substage, bank, addr, out):
    while True:
        writeLabelIfAddrInMap(addr, out)
        b = readbyte(bank, addr)
        if b == 0xFF:
            out(f"{I}ROOM")
            addr += 1
        if b == 0xFE:
            out(f"{I}ROOM_COMPRESSED")
            addr += 1
            while readbyte(bank, addr) < 0xFD:
                writeLabelIfAddrInMap(addr, out)
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
                writeLabelIfAddrInMap(addr, out)
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
                else:
                    writeti(f"; addr={rom.BANK6:X}:{addr2:04X}")
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
    
    # level layout
    write("")
    write(f"org ${rom.LEVEL_SCREEN_TABLE:04X}")
    write(f"banksk{rom.BANK6:X}")
    write("screen_layout_table:")
    for i, level in enumerate(rom.LEVELS):
        if level is None:
            addr = rom.readword(rom.BANK6, rom.LEVEL_SCREEN_TABLE + i*2)
            write(f"    dw ${addr:04X}")
        else:
            write(f"    dw Lvl{level}_ScreenLayout")
        
    
    for i, level in enumerate(rom.LEVELS):
        if level is not None:
            addr = rom.readtableword(rom.BANK6, rom.LEVEL_SCREEN_TABLE, i)
            write("")
            write(f"org ${addr:04X}")
            write(f"banksk{rom.BANK6:X}")
            write(f"Lvl{level}_ScreenLayout:")
            for sublevel in range(rom.SUBSTAGECOUNT[i]):
                write(f"    dw Lvl{level}_{sublevel}_ScreenLayout")

    for i, level in enumerate(rom.LEVELS):
        if level is not None:
            for sublevel in range(rom.SUBSTAGECOUNT[i]):
                addr = rom.readtableword(rom.BANK6, rom.LEVEL_SCREEN_TABLE, i, sublevel)
                xstart, ystart, scrolldir, layout = rom.produce_sublevel_screen_arrangement(i, sublevel)
                table_x0, table_x1, table_y0, table_y1 = rom.get_screensbuff_boundingbox(layout)
                
                write(f"")
                write(f"org ${addr:04X}")
                write(f"banksk{rom.BANK6:X}")
                write(f"Lvl{level}_{sublevel}_ScreenLayout:")
                
                write("")
                for y in range(table_y0, table_y1):
                    s = "    ;"
                    for x in range(table_x0, table_x1):
                        c = layout[x][y]
                        if c == 0:
                            s += "    "
                        else:
                            if x == xstart and y == ystart:
                                s += "["
                            else:
                                s += " "
                            s += f"{c:02X}"
                            if x == xstart and y == ystart:
                                s += "]"
                            else:
                                s += " "
                    s += ";"
                    write(s)
                write("")
                
                write(f"    db ${xstart:02X} ; x start")
                write(f"    db ${ystart:02X} ; y start")
                addr += 2
                write("")
                
                done = False
                while not done:
                    dst = readword(rom.BANK6, addr)
                    x = dst%0x10
                    y = (dst//0x10)%0x10
                    addr += 2
                    
                    stride = readbyte(rom.BANK6, addr)
                    xstride = stride % 0x10
                    if xstride >= 0x8:
                        xstride -= 0x10
                    ystride = stride // 0x10
                    if ystride >= 0x8:
                        ystride -= 0x8
                    addr += 1
                    
                    write(f"    dw ${dst:04X} ; destination x={x:X} y={y:X}")
                    write(f"    db ${stride:02X} ; stride x={xstride} y={ystride}")
                    
                    _bytes = []
                    while True:
                        header = readbyte(rom.BANK6, addr)
                        addr += 1
                        if header in [0xff, 0xfe]:
                            write(f"    db " + ", ".join(_bytes))
                        if header == 0xff:
                            write(f"    db $ff ; end of layout")
                            done = True
                            break
                        elif header == 0xfe:
                            write(f"    db $fe ; next packet")
                            write("")
                            break
                        else:
                            _bytes += [f"${header:02X}"]

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
    
    screenentdata = [""]
    screenentdata2 = [""]
    def writese(s):
        screenentdata[0] += s + "\n"
    def writese2(s):
        screenentdata2[0] += s + "\n"
    writese("")
    writese(f"org ${rom.SCREEN_ENT_TABLE:04X}")
    writese(f"banksk{rom.BANK:X}")
    writese(f"entity_table_index_by_screen:")
    for i, level in enumerate(rom.LEVELS):
        if level is None:
            level = "Plant"
        writese(f"    dw Lvl{level}_ScreenEnts")
    
    for i, level in enumerate(rom.LEVELS):
        if level is not None:
            writese("")
            writese(f"Lvl{level}_ScreenEnts:")
            for sublevel in range(rom.SUBSTAGECOUNT[i]):
                writese(f"    dw Lvl{level}_{sublevel}_ScreenEnts")
    
    prevaddr = None
    screenentaddrassoc = {}
    for i, level in enumerate(rom.LEVELS):
        if level is not None:
            for sublevel in range(rom.SUBSTAGECOUNT[i]):
                screen_ents_begin = rom.readtableword(rom.BANK3, rom.SCREEN_ENT_TABLE, i, sublevel)
                screen_ents_end = rom.get_entry_end(rom.SCREEN_ENT_TABLE, rom.BANK3, i, sublevel)
                screenc = (screen_ents_end - screen_ents_begin)//2
                writese("")
                if i == 1 and sublevel == 0:
                    writese(f"org ${screen_ents_begin:04X}")
                    writese(f"banksk{rom.BANK3:X}")
                else:
                    writese(f"; addr={rom.BANK3:X}:{screen_ents_begin:04X}")
                writese(f"Lvl{level}_{sublevel}_ScreenEnts: ; has {screenc} screen{'s' if screenc != 1 else ''}")
                for screen in range(screenc):
                    entsaddr = rom.readword(rom.BANK3, screen_ents_begin + screen*2)
                    if entsaddr in screenentaddrassoc:
                        rep = screenentaddrassoc[entsaddr]
                        writese(f"    dw Lvl{rep[0]}_{rep[1]}_{rep[2]}_ScreenEnts ; re-used!")
                        writese2(f"\n; ({rep[0]}_{rep[1]}_{rep[2]} reuses previous entry)")
                        continue
                    else:
                        screenentaddrassoc[entsaddr] = (level, sublevel, screen)
                    
                    entsmax = rom.readword(rom.BANK3, screen_ents_end) if level != "Drac3" else entsaddr + 10
                    writese(f"    dw Lvl{level}_{sublevel}_{screen}_ScreenEnts")
                    writese2(f"")
                    if entsaddr != prevaddr:
                        writese2(f"org ${entsaddr:04X}")
                        writese2(f"banksk{rom.BANK3:X}")
                    else:
                        writese2(f"; addr={rom.BANK3:X}:{entsaddr:04X}")
                    writese2(f"Lvl{level}_{sublevel}_{screen}_ScreenEnts:")
                    entcat = 0
                    catnames = ["Misc", "Enemies", "Items"]
                    for entcat in range(3):
                        entslist_begin = rom.readtableword(rom.BANK3, rom.LEVTABS_AND_NAMES[entcat][0], i, sublevel)
                        h = readbyte(rom.BANK3, entsaddr)
                        writese2("")
                        entsaddr += 1
                        if h >= 0x80:
                            writese2(f"    db $80 ; no {catnames[entcat].lower()} in any screen in this room at all")
                            continue
                        
                        writese2(f"    db ${h:02X} ; {catnames[entcat].lower()} count")
                        offset = readbyte(rom.BANK3, entsaddr)
                        entsaddr += 1
                        address = readword(rom.BANK3, entsaddr)
                        entsaddr += 2
                        strange=False
                        label = f"Lvl{level}_{sublevel}_{screen}_{catnames[entcat]}_start"
                        mapEntTableAddrToLabel[address] = mapEntTableAddrToLabel.get(address, []) + [label]
                        if entslist_begin + offset != address:
                            strange=True #print(f"strangeness. {level} {sublevel} {screen} {catnames[entcat]}: {entslist_begin:04X} + {offset:02X} != {address:04X}")
                            writese2(f"    db ${offset:02X} ; offset{' (seems incongruent with address?)' if strange else ''}")
                        else:
                            writese2(f"    db {label} - Lvl{level}_{sublevel}_{catnames[entcat]} ; offset")
                        writese2(f"    dw {label} ; address")
                    prevaddr = entsaddr
    
    for table_addr, table_name in rom.LEVTABS_AND_NAMES:
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
            stagetable_C = readword(rom.BANK3, table_addr + 2*i)
            if not level:
                write(f"    dw Plant_{table_name} ; spurious entry")
            else:
                write(f"    dw {level}_{table_name}")
                leveltables += f"\n{level}_{table_name}:\n"
                for substage in range(rom.SUBSTAGECOUNT[i]):
                    writeld("")
                    substagetable_C = readword(rom.BANK3, stagetable_C + 2*substage)
                    leveltables += f"    dw Lvl{level}_{substage}_{table_name}\n"
                    
                    writeld(f"; addr={rom.BANK3:X}:{substagetable_C:X}")
                    writeld(f"Lvl{level}_{substage}_{table_name}:")
                    writeld(f";   screen, off,  slot, entity,                  x,   y")
                    writeld(f";   note: screen needs high bit set if vertical scrolling")
                    read_substage_data(level, substage, rom.BANK3, substagetable_C, writeld)
        
        write(leveltables)
        write(leveldata[0])
    write(screenentdata[0])
    write(screenentdata2[0])
    
    if len(mapEntTableAddrToLabel) > 0:
        write("")
        write("; somehow, these didn't align to anywhere in particular..?")
        for addr in sorted(mapEntTableAddrToLabel.keys()):
            write(f"org ${addr:04X}")
            for label in mapEntTableAddrToLabel[addr]:
                write(f"{label}:")
            write("")