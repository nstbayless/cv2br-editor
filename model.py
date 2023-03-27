import rom

class JSONDict(dict):
    # This class implemented by ChatGPT
    # WARNING! some attributes are overshadowed by native dict attributes
    # for example, you can't access groove.values directly, must do groove["values"].
    # if you're experiencing an issue where your code works only if you change the
    # key's name, this is probably the reason.
    def __getattr__(self, attr):
        if hasattr(dict, attr):
            return getattr(dict, attr).__get__(self, type(self))
        try:
            return self[attr]
        except KeyError:
            raise AttributeError(attr)
    
    def __setattr__(self, attr, value):
        if hasattr(dict, attr):
            setattr(dict, attr, value)
        else:
            self[attr] = value
            
def loadLevelScreenTable(root, j):
    index = j.index
            
# returns a pair: nes: bytes, data: JSONDict
def loadRom(path):
    with open(path, "rb") as f:
        rom.readrom(f.read())
        j = JSONDict()
        
        j.levels = []
        for i, level in enumerate(rom.LEVELS):
            if i >= 1:
                jl = JSONDict()
                jl.index = i
                jl.name = level
                for 
                loadLevelScreenTable(jl)
                j.levels.append(jl)
                
                

def saveRom(base, path):
    pass
