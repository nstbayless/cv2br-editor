import sys
import os
import rom
from rom import readword, readbyte, readtableword
from PIL import Image, ImageDraw

PALETTE = [
    (0xff, 0xff, 0xff),
    (0xb0, 0xb0, 0xb0),
    (0x30, 0x30, 0x30),
    (0, 0, 0),
]

ENTPALETTES = [
    (0xff, 0xa0, 0x40), # misc
    (0x40, 0x40, 0xff), # enemies
    (0x90, 0x80, 0x20), # items
]

ENTCROSSSIZE = 4

if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} base.gb out/")
    sys.exit(1)
    
def ghosttint(r, g, b):
    return (r//2, g//2, int(b/1.5))

def pasteTileChunk(out, i, chidx, x, y, ghostly=False):
    chunk = get_tile_chunk(chidx, i)
        
    #iterate over tiles
    for k, c in enumerate(chunk):
        cx = k % 4
        cy = k // 4
        xdraw = x + cx * 8
        ydraw = y + cy * 8
        
        img = get_tile_img(c, i)
        if ghostly:
            pixels = out.load()
            pix2 = img.load()
            for _x in range(8):
                for _y in range(8):
                    pixels[xdraw+_x, ydraw+_y] = ghosttint(*pix2[_x,_y])
        else:
            out.paste(img, (xdraw, ydraw))
    

def pasteScreen(out, level, tchunks, x, y, ghostly=False):
    for t, chidx in enumerate(tchunks):
        sx = t % 5
        sy = t // 5
        pasteTileChunk(out, level, chidx, x + sx * 8 * 4, y + sy * 8 * 4, ghostly)

with open(sys.argv[1], "rb") as f:
    rom.readrom(f.read())
dir = sys.argv[2]

VOFF = 0x8000
vrambuffer = [0 for i in range(0x2000)]
def load_vram_buffer(dst, len, bank, addr):
    for i in range(0, len):
        vrambuffer[i + dst - VOFF] = rom.readbyte(bank, addr + i)

def load_vram_metabuffer(bank, addr):
    # this does what routine 0:2E24 does
    while rom.readbyte(bank, addr) != 0:
        destaddr = ((rom.readbyte(bank, addr) << 12) + (rom.readbyte(bank, addr + 1) << 4)) & 0xffff
        addr += 2
        destlen = rom.readbyte(bank, addr) << 4
        addr += 1
        srcbank = rom.readbyte(bank, addr)
        addr += 1
        srcaddr = rom.readword(bank, addr)
        addr += 2
        load_vram_buffer(destaddr, destlen, srcbank, srcaddr)
     
def get_tile_chunk(id, level):
    if id == 0:
        return [0] * 16
    id -= 1
    base = readtableword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, level)
    return [rom.readbyte(rom.BANK2, base + id * 0x10 + i) for i in range(0x10)]

def get_tile_img_memoized(id, level):
    img = Image.new(mode="RGB", size=(8, 8))
    pixels = img.load()
    for i in range(8):
        for j in range(8):
            pixels[i,j] = (0xff, 0xff, 0xff)
    tileaddr = id * 0x10 + 0x1000
    tilevram = vrambuffer[tileaddr:tileaddr+0x10]
    pixelsc = [[0 for i in range(8)] for j in range(8)]
    for i in range(0,16,2):
        for b in range(2):
            for j in range(8):
                pixelsc[j][i//2] += (1 << b) * (1 & (tilevram[i+b] >> (7-j)))
    for i in range(8):
        for j in range(8):
            pixels[i,j] = PALETTE[pixelsc[i][j]]
    return img

TILE_IMG_MAP = {}
# produces an 8x8 tile image
def get_tile_img(id, level):
    if (id, level) not in TILE_IMG_MAP:
        TILE_IMG_MAP[(id, level)] = get_tile_img_memoized(id, level)
    return TILE_IMG_MAP[(id, level)]
    
def write_chunks_image(level):
    # produce image for the tilechunkset
    levelname = rom.LEVELS[level]
    dim = 8*4
    MARGIN=2
    out = Image.new(mode="RGB", size=(dim * 16 + MARGIN * 15, dim * 16 + MARGIN * 15))
    
    tilec = rom.get_entry_end(rom.LEVTAB_TILES4x4_BANK2, rom.BANK2, level) - readtableword(rom.BANK2, rom.LEVTAB_TILES4x4_BANK2, level)
    assert tilec > 0, f"{levelname}: {tilec}"
    tilec = tilec // 0x10 + 1
    for i in range(16):
        for j in range(16):
            chidx = i + j * 16
            pasteTileChunk(out, level, chidx, i * (dim + MARGIN), j * (dim + MARGIN), chidx >= tilec )
        
    out.save(os.path.join(dir, f"{levelname}_tilechunks.png"))
    
    
for i, level in enumerate(rom.LEVELS):
    if level is None:
        continue
    
    # first, load vram for level
    vrambuffer[:] = [0 for i in range(0x2000)]
    buffaddr = readtableword(rom.LEVEL_TILESET_TABLE_BANK, rom.LEVEL_TILESET_TABLE, i)
    load_vram_metabuffer(rom.LEVEL_TILESET_TABLE_BANK, rom.LEVEL_TILESET_COMMON)
    load_vram_metabuffer(rom.LEVEL_TILESET_TABLE_BANK, buffaddr)
    
    write_chunks_image(i)
    
    # produce image for every sublevel
    for sublevel in range(rom.SUBSTAGECOUNT[i]):
        x, y, d, table = rom.produce_sublevel_screen_arrangement(i, sublevel)
        entstable = rom.get_entities_in_screens(i, sublevel)
        table_x0, table_x1, table_y0, table_y1 = rom.get_screensbuff_boundingbox(table)
        
        # print level screens:
        if False:
            print("table:")
            for yi in range(table_y0, table_y1):
                s = ""
                for xi in range(table_x0, table_x1):
                    if table[xi][yi] != 0:
                        s += f" {table[xi][yi]:02X}"
                    else:
                        s += "   "
                print(s)
        
        tiles_begin = readtableword(rom.BANK2, rom.LEVTAB_TILES_BANK2, i, sublevel)
        tiles_end = rom.get_entry_end(rom.LEVTAB_TILES_BANK2, rom.BANK2, i, sublevel)
        assert tiles_end > tiles_begin
        assert (tiles_begin - tiles_end) % 20 == 0
        screenc = (tiles_end - tiles_begin) // 20
        out = Image.new(mode="RGB", size=(8 * 5 * 4 * (table_x1 - table_x0), 4 * 4 * 8 * (table_y1 - table_y0)))
        outents = Image.new(mode="RGBA", size=(8 * 5 * 4 * (table_x1 - table_x0), 4 * 4 * 8 * (table_y1 - table_y0)))
        
        # iterate over screens:
        for yi in range(table_y0, table_y1):
            for xi in range(table_x0, table_x1):
                te = table[xi][yi]
                if te != 0:
                    screen = te & 0x0F
                    tilechunks = [readbyte(rom.BANK6, tiles_begin + 20*screen + r) for r in range(20)]
                    screenxpx = (xi-table_x0)*8*5*4
                    screenypx = (yi-table_y0)*4*8*4
                    pasteScreen(out, i, tilechunks, screenxpx, screenypx, screen >= screenc)
                    
                    # draw entities
                    for cat, ents in enumerate(entstable[xi][yi]):
                        color = ENTPALETTES[cat]
                        for ent in ents:
                            if screen < screenc:
                                entx = ent["x"]
                                enty = ent["y"]
                                entt = ent["type"]
                                name = f"{entt:02X}" if entt not in rom.Entities else rom.Entities[entt]
                                for offset, col in zip([0], [color]):
                                    _x = screenxpx + entx + offset
                                    _y = screenypx + enty + offset
                                    ImageDraw.Draw(outents).line((screenxpx + min(entx, 0xa0) + offset - ENTCROSSSIZE, _y, _x + ENTCROSSSIZE, _y), fill=col)
                                    ImageDraw.Draw(outents).line((_x, screenypx + min(enty, 0x80) + offset - ENTCROSSSIZE, _x, _y + ENTCROSSSIZE), fill=col)
                                    anchor = ""
                                    if entx >= 0x78:
                                        anchor = "r"
                                    else:
                                        entx = 4
                                        anchor = "l"
                                    if enty >= 0x60:
                                        anchor += "b"
                                        _y = screenypx + min(enty,0x80) + offset
                                        _y -= 12
                                    else:
                                        anchor += "t"
                                    ImageDraw.Draw(outents).text((_x, _y), name, fill=col)
                    
        out.paste(outents, (0, 0), outents)
        out.save(os.path.join(dir, f"{level}_{sublevel}.png"))