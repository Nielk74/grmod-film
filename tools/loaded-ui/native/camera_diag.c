/* SPDX-License-Identifier: GPL-2.0-only */
/* Loaded stage 1d: DIAGNOSTIC adapter. Same hooks, services and Loaded sequence as camera_loaded.c, but every completed shot
 * first draws a diagnostic panel with ONE owned view at the Terminal's rectangle (464,259, 240x176), created, attached, drawn
 * and sized exactly as camera_gr3.c did in the build that ran on the camera (a single heap block holding the pixels, 172 KB).
 * The panel does not depend on anything it reports on. It shows twelve step cells (grey = not reached, orange = running,
 * green = ok, red = failed). The real Loaded sequence then runs one step per timer tick AFTER the panel exists, the running
 * step shown in orange one tick before it executes, so a failure (or a hang) leaves the failing cell on the screen:
 *   1 hook fired and clock read   2 root found   3 film read   4 Loaded state allocated   5A..5D the four pixel buffers
 *   6 four views created   7 views attached   8 loaded_start accepted   9 first tick done
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
#define DIAG_MS 6000u
#define DIAG_TICKS 182u            /* 6 s of 33 ms ticks, used when the clock cannot be read */
#define USERDATA_MODEL 0x55063f30u

#define NV 4u
static const uint8_t VIEW_ID[NV]={LOADED_V_TOP,LOADED_V_BOTTOM,LOADED_V_COUNTER,LOADED_V_TAB};

/* The Loaded part: its own allocations, made only after the panel exists. */
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
    uint32_t pixels[DIAG_W*DIAG_H];            /* the proven size: Terminal's pixel array was 168,960 bytes */
} Diag;
#define MAGIC 0x44474c47u
/* Field offsets for the emulator checks (read-only data). */
const uint32_t grmod_layout[]={__builtin_offsetof(Diag,ld),__builtin_offsetof(Diag,cell),__builtin_offsetof(Diag,step),
    __builtin_offsetof(Diag,film),__builtin_offsetof(Diag,shots),__builtin_offsetof(Ld,pixels),__builtin_offsetof(Ld,engine),
    __builtin_offsetof(Ld,views),sizeof(Diag),sizeof(Ld),__builtin_offsetof(Diag,info),__builtin_offsetof(Diag,pixels),
    __builtin_offsetof(Diag,view),__builtin_offsetof(Ld,params),__builtin_offsetof(Diag,sequence),__builtin_offsetof(Diag,diag_on)};

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
static void cat(char *dst,const char *s){while(*dst)dst++;while((*dst++=*s++)){}}
static void cat_dec(char *dst,uint32_t v){
    char tmp[11];uint32_t n=0,i;
    while(*dst)dst++;
    do{tmp[n++]=(char)('0'+v%10u);v/=10u;}while(v&&n<10);
    for(i=0;i<n;i++)dst[i]=tmp[n-1-i];
    dst[n]=0;
}
static void cat_hex4(char *dst,uint32_t v){
    uint32_t i;
    while(*dst)dst++;
    for(i=0;i<4;i++){uint32_t n=(v>>(12-4*i))&15u;dst[i]=(char)(n<10u?'0'+n:'A'+n-10u);}
    dst[4]=0;
}
static void draw_panel(Diag *d){
    uint32_t i;
    box(d,0,0,(int32_t)DIAG_W,(int32_t)DIAG_H,0xff101010u);
    box(d,0,0,(int32_t)DIAG_W,2,0xffffffffu);box(d,0,(int32_t)DIAG_H-2,(int32_t)DIAG_W,2,0xffffffffu);
    box(d,0,0,2,(int32_t)DIAG_H,0xffffffffu);box(d,(int32_t)DIAG_W-2,0,2,(int32_t)DIAG_H,0xffffffffu);
    text(d,"DIAG 1D",8,6,0xffffff00u);
    for(i=0;i<NCELLS;i++){
        int32_t cx=6+(int32_t)(i%6u)*38,cy=i<6u?24:70;
        text(d,LABEL[i],cx+(LABEL[i][1]?4:13),cy,0xffffffffu);
        box(d,cx,cy+16,34,24,CELL_COLOUR[d->cell[i]]);
    }
    text(d,d->info[0],8,118,0xffffffffu);
    text(d,d->info[1],8,136,0xffffffffu);
    text(d,d->info[2],8,154,0xffffffffu);
}
static void refresh(Diag *d){draw_panel(d);if(d->root)view_invalidate(d->root);}

/* ---------------------------------------------------------------- native tree (as camera_gr3.c) */
static void *find_root(void **owner){
    void *app=app_get(),*model,*c,*root;uint32_t vt;
    if(!app)return 0;model=model_get(app);if(!model)return 0;
    c=controller_get(model);if(!c)return 0;vt=rd32(c);
    if(vt!=0x53b2f9e8u&&vt!=0x53b41380u)return 0;
    root=ptr(c,0x15c);if(!root||rd32(root)!=0x53c09f10u)return 0;
    if(canvas_slot(c,0)!=root&&canvas_slot(c,3)!=root)return 0;
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
        if(!s->view||ptr(s->view,4))return 0;       /* our detached object must not belong to another native tree */
        view_add(root,s->view);s->root=root;s->controller=controller;view_visible(s->view,1);s->diag_attached=1;
    }
    if(s->ld&&s->ld->wanted&&!s->ld->attached){
        for(i=0;i<NV;i++)if(!s->ld->views[i]||ptr(s->ld->views[i],4))return 0;
        for(i=0;i<NV;i++)view_add(root,s->ld->views[i]);
        s->root=root;s->controller=controller;
        for(i=0;i<NV;i++)view_visible(s->ld->views[i],1);
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
    if(have_clock&&s->ld&&s->ld->running&&s->ld->engine.active){
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
static void fail_cell(Diag *d,uint32_t cell){d->cell[cell]=G_BAD;d->sequence=0;}

static void step_film(Diag *d){
    const uint8_t *model=(const uint8_t *)(uintptr_t)USERDATA_MODEL,*rec;
    uintptr_t at;uint32_t set,look,movie;char *o=d->info[0];
    o[0]=0;
    rec=(const uint8_t *)ptr(model,4);at=(uintptr_t)rec;d->rec=(uint32_t)at;
    if(!rec){cat(o,"NO RECORD");fail_cell(d,C_FILM);return;}
    if(at&3u){cat(o,"MISALIGNED");fail_cell(d,C_FILM);return;}
    movie=rec[0x44];
    if(movie){cat(o,"MOVIE ");cat_dec(o,movie);fail_cell(d,C_FILM);return;}
    set=rec[0x1c0];
    if(set>2u){cat(o,"SET ");cat_dec(o,set);fail_cell(d,C_FILM);return;}
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
        if(!d->ld){fail_cell(d,cell);return;}
        zero_words(d->ld,sizeof(Ld));d->ld->magic=MAGIC;loaded_init(&d->ld->engine);
        d->cell[cell]=G_OK;return;
    }
    i=step-S_BUF0;
    if(!d->ld||d->ld->pixels[i]){d->cell[cell]=G_OK;return;}
    d->ld->pixels[i]=(uint32_t *)heap_alloc(loaded_view_rect[VIEW_ID[i]][2]*loaded_view_rect[VIEW_ID[i]][3]*4u);
    if(!d->ld->pixels[i]){release_ld(d);fail_cell(d,cell);return;}   /* a failed piece frees everything allocated for Loaded */
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
        if(!d->ld->views[i]){fail_cell(d,C_VIEWS);return;}          /* created views are kept for the next shot */
    }
    d->cell[C_VIEWS]=G_OK;
}
static void step_attach(Diag *d){
    void *controller=0,*root=find_root(&controller);
    if(!root){fail_cell(d,C_ATTACH);return;}
    d->ld->wanted=1;
    if(!attach_wanted(d,root,controller)||!d->ld->attached){d->ld->wanted=0;fail_cell(d,C_ATTACH);return;}
    d->cell[C_ATTACH]=G_OK;
}
static void step_start(Diag *d){
    uint32_t now=0,n=d->shots-1u;loaded_params *p=&d->ld->params;
    if(!grmod_clock_ms(&now)){d->ld->wanted=0;detach_ld(d);fail_cell(d,C_START);return;}
    p->moment=LOADED_SHOT;p->film=d->film;p->frame=n%LOADED_ROLL_FRAMES+1u;
    p->roll=1u+n/LOADED_ROLL_FRAMES;if(p->roll>999999u)p->roll=999999u;
    p->tier=1;p->tab_mode=LOADED_PEEK;p->counter_mode=LOADED_PEEK;p->peek_ms=-1;p->tab_peek_ms=-2;p->counter_peek_ms=-2;
    p->month=12;p->year=0;p->thumbs=0;p->circled=-1;p->hold=0;
    d->ld->pending_roll=p->frame==LOADED_ROLL_FRAMES;
    if(loaded_start(&d->ld->engine,p,now)!=0){d->ld->wanted=0;detach_ld(d);fail_cell(d,C_START);return;}
    loaded_peek(&d->ld->engine,now);
    d->ld->running=1;
    d->cell[C_START]=G_OK;
}
static void step_tick(Diag *d){
    uint32_t now=0;int r;
    if(!grmod_clock_ms(&now)){drop_loaded(d);fail_cell(d,C_TICK);return;}
    r=loaded_tick(&d->ld->engine,&d->ld->buffers,now);
    if(r<0){drop_loaded(d);fail_cell(d,C_TICK);return;}
    if(r&0x1f)view_invalidate(d->root);
    d->cell[C_TICK]=G_OK;
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

static void finish_loaded(Diag *s){drop_loaded(s);}

void grmod_cancel(void){
    Diag *s=state();
    if(!s)return;
    disarm(s);drop_loaded(s);s->sequence=0;s->marked=0;s->diag_on=0;
    detach_all(s);
}

static void update(Diag *s){
    void *controller=0,*root;uint32_t now=0;int have_clock,r;
    root=find_root(&controller);
    if(!root||!attach_wanted(s,root,controller)){grmod_cancel();return;}
    have_clock=grmod_clock_ms(&now);
    s->diag_ticks++;
    if(s->sequence){
        if(!s->marked){s->cell[C_FILM+s->step]=G_RUN;s->marked=1;refresh(s);}       /* shown before the step runs */
        else{
            s->marked=0;run_step(s);
            if(s->sequence&&++s->step>=NSTEPS)s->sequence=0;
            refresh(s);
        }
    }else if(s->ld&&s->ld->running){
        if(!have_clock){drop_loaded(s);refresh(s);}
        else{
            Ld *ld=s->ld;
            /* frame 36: the end of the roll follows its shot without a break */
            if(ld->pending_roll&&ld->engine.active&&now-ld->engine.start>=loaded_duration(ld->params.film,ld->engine.moment)){
                ld->pending_roll=0;ld->params.moment=LOADED_ROLL;ld->params.hold=1;
                if(loaded_start(&ld->engine,&ld->params,now)!=0){drop_loaded(s);refresh(s);}
            }
            if(s->ld&&s->ld->running){
                r=loaded_tick(&ld->engine,&ld->buffers,now);
                if(r<0||!(r&0x300))finish_loaded(s);
                else if(r&0x1f)view_invalidate(root);
            }
        }
    }
    if(s->diag_on&&!s->sequence){
        int expired=have_clock?(now-s->diag_start>=DIAG_MS):(s->diag_ticks>=DIAG_TICKS);
        if(expired){
            if(s->diag_attached){detach_one(s->root,s->view);s->diag_attached=0;view_invalidate(s->root);}
            s->diag_on=0;
        }
    }
    if(!s->diag_on&&!s->sequence&&!(s->ld&&s->ld->running)){detach_all(s);return;}
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
    Diag *s;void *controller=0,*root;uint32_t now=0,i;int clock_ok;
    root=find_root(&controller);if(!root){grmod_cancel();return;}
    s=create();if(!s)return;
    disarm(s);s->transition=0;
    drop_loaded(s);                              /* a shot while a moment shows restarts everything */
    s->shots++;
    for(i=0;i<NCELLS;i++)s->cell[i]=G_GREY;
    for(i=0;i<3;i++)s->info[i][0]=0;
    clock_ok=grmod_clock_ms(&now);
    s->cell[C_HOOK]=clock_ok?G_OK:G_BAD;s->cell[C_ROOT]=G_OK;
    cat(s->info[1],"SHOT ");cat_dec(s->info[1],s->shots);
    cat(s->info[2],"P");cat_hex4(s->info[2],(uint32_t)(uintptr_t)s);
    s->step=0;s->marked=0;s->sequence=1;s->diag_on=1;s->diag_ticks=0;s->diag_start=now;s->film=LD_FILMS-1u;
    if(!s->view){
        s->view=make_view(s,464,259,DIAG_W,DIAG_H);
        if(!s->view){grmod_cancel();return;}
    }
    if(!attach_wanted(s,root,controller)){grmod_cancel();return;}
    refresh(s);
    arm(s,now,clock_ok);
}

void grmod_timer_expired(void *listener,uint32_t id){
    Diag *s=state();
    if(!s||listener!=&s->listener||!id||id!=s->timer_id)return;
    s->timer_id=0;
    if(s->transition)return;
    update(s);
}
void grmod_before_transition(void *old_controller,uint32_t destination_id){
    Diag *s=state();uint32_t id=destination_id-0x08000000u;(void)old_controller;if(!s)return;
    ++s->transition;
    if(id<=2||(id>=0x0cu&&id<=0x11u)){disarm(s);detach_all(s);}
    else grmod_cancel();
}
void grmod_after_transition(void){
    Diag *s=state();if(!s||!s->transition)return;
    if(--s->transition)return;
    update(s);
}
void grmod_before_canvas_delete(void *root){
    Diag *s=state();if(s&&s->root==root)grmod_cancel();
}
/* The silent build never patches the audio shutdown hook: this callback is unreachable and does nothing. */
void grmod_before_audio_shutdown(void){}

uint32_t loaded_film_of_look(uint32_t look){
    if(look>=64u&&look<64u+LD_SLOTS)return ld_film_of_slot[look-64u];
    return LD_FILMS-1u;
}
uint32_t loaded_selected_film(void){return 0xffffffffu;}   /* the diagnostic reads the film itself, step by step */

static int32_t maximum(int32_t a,int32_t b){return a>b?a:b;}
static int32_t minimum(int32_t a,int32_t b){return a<b?a:b;}

void grmod_draw(void *view,void *surface){
    static const uint8_t context[8]={0,0,0,0,0,0,0,0};
    Diag *s=state();const int32_t *absolute,*clip;uint32_t stride,height,width,visible_h,capacity,i;
    int32_t x0,y0,x1,y1,sx,sy,vw,vh;uintptr_t pixels;const Bitmap *bitmap;const uint32_t *source;
    if(!s||!surface||!s->root||s->transition)goto finish;
    if(view==s->view){
        if(!s->diag_on||!s->diag_attached)goto finish;
        vw=(int32_t)DIAG_W;vh=(int32_t)DIAG_H;bitmap=&s->bitmap;source=s->pixels;
    }else{
        Ld *ld=s->ld;
        if(!ld||!ld->attached||!ld->running)goto finish;
        for(i=0;i<NV;i++)if(ld->views[i]==view)break;
        if(i==NV||!ld->pixels[i])goto finish;
        if(!(ld->engine.dirty&(1u<<VIEW_ID[i])))goto finish;
        vw=(int32_t)loaded_view_rect[VIEW_ID[i]][2];vh=(int32_t)loaded_view_rect[VIEW_ID[i]][3];
        bitmap=&ld->bitmaps[i];source=ld->pixels[i];
    }
    if(!byte(view,0x9e)||ptr(view,4)!=s->root||ptr(s->root,0xec)!=surface||byte(surface,2)!=5)goto finish;
    stride=half(surface,0x18);height=half(surface,0x1a);
    width=half(surface,0x1c);visible_h=half(surface,0x1e);pixels=(uintptr_t)ptr(surface,8);
    if(!stride||stride>4096||!height||height>4096||!width||width>stride||!visible_h||visible_h>height||
       !pixels||(pixels&3u))goto finish;
    capacity=stride*height*4u;if(pixels>0xffffffffu-capacity)goto finish;
    absolute=(const int32_t *)((const uint8_t *)view+0x30);
    clip=(const int32_t *)((const uint8_t *)view+0x64);
    if(absolute[0]<-4096||absolute[0]>4096||absolute[1]<-4096||absolute[1]>4096||
       absolute[2]!=vw||absolute[3]!=vh||
       clip[0]<-4096||clip[0]>4096||clip[1]<-4096||clip[1]>4096||
       clip[2]<=0||clip[2]>4096||clip[3]<=0||clip[3]>4096)goto finish;
    x0=maximum(maximum(absolute[0],clip[0]),0);y0=maximum(maximum(absolute[1],clip[1]),0);
    x1=minimum(minimum(absolute[0]+vw,clip[0]+clip[2]),(int32_t)width);
    y1=minimum(minimum(absolute[1]+vh,clip[1]+clip[3]),(int32_t)visible_h);
    sx=x0-absolute[0];sy=y0-absolute[1];
    if(x1<=x0||y1<=y0||sx<0||sy<0||sx+x1-x0>vw||sy+y1-y0>vh)goto finish;
    NATIVE(copy_fn,0x5320a020u)(context,surface,absolute[0],absolute[1],
        (uint32_t)sx,(uint32_t)sy,(uint32_t)(x1-x0),(uint32_t)(y1-y0),bitmap,source);
finish:
    base_draw(view,surface);
}
