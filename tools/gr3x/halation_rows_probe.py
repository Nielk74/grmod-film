"""Round 7: a film's Halation and Colour rows on the Image Control parameter screen
(core/src/fw/gr3x/halation-rows.ts), executed through the patched official code:

  - the parameter-line table: the 36 official entries unchanged in the copy, all four table
    sites moved to it, entries 36..38 Standard's lines of each set plus (stills only) kind 15
    (Halation, Grain Effect's row) and kind 10 (Colour, HDR Tone's Toning row);
  - GetBaseKindDetailControl (0x531aca98) for every look 0..255, photo sets 0..3 and both movie
    flags (as round 6);
  - the official line functions on the new entries: both added lines valid in stills only, their
    kinds 15 and 10;
  - every hook, run from its patched word to the next official instruction: names (kind 15
    Halation, kind 10 Colour for a film), Halation's start and position (Grain Effect's value of the
    stored strength, which the official map 0x531ac868 turns into the position = the strength),
    value text ("--", "1", "2", "3"), icon and setter (the position); Colour's scale, its two
    positions, start and position (the colour), empty text, red or white icon and setter; for any
    other look the official call with the same arguments; callee-saved registers and the stack as
    on entry;
  - Cancel: the parameter backup and restore keep and put back strength and colour (rounds 7..9:
    thunks; round 10: the screen's own Toning restore, 0x532c056c, whose look read takes a film as
    Bleach Bypass, puts the byte back through Bleach Bypass's Toning setter, and the thunks stay
    unpatched).
Round 10 (films.c): the settings are read back through the films' module, booted through the
settings scaffold (films_probe.FilmsProbe); a film owns photo set 1 (its Halation is the field there).
UI widgets are not drawn; the controller is a synthetic object with the fields the code reads.
GR Mod's Grain row (manifest 'grainRow', films.c GRAIN_ROW): a third added line, kind 11 (Cross
Processing's Toning row) as Grain Effect's for a film: its name 0x133, scale 57, four positions,
start and position (the film's grain), value text, icon 0x1de and setter; the Colour line with kind
10 with four positions (red, orange, gold, white) and their icons; Cancel over the whole byte (0..95).
"""
import argparse,hashlib,json,random,struct
from pathlib import Path
from unicorn import arm_const as reg
from slots_probe import REC,REGION,fresh_record
from halation_screen_probe import ScreenProbe,FOCUS as FOCUS_ADDRESS,movw_value,SITES,TABLE,BASE_COLUMN,IS_VALID,LINE_COUNT,CURRENT_KIND,SUBTITLE,SUBTITLE_TABLE,OFFICIAL_COLUMN,SETTINGS,CTL
from native_probe import STACK
from films_probe import FilmsProbe,fresh_records,RECS,FIELD

if not __debug__:raise RuntimeError('Validation requires Python assertions')

SCALE10,POSITIONS10,START10,POSITION10,LIST_TEXT10,LIST_ICON10,SETTER10=0x531adcbc,0x531adce0,0x531adca0,0x531b0514,0x531af494,0x531af4a8,0x531b0d8c
START15,POSITION15,LIST_TEXT15,LIST_ICON15,SETTER15=0x531ae84c,0x531b0564,0x531af6ec,0x531af700,0x531b0d28
MAP15,MAP10=0x531ac868,0x531ac6f0
SCALE11,POSITIONS11,START11,POSITION11,LIST_TEXT11,LIST_ICON11,SETTER11=0x531addfc,0x531ade20,0x531adde0,0x531b0524,0x531af50c,0x531af520,0x531b0d78
NATIVE={0x532c70e4:'stored10',0x532c297c:'live10',0x532aca68:'text10',0x532c0894:'hdr',
        0x532c9744:'stored15',0x532c2a5c:'live15',0x532ace68:'text15',0x532c1780:'particle',
        0x532c7270:'stored11',0x532c299c:'live11',0x532ad000:'text11',0x532c09a8:'cross'}
# The Grain row's Toning byte (films.c GRAIN_ROW): h + 18 g; h's strength and colour position (red 0, gold 1, white 2).
def hal_of(v):
    h=v%24 if v<=95 else 0
    st=[0,1,3,2,1,2,3,0,0,0,0,0,1,2,3,0,0,0,1,2,3,0,0,0][h];co=[0,0,0,0,3,3,3,0,0,3,3,3,2,2,2,2,2,2,1,1,1,1,1,1][h]
    return st,co,(v//24 if v<=95 else 0)

class RowsProbe(ScreenProbe):
    def _hook(self,cpu,at,size,user):
        if at in NATIVE:
            self.native.append((NATIVE[at],cpu.reg_read(reg.UC_ARM_REG_R0),cpu.reg_read(reg.UC_ARM_REG_R1)))
            cpu.reg_write(reg.UC_ARM_REG_R0,0x7777);cpu.reg_write(reg.UC_ARM_REG_PC,cpu.reg_read(reg.UC_ARM_REG_LR))
        else:super()._hook(cpu,at,size,user)
    def site_to(self,at,end,regs,flags=0):
        c=self.uc;values=[0x12340000+i for i in range(13)]
        for k,v in regs.items():values[k]=v
        for i,v in enumerate(values):c.reg_write(getattr(reg,'UC_ARM_REG_R'+str(i)),v)
        c.reg_write(reg.UC_ARM_REG_SP,STACK);c.reg_write(reg.UC_ARM_REG_LR,0x5a5a5a5a);c.reg_write(reg.UC_ARM_REG_CPSR,0x13|(flags<<28))
        self.native=[];c.emu_start(at,end,count=20000)
        assert c.reg_read(reg.UC_ARM_REG_PC)==end and c.reg_read(reg.UC_ARM_REG_SP)==STACK
        out=[c.reg_read(getattr(reg,'UC_ARM_REG_R'+str(i))) for i in range(13)]
        assert out[4:12]==values[4:12],hex(at)
        return out,values

TONING_RESTORE,LIVE_LOOK,SET_OF,SETTINGS_GETTER=0x532c056c,0x53549ee8,0x532bd6d4,0x5320b31c
BACKUP,BACKUP_BODY,RESTORE,RESTORE_BODY=0x532c337c,0x532c325c,0x532c34a8,0x532c33c8

class RowsProbe10(FilmsProbe):
    """Round 10: the screen probe's controller and site runs on the films' module harness."""
    def __init__(self,data,manifest):
        super().__init__(data,manifest);self.native=[];self.focus=0;self.restoring=None
    def _hook(self,cpu,at,size,user):
        ret=lambda v:(cpu.reg_write(reg.UC_ARM_REG_R0,v),cpu.reg_write(reg.UC_ARM_REG_PC,cpu.reg_read(reg.UC_ARM_REG_LR)))
        if self.restoring and at in (LIVE_LOOK,SET_OF,SETTINGS_GETTER):
            look,set_=self.restoring;ret(look if at==LIVE_LOOK else set_ if at==SET_OF else 0x55063f30)
        elif at in NATIVE:
            self.native.append((NATIVE[at],cpu.reg_read(reg.UC_ARM_REG_R0),cpu.reg_read(reg.UC_ARM_REG_R1)));ret(0x7777)
        elif at==FOCUS_ADDRESS:ret(self.focus)
        else:super()._hook(cpu,at,size,user)
    logged=ScreenProbe.logged;controller=ScreenProbe.controller;site=ScreenProbe.site;site_to=RowsProbe.site_to

def verify(data,manifest):
    films=manifest['filmCount'];e=manifest['lookEntries']['halationRows'];report={};calls=0
    r10=bool(manifest.get('round10'))
    n=(RowsProbe10 if r10 else RowsProbe)(data,manifest);c=n.uc;orig=lambda a,k:data[a-0x53000000:a-0x53000000+k]
    film=lambda look:64<=look<64+films
    cols,icons=manifest['catalogs']['textColumns'],manifest['catalogs']['iconCount']
    G=bool(manifest.get('grainRow'))
    # The teal sky builds: the films' Hue row is named "Teal Sky" and has its own icon (text and icon last).
    T=bool(manifest['lookEntries'].get('films',{}).get('tealHue'))
    hal_text,col_text,teal_text=(cols-3,cols-2,cols-1) if T else (cols-2,cols-1,None)
    k=4+(2 if G else 0)+(1 if T else 0)
    hal_icon,col_scale,red_icon,white_icon=icons-k,icons-k+1,icons-k+2,icons-k+3
    gold_icon,orange_icon,teal_icon=icons-k+4,icons-k+5,icons-1
    # 1. The table.
    table=None
    for lo,hi,r in SITES:
        v=movw_value(struct.unpack('<I',c.mem_read(lo,4))[0],struct.unpack('<I',c.mem_read(hi,4))[0])
        table=table or v;assert v==table and v==e['table']
    assert bytes(c.mem_read(table,36*8))==orig(TABLE,36*8)
    entries=[struct.unpack('<2I',bytes(c.mem_read(table+8*k,8))) for k in range(39)]
    def items(k):p,cnt=entries[k];return [tuple(c.mem_read(p+2*i,2)) for i in range(cnt)]
    std=[items(0),items(12),items(24)]
    for s in range(3):assert items(36+s)==std[s]+([(0,11)] if G else [])+[(0,15),(0,10)],s
    assert items(37)==items(38) and all(k not in (10,11,15) for _,k in items(0))
    report['table']=dict(entries=39,film_lines=[len(items(36+s)) for s in range(3)])
    if G:
        # The screen's number of lines (0x531afbe0): after its loop over the camera's looks (most
        # lines, at +0x19e), the films' lines count too: the hook from 0x531afc48 to the allocation.
        for movie in (0,1):
            for look in (11,64,64+films-1,20):
                n.controller(look,0,movie);most=0
                for s in range(3):
                    for col in range(12):most=max(most,n.call(LINE_COUNT,CTL,s,col))
                c.mem_write(CTL+0x19e,bytes([most]))
                out,vals=n.site_to(0x531afc48,0x531afc4c,{5:CTL});calls+=1
                want=max([most]+[n.call(LINE_COUNT,CTL,s,36-11*s) for s in range(3)])
                assert out[0]==want==c.mem_read(CTL+0x19e,1)[0],(look,movie,out[0],want)
                if movie==0:
                    assert want==max(len(items(36+s)) for s in range(3))>most,(want,most)
                    report['screen_lines']=dict(camera_looks=most,with_films=want)
    # 2. Base column, every look, every set, both movie flags (the asserts only log).
    columns=0
    for movie in (0,1):
        for s in range(4):
            for look in range(256):
                n.controller(look,s,movie);col,logged=n.logged(BASE_COLUMN,CTL,look);calls+=1
                want=OFFICIAL_COLUMN[look-11] if 11<=look<=22 else (36-11*s if film(look) and s<3 else 0)
                assert col==want,(look,s,movie,col,want);columns+=1
                want_log=([0x363] if movie and look==14 else [])+([0x364] if movie and look==20 else [])+([] if 11<=look<=22 or (film(look) and s<3) else [0x375])
                assert logged==want_log,(look,s,movie,logged)
    report['base_columns']=columns
    # 3. Official line functions on the new entries (against Standard's).
    for movie in (0,1):
        for s in range(3):
            fc,sc=36-11*s,0
            n.controller(64,s,movie)
            for line in range(len(std[s])):
                assert n.call(IS_VALID,CTL,s,fc,line)==n.call(IS_VALID,CTL,s,sc,line);calls+=2
            kinds=[11,15,10] if G else [15,10]
            added=[n.call(IS_VALID,CTL,s,fc,len(std[s])+k) for k in range(len(kinds))];calls+=len(kinds)
            assert added==([1]*len(kinds) if movie==0 else [0]*len(kinds)),(s,movie,added)
            assert n.call(LINE_COUNT,CTL,s,fc)-n.call(LINE_COUNT,CTL,s,sc)==sum(added);calls+=2
            c.mem_write(CTL+0x19a,bytes([fc]))
            for k,kind in enumerate(kinds):n.focus=len(std[s])+k;assert n.call(CURRENT_KIND,CTL)==kind;calls+=1
    # 4. Hooks, with settings read back through slots3.c itself.
    if r10:
        recs=fresh_records(random.Random(5),films)
        for r in recs:
            for k in range(6):r[0x1c2+2*k if k<3 else 0x57e+2*(k-3)]=11
        recs[0][0x1c4]=64   # photo set 1: film 64 owns Bleach Bypass's fields (its Halation is the field)
        n.records(recs);assert n.boot();calls+=1
        fn=lambda name:n.sym[name]
    else:
        rec=fresh_record(random.Random(5));c.mem_write(REC,bytes(rec));c.mem_write(SETTINGS,struct.pack('<I',REC))
        assert n.boot();calls+=1
        own=manifest['lookEntries']['ownParameters'];fn=lambda name:own['module']+own['exports'][name]
    strength=lambda look,s:(look*7+s*5)%4
    colour=lambda look,s:(look+s)%(4 if G else 2)
    grain=lambda look,s:(look*3+s)%4 if G else 0
    def restore(look,s):
        n.call(fn('sp_hal_put'),look,s,strength(look,s));n.call(fn('sp_col_put'),look,s,colour(look,s))
        if G:n.call(fn('sp_grain_put'),look,s,grain(look,s))
    for look in range(64,64+films):
        for s in range(3):restore(look,s);calls+=2
    looks=list(range(0,24))+list(range(60,90))+[255]
    hooks=0
    for look in looks:
        for s in range(4):
            isfilm=film(look)
            st=strength(look,s) if isfilm and s<3 else 0
            co=colour(look,s) if isfilm and s<3 else 0
            gr=grain(look,s) if isfilm and s<3 else 0
            n.controller(look,s)
            # Names: Halation (kind 15) and Colour (kind 10) for a film, the official text otherwise.
            for kind in (1,7,9,10,11,13,14,15,17):
                for flags in (0,15):
                    out,vals,f=n.site(SUBTITLE,{0:kind,3:SUBTITLE_TABLE+kind*4,4:CTL},flags);calls+=1
                    official=struct.unpack('<H',orig(SUBTITLE_TABLE+kind*4+2,2))[0]
                    want=hal_text if kind==15 and isfilm else col_text if kind==10 and isfilm else 0x133 if kind==11 and isfilm and G else teal_text if kind==1 and isfilm and T else official
                    assert out[1]==want,(look,kind) ;assert out[0]==kind and out[2:4]==vals[2:4];hooks+=1
            # ---- Teal sky (kind 1, Hue): its list icon
            out,vals=n.site_to(0x531af070,0x531af074,{0:0x111,2:0x222,6:CTL})
            assert out[1]==(teal_icon if isfilm and T else 0x1e1) and (out[0],out[2])==(0x111,0x222);hooks+=1
            # ---- Halation (kind 15)
            for at,ctl,kind in ((START15,6,'stored15'),(POSITION15,5,'live15')):
                out,vals=n.site_to(at,at+4,{0:0x6205c000,1:look,ctl:CTL});calls+=1
                if isfilm:
                    assert out[0]==(4-st)&3 and not n.native,(look,s)
                    assert n.call(MAP15,out[0])==st;calls+=1   # the official map gives the position
                else:assert out[0]==0x7777 and n.native==[(kind,0x6205c000,look)]
                hooks+=1
            buf=REGION+0x9000;c.mem_write(buf,b'\xa5'*4)
            out,vals=n.site_to(LIST_TEXT15,LIST_TEXT15+4,{0:0x62049000,1:buf,6:CTL})
            if isfilm:assert bytes(c.mem_read(buf,4))==[b'--\0',b'1\0\0',b'2\0\0',b'3\0\0'][st]+b'\xa5' and not n.native
            else:assert n.native==[('text15',0x62049000,buf)]
            hooks+=1
            out,vals=n.site_to(LIST_ICON15,LIST_ICON15+4,{0:0x111,2:0x222,6:CTL});assert out[1]==(hal_icon if isfilm else 0x1de) and (out[0],out[2])==(0x111,0x222);hooks+=1
            for pos in range(4):
                out,vals=n.site_to(SETTER15,SETTER15+4,{0:0x6205c000,1:[0,3,2,1][pos],4:CTL,6:pos});calls+=1
                if isfilm:
                    assert not n.native and n.call(fn('sp_hal'),look,s)==(pos if s<3 else 0) and n.call(fn('sp_col'),look,s)==co
                    if G:assert n.call(fn('sp_grain'),look,s)==gr
                    restore(look,s)
                else:assert n.native==[('particle',0x6205c000,[0,3,2,1][pos])]
                hooks+=1
            # ---- Colour (kind 10)
            out,vals=n.site_to(SCALE10,SCALE10+4,{6:CTL});assert out[3]==(col_scale if isfilm else 0xd3) and out[:3]==vals[:3];hooks+=1
            out,vals=n.site_to(POSITIONS10,POSITIONS10+8,{6:CTL});assert (out[2],out[3])==(((3,0x78) if G else (1,0x168)) if isfilm else (2,0xb4)) and out[:2]==vals[:2];hooks+=1
            for at,ctl,kind in ((START10,6,'stored10'),(POSITION10,5,'live10')):
                # Four positions: a film's position comes back past the map (at + 8).
                out,vals=n.site_to(at,at+(8 if isfilm and G else 4),{0:0x6205c000,1:look,ctl:CTL});calls+=1
                if isfilm:
                    assert out[0]==co and not n.native,(look,s)
                    if not G:assert n.call(MAP10,out[0])==co;calls+=1
                else:assert out[0]==0x7777 and n.native==[(kind,0x6205c000,look)]
                hooks+=1
            c.mem_write(buf,b'\xa5'*4)
            out,vals=n.site_to(LIST_TEXT10,LIST_TEXT10+4,{0:0x62049000,1:buf,6:CTL})
            if isfilm:assert bytes(c.mem_read(buf,4))==b'\0\xa5\xa5\xa5' and not n.native
            else:assert n.native==[('text10',0x62049000,buf)]
            hooks+=1
            out,vals=n.site_to(LIST_ICON10,LIST_ICON10+4,{0:0x111,2:0x222,6:CTL})
            icon=([red_icon,orange_icon,gold_icon,white_icon][co] if G else white_icon if co else red_icon) if isfilm else 0x1e9
            assert out[1]==icon and (out[0],out[2])==(0x111,0x222);hooks+=1
            for v in ((0,1,2,3) if G else (0,1,2)):
                # (r1 the native value of the position, [0, 1, 2, 0]; r6 the position.)
                out,vals=n.site_to(SETTER10,SETTER10+4,{0:0x6205c000,1:[0,1,2,0][v],4:CTL,6:v});calls+=1
                if isfilm:
                    assert not n.native and n.call(fn('sp_col'),look,s)==((v if v<2 or G else co) if s<3 else 0) and n.call(fn('sp_hal'),look,s)==st
                    restore(look,s)
                else:assert n.native==[('hdr',0x6205c000,[0,1,2,0][v])]
                hooks+=1
            # ---- Grain (kind 11, the Grain row)
            if G:
                out,vals=n.site_to(SCALE11,SCALE11+4,{6:CTL});assert out[3]==(0x39 if isfilm else 0x33) and out[:3]==vals[:3];hooks+=1
                out,vals=n.site_to(POSITIONS11,POSITIONS11+8,{6:CTL});assert (out[2],out[3])==((3,0x78) if isfilm else (2,0xb4)) and out[:2]==vals[:2];hooks+=1
                for at,ctl,kind in ((START11,6,'stored11'),(POSITION11,5,'live11')):
                    out,vals=n.site_to(at,at+(8 if isfilm else 4),{0:0x6205c000,1:look,ctl:CTL});calls+=1
                    if isfilm:assert out[0]==gr and not n.native,(look,s)
                    else:assert out[0]==0x7777 and n.native==[(kind,0x6205c000,look)]
                    hooks+=1
                c.mem_write(buf,b'\xa5'*4)
                out,vals=n.site_to(LIST_TEXT11,LIST_TEXT11+4,{0:0x62049000,1:buf,7:CTL})
                if isfilm:assert bytes(c.mem_read(buf,4))==[b'--\0',b'1\0\0',b'2\0\0',b'3\0\0'][gr]+b'\xa5' and not n.native
                else:assert n.native==[('text11',0x62049000,buf)]
                hooks+=1
                out,vals=n.site_to(LIST_ICON11,LIST_ICON11+4,{0:0x111,2:0x222,7:CTL});assert out[1]==(0x1de if isfilm else 0x1e9) and (out[0],out[2])==(0x111,0x222);hooks+=1
                for pos in range(4):
                    out,vals=n.site_to(SETTER11,SETTER11+4,{0:0x6205c000,1:[0,1,2,0][pos],4:CTL,6:pos});calls+=1
                    if isfilm:
                        assert not n.native and n.call(fn('sp_grain'),look,s)==(pos if s<3 else 0)
                        assert n.call(fn('sp_hal'),look,s)==st and n.call(fn('sp_col'),look,s)==co
                        restore(look,s)
                    else:assert n.native==[('cross',0x6205c000,[0,1,2,0][pos])]
                    hooks+=1
    report['hook_cases']=hooks
    if r10:
        # Cancel (round 10): no thunks; the screen backs the Toning byte up with the other parameters
        # (its live value, 0x5354a14c) and puts it back with 0x532c056c, whose look read (patched)
        # takes a film as Bleach Bypass: Bleach Bypass's Toning setter of the set, i.e. the field.
        for at,body in ((BACKUP,BACKUP_BODY),(RESTORE,RESTORE_BODY)):
            assert struct.unpack('<I',c.mem_read(at,4))[0]==struct.unpack('<I',orig(at,4))[0],hex(at)
            assert all(s['address']!=at for s in manifest['sites']),hex(at)
        assert any(s['address']==0x532c058c for s in manifest['sites'])
        obj=REGION+0xa800;restores=0
        for look in (64,64+films-1,18,11,12,64+films,255):
            for s in range(3):
                for v in range(96 if G else 12):
                    c.mem_write(obj,bytes(0x40))
                    n.restoring=(look,s);n.toning=[]
                    n.call(TONING_RESTORE,obj,v);calls+=1;n.restoring=None
                    want=[(s,v)] if look==18 or film(look) else []
                    assert n.toning==want,(look,s,v,n.toning);restores+=1
                    if film(look) and s==1 and look==64:
                        assert c.mem_read(RECS[0]+FIELD[7][1],1)[0]==v
                        if G:
                            st,co,g=hal_of(v)
                            assert n.call(fn('sp_hal'),64,1)==st and n.call(fn('sp_col'),64,1)==co and n.call(fn('sp_grain'),64,1)==g,v;calls+=3
                        else:
                            st=[0,1,3,2,1,2,3,0,0,0,0,0][v];co=[0,0,0,0,1,1,1,0,0,1,1,1][v]
                            assert n.call(fn('sp_hal'),64,1)==st and n.call(fn('sp_col'),64,1)==co;calls+=2
        restore(64,1)
        report['cancel_restores']=restores
        return dict(schema=1,rtos_sha256=hashlib.sha256(data).hexdigest(),films=films,calls=calls,**report,hardware_tested=False,
            scope='Patched ImageControlDetailController functions and hook stubs with a synthetic controller; widgets not drawn; the films\' module booted through the settings scaffold.')
    # Cancel: the thunks of the parameter backup and restore keep and put back strength and colour.
    for at,body in ((0x532c337c,0x532c325c),(0x532c34a8,0x532c33c8)):
        if at==0x532c34a8:
            n.call(fn('sp_hal_put'),64,0,(strength(64,0)+1)%4);n.call(fn('sp_col_put'),64,0,1-colour(64,0))
            assert n.call(fn('sp_hal'),64,0)!=strength(64,0) and n.call(fn('sp_col'),64,0)!=colour(64,0)
        c.reg_write(reg.UC_ARM_REG_SP,STACK);c.reg_write(reg.UC_ARM_REG_LR,0x5a5a5a5a);c.reg_write(reg.UC_ARM_REG_R0,0x6205c000)
        c.emu_start(at,body,count=5000)
        assert c.reg_read(reg.UC_ARM_REG_PC)==body and c.reg_read(reg.UC_ARM_REG_SP)==STACK and c.reg_read(reg.UC_ARM_REG_LR)==0x5a5a5a5a and c.reg_read(reg.UC_ARM_REG_R0)==0x6205c000
        calls+=1
    assert n.call(fn('sp_hal'),64,0)==strength(64,0) and n.call(fn('sp_col'),64,0)==colour(64,0)
    report['cancel_restores']=True
    return dict(schema=1,rtos_sha256=hashlib.sha256(data).hexdigest(),films=films,calls=calls,**report,hardware_tested=False,
        scope='Patched ImageControlDetailController functions and hook stubs with a synthetic controller; widgets not drawn.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for s in ('rtos','manifest','report'):p.add_argument('--'+s,type=Path,required=True)
    a=p.parse_args();result=verify(a.rtos.read_bytes(),json.loads(a.manifest.read_text()))
    with a.report.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
