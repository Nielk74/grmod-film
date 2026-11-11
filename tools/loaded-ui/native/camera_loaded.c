/* SPDX-License-Identifier: GPL-2.0-only */
/* Loaded, stage 1: GR III 2.10 film pack adapter. Derived from tools/shot-animation/native/camera_gr3.c
 * (silent Terminal, camera-tested 2026-11-05): the same hook sites, the same native services and the same
 * view lifetime, generalised from one owned view to four (top band, bottom band, counter, tab).
 *
 * Views exist only while a moment started by a completed shot is running. Anything unexpected (allocation,
 * clock, controller, view, film) means no animation for that shot and nothing else. Nothing here waits,
 * writes settings, or touches audio.
 */
#include "camera_loaded.h"
#include "../../shot-animation/native/camera_clock.h"
#include "loaded.h"
#include "loaded_data.h"

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

/* The four views of tier 1, in attach order (the loaded.h view numbers). They do not overlap one another. */
#define NV 4u
static const uint8_t VIEW_ID[NV]={LOADED_V_TOP,LOADED_V_BOTTOM,LOADED_V_COUNTER,LOADED_V_TAB};

typedef struct {
    uint32_t magic;
    void *views[NV],*root,*controller,*timer_model;
    uint32_t *pixels[NV];
    Bitmap bitmaps[NV];
    uint32_t timer_id,transition,shots,pending_roll,roll_frame;
    uint32_t view_vtable[24],timer_vtable[3];
    Listener listener;
    loaded_params params;
    loaded_buffers buffers;
    loaded engine;
} Adapter;
#define MAGIC 0x31444c47u
/* Field offsets for the emulator checks (read-only data). */
const uint32_t grmod_layout[]={__builtin_offsetof(Adapter,views),__builtin_offsetof(Adapter,pixels),__builtin_offsetof(Adapter,shots),
    __builtin_offsetof(Adapter,pending_roll),__builtin_offsetof(Adapter,engine),sizeof(Adapter)};

static uint32_t rd32(const void *p){return *(const uint32_t *)p;}
static void *ptr(const void *p,uint32_t off){return *(void *const *)((const uint8_t *)p+off);}
static uint8_t byte(const void *p,uint32_t off){return *((const uint8_t *)p+off);}
static uint16_t half(const void *p,uint32_t off){return *(const uint16_t *)((const uint8_t *)p+off);}
static Adapter *state(void){
    Adapter *s=(Adapter *)grmod_adapter_state;
    __asm__ volatile("dmb ish" ::: "memory");
    return s&&s->magic==MAGIC?s:0;
}
static void listener_noop(void *self){(void)self;}
static uint32_t view_pixels(uint32_t v){return loaded_view_rect[VIEW_ID[v]][2]*loaded_view_rect[VIEW_ID[v]][3];}

/* ---------------------------------------------------------------- the selected film
 * Read, never written, from the UI task: the settings object (UserDataModel, the singleton 0x5320b31c returns,
 * 0x55063f30) holds a pointer to the record in use at +4. Byte 0x44 of the record is the movie flag, 0x1c0 the
 * active Image Control set (0..2) and 0x1c2 + 2*set that set's look: the camera's own looks are 11..22, the
 * film pack's film k is look 64 + k. The film pack's native modules read the same bytes (tools/gr3x/native). */
#define USERDATA_MODEL 0x55063f30u
/* Pack film k (look 64 + k) as a Loaded film. The pack this image is built on has Pro 400H in slot 0, which the
 * Loaded table does not have; slots 1..19 are the same films in the same order (Astia ... Platinum). */
static const uint8_t FILM_OF_SLOT[20]={LD_FILMS-1,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19};
uint32_t loaded_film_of_look(uint32_t look){
    if(look>=64u&&look<64u+20u)return FILM_OF_SLOT[look-64u];
    return LD_FILMS-1u;   /* the camera's own looks and anything unknown: the neutral GR III strip */
}
/* 0..20, or 0xffffffff when the settings cannot be read as expected (no animation then). */
uint32_t loaded_selected_film(void){
    const uint8_t *model=(const uint8_t *)(uintptr_t)USERDATA_MODEL,*rec;
    uintptr_t at;uint32_t set;
    rec=(const uint8_t *)ptr(model,4);at=(uintptr_t)rec;
    /* As the film pack's own readers (films.c record_of): a null record means not initialised; no other validation exists. */
    if(!rec||(at&3u))return 0xffffffffu;
    if(rec[0x44]!=0)return 0xffffffffu;           /* movie mode: not a still-shot moment */
    set=rec[0x1c0];if(set>2u)return 0xffffffffu;
    return loaded_film_of_look(rec[0x1c2+2u*set]);
}

/* ---------------------------------------------------------------- allocation: all or nothing */
static void release(Adapter *s){
    uint32_t i;
    for(i=0;i<NV;i++)if(s->pixels[i]){heap_free(s->pixels[i]);s->pixels[i]=0;}
}
static Adapter *create(void){
    Adapter *s=state();uint32_t i,bytes;
    if(s)return s;
    s=(Adapter *)heap_alloc(sizeof(*s));if(!s)return 0;
    for(i=0;i<sizeof(*s)/4u;i++)((volatile uint32_t *)s)[i]=0;
    for(i=0;i<NV;i++){
        bytes=view_pixels(i)*4u;
        s->pixels[i]=(uint32_t *)heap_alloc(bytes);
        if(!s->pixels[i]){release(s);heap_free(s);return 0;}   /* a failure of any piece frees everything */
        s->buffers.pixels[VIEW_ID[i]]=s->pixels[i];
        s->buffers.stride[VIEW_ID[i]]=loaded_view_rect[VIEW_ID[i]][2];
        s->buffers.capacity[VIEW_ID[i]]=view_pixels(i);
        s->bitmaps[i].width=loaded_view_rect[VIEW_ID[i]][2];s->bitmaps[i].height=loaded_view_rect[VIEW_ID[i]][3];
    }
    for(i=0;i<24;i++)s->view_vtable[i]=((const uint32_t *)(uintptr_t)0x53c0a8a0u)[i];
    s->view_vtable[2+0x4c/4]=(uint32_t)(uintptr_t)grmod_draw;
    s->timer_vtable[0]=(uint32_t)(uintptr_t)listener_noop;
    s->timer_vtable[1]=(uint32_t)(uintptr_t)listener_noop;
    s->timer_vtable[2]=(uint32_t)(uintptr_t)grmod_timer_expired;
    s->listener.vtable=s->timer_vtable;
    s->timer_model=timer_get();
    loaded_init(&s->engine);
    s->magic=MAGIC;
    __asm__ volatile("dmb ish" ::: "memory");
    grmod_adapter_state=s;return s;
}

/* ---------------------------------------------------------------- native tree (as camera_gr3.c, per view) */
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
static void detach(Adapter *s){
    void *root=s->root;uint32_t *it,*end,i;
    if(!root)return;
    for(i=0;i<NV;i++){
        void *v=s->views[i];if(!v)continue;
        view_visible(v,0);
        /* the vector is re-read for each view: erasing moves the later children */
        if(child_vector(root,&it,&end))for(;it!=end;it++)if(*it==(uint32_t)(uintptr_t)v){
            vector_erase((uint8_t *)root+8,it);break;
        }
        view_parent(v,0);
    }
    view_invalidate(root);s->root=0;s->controller=0;
}
static int attach(Adapter *s,void *root,void *controller){
    uint32_t *begin,*end,i;
    if(s->root==root&&s->controller==controller)return 1;
    detach(s);
    if(!child_vector(root,&begin,&end))return 0;
    for(i=0;i<NV;i++){
        uint32_t descriptor[6];
        const uint16_t *r=loaded_view_rect[VIEW_ID[i]];
        if(s->views[i])continue;
        descriptor[0]=10;descriptor[1]=r[0];descriptor[2]=r[1];descriptor[3]=r[2];descriptor[4]=r[3];descriptor[5]=0;
        s->views[i]=view_factory((void *)descriptor);
        if(!s->views[i])return 0;                   /* created views are kept for the next shot */
        *(uint32_t **)s->views[i]=s->view_vtable+2;view_visible(s->views[i],0);
    }
    /* Our detached objects must not already belong to a different native tree. */
    for(i=0;i<NV;i++)if(ptr(s->views[i],4))return 0;
    for(i=0;i<NV;i++){view_add(root,s->views[i]);}
    s->root=root;s->controller=controller;
    for(i=0;i<NV;i++)view_visible(s->views[i],1);
    view_invalidate(root);return 1;
}

static void disarm(Adapter *s){
    uint32_t id=s->timer_id;s->timer_id=0;
    if(id&&s->timer_model)timer_stop(s->timer_model,id);
}
static void arm(Adapter *s,uint32_t now){
    uint32_t delay=33,elapsed,dur;
    if(s->timer_id||s->transition||!s->engine.active)return;
    elapsed=now-s->engine.start;dur=loaded_duration(s->params.film,s->engine.moment);
    if(elapsed<dur&&dur-elapsed<delay)delay=dur-elapsed?dur-elapsed:1;
    if(s->timer_model)s->timer_id=timer_start(s->timer_model,delay,&s->listener);
}

void grmod_cancel(void){
    Adapter *s=state();uint32_t now=0;
    if(!s)return;
    disarm(s);loaded_cancel(&s->engine);s->pending_roll=0;
    detach(s);(void)grmod_clock_ms(&now);
}

static void finish_moment(Adapter *s){
    loaded_cancel(&s->engine);s->pending_roll=0;detach(s);
}

static void update(Adapter *s,uint32_t now){
    void *controller=0,*root;int r;
    if(s->engine.active){
        root=find_root(&controller);
        if(!root||!attach(s,root,controller)){grmod_cancel();return;}
        r=loaded_tick(&s->engine,&s->buffers,now);
        if(r<0){grmod_cancel();return;}
        if(!(r&0x100)){
            /* the shot's moment is over: after frame 36 the end of the roll follows, once */
            if(s->pending_roll){
                s->pending_roll=0;s->params.moment=LOADED_ROLL;
                if(loaded_start(&s->engine,&s->params,now)!=0){grmod_cancel();return;}
                r=loaded_tick(&s->engine,&s->buffers,now);
                if(r<0){grmod_cancel();return;}
            }else{finish_moment(s);return;}
        }
        if(r&0x1f)view_invalidate(root);
    }
    arm(s,now);
}

void grmod_on_shot(void){
    Adapter *s;void *controller=0,*root;uint32_t now,film,n;
    if(!grmod_clock_ms(&now)){grmod_cancel();return;}
    root=find_root(&controller);if(!root){grmod_cancel();return;}
    film=loaded_selected_film();if(film==0xffffffffu){grmod_cancel();return;}
    s=create();if(!s)return;
    disarm(s);s->transition=0;
    n=s->shots++;
    s->params.moment=LOADED_SHOT;s->params.film=film;s->params.frame=n%LOADED_ROLL_FRAMES+1u;
    s->params.roll=1u+n/LOADED_ROLL_FRAMES;if(s->params.roll>999999u)s->params.roll=999999u;
    s->params.tier=1;s->params.tab_mode=LOADED_PEEK;s->params.counter_mode=LOADED_PEEK;
    s->params.peek_ms=-1;s->params.tab_peek_ms=-2;s->params.counter_peek_ms=-2;
    s->params.month=12;s->params.year=0;s->params.thumbs=0;s->params.circled=-1;
    s->pending_roll=s->params.frame==LOADED_ROLL_FRAMES;
    if(!attach(s,root,controller)){grmod_cancel();return;}
    /* First-load native construction may take time: the clock is read again just before the first render. */
    if(!grmod_clock_ms(&now)){grmod_cancel();return;}
    if(loaded_start(&s->engine,&s->params,now)!=0){grmod_cancel();return;}
    update(s,now);
}

void grmod_timer_expired(void *listener,uint32_t id){
    Adapter *s=state();uint32_t now;
    if(!s||listener!=&s->listener||!id||id!=s->timer_id)return;
    s->timer_id=0;
    if(s->transition)return;
    if(!grmod_clock_ms(&now)){grmod_cancel();return;}
    update(s,now);
}

void grmod_before_transition(void *old_controller,uint32_t destination_id){
    Adapter *s=state();uint32_t id=destination_id-0x08000000u;(void)old_controller;if(!s)return;
    ++s->transition;
    if(id<=2||(id>=0x0cu&&id<=0x11u)){disarm(s);detach(s);}
    else grmod_cancel();
}
void grmod_after_transition(void){
    Adapter *s=state();uint32_t now;if(!s||!s->transition)return;
    if(--s->transition)return;
    if(!grmod_clock_ms(&now)){grmod_cancel();return;}update(s,now);
}
void grmod_before_canvas_delete(void *root){
    Adapter *s=state();if(s&&s->root==root)grmod_cancel();
}
/* The silent build never patches the audio shutdown hook: this callback is unreachable and does nothing. */
void grmod_before_audio_shutdown(void){}

static int32_t maximum(int32_t a,int32_t b){return a>b?a:b;}
static int32_t minimum(int32_t a,int32_t b){return a<b?a:b;}

void grmod_draw(void *view,void *surface){
    static const uint8_t context[8]={0,0,0,0,0,0,0,0};
    Adapter *s=state();const int32_t *absolute,*clip;uint32_t stride,height,width,visible_h,capacity,i,v;
    int32_t x0,y0,x1,y1,sx,sy,vw,vh;uintptr_t pixels;
    if(!s||!surface||!s->root||!s->engine.active||s->transition)goto finish;
    for(i=0;i<NV;i++)if(s->views[i]==view)break;
    if(i==NV)goto finish;
    v=VIEW_ID[i];
    if(!(s->engine.dirty&(1u<<v)))goto finish;                      /* nothing visible in this view */
    vw=(int32_t)loaded_view_rect[v][2];vh=(int32_t)loaded_view_rect[v][3];
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
        (uint32_t)sx,(uint32_t)sy,(uint32_t)(x1-x0),(uint32_t)(y1-y0),&s->bitmaps[i],s->pixels[i]);
finish:
    base_draw(view,surface);
}
