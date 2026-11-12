/* SPDX-License-Identifier: GPL-2.0-only */
/* Loaded stage 1f: DIAGNOSTIC adapter plus the candidate fix for the rectangle problem seen in stage 1e. Stage 1e's panel, counters, per-view draw
 * statistics, proof patterns and per-shot log are kept. New:
 *  - layout: a view attached to a root that is clean gets no absolute rectangle (a fresh view already carries its own "needs layout" flag, so
 *    view_visible does not flag the ancestors and the layout pass never visits it). After attaching, the root is asked to lay out its new
 *    children through its own vtable slot 0x20 (the request view_visible makes). The variant follows the hook count (1, 4, 7 ... A; 2, 5, 8 ... B; 3, 6, 9 ... C):
 *      A the Loaded steps run on timer ticks and the root is asked to lay out (the candidate fix),
 *      B the Loaded steps 1 to 7 run inside the hook with the panel, no request (the panel's own path),
 *      C stage 1e's behaviour as the control: timer ticks, no request;
 *  - a global event log with absolute clock times that survives across photos: the shutter release hook, the completion hook, transitions,
 *    attach, first copy of each view, and every UI event the camera dispatches (rate limited to one per id and 500 ms), read from a sixth
 *    hook at the UI event dispatcher 0x53228ab4;
 *  - two pages: the last 8 global events with the time between them, and the 8 events before the last hook with their distance to it.
 * Nothing is written to the settings, nothing is played, nothing waits. */
#include "camera_loaded.h"
#include "../../shot-animation/native/camera_clock.h"
#include "loaded.h"
#include "loaded_data.h"
#include "loaded_slots.h"

#define NATIVE(type,address) ((type)(uintptr_t)(address))
typedef void *(*get_fn)(void);
typedef void *(*get_from_fn)(void *);
typedef void *(*alloc_fn)(uint32_t);
typedef void (*one_fn)(void *);
typedef void (*two_fn)(void *,void *);
typedef void (*flag_fn)(void *,uint32_t);
typedef uint32_t (*timer_start_fn)(void *,uint32_t,void *);
typedef int (*timer_stop_fn)(void *,uint32_t);
typedef void *(*slot_fn)(void *,uint32_t);

#define heap_alloc NATIVE(alloc_fn,0x536af2a8u)
#define heap_free NATIVE(one_fn,0x536af2e4u)
#define app_get NATIVE(get_fn,0x5320ad88u)
#define model_get NATIVE(get_from_fn,0x5320aefcu)
#define controller_get NATIVE(get_from_fn,0x53228a90u)
#define canvas_slot NATIVE(slot_fn,0x5316ce30u)
#define view_factory NATIVE(get_from_fn,0x533ad7f0u)
#define view_add NATIVE(two_fn,0x533aba64u)
#define view_parent NATIVE(two_fn,0x533ac120u)
#define vector_erase NATIVE(two_fn,0x536b6f68u)
#define view_visible NATIVE(flag_fn,0x533ad3c0u)
#define view_invalidate NATIVE(one_fn,0x533ad308u)
#define base_draw NATIVE(two_fn,0x533ab9bcu)
#define timer_get NATIVE(get_fn,0x5320b01cu)
#define timer_start NATIVE(timer_start_fn,0x5322b468u)
#define timer_stop NATIVE(timer_stop_fn,0x5322b1ecu)

typedef struct { uint16_t width,height; uint32_t word_offset; } Bitmap;
typedef void (*copy_fn)(const void *,void *,int32_t,int32_t,
                       uint32_t,uint32_t,uint32_t,uint32_t,const Bitmap *,const uint32_t *);
typedef struct { uint32_t *vtable; } Listener;

#define DIAG_W 240u
#define DIAG_H 176u
#define DIAG_MS 15000u             /* ten pages of 1.5 s */
#define DIAG_TICKS 455u            /* the same in 33 ms ticks, used when the clock cannot be read */
#define PAGE_MS 1500u
#define NPAGES 10u
#define PROOF_MS 1000u
#define PROOF_TICKS 31u
#define USERDATA_MODEL 0x55063f30u
#define VT_LV 0x53b2f9e8u
#define VT_QV 0x53b41380u

#define NV 4u
static const uint8_t VIEW_ID[NV]={LOADED_V_TOP,LOADED_V_BOTTOM,LOADED_V_COUNTER,LOADED_V_TAB};

typedef struct {
    uint32_t magic;
    void *views[NV];
    uint32_t *pixels[NV];
    Bitmap bitmaps[NV];
    uint32_t pending_roll,running,attached,wanted;
    loaded_params params;
    loaded_buffers buffers;
    loaded engine;
} Ld;

enum { C_HOOK,C_ROOT,C_FILM,C_STATE,C_BUF0,C_BUF1,C_BUF2,C_BUF3,C_VIEWS,C_ATTACH,C_START,C_TICK,NCELLS };
enum { G_GREY,G_RUN,G_OK,G_BAD };
enum { S_FILM,S_STATE,S_BUF0,S_BUF1,S_BUF2,S_BUF3,S_VIEWS,S_ATTACH,S_START,S_TICK,NSTEPS };   /* step n is cell n + 2 */
enum { R_CLOCK,R_ROOT,R_FILM,R_CREATE,R_ATTACH,R_START,R_TICK,R_TRANS,R_CANVAS,R_EXT,NREASON };
enum { L_HOOK,L_BEFORE,L_AFTER,L_ATT,L_CALL1,L_CALL2,L_CALL3,L_CALL4,L_DRAW1,L_DRAW2,L_DRAW3,L_DRAW4,L_PANEL,L_CANCEL,L_ROOTFAIL,L_STALE,L_REATT,NLOGCODE };
static const char *const LOGNAME[NLOGCODE]={"HK","TB","TA","AT","C1","C2","C3","C4","D1","D2","D3","D4","PC","XC","RF","ST","RA"};
static const char *const REASON[NREASON]={"CLOCK","ROOT","FILM","CREATE","ATTACH","START","TICK","TRANS","CANVAS","EXT"};

/* Per view statistics, split by the controller type seen at the draw: 0 LiveView, 1 QuickView, 2 other. Index 4 is the panel, 5 an unknown view. */
typedef struct { uint32_t calls[3],copied[3],rej[3],parent_ok;int32_t abs[4]; } VStat;
typedef struct { uint8_t code,ctype,aux,pad;uint32_t ms; } LogE;
typedef struct { uint16_t code;uint8_t ctype,aux;uint32_t t; } GLogE;
#define NGLOG 160u
enum { GK_RELEASE=0x1001,GK_HOOK,GK_BEFORE,GK_AFTER,GK_ATT,GK_D1,GK_D2,GK_D3,GK_D4,GK_PD,GK_CANCEL };
static const char *const GNAME[11]={"RL","HK","TB","TA","AT","D1","D2","D3","D4","PD","XC"};
#define NLOG 24u

typedef struct {
    uint32_t magic;
    void *view,*root,*controller,*timer_model;
    uint32_t timer_id,transition,shots;
    uint32_t view_vtable[24],timer_vtable[3];
    Listener listener;
    Bitmap bitmap;
    Ld *ld;
    uint8_t cell[NCELLS];
    char info[3][16];
    uint32_t step,marked,sequence,diag_on,diag_attached,diag_ticks,diag_start,film,rec;
    uint32_t proof,proof_start,proof_ticks,page,variant,reattach,proof_seen,tk_panel,tk_ld;
    VStat vs[6];
    uint32_t surf[3][4];
    uint32_t hook,rootfail_h,rootfail_u,last_vt,trans_b,trans_a,ticks,stale,late,cancels[NREASON],last_cancel,last_cancel_hook;
    uint32_t t_hook,t_root,t_att,t_first,first_pending,first_draw_ms,panel_calls_shot,first_call_mask,first_copy_mask,ld_copies_shot,last_tick;
    LogE log[NLOG];uint32_t nlog;
    GLogE glog[NGLOG];uint32_t ng,ev_total,ev_logged;
    uint16_t ev_id[16];uint32_t ev_t[16];
    GLogE pre[8];uint32_t npre,t_pre;
    uint32_t pixels[DIAG_W*DIAG_H];            /* the proven size: Terminal's pixel array was 168,960 bytes */
} Diag;
#define MAGIC 0x44474c47u
/* Field offsets for the emulator checks (read-only data). */
const uint32_t grmod_layout[]={__builtin_offsetof(Diag,ld),__builtin_offsetof(Diag,cell),__builtin_offsetof(Diag,step),
    __builtin_offsetof(Diag,film),__builtin_offsetof(Diag,shots),__builtin_offsetof(Ld,pixels),__builtin_offsetof(Ld,engine),
    __builtin_offsetof(Ld,views),sizeof(Diag),sizeof(Ld),__builtin_offsetof(Diag,info),__builtin_offsetof(Diag,pixels),
    __builtin_offsetof(Diag,view),__builtin_offsetof(Ld,params),__builtin_offsetof(Diag,sequence),__builtin_offsetof(Diag,diag_on),
    /* 16 */ __builtin_offsetof(Diag,vs),sizeof(VStat),__builtin_offsetof(Diag,hook),__builtin_offsetof(Diag,rootfail_h),
    __builtin_offsetof(Diag,rootfail_u),__builtin_offsetof(Diag,last_vt),__builtin_offsetof(Diag,trans_b),__builtin_offsetof(Diag,trans_a),
    /* 24 */ __builtin_offsetof(Diag,ticks),__builtin_offsetof(Diag,stale),__builtin_offsetof(Diag,late),__builtin_offsetof(Diag,cancels),
    __builtin_offsetof(Diag,last_cancel),__builtin_offsetof(Diag,proof),__builtin_offsetof(Diag,page),__builtin_offsetof(Diag,variant),
    /* 32 */ __builtin_offsetof(Diag,t_root),__builtin_offsetof(Diag,t_att),__builtin_offsetof(Diag,t_first),__builtin_offsetof(Diag,first_draw_ms),
    __builtin_offsetof(Diag,panel_calls_shot),__builtin_offsetof(Diag,log),__builtin_offsetof(Diag,nlog),__builtin_offsetof(Diag,surf),
    /* 40 */ sizeof(LogE),__builtin_offsetof(Diag,ld_copies_shot),__builtin_offsetof(Diag,last_cancel_hook),__builtin_offsetof(Diag,reattach),
    /* 44 */ __builtin_offsetof(Diag,proof_seen),__builtin_offsetof(Diag,tk_panel),__builtin_offsetof(Diag,tk_ld),__builtin_offsetof(Diag,first_copy_mask),
    /* 48 */ __builtin_offsetof(Diag,glog),__builtin_offsetof(Diag,ng),sizeof(GLogE),__builtin_offsetof(Diag,pre),__builtin_offsetof(Diag,npre),
    __builtin_offsetof(Diag,t_pre),__builtin_offsetof(Diag,ev_total),__builtin_offsetof(Diag,ev_logged)};

static uint32_t rd32(const void *p){return *(const uint32_t *)p;}
static void *ptr(const void *p,uint32_t off){return *(void *const *)((const uint8_t *)p+off);}
static uint8_t byte(const void *p,uint32_t off){return *((const uint8_t *)p+off);}
static uint16_t half(const void *p,uint32_t off){return *(const uint16_t *)((const uint8_t *)p+off);}
static Diag *state(void){
    Diag *s=(Diag *)grmod_adapter_state;
    __asm__ volatile("dmb ish" ::: "memory");
    return s&&s->magic==MAGIC?s:0;
}
static void listener_noop(void *self){(void)self;}
static void zero_words(void *p,uint32_t bytes){uint32_t i;for(i=0;i<bytes/4u;i++)((volatile uint32_t *)p)[i]=0;}
static uint32_t ctype_of(const void *controller){
    uint32_t vt;
    if(!controller)return 2;
    vt=rd32(controller);
    return vt==VT_LV?0u:vt==VT_QV?1u:2u;
}
static uint32_t cur_ctype(void){
    void *app=app_get(),*model,*c;
    if(!app)return 2;model=model_get(app);if(!model)return 2;c=controller_get(model);
    return ctype_of(c);
}
static void glog(Diag *s,uint32_t code,uint32_t ctype,uint32_t aux){
    uint32_t now=0;GLogE *e;
    if(!grmod_clock_ms(&now))now=0;
    e=&s->glog[s->ng%NGLOG];e->code=(uint16_t)code;e->ctype=(uint8_t)ctype;e->aux=(uint8_t)aux;e->t=now;s->ng++;
}
static void log_ev(Diag *s,uint32_t code,uint32_t ctype,uint32_t aux){
    static const uint16_t GMAP[NLOGCODE]={GK_HOOK,GK_BEFORE,GK_AFTER,GK_ATT,0,0,0,0,GK_D1,GK_D2,GK_D3,GK_D4,GK_PD,GK_CANCEL,0,0,0};
    uint32_t now=0;
    if(GMAP[code])glog(s,GMAP[code],ctype,aux);
    if(s->nlog>=NLOG)return;
    s->log[s->nlog].code=(uint8_t)code;s->log[s->nlog].ctype=(uint8_t)ctype;s->log[s->nlog].aux=(uint8_t)aux;
    s->log[s->nlog].ms=grmod_clock_ms(&now)?now-s->t_hook:0u;
    s->nlog++;
}

/* ---------------------------------------------------------------- the panel: plain software drawing into its own buffer */
static void box(Diag *d,int32_t x,int32_t y,int32_t w,int32_t h,uint32_t c){
    int32_t xx,yy;
    for(yy=y;yy<y+h;yy++)for(xx=x;xx<x+w;xx++)
        if(xx>=0&&yy>=0&&xx<(int32_t)DIAG_W&&yy<(int32_t)DIAG_H)d->pixels[(uint32_t)yy*DIAG_W+(uint32_t)xx]=c;
}
static void glyph(Diag *d,uint32_t code,int32_t x,int32_t y,uint32_t c){
    int32_t g=code<256?ld_font_index[code]:-1,row,col;
    if(g<0)return;
    for(row=0;row<7;row++){
        uint32_t bits=ld_font_data[g*7+row];
        for(col=0;col<5;col++)if(bits&(16u>>col))box(d,x+col*2,y+row*2,2,2,c);
    }
}
static void text(Diag *d,const char *t,int32_t x,int32_t y,uint32_t c){
    int32_t i;for(i=0;t[i];i++)glyph(d,(uint8_t)t[i],x+i*12,y,c);
}
static const uint32_t CELL_COLOUR[4]={0xff5a5a5fu,0xff14a0fau,0xff46be28u,0xff2828dcu};   /* 0xAABBGGRR: grey, orange, green, red */
static const char *const LABEL[NCELLS]={"1","2","3","4","5A","5B","5C","5D","6","7","8","9"};
static uint32_t len(const char *s){uint32_t n=0;while(s[n])n++;return n;}
static void cat(char *dst,const char *s){while(*dst)dst++;while((*dst++=*s++)){}}
static void cat_dec(char *dst,uint32_t v){
    char tmp[11];uint32_t n=0,i;
    while(*dst)dst++;
    do{tmp[n++]=(char)('0'+v%10u);v/=10u;}while(v&&n<10);
    for(i=0;i<n;i++)dst[i]=tmp[n-1-i];
    dst[n]=0;
}
static void cat_sdec(char *dst,int32_t v){
    if(v<0){cat(dst,"-");cat_dec(dst,(uint32_t)(-(int64_t)v));}else cat_dec(dst,(uint32_t)v);
}
static void cat_hex4(char *dst,uint32_t v){
    uint32_t i;
    while(*dst)dst++;
    for(i=0;i<4;i++){uint32_t n=(v>>(12-4*i))&15u;dst[i]=(char)(n<10u?'0'+n:'A'+n-10u);}
    dst[4]=0;
}
static void pad(char *dst,uint32_t column){uint32_t n=len(dst);while(n<column&&n<22u){dst[n++]=' ';}dst[n]=0;}
static const char CTL[3]={'L','Q','O'};
static void row(Diag *d,uint32_t r,const char *t){text(d,t,8,4+(int32_t)r*15,0xffffffffu);}

static void page_cells(Diag *d){
    uint32_t i;
    text(d,"DIAG 1E",8,6,0xffffff00u);
    {char v[4];v[0]='V';v[1]=' ';v[2]=(char)('A'+(int32_t)d->variant);v[3]=0;text(d,v,150,6,0xffffff00u);}
    if(d->proof)text(d,"PROOF",90,6,0xff00ffffu);
    for(i=0;i<NCELLS;i++){
        int32_t cx=6+(int32_t)(i%6u)*38,cy=i<6u?24:70;
        text(d,LABEL[i],cx+(LABEL[i][1]?4:13),cy,0xffffffffu);
        box(d,cx,cy+16,34,24,CELL_COLOUR[d->cell[i]]);
    }
    text(d,d->info[0],8,118,0xffffffffu);
    text(d,d->info[1],8,136,0xffffffffu);
    text(d,d->info[2],8,154,0xffffffffu);
}
static void vname(char *l,uint32_t v){l[0]=0;if(v==4)cat(l,"N");else cat_dec(l,v+1u);pad(l,2);}
static void page_counts(Diag *d){
    char l[24];uint32_t v;
    row(d,0,"V  LV C/K   QV C/K");
    for(v=0;v<5;v++){
        vname(l,v);cat_dec(l,d->vs[v].calls[0]>999u?999u:d->vs[v].calls[0]);cat(l,"/");cat_dec(l,d->vs[v].copied[0]>999u?999u:d->vs[v].copied[0]);pad(l,11);
        cat_dec(l,d->vs[v].calls[1]>999u?999u:d->vs[v].calls[1]);cat(l,"/");cat_dec(l,d->vs[v].copied[1]>999u?999u:d->vs[v].copied[1]);
        row(d,1u+v,l);
    }
    l[0]=0;cat(l,"OTHER ");cat_dec(l,d->vs[0].calls[2]+d->vs[1].calls[2]+d->vs[2].calls[2]+d->vs[3].calls[2]+d->vs[4].calls[2]);cat(l," UNK ");
    cat_dec(l,d->vs[5].calls[0]+d->vs[5].calls[1]+d->vs[5].calls[2]);row(d,6,l);
}
static void rejtext(char *l,const VStat *v,uint32_t t){if(!v->calls[t])cat(l,"-");else cat_dec(l,v->rej[t]);}
static void page_rejects(Diag *d){
    char l[24];uint32_t v,t;
    row(d,0,"LAST REJECT LV QV");
    for(v=0;v<5;v++){vname(l,v);rejtext(l,&d->vs[v],0);pad(l,8);rejtext(l,&d->vs[v],1);row(d,1u+v,l);}
    row(d,6,"SURF W H STR FMT");
    for(t=0;t<2;t++){
        l[0]=0;l[0]=CTL[t];l[1]=0;pad(l,2);cat_dec(l,d->surf[t][0]);cat(l," ");cat_dec(l,d->surf[t][1]);cat(l," ");cat_dec(l,d->surf[t][2]);cat(l," ");cat_dec(l,d->surf[t][3]);
        row(d,7u+t,l);
    }
}
static void page_abs(Diag *d){
    char l[24];uint32_t v,k;
    row(d,0,"ABS X Y W H PAR");
    for(v=0;v<5;v++){
        vname(l,v);
        for(k=0;k<4;k++){cat_sdec(l,d->vs[v].abs[k]);cat(l," ");}
        cat_dec(l,d->vs[v].parent_ok);row(d,1u+v,l);
    }
    l[0]=0;cat(l,"NOW ");{char c[2];c[0]=CTL[cur_ctype()];c[1]=0;cat(l,c);}cat(l," VT ");cat_hex4(l,d->controller?rd32(d->controller):0u);row(d,7,l);
}
static void page_events(Diag *d){
    char l[24];
    row(d,0,"EVENT COUNTERS");
    l[0]=0;cat(l,"HOOK ");cat_dec(l,d->hook);row(d,1,l);
    l[0]=0;cat(l,"RTF H ");cat_dec(l,d->rootfail_h);cat(l," U ");cat_dec(l,d->rootfail_u);row(d,2,l);
    l[0]=0;cat(l,"LAST VT ");cat_hex4(l,d->last_vt);row(d,3,l);
    l[0]=0;cat(l,"TRANS B ");cat_dec(l,d->trans_b);cat(l," A ");cat_dec(l,d->trans_a);row(d,4,l);
    l[0]=0;cat(l,"TICKS ");cat_dec(l,d->ticks);cat(l," LATE ");cat_dec(l,d->late);row(d,5,l);
    l[0]=0;cat(l,"STALE ");cat_dec(l,d->stale);cat(l," SHOT ");cat_dec(l,d->shots);row(d,6,l);
    l[0]=0;cat(l,"PANEL CALLS ");cat_dec(l,d->panel_calls_shot);row(d,7,l);
    l[0]=0;cat(l,"FIRST DRAW ");cat_dec(l,d->first_draw_ms);cat(l," MS");row(d,8,l);
    l[0]=0;cat(l,"P");cat_hex4(l,(uint32_t)(uintptr_t)d);cat(l," V ");{char v[2];v[0]=(char)('A'+(int32_t)d->variant);v[1]=0;cat(l,v);}row(d,9,l);
    l[0]=0;cat(l,"TK1 P ");cat_dec(l,d->tk_panel);cat(l," L ");cat_dec(l,d->tk_ld);row(d,10,l);
}
static void page_cancels(Diag *d){
    char l[24];uint32_t i;
    row(d,0,"CANCELS BY REASON");
    for(i=0;i<NREASON;i+=2){
        l[0]=0;cat(l,REASON[i]);cat(l," ");cat_dec(l,d->cancels[i]);pad(l,11);
        if(i+1<NREASON){cat(l,REASON[i+1]);cat(l," ");cat_dec(l,d->cancels[i+1]);}
        row(d,1u+i/2u,l);
    }
    l[0]=0;cat(l,"LAST ");if(d->last_cancel)cat(l,REASON[d->last_cancel-1u]);else cat(l,"NONE");cat(l," HK ");cat_dec(l,d->last_cancel_hook);row(d,6,l);
    row(d,7,"LAST SHOT MS");
    l[0]=0;cat(l,"H>R ");cat_dec(l,d->t_root);cat(l," H>A ");cat_dec(l,d->t_att);row(d,8,l);
    l[0]=0;cat(l,"H>T ");cat_dec(l,d->t_first);cat(l," CLK ");cat_hex4(l,d->t_hook);row(d,9,l);
}
static void page_log(Diag *d,uint32_t first){
    char l[24];uint32_t i;
    for(i=0;i<11u;i++){
        uint32_t k=first+i;
        if(k>=d->nlog)break;
        l[0]=0;cat(l,LOGNAME[d->log[k].code]);cat(l," ");{char c[2];c[0]=CTL[d->log[k].ctype];c[1]=0;cat(l,c);}cat(l," ");cat_dec(l,d->log[k].ms);
        if(d->log[k].code==L_CALL1||d->log[k].code==L_CALL2||d->log[k].code==L_CALL3||d->log[k].code==L_CALL4||d->log[k].code==L_PANEL||d->log[k].code==L_CANCEL){
            cat(l," R");cat_dec(l,d->log[k].aux);
        }
        row(d,i,l);
    }
}
static void gname(char *l,uint32_t code){if(code>=GK_RELEASE&&code<=GK_CANCEL)cat(l,GNAME[code-GK_RELEASE]);else cat_hex4(l,code);}
static void page_glog(Diag *d){
    char l[24];uint32_t n=d->ng>8u?8u:d->ng,i;
    row(d,0,"LAST 8 EVENTS DT MS");
    for(i=0;i<n;i++){
        const GLogE *e=&d->glog[(d->ng-n+i)%NGLOG],*pv=i?&d->glog[(d->ng-n+i-1u)%NGLOG]:0;
        l[0]=0;gname(l,e->code);cat(l," ");{char c[2];c[0]=CTL[e->ctype];c[1]=0;cat(l,c);}cat(l," +");cat_dec(l,pv?e->t-pv->t:0u);
        row(d,1u+i,l);
    }
    l[0]=0;cat(l,"UI EV ");cat_dec(l,d->ev_total);cat(l," LOGGED ");cat_dec(l,d->ev_logged);row(d,10,l);
}
static void page_pre(Diag *d){
    char l[24];uint32_t i;
    row(d,0,"BEFORE LAST HOOK MS");
    for(i=0;i<d->npre&&i<8u;i++){
        l[0]=0;gname(l,d->pre[i].code);cat(l," ");{char c[2];c[0]=CTL[d->pre[i].ctype];c[1]=0;cat(l,c);}cat(l," -");cat_dec(l,d->t_pre-d->pre[i].t);
        row(d,1u+i,l);
    }
}
static void draw_panel(Diag *d){
    box(d,0,0,(int32_t)DIAG_W,(int32_t)DIAG_H,0xff101010u);
    box(d,0,0,(int32_t)DIAG_W,2,0xffffffffu);box(d,0,(int32_t)DIAG_H-2,(int32_t)DIAG_W,2,0xffffffffu);
    box(d,0,0,2,(int32_t)DIAG_H,0xffffffffu);box(d,(int32_t)DIAG_W-2,0,2,(int32_t)DIAG_H,0xffffffffu);
    switch(d->page){
    case 1:page_counts(d);break;
    case 2:page_rejects(d);break;
    case 3:page_abs(d);break;
    case 4:page_events(d);break;
    case 5:page_cancels(d);break;
    case 6:page_log(d,0);break;
    case 7:page_log(d,11);break;
    case 8:page_glog(d);break;
    case 9:page_pre(d);break;
    default:page_cells(d);break;
    }
}
static void refresh(Diag *d){
    uint32_t i;
    draw_panel(d);
    if(d->root){
        view_invalidate(d->root);
        if(d->diag_attached)view_invalidate(d->view);
        if(d->ld&&d->ld->attached)for(i=0;i<NV;i++)view_invalidate(d->ld->views[i]);
    }
}

/* ---------------------------------------------------------------- native tree (as camera_gr3.c) */
static void *fr_fail(Diag *s,uint32_t *counter,uint32_t code){if(s){(*counter)++;s->last_vt=code;}return 0;}
static void *find_root(Diag *s,uint32_t *counter,void **owner){
    void *app=app_get(),*model,*c,*root;uint32_t vt;
    if(!app)return fr_fail(s,counter,0xa000u);
    model=model_get(app);if(!model)return fr_fail(s,counter,0xb000u);
    c=controller_get(model);if(!c)return fr_fail(s,counter,0xc000u);
    vt=rd32(c);
    if(vt!=VT_LV&&vt!=VT_QV)return fr_fail(s,counter,vt&0xffffu);
    root=ptr(c,0x15c);if(!root||rd32(root)!=0x53c09f10u)return fr_fail(s,counter,0xe000u);
    if(canvas_slot(c,0)!=root&&canvas_slot(c,3)!=root)return fr_fail(s,counter,0xe001u);
    *owner=c;return root;
}
static int child_vector(void *root,uint32_t **begin,uint32_t **end){
    uintptr_t b=(uintptr_t)ptr(root,0xc),e=(uintptr_t)ptr(root,0x10),cap=(uintptr_t)ptr(root,0x14);
    if((b|e|cap)&3u)return 0;
    if(!b){*begin=0;*end=0;return !e&&!cap;}
    if(e<b||cap<e||cap-b>16384u)return 0;
    *begin=(uint32_t *)b;*end=(uint32_t *)e;return 1;
}
static void detach_one(void *root,void *v){
    uint32_t *it,*end;
    if(!v)return;
    view_visible(v,0);
    if(child_vector(root,&it,&end))for(;it!=end;it++)if(*it==(uint32_t)(uintptr_t)v){vector_erase((uint8_t *)root+8,it);break;}
    view_parent(v,0);
}
static void detach_ld(Diag *s){
    uint32_t i;
    if(s->root&&s->ld&&s->ld->attached){for(i=0;i<NV;i++)detach_one(s->root,s->ld->views[i]);s->ld->attached=0;view_invalidate(s->root);}
}
static void detach_all(Diag *s){
    void *root=s->root;
    if(!root)return;
    detach_ld(s);
    if(s->diag_attached){detach_one(root,s->view);s->diag_attached=0;}
    view_invalidate(root);s->root=0;s->controller=0;
}
/* Attach what is wanted and not yet attached; a changed root first detaches everything. 0 on any failure. */
static int attach_wanted(Diag *s,void *root,void *controller){
    uint32_t *begin,*end,i;
    if(s->root&&(s->root!=root||s->controller!=controller))detach_all(s);
    if(!child_vector(root,&begin,&end))return 0;
    if(s->diag_on&&!s->diag_attached){
        if(!s->view||ptr(s->view,4))return 0;
        view_add(root,s->view);s->root=root;s->controller=controller;view_visible(s->view,1);s->diag_attached=1;
    }
    if(s->ld&&s->ld->wanted&&!s->ld->attached){
        for(i=0;i<NV;i++)if(!s->ld->views[i]||ptr(s->ld->views[i],4))return 0;
        for(i=0;i<NV;i++)view_add(root,s->ld->views[i]);
        s->root=root;s->controller=controller;
        for(i=0;i<NV;i++)view_visible(s->ld->views[i],1);
        if(s->variant==0)((two_fn)(uintptr_t)(*(uint32_t **)root)[8])(root,s->ld->views[0]);   /* layout request, see the header */
        s->ld->attached=1;
    }
    s->root=root;s->controller=controller;
    view_invalidate(root);return 1;
}
static void *make_view(Diag *s,int32_t x,int32_t y,uint32_t w,uint32_t h){
    uint32_t descriptor[6];void *v;
    descriptor[0]=10;descriptor[1]=(uint32_t)x;descriptor[2]=(uint32_t)y;descriptor[3]=w;descriptor[4]=h;descriptor[5]=0;
    v=view_factory((void *)descriptor);
    if(!v)return 0;
    *(uint32_t **)v=s->view_vtable+2;view_visible(v,0);
    return v;
}

/* ---------------------------------------------------------------- timer */
static void disarm(Diag *s){
    uint32_t id=s->timer_id;s->timer_id=0;
    if(id&&s->timer_model)timer_stop(s->timer_model,id);
}
static void arm(Diag *s,uint32_t now,int have_clock){
    uint32_t delay=33,elapsed,dur;
    if(s->timer_id||s->transition)return;
    if(!(s->sequence||s->diag_on||(s->ld&&s->ld->running)))return;
    if(have_clock&&s->ld&&s->ld->running&&!s->proof&&s->ld->engine.active){
        elapsed=now-s->ld->engine.start;dur=loaded_duration(s->ld->params.film,s->ld->engine.moment);
        if(elapsed<dur&&dur-elapsed<delay)delay=dur-elapsed?dur-elapsed:1;
    }
    if(s->timer_model)s->timer_id=timer_start(s->timer_model,delay,&s->listener);
}

/* ---------------------------------------------------------------- the Loaded part */
static void release_ld(Diag *s){
    uint32_t i;Ld *ld=s->ld;
    if(!ld)return;
    detach_ld(s);
    for(i=0;i<NV;i++)if(ld->pixels[i]){heap_free(ld->pixels[i]);ld->pixels[i]=0;}
    s->ld=0;ld->magic=0;heap_free(ld);
}
static void drop_loaded(Diag *s){
    if(!s->ld)return;
    loaded_cancel(&s->ld->engine);s->ld->pending_roll=0;s->ld->running=0;s->ld->wanted=0;detach_ld(s);
}
static void count_cancel(Diag *s,uint32_t reason){
    if(reason<NREASON)s->cancels[reason]++;
    s->last_cancel=reason+1u;s->last_cancel_hook=s->hook;
    log_ev(s,L_CANCEL,cur_ctype(),reason);
}
static void fail_cell(Diag *d,uint32_t cell,uint32_t reason){d->cell[cell]=G_BAD;d->sequence=0;count_cancel(d,reason);}

static void step_film(Diag *d){
    const uint8_t *model=(const uint8_t *)(uintptr_t)USERDATA_MODEL,*rec;
    uintptr_t at;uint32_t set,look,movie;char *o=d->info[0];
    o[0]=0;
    rec=(const uint8_t *)ptr(model,4);at=(uintptr_t)rec;d->rec=(uint32_t)at;
    if(!rec){cat(o,"NO RECORD");fail_cell(d,C_FILM,R_FILM);return;}
    if(at&3u){cat(o,"MISALIGNED");fail_cell(d,C_FILM,R_FILM);return;}
    movie=rec[0x44];
    if(movie){cat(o,"MOVIE ");cat_dec(o,movie);fail_cell(d,C_FILM,R_FILM);return;}
    set=rec[0x1c0];
    if(set>2u){cat(o,"SET ");cat_dec(o,set);fail_cell(d,C_FILM,R_FILM);return;}
    look=rec[0x1c2+2u*set];
    d->film=loaded_film_of_look(look);
    cat(o,"L");cat_dec(o,look);cat(o," F");cat_dec(o,d->film);
    d->cell[C_FILM]=G_OK;
}
static void step_alloc(Diag *d,uint32_t step){
    uint32_t cell=step+2u,i;
    if(step==S_STATE){
        if(d->ld){d->cell[cell]=G_OK;return;}
        d->ld=(Ld *)heap_alloc(sizeof(Ld));
        if(!d->ld){fail_cell(d,cell,R_CREATE);return;}
        zero_words(d->ld,sizeof(Ld));d->ld->magic=MAGIC;loaded_init(&d->ld->engine);
        d->cell[cell]=G_OK;return;
    }
    i=step-S_BUF0;
    if(!d->ld||d->ld->pixels[i]){d->cell[cell]=G_OK;return;}
    d->ld->pixels[i]=(uint32_t *)heap_alloc(loaded_view_rect[VIEW_ID[i]][2]*loaded_view_rect[VIEW_ID[i]][3]*4u);
    if(!d->ld->pixels[i]){release_ld(d);fail_cell(d,cell,R_CREATE);return;}
    d->ld->buffers.pixels[VIEW_ID[i]]=d->ld->pixels[i];
    d->ld->buffers.stride[VIEW_ID[i]]=loaded_view_rect[VIEW_ID[i]][2];
    d->ld->buffers.capacity[VIEW_ID[i]]=loaded_view_rect[VIEW_ID[i]][2]*loaded_view_rect[VIEW_ID[i]][3];
    d->ld->bitmaps[i].width=loaded_view_rect[VIEW_ID[i]][2];d->ld->bitmaps[i].height=loaded_view_rect[VIEW_ID[i]][3];
    d->cell[cell]=G_OK;
}
static void step_views(Diag *d){
    uint32_t i;
    for(i=0;i<NV;i++){
        const uint16_t *r=loaded_view_rect[VIEW_ID[i]];
        if(d->ld->views[i])continue;
        d->ld->views[i]=make_view(d,r[0],r[1],r[2],r[3]);
        if(!d->ld->views[i]){fail_cell(d,C_VIEWS,R_CREATE);return;}
    }
    d->cell[C_VIEWS]=G_OK;
}
static void step_attach(Diag *d){
    void *controller=0,*root=find_root(d,&d->rootfail_u,&controller);
    if(!root){fail_cell(d,C_ATTACH,R_ROOT);return;}
    d->ld->wanted=1;
    if(!attach_wanted(d,root,controller)||!d->ld->attached){d->ld->wanted=0;fail_cell(d,C_ATTACH,R_ATTACH);return;}
    log_ev(d,L_ATT,ctype_of(controller),0);
    d->cell[C_ATTACH]=G_OK;
}
static void step_start(Diag *d){
    uint32_t now=0,n=d->shots-1u;loaded_params *p=&d->ld->params;
    if(!grmod_clock_ms(&now)){d->ld->wanted=0;detach_ld(d);fail_cell(d,C_START,R_CLOCK);return;}
    p->moment=LOADED_SHOT;p->film=d->film;p->frame=n%LOADED_ROLL_FRAMES+1u;
    p->roll=1u+n/LOADED_ROLL_FRAMES;if(p->roll>999999u)p->roll=999999u;
    p->tier=1;p->tab_mode=LOADED_PEEK;p->counter_mode=LOADED_PEEK;p->peek_ms=-1;p->tab_peek_ms=-2;p->counter_peek_ms=-2;
    p->month=12;p->year=0;p->thumbs=0;p->circled=-1;p->hold=0;
    d->ld->pending_roll=p->frame==LOADED_ROLL_FRAMES;
    if(loaded_start(&d->ld->engine,p,now)!=0){d->ld->wanted=0;detach_ld(d);fail_cell(d,C_START,R_START);return;}
    loaded_peek(&d->ld->engine,now);
    d->ld->running=1;
    d->cell[C_START]=G_OK;
}

/* ---- the proof phase: solid test patterns written straight into the four Loaded buffers, bypassing the renderer */
static void pbox(uint32_t *px,int32_t w,int32_t h,int32_t x,int32_t y,int32_t bw,int32_t bh,uint32_t c){
    int32_t xx,yy;
    for(yy=y;yy<y+bh;yy++)for(xx=x;xx<x+bw;xx++)
        if(xx>=0&&yy>=0&&xx<w&&yy<h)px[yy*w+xx]=c;
}
static void fill_proof(Diag *d){
    static const uint32_t COL[NV]={0xff0000ffu,0xff00ff00u,0xffff0000u,0xff00ffffu};      /* red, green, blue, yellow (0xAABBGGRR) */
    uint32_t i;
    for(i=0;i<NV;i++){
        const uint16_t *r=loaded_view_rect[VIEW_ID[i]];
        int32_t w=(int32_t)r[2],h=(int32_t)r[3],bw=w-12<72?w-12:72,bh=h-12,x=(w-bw)/2,y=(h-bh)/2,rw,col,g;
        uint32_t *px=d->ld->pixels[i],n;
        for(n=0;n<(uint32_t)(w*h);n++)px[n]=0;
        pbox(px,w,h,0,0,w,3,COL[i]);pbox(px,w,h,0,h-3,w,3,COL[i]);pbox(px,w,h,0,0,3,h,COL[i]);pbox(px,w,h,w-3,0,3,h,COL[i]);
        pbox(px,w,h,x,y,bw,bh,COL[i]);
        g=ld_font_index[(uint32_t)('1'+(int32_t)i)];
        if(g>=0)for(rw=0;rw<7;rw++){
            uint32_t bits=ld_font_data[g*7+rw];
            for(col=0;col<5;col++)if(bits&(16u>>col))pbox(px,w,h,w/2-8+col*3,h/2-10+rw*3,3,3,0xff000000u);
        }
    }
    d->ld->engine.dirty=(1u<<LOADED_VIEWS)-1u;
}
static void start_proof(Diag *d,uint32_t now){
    fill_proof(d);d->proof=1;d->proof_start=now;d->proof_ticks=0;d->proof_seen=0;view_invalidate(d->root);
}
static void end_proof(Diag *s,uint32_t now){
    Ld *ld=s->ld;loaded_params p=ld->params;
    s->proof=0;
    loaded_init(&ld->engine);ld->params=p;
    if(loaded_start(&ld->engine,&ld->params,now)!=0){count_cancel(s,R_START);drop_loaded(s);return;}
    loaded_peek(&ld->engine,now);
}
static void step_tick(Diag *d){
    uint32_t now=0;int r;
    if(!grmod_clock_ms(&now)){drop_loaded(d);fail_cell(d,C_TICK,R_CLOCK);return;}
    r=loaded_tick(&d->ld->engine,&d->ld->buffers,now);
    if(r<0){drop_loaded(d);fail_cell(d,C_TICK,R_TICK);return;}
    if(r&0x1f)view_invalidate(d->root);
    d->cell[C_TICK]=G_OK;
    start_proof(d,now);
}
static void run_step(Diag *d){
    switch(d->step){
    case S_FILM:step_film(d);break;
    case S_STATE:case S_BUF0:case S_BUF1:case S_BUF2:case S_BUF3:step_alloc(d,d->step);break;
    case S_VIEWS:step_views(d);break;
    case S_ATTACH:step_attach(d);break;
    case S_START:step_start(d);break;
    default:step_tick(d);break;
    }
}

static void cancel_why(Diag *s,uint32_t reason){
    count_cancel(s,reason);
    disarm(s);drop_loaded(s);s->sequence=0;s->marked=0;s->proof=0;s->reattach=0;s->diag_on=0;
    detach_all(s);
}
static Diag *create(void);
void grmod_cancel(void){
    Diag *s=state();
    if(!s){s=create();if(!s)return;}             /* the first shutter release makes the block, so the log starts there */
    glog(s,GK_RELEASE,cur_ctype(),0);
    cancel_why(s,R_EXT);
}

static void update(Diag *s){
    void *controller=0,*root;uint32_t now=0,elapsed,page,changed;int have_clock,r;
    root=find_root(s,&s->rootfail_u,&controller);
    if(!root){cancel_why(s,R_ROOT);return;}
    if(!attach_wanted(s,root,controller)){cancel_why(s,R_ATTACH);return;}
    have_clock=grmod_clock_ms(&now);
    if(s->first_pending){s->first_pending=0;if(have_clock)s->t_first=now-s->t_hook;}
    if(have_clock){if(s->last_tick&&now-s->last_tick>100u)s->late++;s->last_tick=now;}
    s->diag_ticks++;
    elapsed=have_clock?now-s->diag_start:s->diag_ticks*33u;
    page=(elapsed/PAGE_MS)%NPAGES;changed=page!=s->page;s->page=page;
    if(s->sequence){
        if(!s->marked){s->cell[C_FILM+s->step]=G_RUN;s->marked=1;refresh(s);}
        else{
            s->marked=0;run_step(s);
            if(s->sequence&&++s->step>=NSTEPS)s->sequence=0;
            refresh(s);
        }
    }else if(s->proof){
        s->proof_ticks++;
        if(have_clock?(now-s->proof_start>=PROOF_MS):(s->proof_ticks>=PROOF_TICKS)){
            if(have_clock)end_proof(s,now);else{s->proof=0;drop_loaded(s);count_cancel(s,R_CLOCK);}
        }else refresh(s);
    }else if(s->ld&&s->ld->running){
        if(!have_clock){drop_loaded(s);count_cancel(s,R_CLOCK);refresh(s);}
        else{
            Ld *ld=s->ld;
            if(ld->pending_roll&&ld->engine.active&&now-ld->engine.start>=loaded_duration(ld->params.film,ld->engine.moment)){
                ld->pending_roll=0;ld->params.moment=LOADED_ROLL;ld->params.hold=1;
                if(loaded_start(&ld->engine,&ld->params,now)!=0){drop_loaded(s);refresh(s);}
            }
            if(s->ld&&s->ld->running){
                r=loaded_tick(&ld->engine,&ld->buffers,now);
                if(r<0||!(r&0x300)){
                    if(!s->ld_copies_shot){s->stale++;log_ev(s,L_STALE,ctype_of(controller),0);}
                    drop_loaded(s);
                }else if(r&0x1f){uint32_t i;view_invalidate(root);for(i=0;i<NV;i++)view_invalidate(ld->views[i]);}
            }
        }
    }
    if(s->diag_on&&!s->sequence&&(changed||(s->diag_ticks&3u)==0))refresh(s);
    if(s->diag_on&&!s->sequence){
        int expired=have_clock?(now-s->diag_start>=DIAG_MS):(s->diag_ticks>=DIAG_TICKS);
        if(expired){
            if(s->diag_attached){detach_one(s->root,s->view);s->diag_attached=0;view_invalidate(s->root);}
            s->diag_on=0;
        }
    }
    if(!s->diag_on&&!s->sequence&&!(s->ld&&(s->ld->running||s->ld->wanted))){detach_all(s);return;}
    arm(s,now,have_clock);
}

static Diag *create(void){
    Diag *s=state();uint32_t i;
    if(s)return s;
    s=(Diag *)heap_alloc(sizeof(*s));if(!s)return 0;
    zero_words(s,sizeof(*s));
    for(i=0;i<24;i++)s->view_vtable[i]=((const uint32_t *)(uintptr_t)0x53c0a8a0u)[i];
    s->view_vtable[2+0x4c/4]=(uint32_t)(uintptr_t)grmod_draw;
    s->timer_vtable[0]=(uint32_t)(uintptr_t)listener_noop;
    s->timer_vtable[1]=(uint32_t)(uintptr_t)listener_noop;
    s->timer_vtable[2]=(uint32_t)(uintptr_t)grmod_timer_expired;
    s->listener.vtable=s->timer_vtable;
    s->bitmap.width=DIAG_W;s->bitmap.height=DIAG_H;
    s->timer_model=timer_get();
    s->magic=MAGIC;
    __asm__ volatile("dmb ish" ::: "memory");
    grmod_adapter_state=s;return s;
}

void grmod_on_shot(void){
    Diag *s;void *controller=0,*root;uint32_t now=0,later=0,i;int clock_ok;
    s=create();if(!s)return;                      /* the counters live in the block: made before anything can return early */
    s->hook++;
    clock_ok=grmod_clock_ms(&now);
    s->t_hook=now;s->t_root=0;s->t_att=0;s->t_first=0;s->first_pending=0;s->first_draw_ms=0;s->panel_calls_shot=0;
    s->first_call_mask=0;s->first_copy_mask=0;s->ld_copies_shot=0;s->tk_panel=0;s->tk_ld=0;s->last_tick=now;s->nlog=0;
    {   /* the eight events before this hook, with their distance to it */
        uint32_t k,n=s->ng>8u?8u:s->ng;
        s->t_pre=now;s->npre=n;
        for(k=0;k<n;k++)s->pre[k]=s->glog[(s->ng-n+k)%NGLOG];
    }
    log_ev(s,L_HOOK,cur_ctype(),0);
    root=find_root(s,&s->rootfail_h,&controller);
    if(!root){log_ev(s,L_ROOTFAIL,2,0);cancel_why(s,R_ROOT);return;}
    if(grmod_clock_ms(&later))s->t_root=later-now;
    disarm(s);s->transition=0;
    drop_loaded(s);s->reattach=0;
    s->variant=(s->hook+2u)%3u;                  /* hooks 1,4,7: A timer ticks plus layout request; 2,5,8: B steps inside the hook; 3,6,9: C control */
    s->shots++;
    for(i=0;i<NCELLS;i++)s->cell[i]=G_GREY;
    for(i=0;i<3;i++)s->info[i][0]=0;
    s->cell[C_HOOK]=clock_ok?G_OK:G_BAD;s->cell[C_ROOT]=G_OK;
    cat(s->info[1],"SHOT ");cat_dec(s->info[1],s->shots);
    cat(s->info[2],"P");cat_hex4(s->info[2],(uint32_t)(uintptr_t)s);
    s->step=0;s->marked=0;s->sequence=1;s->diag_on=1;s->diag_ticks=0;s->diag_start=now;s->film=LD_FILMS-1u;
    s->proof=0;s->page=0;
    if(!s->view){
        s->view=make_view(s,464,259,DIAG_W,DIAG_H);
        if(!s->view){cancel_why(s,R_CREATE);return;}
    }
    if(!attach_wanted(s,root,controller)){cancel_why(s,R_ATTACH);return;}
    refresh(s);
    if(s->variant==1){                           /* B: the Loaded steps up to the attach run here, as the panel's own attach did */
        uint32_t k;
        for(k=S_FILM;k<=S_ATTACH&&s->sequence;k++){s->step=k;run_step(s);}
        if(s->sequence)s->step=S_START;
        refresh(s);
    }
    if(grmod_clock_ms(&later))s->t_att=later-now;
    s->first_pending=1;
    arm(s,now,clock_ok);
}

/* The sixth hook: every UI event the camera dispatches (0x53228ab4), logged once per id and 500 ms with the clock time. */
void grmod_on_event(void *app,const uint16_t *event){
    Diag *s=state();uint32_t id,now=0,slot;
    (void)app;
    if(!s||!event)return;
    id=event[0];
    s->ev_total++;
    if(!grmod_clock_ms(&now))return;
    slot=id&15u;
    if(s->ev_id[slot]==id&&now-s->ev_t[slot]<500u)return;
    s->ev_id[slot]=(uint16_t)id;s->ev_t[slot]=now;
    s->ev_logged++;
    {GLogE *e=&s->glog[s->ng%NGLOG];e->code=(uint16_t)id;e->ctype=2;e->aux=0;e->t=now;s->ng++;}
}

void grmod_timer_expired(void *listener,uint32_t id){
    Diag *s=state();
    if(!s||listener!=&s->listener||!id||id!=s->timer_id)return;
    s->timer_id=0;
    s->ticks++;
    if(s->transition)return;
    update(s);
}
void grmod_before_transition(void *old_controller,uint32_t destination_id){
    Diag *s=state();uint32_t id=destination_id-0x08000000u;if(!s)return;
    ++s->transition;s->trans_b++;
    log_ev(s,L_BEFORE,ctype_of(old_controller),id&0xffu);
    if(id<=2||(id>=0x0cu&&id<=0x11u)){disarm(s);detach_all(s);}
    else cancel_why(s,R_TRANS);
}
void grmod_after_transition(void){
    Diag *s=state();if(!s||!s->transition)return;
    s->trans_a++;
    log_ev(s,L_AFTER,cur_ctype(),0);
    if(--s->transition)return;
    update(s);
}
void grmod_before_canvas_delete(void *root){
    Diag *s=state();if(s&&s->root==root)cancel_why(s,R_CANVAS);
}
void grmod_before_audio_shutdown(void){}

uint32_t loaded_film_of_look(uint32_t look){
    if(look>=64u&&look<64u+LD_SLOTS)return ld_film_of_slot[look-64u];
    return LD_FILMS-1u;
}
uint32_t loaded_selected_film(void){return 0xffffffffu;}

static int32_t maximum(int32_t a,int32_t b){return a>b?a:b;}
static int32_t minimum(int32_t a,int32_t b){return a<b?a:b;}

/* Reject codes (also in the README): 1 no surface, root or transition running; 2 view not on / not attached / Loaded not running;
 * 3 view unknown or no pixel buffer; 4 nothing visible in this view (not dirty); 5 view hidden byte; 6 parent is not the root;
 * 7 surface is not the root's surface; 8 surface format byte is not 5; 9 surface geometry unusable; 10 surface size overflow;
 * 11 absolute rectangle unusable or differs from the view's size; 12 clip rectangle unusable; 13 empty intersection; 0 copied. */
#define REJECT(n) do{rej=(n);goto finish;}while(0)
void grmod_draw(void *view,void *surface){
    static const uint8_t context[8]={0,0,0,0,0,0,0,0};
    Diag *s=state();const int32_t *absolute,*clip;uint32_t stride,height,width,visible_h,capacity,i,idx=5,rej=1,ct=2;
    int32_t x0,y0,x1,y1,sx,sy,vw=0,vh=0;uintptr_t pixels;const Bitmap *bitmap=0;const uint32_t *source=0;VStat *vs=0;
    if(!s)goto finish;
    if(view==s->view)idx=4;
    else if(s->ld)for(i=0;i<NV;i++)if(s->ld->views[i]==view){idx=i;break;}
    ct=ctype_of(s->controller);
    vs=&s->vs[idx];vs->calls[ct]++;
    {
        const int32_t *a=(const int32_t *)((const uint8_t *)view+0x30);
        vs->abs[0]=a[0];vs->abs[1]=a[1];vs->abs[2]=a[2];vs->abs[3]=a[3];
        vs->parent_ok=ptr(view,4)==s->root;
    }
    if(idx==4){
        s->panel_calls_shot++;
        if(!(s->first_call_mask&(1u<<4))){
            uint32_t now=0;
            s->first_call_mask|=1u<<4;
            if(grmod_clock_ms(&now))s->first_draw_ms=now-s->t_hook;
            s->tk_panel=s->diag_ticks;
        }
    }
    if(!surface||!s->root||s->transition)REJECT(1);
    if(idx==4){
        if(!s->diag_on||!s->diag_attached)REJECT(2);
        vw=(int32_t)DIAG_W;vh=(int32_t)DIAG_H;bitmap=&s->bitmap;source=s->pixels;
    }else if(idx==5)REJECT(3);
    else{
        Ld *ld=s->ld;
        if(!ld->attached||!ld->running)REJECT(2);
        if(!ld->pixels[idx])REJECT(3);
        if(!(ld->engine.dirty&(1u<<VIEW_ID[idx])))REJECT(4);
        vw=(int32_t)loaded_view_rect[VIEW_ID[idx]][2];vh=(int32_t)loaded_view_rect[VIEW_ID[idx]][3];
        bitmap=&ld->bitmaps[idx];source=ld->pixels[idx];
    }
    if(!byte(view,0x9e))REJECT(5);
    if(!vs->parent_ok)REJECT(6);
    if(ptr(s->root,0xec)!=surface)REJECT(7);
    if(byte(surface,2)!=5)REJECT(8);
    stride=half(surface,0x18);height=half(surface,0x1a);
    width=half(surface,0x1c);visible_h=half(surface,0x1e);pixels=(uintptr_t)ptr(surface,8);
    s->surf[ct][0]=width;s->surf[ct][1]=visible_h;s->surf[ct][2]=stride;s->surf[ct][3]=byte(surface,2);
    if(!stride||stride>4096||!height||height>4096||!width||width>stride||!visible_h||visible_h>height||
       !pixels||(pixels&3u))REJECT(9);
    capacity=stride*height*4u;if(pixels>0xffffffffu-capacity)REJECT(10);
    absolute=(const int32_t *)((const uint8_t *)view+0x30);
    clip=(const int32_t *)((const uint8_t *)view+0x64);
    if(absolute[0]<-4096||absolute[0]>4096||absolute[1]<-4096||absolute[1]>4096||
       absolute[2]!=vw||absolute[3]!=vh)REJECT(11);
    if(clip[0]<-4096||clip[0]>4096||clip[1]<-4096||clip[1]>4096||
       clip[2]<=0||clip[2]>4096||clip[3]<=0||clip[3]>4096)REJECT(12);
    x0=maximum(maximum(absolute[0],clip[0]),0);y0=maximum(maximum(absolute[1],clip[1]),0);
    x1=minimum(minimum(absolute[0]+vw,clip[0]+clip[2]),(int32_t)width);
    y1=minimum(minimum(absolute[1]+vh,clip[1]+clip[3]),(int32_t)visible_h);
    sx=x0-absolute[0];sy=y0-absolute[1];
    if(x1<=x0||y1<=y0||sx<0||sy<0||sx+x1-x0>vw||sy+y1-y0>vh)REJECT(13);
    NATIVE(copy_fn,0x5320a020u)(context,surface,absolute[0],absolute[1],
        (uint32_t)sx,(uint32_t)sy,(uint32_t)(x1-x0),(uint32_t)(y1-y0),bitmap,source);
    vs->copied[ct]++;rej=0;
    if(idx<4){if(!s->ld_copies_shot)s->tk_ld=s->diag_ticks;s->ld_copies_shot++;}
finish:
    if(vs){
        vs->rej[ct]=rej;
        if(idx<4&&!(s->first_call_mask&(1u<<idx))){s->first_call_mask|=1u<<idx;log_ev(s,L_CALL1+idx,ct,rej);}
        if(idx<4&&rej==0&&!(s->first_copy_mask&(1u<<idx))){s->first_copy_mask|=1u<<idx;log_ev(s,L_DRAW1+idx,ct,0);}
        if(idx==4&&!(s->first_call_mask&(1u<<5))){s->first_call_mask|=1u<<5;log_ev(s,L_PANEL,ct,rej);}
    }
    base_draw(view,surface);
}
