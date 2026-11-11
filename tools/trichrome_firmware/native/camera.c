/* SPDX-License-Identifier: GPL-2.0-only
 * Exact GR III2.10 adapter. Native BeforeExpose events supply ordinals; JPEG
 * calls only consume matching records. Heap-owned state and reduced pixels.
 */
#include "trichrome.h"
#define ANCHOR ((volatile u32 *)0x5580438cu)
#define MAGIC 0x33495254u
#define SETTINGS_AT 0x6c4u
#define SETTINGS_N (0x81au-SETTINGS_AT)
#define EXPIRE 30000u
#define FN(t,a) ((t)(a))
typedef void *(*alloc_fn)(u32);
typedef void (*free_fn)(void *);
typedef void *(*cache_fn)(void);
typedef void (*cache_op)(void *,u32,u32);
typedef int (*clock_fn)(unsigned long long *);
struct tag {u32 common,epoch,index,time;};
struct adapter {
  u32 magic;volatile u32 lock,abort;
  u32 epoch,active,ordinal,armed_at,settings_valid;
  u8 settings[SETTINGS_N];u8 pad[2];
  struct tag tag[3];struct tri_state pixels;
};
static void *allocate(u32 n){return FN(alloc_fn,0x536af2a8u)(n);}
static void release(void *p){FN(free_fn,0x536af2e4u)(p);}
static void invalidate(u32 a,u32 n){void *c=FN(cache_fn,0x536bbc30u)();FN(cache_op,0x536bbcc0u)(c,a,n);}
static void clean(u32 a,u32 n){void *c=FN(cache_fn,0x536bbc30u)();FN(cache_op,0x536bbcacu)(c,a,n);}
static struct tri_ctx context(void){struct tri_ctx k={allocate,release,invalidate,clean};return k;}
static int now(u32 *out){unsigned long long t;if(!FN(clock_fn,0x536afc5cu)(&t))return 0;*out=(u32)t;return 1;}
static int ram(u32 p){return p>=0x40000000u&&p<0xbff80000u&&!(p&3);}
static struct adapter *state(int create){
  u32 p=__atomic_load_n(ANCHOR,__ATOMIC_ACQUIRE),expect=0,i;
  struct adapter *s;
  if(p==0&&create){
    if(!__atomic_compare_exchange_n(ANCHOR,&expect,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return 0;
    s=(struct adapter *)allocate(sizeof(*s));
    if(!s){__atomic_store_n(ANCHOR,0,__ATOMIC_RELEASE);return 0;}
    for(i=0;i<sizeof(*s);i++)((u8 *)s)[i]=0;
    s->magic=MAGIC;__atomic_store_n(ANCHOR,(u32)s,__ATOMIC_RELEASE);return s;
  }
  if(!ram(p))return 0;s=(struct adapter *)p;return s->magic==MAGIC?s:0;
}
static void clear(struct adapter *s){u32 i;s->active=0;s->settings_valid=0;s->ordinal=0;for(i=0;i<3;i++)s->tag[i].common=0;}
static int take(struct adapter *s){
  if(__atomic_exchange_n(&s->lock,1,__ATOMIC_ACQUIRE)){__atomic_store_n(&s->abort,1,__ATOMIC_RELEASE);return 0;}
  return 1;
}
static void drop(struct adapter *s){__atomic_store_n(&s->lock,0,__ATOMIC_RELEASE);}
static int same_settings(struct adapter *s,const u8 *c){u32 i;if(s->pad[0]!=c[0xc8])return 0;for(i=0;i<SETTINGS_N;i++)if(s->settings[i]!=c[SETTINGS_AT+i])return 0;return 1;}
static void stop(struct adapter *s){struct tri_ctx k=context();tri_cancel(&k,&s->pixels);}
u32 tri_camera_state_bytes(void){return sizeof(struct adapter);}

/* r0/r1 original OnReleaseContinuous arguments are retained by the wrapper. */
void tri_camera_arm(void *owner,void *command){
  struct adapter *s=state(1);u32 t=0;(void)owner;
  if(!s)return;
  if(!take(s)){stop(s);return;}
  clear(s);s->epoch++;if(!s->epoch)s->epoch=1;
  __atomic_store_n(&s->abort,0,__ATOMIC_RELEASE);
  if(ram((u32)command)&&now(&t)){s->active=1;s->armed_at=t;}
  drop(s);stop(s);
}

/* r2 at SetShootingInfoResultBeforeExpose0x534322d8, before its native body. */
void tri_camera_expose(void *owner,u32 event,u8 *common){
  struct adapter *s=state(0);u32 t=0,i,bad=0;(void)owner;(void)event;
  if(!s)return;
  if(!take(s)){stop(s);return;}
  if(__atomic_load_n(&s->abort,__ATOMIC_ACQUIRE)||!s->active||!now(&t)||
     t-s->armed_at>EXPIRE||!ram((u32)common)||common[0x6f4]!=2||common[0x77c]<64||common[0x77c]>=84){bad=1;goto done;}
  if(s->ordinal>=3)goto done;
  for(i=0;i<3;i++)if(s->tag[i].common==(u32)common){bad=1;goto done;}
  if(s->settings_valid){if(!same_settings(s,common)){bad=1;goto done;}}
  else {for(i=0;i<SETTINGS_N;i++)s->settings[i]=common[SETTINGS_AT+i];s->pad[0]=common[0xc8];s->settings_valid=1;}
  i=s->ordinal++;s->tag[i].common=(u32)common;s->tag[i].epoch=s->epoch;s->tag[i].index=i+1;s->tag[i].time=t;
done:if(bad)clear(s);drop(s);if(bad)stop(s);
}

/* Optional processing override copies are RAW/reprocessing paths, not exposure
 * events. They cannot acquire a tag just because their drive byte was copied. */
void tri_camera_override(void *frame,u32 mode,void *source){
  struct adapter *s=state(0);(void)frame;(void)mode;
  if(!s||!source)return;
  if(take(s)){clear(s);drop(s);}stop(s);
}

void tri_camera_cancel(void){struct adapter *s=state(0);if(!s)return;if(take(s)){clear(s);drop(s);}stop(s);}

void tri_camera_jpeg(u8 *config){
  struct adapter *s=state(0);struct tri_ctx k=context();struct tri_identity id;
  struct tri_picture pics[3];u8 *common;u32 t=0,i,j,found=3,bad=0;
  if(!s)return;
  if(!take(s)){stop(s);return;}
  if(!ram((u32)config)){bad=1;goto done;}
  common=*(u8 **)(config+0x34);
  if(__atomic_load_n(&s->abort,__ATOMIC_ACQUIRE)||!s->active||!now(&t)||t-s->armed_at>EXPIRE||
     !ram((u32)common)||common[0x6f4]!=2||common[0x77c]<64||common[0x77c]>=84||!same_settings(s,common)){bad=1;goto done;}
  for(i=0;i<3;i++)if(s->tag[i].common==(u32)common){found=i;break;}
  if(found==3){bad=1;goto done;}
  id.generation=s->tag[found].epoch;id.index=s->tag[found].index;
  id.signature=s->epoch;id.kind=1;id.milliseconds=t;
  s->tag[found].common=0; /* consume exactly once before any pixel operation */
  for(i=0;i<3;i++){
    struct tri_picture *p=*(struct tri_picture **)(config+0x3c+i*4);
    if(!ram((u32)p)){bad=1;goto done;}
    for(j=0;j<sizeof(*p);j++)((u8 *)&pics[i])[j]=((const u8 *)p)[j];
  }
  if((u32)pics[0].width*2!=(u32)pics[0].height*3){bad=1;goto done;}
done:if(bad)clear(s);drop(s);
  if(bad||__atomic_load_n(&s->abort,__ATOMIC_ACQUIRE)){stop(s);return;}
  (void)tri_process(&k,&s->pixels,&id,pics,3);
}
