/* SPDX-License-Identifier: GPL-2.0-only */
/* Exact GR III 2.10 only. UI-task ownership, native heap allocation and a
 * startup-zeroed absolute RAM anchor are part of the link/patch contract.
 * Physical display, DMA/cache behavior and frame performance need camera tests.
 */
#include "camera_gr3.h"
#include "camera_clock.h"
#include "terminal.h"

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
typedef int (*lock_fn)(void *,uint32_t);
typedef uint32_t (*value_fn)(void *);
typedef int (*parse_fn)(void **,const uint8_t *);
typedef int (*mutex_init_fn)(void *,const char *,uint32_t,uint32_t,uint32_t,int32_t);

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
#define audio_factory NATIVE(get_fn,0x53568e58u)
#define audio_get NATIVE(get_from_fn,0x53568ec0u)
#define mutex_lock NATIVE(lock_fn,0x536ae71cu)
#define mutex_unlock NATIVE(one_fn,0x536ae870u)
#define mutex_construct NATIVE(one_fn,0x536ae668u)
#define mutex_initialize NATIVE(mutex_init_fn,0x536aef0cu)
#define userdata_get NATIVE(get_from_fn,0x5320b31cu)
#define sound_disabled NATIVE(value_fn,0x53246528u)
#define sound_volume NATIVE(value_fn,0x5324651cu)
#define wave_parse NATIVE(parse_fn,0x53568f8cu)
#define wave_start NATIVE(one_fn,0x53567004u)
#define wave_cancel NATIVE(one_fn,0x53566b74u)
#define volume_set NATIVE(flag_fn,0x535677a8u)

typedef struct { uint16_t width,height; uint32_t word_offset; } Bitmap;
typedef void (*copy_fn)(const void *,void *,int32_t,int32_t,
                       uint32_t,uint32_t,uint32_t,uint32_t,const Bitmap *,const uint32_t *);
typedef struct { uint32_t *vtable; } Listener;
typedef struct {
    terminal_player player;
    uint32_t magic;
    void *view,*root,*controller,*timer_model,*audio;
    uint32_t timer_id,transition,entropy;
    uint32_t view_vtable[24],timer_vtable[3];
    Listener listener;
    Bitmap bitmap;
    const uint8_t *own_wave,*wanted_wave;
    uint32_t wanted_bytes,saved_volume;
    uint8_t volume_owned,stop_audio;
    uint32_t audio_gate[5],audio_gate_ready;
    uint32_t pixels[TERMINAL_PIXELS];
} Adapter;
#define MAGIC 0x324d5254u

static uint32_t rd32(const void *p){return *(const uint32_t *)p;}
static void *ptr(const void *p,uint32_t off){return *(void *const *)((const uint8_t *)p+off);}
static uint8_t byte(const void *p,uint32_t off){return *((const uint8_t *)p+off);}
static uint16_t half(const void *p,uint32_t off){return *(const uint16_t *)((const uint8_t *)p+off);}
static uint32_t le16(const uint8_t *p){return p[0]|(uint32_t)p[1]<<8;}
static uint32_t le32(const uint8_t *p){return le16(p)|le16(p+2)<<16;}
static Adapter *state(void){
    Adapter *s=(Adapter *)grmod_adapter_state;
    __asm__ volatile("dmb ish" ::: "memory"); /* Acquire published initialized state. */
    return s&&s->magic==MAGIC?s:0;
}
static void listener_noop(void *self){(void)self;}

static Adapter *create(void){
    Adapter *s=state();uint32_t i,bytes;
    if(s)return s;
    s=(Adapter *)heap_alloc(sizeof(*s));if(!s)return 0;
    for(i=0;i<sizeof(*s)/4u;i++)((volatile uint32_t *)s)[i]=0;
    /* The struct's tail is uint32_t, so sizeof is a multiple of four. */
    bytes=(uint32_t)((uintptr_t)terminal_asset_end-(uintptr_t)terminal_asset_start);
    if(!terminal_load(&s->player,terminal_asset_start,bytes)){heap_free(s);return 0;}
    for(i=0;i<24;i++)s->view_vtable[i]=((const uint32_t *)(uintptr_t)0x53c0a8a0u)[i];
    s->view_vtable[2+0x4c/4]=(uint32_t)(uintptr_t)grmod_draw;
    s->timer_vtable[0]=(uint32_t)(uintptr_t)listener_noop;
    s->timer_vtable[1]=(uint32_t)(uintptr_t)listener_noop;
    s->timer_vtable[2]=(uint32_t)(uintptr_t)grmod_timer_expired;
    s->listener.vtable=s->timer_vtable;
    s->bitmap.width=TERMINAL_W;s->bitmap.height=TERMINAL_H;
    s->timer_model=timer_get();
    /* Exact native AudioService mutex construction parameters, including
     * nonrecursive flag0 and creation timeout0. Keep this20-byte mutex for the
     * rest of the boot; it must outlive the native AudioService it protects. */
    mutex_construct(s->audio_gate);
    if(!grmod_audio_shutdown_latch)
        s->audio_gate_ready=mutex_initialize(s->audio_gate,"GRMod animation audio",2,0x8c,0,0)!=0;
    s->magic=MAGIC;
    __asm__ volatile("dmb ish" ::: "memory"); /* Publish only after gate initialization. */
    grmod_adapter_state=s;return s;
}

/* Registration is a stronger predicate than a controller's retained root field.
 * Native frame setup rebinds the Canvas to the surface descriptor embedded at
 * controller+0xc+slot*0x30. No display/controller slot is allocated by us. */
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
    void *root=s->root;uint32_t *it,*end;
    if(!root)return;
    if(s->view){
        view_visible(s->view,0);
        if(child_vector(root,&it,&end))for(;it!=end;it++)if(*it==(uint32_t)(uintptr_t)s->view){
            vector_erase((uint8_t *)root+8,it);break;
        }
        view_parent(s->view,0);
    }
    view_invalidate(root);s->root=0;s->controller=0;
}

static int attach(Adapter *s,void *root,void *controller){
    static const uint32_t descriptor[6]={10,464,259,240,176,0};
    uint32_t *begin,*end;
    if(s->root==root&&s->controller==controller)return 1;
    detach(s);
    if(!child_vector(root,&begin,&end))return 0;
    if(!s->view){
        s->view=view_factory((void *)descriptor);if(!s->view)return 0;
        *(uint32_t **)s->view=s->view_vtable+2;view_visible(s->view,0);
    }
    /* Our detached object must not already belong to a different native tree. */
    if(ptr(s->view,4))return 0;
    view_add(root,s->view);s->root=root;s->controller=controller;
    view_visible(s->view,1);view_invalidate(root);return 1;
}

static int wave_valid(const uint8_t *wav,uint32_t bytes){
    uint32_t n=48000u*4u*TERMINAL_DURATION/1000u;
    if(!wav||bytes!=44u+n)return 0;
    return le32(wav)==0x46464952u&&le32(wav+4)==bytes-8u&&le32(wav+8)==0x45564157u&&
        le32(wav+12)==0x20746d66u&&le32(wav+16)==16&&le16(wav+20)==1&&le16(wav+22)==2&&
        le32(wav+24)==48000&&le32(wav+28)==192000&&le16(wav+32)==4&&le16(wav+34)==16&&
        le32(wav+36)==0x61746164u&&le32(wav+40)==n;
}

static void select_wave(Adapter *s){
    const uint8_t *start,*end;
    if(grmod_audio_shutdown_latch||!s->audio_gate_ready){s->wanted_wave=0;s->wanted_bytes=0;return;}
    if(s->player.sequence==0){start=terminal_wav_dash_start;end=terminal_wav_dash_end;}
    else if(s->player.sequence==1){start=terminal_wav_portal_start;end=terminal_wav_portal_end;}
    else{start=terminal_wav_rocket_start;end=terminal_wav_rocket_end;}
    s->wanted_bytes=(uint32_t)((uintptr_t)end-(uintptr_t)start);
    s->wanted_wave=wave_valid(start,s->wanted_bytes)?start:0;
}

static void forget_wave(Adapter *s){s->own_wave=0;s->volume_owned=0;s->stop_audio=0;}

/* One service critical section covers the ownership test and every change.
 * try-lock never blocks the UI task. Busy cancellation leaves own_wave retained,
 * and arm() keeps retrying even after the visual player has been cancelled. */
static void audio_update_locked(Adapter *s){
    uint8_t *a;void *ud;uint32_t state_value,muted=1,volume=0;const uint8_t *current;
    /* The native C++ initialization guard is NOT cleared on factory shutdown,
     * and factory+4 is left dangling. The separate shutdown hook/latch is
     * therefore mandatory; no native audio pointer is read after it is set. */
    if(grmod_audio_shutdown_latch){s->wanted_wave=0;forget_wave(s);s->audio=0;return;}
    if(!s->own_wave&&!s->wanted_wave)return;
    /* Avoid initializing an unavailable service from this optional effect. */
    if(!(*(const volatile uint32_t *)(uintptr_t)0x55348b28u&1u)){
        s->wanted_wave=0;forget_wave(s);s->audio=0;return;
    }
    a=(uint8_t *)audio_get(audio_factory());
    if(a!=s->audio){forget_wave(s);s->audio=a;}
    if(!a||rd32(a)!=0x53d1b7b8u){s->wanted_wave=0;forget_wave(s);return;}
    if(!mutex_lock(a+0x104,0)){
        /* New entrance audio is immediate-or-skip. Only an existing owned
         * wave/cancellation survives a busy lock for the next UI retry. */
        s->wanted_wave=0;return;
    }
    ud=userdata_get(app_get());
    if(ud){muted=sound_disabled(ud);volume=sound_volume(ud);}
    if(volume>20)volume=20;
    state_value=a[0x35];current=(const uint8_t *)ptr(a,0xf8);
    if(s->own_wave){
        if(state_value==5&&current==s->own_wave){
            if(s->stop_audio||muted||!s->player.active||s->wanted_wave){
                wave_cancel(a);
                if(s->volume_owned)volume_set(a,s->saved_volume);
                forget_wave(s);state_value=a[0x35];current=(const uint8_t *)ptr(a,0xf8);
            }
        }else{
            /* Restore only our known natural completion at idle; relinquish any
             * foreign cue/wave without calling either stop or volume_set. */
            if(state_value==1&&!current&&s->volume_owned)volume_set(a,s->saved_volume);
            forget_wave(s);
        }
    }
    if(s->wanted_wave&&s->player.active){
        if(!muted&&state_value==1&&!current&&a[0x36]==1&&a[0x37]==1&&!a[0x38]&&!a[0xf6]){
            if(wave_parse((void **)(a+0xf8),s->wanted_wave)){
                s->saved_volume=volume;volume_set(a,20);wave_start(a);
                if(a[0x35]==5&&ptr(a,0xf8)==s->wanted_wave){s->own_wave=s->wanted_wave;s->volume_owned=1;s->stop_audio=0;}
                else if(a[0x35]==1&&!ptr(a,0xf8))volume_set(a,s->saved_volume);
            }
        }
        /* A foreign active cue, mute, or a non-idle service suppresses this
         * shot's custom sound, without scheduling an entrance sound later. */
        s->wanted_wave=0;
    }
    mutex_unlock(a+0x104);
}

/* All native AudioService pointer lookup, locking, reads and calls occur inside
 * this module gate. Normal UI work never waits. Shutdown sets the latch first,
 * then acquires this same permanent gate before permitting native service free.
 * Rechecking the latch AFTER acquiring closes the preemption-before-lock case. */
static void audio_update(Adapter *s){
    if(grmod_audio_shutdown_latch)return;
    if(!s->audio_gate_ready){s->wanted_wave=0;forget_wave(s);s->audio=0;return;}
    if(!s->own_wave&&!s->wanted_wave)return;
    if(!mutex_lock(s->audio_gate,0)){s->wanted_wave=0;return;}
    audio_update_locked(s);
    mutex_unlock(s->audio_gate);
}

static void disarm(Adapter *s){
    uint32_t id=s->timer_id;s->timer_id=0;
    /* Native stop(0) matches a free slot, so zero is never passed. */
    if(id&&s->timer_model)timer_stop(s->timer_model,id);
}

static void arm(Adapter *s,uint32_t now){
    uint32_t delay=33,elapsed;
    if(s->timer_id||s->transition||(!s->player.active&&!s->own_wave&&!s->wanted_wave))return;
    if(s->player.active){
        elapsed=now-s->player.started;
        if(elapsed<TERMINAL_DURATION&&TERMINAL_DURATION-elapsed<delay)delay=TERMINAL_DURATION-elapsed;
    }
    if(s->timer_model)s->timer_id=timer_start(s->timer_model,delay,&s->listener);
}

void grmod_cancel(void){
    Adapter *s=state();uint32_t now=0;if(!s)return;
    disarm(s);terminal_cancel(&s->player);s->wanted_wave=0;s->stop_audio=1;
    detach(s);audio_update(s);(void)grmod_clock_ms(&now);arm(s,now);
}

static void update(Adapter *s,uint32_t now){
    void *controller=0,*root;int result;
    if(s->player.active){
        if(now-s->player.started>=TERMINAL_DURATION){
            terminal_cancel(&s->player);s->wanted_wave=0;s->stop_audio=1;detach(s);
        }else{
            root=find_root(&controller);
            if(!root||!attach(s,root,controller)){grmod_cancel();return;}
            result=terminal_tick(&s->player,now,s->pixels,TERMINAL_W,TERMINAL_PIXELS);
            if(result<0){grmod_cancel();return;}
            if(result>0)view_invalidate(root);
        }
    }
    audio_update(s);arm(s,now);
}

void grmod_on_shot(void){
    Adapter *s;void *controller=0,*root;uint32_t now;
    if(!grmod_clock_ms(&now)){grmod_cancel();return;}
    root=find_root(&controller);if(!root){grmod_cancel();return;}
    s=create();if(!s)return;
    disarm(s);s->transition=0;
    if(!attach(s,root,controller)){grmod_cancel();return;}
    /* First-load asset validation and native construction may take time. The
     * approved7600ms starts after that work, immediately before first render. */
    if(!grmod_clock_ms(&now)){grmod_cancel();return;}
    s->entropy=s->entropy*1664525u+1013904223u+now;
    if(!terminal_shot(&s->player,now,s->entropy)){grmod_cancel();return;}
    select_wave(s);s->stop_audio=1;update(s,now);
}

void grmod_timer_expired(void *listener,uint32_t id){
    Adapter *s=state();uint32_t now;
    if(!s||listener!=&s->listener||!id||id!=s->timer_id)return;
    s->timer_id=0; /* Native expiry already cleared its slot before this call. */
    if(s->transition)return;
    if(!grmod_clock_ms(&now)){grmod_cancel();return;}
    update(s,now);
}

void grmod_before_transition(void *old_controller,uint32_t destination_id){
    Adapter *s=state();uint32_t id=destination_id-0x08000000u;(void)old_controller;if(!s)return;
    ++s->transition;
    if(id<=2u||(id>=0x0cu&&id<=0x11u)){disarm(s);detach(s);}
    else grmod_cancel(); /* Before old-controller exit can tear audio down. */
}

void grmod_after_transition(void){
    Adapter *s=state();uint32_t now;if(!s||!s->transition)return;
    if(--s->transition)return;
    if(!grmod_clock_ms(&now)){grmod_cancel();return;}update(s,now);
}

void grmod_before_canvas_delete(void *root){
    Adapter *s=state();if(s&&s->root==root)grmod_cancel();
}

void grmod_before_audio_shutdown(void){
    Adapter *s;
    /* The latch exists even before first-shot construction. Once set, no new
     * UI audio operation enters the service. Drain an already-running one by
     * taking its permanent module gate; never lock/access a dying service here. */
    grmod_audio_shutdown_latch=1;
    __asm__ volatile("dmb ish" ::: "memory");
    s=state();if(!s)return;
    if(s->audio_gate_ready){
        /* Every retry is the native blocking infinite wait, not a polling
         * sleep/spin. Do not permit service deletion until the gate is owned. */
        while(!mutex_lock(s->audio_gate,0xffffffffu)){}
    }
    s->wanted_wave=0;forget_wave(s);s->audio=0;
    if(s->audio_gate_ready)mutex_unlock(s->audio_gate);
}

static int32_t maximum(int32_t a,int32_t b){return a>b?a:b;}
static int32_t minimum(int32_t a,int32_t b){return a<b?a:b;}

void grmod_draw(void *view,void *surface){
    static const uint8_t context[8]={0,0,0,0,0,0,0,0};
    Adapter *s=state();const int32_t *absolute,*clip;uint32_t stride,height,width,visible_h,capacity;
    int32_t x0,y0,x1,y1,sx,sy;uintptr_t pixels;
    if(!s||view!=s->view||!surface||!s->root||!s->player.active||s->transition||
       !byte(view,0x9e)||ptr(view,4)!=s->root||ptr(s->root,0xec)!=surface||byte(surface,2)!=5)goto finish;
    stride=half(surface,0x18);height=half(surface,0x1a);
    width=half(surface,0x1c);visible_h=half(surface,0x1e);pixels=(uintptr_t)ptr(surface,8);
    if(!stride||stride>4096||!height||height>4096||!width||width>stride||!visible_h||visible_h>height||
       !pixels||(pixels&3u))goto finish;
    capacity=stride*height*4u;if(pixels>0xffffffffu-capacity)goto finish;
    absolute=(const int32_t *)((const uint8_t *)view+0x30);
    clip=(const int32_t *)((const uint8_t *)view+0x64);
    if(absolute[0]<-4096||absolute[0]>4096||absolute[1]<-4096||absolute[1]>4096||
       absolute[2]!=(int32_t)TERMINAL_W||absolute[3]!=(int32_t)TERMINAL_H||
       clip[0]<-4096||clip[0]>4096||clip[1]<-4096||clip[1]>4096||
       clip[2]<=0||clip[2]>4096||clip[3]<=0||clip[3]>4096)goto finish;
    x0=maximum(maximum(absolute[0],clip[0]),0);y0=maximum(maximum(absolute[1],clip[1]),0);
    x1=minimum(minimum(absolute[0]+TERMINAL_W,clip[0]+clip[2]),(int32_t)width);
    y1=minimum(minimum(absolute[1]+TERMINAL_H,clip[1]+clip[3]),(int32_t)visible_h);
    sx=x0-absolute[0];sy=y0-absolute[1];
    if(x1<=x0||y1<=y0||sx<0||sy<0||sx+x1-x0>(int32_t)TERMINAL_W||sy+y1-y0>(int32_t)TERMINAL_H)goto finish;
    NATIVE(copy_fn,0x5320a020u)(context,surface,absolute[0],absolute[1],
        (uint32_t)sx,(uint32_t)sy,(uint32_t)(x1-x0),(uint32_t)(y1-y0),&s->bitmap,s->pixels);
finish:
    /* Native base bookkeeping/child traversal is required even when we skip. */
    base_draw(view,surface);
}
