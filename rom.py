import sys

def romaddr(bank, addr):
    return bank * 0x4000 + addr % 0x4000
    
def readbyte(bank, addr):
    return data[romaddr(bank, addr)]
    
def readword(bank, addr, littleEndian=True):
    if littleEndian:
        return readbyte(bank, addr) + 0x100 * readbyte(bank, addr+1)
    else:
        return readbyte(bank, addr+1) + 0x100 * readbyte(bank, addr)

def readtableword(bank, addr, arg0, *args):
    for i in [arg0] + list(args):
        addr = readword(bank, addr + 2*i)
    return addr
    
def readtablebyte(bank, addr, arg0, *args):
    args = [arg0] + list(args)
    if len(args) > 1:
        addr = readtableword(bank, addr, *args[:-1])
    return readbyte(bank, addr + args[-1])

# returns startx, starty, scrolldir, then a 16x16 array of screen bytes
def produce_sublevel_screen_arrangement(level, sublevel):
    scrolldir = readtablebyte(BANK2, LEVEL_SCROLLDIR_TABLE, level, sublevel)
    screenbuffaddr = readtableword(BANK6, LEVEL_SCREEN_TABLE, level, sublevel)
    startx = readbyte(BANK6, screenbuffaddr)
    starty = readbyte(BANK6, screenbuffaddr+1)
    screenbuffaddr += 2
    buff = [[0 for j in range(16)] for i in range(16)]
    while True:
        dst = readword(BANK6, screenbuffaddr)
        # very wasteful! This byte is always 0xDD!
        assert (dst >> 8) == 0xDD
        x=dst%0x10
        y=(dst//0x10)%0x10
        screenbuffaddr += 2
        stride = readbyte(BANK6, screenbuffaddr)
        xstride = stride % 0x10
        if xstride >= 0x8:
            xstride -= 0x10
        ystride = stride // 0x10
        if ystride >= 0x8:
            ystride -= 0x8
        screenbuffaddr += 1
        while True:
            header = readbyte(BANK6, screenbuffaddr)
            screenbuffaddr += 1
            if header == 0xff:
                return startx, starty, scrolldir, buff
            elif header == 0xfe:
                break
            x %= 0x10
            y %= 0x10
            buff[x][y] = header
            x += xstride
            y += ystride

def get_screensbuff_boundingbox(arr):
    # this function implemented by ChatGPT
    min_row = len(arr)
    min_col = len(arr[0])
    max_row = -1
    max_col = -1
    for i in range(len(arr)):
        for j in range(len(arr[i])):
            if arr[i][j] != 0:
                if i < min_row:
                    min_row = i
                if j < min_col:
                    min_col = j
                if i > max_row:
                    max_row = i
                if j > max_col:
                    max_col = j
    return min_row, max_row+1, min_col, max_col+1,

# returns [(entcount, offset, entstart) for each category]
# To be honest, I'm not really sure what the offset field is for, but it's in the ROM,
# and it's often equal to entstart minus (base of entity list for sublevel-entcat)
def read_ent_slices(bank, addr):
    retv = []
    for i in range(3):
        header = readbyte(bank, addr)
        addr += 1
        if header >= 0x80:
            retv.append((0, None, None))
        else:
            offset = readbyte(bank, addr)
            addr += 1
            entstart = readword(bank, addr)
            addr += 2
            retv.append((header, offset, entstart))
    return retv

# this is a bit involved, as the game isn't laid out in a way that makes
# random access like this easy.
# We need to floodfill a bit.
# We consider a "room" to be a consecutive intra-scrolling sequence of screens.
def get_entities_in_screens(level, sublevel):
    maxsid = (get_entry_end(BANK3, SCREEN_ENT_TABLE, level, sublevel) - readtableword(BANK3, SCREEN_ENT_TABLE, level, sublevel)) // 2
    sublevelentstartbycat = [readtableword(BANK3, LEVTABS_AND_NAMES[i][0], level, sublevel) for i in range(3)]
    startx, starty, scrolldir, screens = produce_sublevel_screen_arrangement(level, sublevel)
    entstable = [[None for j in range(16)] for i in range(16)]
    for x in range(16):
        for y in range(16):
            s = screens[x][y]
            if s != 0 and entstable[x][y] is None:
                sid = s & 0xf
                stype = s >> 4
                
                # A is left/top of a long room
                # B is a non-scrolling room
                # 9 is right/bottom of long room
                if stype not in [0xA, 0xB, 0x9]:
                    continue
                
                flooddir = {0xA: 1, 0xB: 0, 0x9: -1}[stype]
                flooddirx = 0 if scrolldir == 1 else flooddir
                flooddiry = 0 if scrolldir == 0 else flooddir
                endflood = {0xA: 0x9, 0xB: 0xB, 0x9: 0xA}[stype]
                entsize = {0xA: 6, 0xB: 4, 0x9: 6}[stype]
                
                if sid >= maxsid:
                    continue
                
                
                # find start of 'room' in entity table for each entcat
                entslices = read_ent_slices(BANK3, readtableword(BANK3, SCREEN_ENT_TABLE, level, sublevel, sid))
                entroomstart = []
                entroomend = []
                
                #if level == 2 and sublevel == 2 and sid == 4:
                #    breakpoint()
                
                for i, slice in enumerate(entslices):
                    start = slice[2]
                    if start is None:
                        entroomstart.append(None)
                        entroomend.append(None)
                    elif stype == 0xB:
                        end = start + slice[0] * entsize
                        entroomstart.append(start)
                        entroomend.append(end)
                    else:
                        end = start
                        # find start
                        while True:
                            if start-1 == sublevelentstartbycat[i] or readbyte(BANK3, start-1) >= 0x80:
                                entroomstart.append(start)
                                break
                            else:
                                start -= entsize
                        # find end
                        while True:
                            b = readbyte(BANK3, end)
                            if b >= 0xF0:
                                entroomend.append(end)
                                break
                            else:
                                end += entsize
                  
                # begin floodfill across screens in this room  
                _x = x
                _y = y
                while True:
                    ents = []
                    for start, end in zip(entroomstart, entroomend):
                        ents.append([])
                        if start is None or end is None:
                            continue
                        # get ents in this cat(egory) on this screen by looking between start and end
                        for e in range(start, end, entsize):
                            if entsize == 4:
                                slot = readbyte(BANK3, e)
                                type = readbyte(BANK3, e+1)
                                ex = readbyte(BANK3, e+2)
                                ey = readbyte(BANK3, e+3)
                                ents[-1].append({
                                    "x":ex,
                                    "y":ey,
                                    "slot":slot,
                                    "type":type,
                                    
                                    # in non-scrolling rooms, entities don't need a scroll margin
                                    "margin":None
                                })
                            else:
                                scroll = readword(BANK3, e, False)
                                slot = readbyte(BANK3, e+2)
                                type = readbyte(BANK3, e+3)
                                ex = readbyte(BANK3, e+4)
                                ey = readbyte(BANK3, e+5)
                                if scrolldir == 0:
                                    # horizontal
                                    escreen = ((scroll >> 8) & 0x7f) + (ex + (scroll & 0xff)) // 0xa0
                                    if escreen != _x:
                                        continue
                                    epos = (ex + (scroll & 0xff)) % 0xa0
                                    ents[-1].append({
                                        "x":epos,
                                        "y":ey,
                                        "screen-x": escreen,
                                        "screen-y": y,
                                        "slot":slot,
                                        "type":type,
                                        "margin-x": ex,
                                    })
                                else:
                                    # vertical
                                    escreen = ((scroll >> 8) & 0x7f) + (ey + (scroll & 0xff)) // 0x80
                                    if escreen != _y:
                                        continue
                                    epos = (ey + (scroll & 0xff)) % 0x80
                                    ents[-1].append({
                                        "x":ex,
                                        "y":epos,
                                        "screen-x": x,
                                        "screen-y": escreen,
                                        "slot":slot,
                                        "type":type,
                                        "margin-y": ey,
                                    })
                    entstable[_x][_y] = ents
                                    
                    if screens[_x][_y] >> 4 == endflood:
                        break
                    else:
                        _x += flooddirx
                        if _x < 0:
                            _x = 0xf
                        if _x >= 0x10:
                            _x = 0
                        _y += flooddiry
                        if _y < 0:
                            _y = 0xf
                        if _y >= 0x10:
                            _y = 0
    
    # replace Nones with Empties
    for erow in entstable:
        for i, ents in enumerate(erow):
            if ents is None:
                erow[i] = [[], [], []]
    
    return entstable

def get_entry_end(bank, table, level, substage=None, screen=None, drac3_size=None):
    if drac3_size is None:
        if table == LEVTAB_TILES_BANK2 and bank == BANK2:
            drac3_size = 5*20 # this is a guess
        if table == LEVTAB_TILES4x4_BANK2 and bank == BANK2:
            drac3_size = 0x820 # this is a guess
        if table == SCREEN_ENT_TABLE and bank == BANK3:
            drac3_size = 4 # this is a guess
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
        if level >= len(SUBSTAGECOUNT) or (table == LEVTAB_TILES4x4_BANK2 and bank == BANK2 and level >= len(SUBSTAGECOUNT)-1):
            level -= 1
        else:
            drac3_size = 0
        
    addr2 = readword(bank, table + 2*level)
    if substage is not None:
        addr2 = readword(bank, addr2 + 2*substage)
    return addr2 + drac3_size

def readrom(_data):
    global data
    data = _data
    
    if not data or len(data) <= 100:
        print(f"romfile invalid?")
        sys.exit(1)
    
    global ROMTYPE

    # determine which rom this is from header
    ROMTYPE = "unk"
    if data[0x14B] == 0xA4 and data[0x134] == 0x43:
        ROMTYPE = "us"
    elif data[0x14B] == 0xA4 and data[0x134] == 0x44:
        ROMTYPE = "jp"
    elif data[0x14B] == 0x33 and data[0x13C] == 0x34:
        ROMTYPE = "kgbc4eu"
    else:
        print("Unrecognized ROM. Please check the hash. Supported roms: us/ue, jp, kgbc4eu")
        sys.exit(1)

    # fixed bank 0
    global LD_HL_LEVEL_A_SUBLEVEL
    LD_HL_LEVEL_A_SUBLEVEL = 0x2873

    # bank2
    global BANK2
    BANK2 = 2
    global LEVTAB_TILES4x4_BANK2
    LEVTAB_TILES4x4_BANK2 = 0x42a5
    global LEVTAB_TILES_BANK2
    LEVTAB_TILES_BANK2 = 0x42C4
    global TILES4x4_BEGIN
    TILES4x4_BEGIN = 0x44c0
    global LEVEL_TILESET_TABLE
    global LEVEL_TILESET_TABLE_BANK
    global LEVEL_TILESET_COMMON
    LEVEL_TILESET_TABLE_BANK = 0
    LEVEL_TILESET_TABLE = 0x2e06
    LEVEL_TILESET_COMMON = 0x2b50
    global LEVEL_SCROLLDIR_TABLE
    LEVEL_SCROLLDIR_TABLE = 0x4320
    
    # bank3
    global BANK
    global BANK3
    BANK3 = 3
    BANK = 3
    global LEVTAB_ROUTINE
    LEVTAB_ROUTINE = 0x6cc7
    global SCREEN_ENT_TABLE
    SCREEN_ENT_TABLE = 0x62c1

    # bank6
    global BANK6
    BANK6 = 6
    global LEVEL_SCREEN_TABLE
    LEVEL_SCREEN_TABLE = 0x5020
    
    if ROMTYPE == "jp":
        LEVEL_SCREEN_TABLE = 0x4fb0

    if ROMTYPE == "kgbc4eu":
        BANK2 = 0x12
        BANK3 = 0x13
        BANK = 0x13
        BANK6 = 0x16
        LEVTAB_TILES4x4_BANK2 += 75
        LEVTAB_TILES_BANK2 += 75
        LEVEL_SCROLLDIR_TABLE += 75
        TILES4x4_BEGIN = 0x4560
        LEVTAB_ROUTINE = 0x70af
        LEVEL_TILESET_TABLE = 0x5A15
        LEVEL_TILESET_TABLE_BANK = 0x16
        LEVEL_TILESET_COMMON = 0x5a33
        LEVEL_SCREEN_TABLE = 0x50C8
        SCREEN_ENT_TABLE = 0x66aa

    global LEVTAB_A, LEVTAB_B, LEVTAB_C, LEVELS, SUBSTAGECOUNT, Entities
    LEVTAB_A = readword(BANK, LEVTAB_ROUTINE + 4)
    LEVTAB_B = readword(BANK, LEVTAB_ROUTINE + 13)
    LEVTAB_C = readword(BANK, LEVTAB_ROUTINE + 22) # us:0x5d25
    global LEVTABS_AND_NAMES
    LEVTABS_AND_NAMES = [(LEVTAB_A, "Misc"), (LEVTAB_B, "Enemies"), (LEVTAB_C, "Items")]

    LEVELS = [None, "Plant", "Crystal", "Cloud", "Rock", "Drac1", "Drac2", "Drac3"]
    SUBSTAGECOUNT = [0, 6, 5, 5, 6, 5, 5, 1]

    Entities = {
        0x00: "NONE",
        0x01: "ITM_CROSS" if ROMTYPE == "jp" else "ITM_AXE",
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
        
        0x10: "ROPESPIKEBALL",
        0x12: "VMOVPLAT",
        0x13: "HMOVPLAT",
        0x15: "BGANIM_PLANT",
        0x1C: "ENM_SKELETON_1C",
        0x1E: "ENM_FORNEUS",
        0x1F: "ENM_BAT_1F",
        
        0x20: "ENM_SKELETON_20",
        0x21: "ENM_MUDMAN",
        0x22: "BOSS_TWINTRIDENT",
        0x23: "CRACKBLOCK",
        0x24: "BGBLOSSOM",
        0x25: "SPAWNEYE_RIGHT",
        0x26: "SPAWNEYE_LEFT",
        0x2B: "SPIKEWALL",
        
        0x31: "SPIKEWALL2",
        0x32: "TMOVPLAT",
        0x33: "ENM_KNIGHT",
        0x34: "ENM_RAVEN",
        0x35: "ITM_WHIP_CHAIN",
        0x37: "ENM_WATER_CREEP",
        0x3B: "SPAWNEYE_TOP_3B",
        0x3C: "SPAWNEYE_TOP_3C",
        
        0x41: "ENM_DAGGER",
        0x43: "LOOSEPULLEY_43",
        0x44: "LOOSEPULLEY_44",
        0x45: "BOSS_DARKSIDE",
        0x48: "ENM_PANAGUCHI_VMOV",
        0x4A: "SPIKEFLOOR",
        0x4B: "PULLEY",
        0x4E: "BGFLAME",
        
        0x53: "BOSS_ANGEL_MUMMY",
        0x56: "EXTRUDER_RIGHT",
        0x57: "EXTRUDER_LEFT",
        0x58: "EXTRUDER_CTRL",
        0x5B: "ENM_NIGHTSTALKER",
        0x5D: "ENM_BEATLE",
        
        0x60: "BOSS_IRON_DOLL",
        
        0x69: "BOSS_BONE_SERPENT",
        
        0x72: "BOSS_SOLEIL",
        0x73: "BOSS_DRACULA",
    }

def getEntityName(id):
    name = f"${id:02X}"
    if id in Entities:
        name += ":" + Entities.get(id)
    return name

PALETTE = [
    (0xff, 0xff, 0xff),
    (0xb0, 0xb0, 0xb0),
    (0x40, 0x40, 0x40),
    (0, 0, 0),
]

ENTPALETTES = [
    (0x5C, 0xCE, 0x98), # misc
    (0xA5, 0x86, 0x14), # enemies
    (0xEE, 0x6F, 0xA4), # items
]

# per entcat
SLOTCOUNT = [
    8,
    8,
    4
]

SLOTRAMSTART = [
    0xc400,
    0xCC00,
    0xD400,
]