/* SPDX-License-Identifier: GPL-2.0-only
 * Tripod-only bounded RGB temporal deltas on native YCbCr4:2:2. No firmware
 * source/generation claim is made by this portable core. The adapter must prove
 * tri_identity before invoking it. All source pictures are borrowed for this
 * call only; persistent state holds owned reduced pixels and scalar geometry.
 */
#include "trichrome.h"
#define LIMIT 3100000u
#define EXPIRY 30000u

static u8 clamp(s32 x){return (u8)(x<0?0:x>255?255:x);}
static int range(const void *p,u32 n){u32 a=(u32)p;return a>=0x5d000000u&&a<0xc0000000u&&n<=0xc0000000u-a;}
static int overlap(const void *a,u32 an,const void *b,u32 bn){return (u32)a<(u32)b+bn&&(u32)b<(u32)a+an;}
static int picture_ok(const struct tri_picture *p){
  u32 w=p->width,h=p->height,n=(u32)p->stride*h;
  return p->format==1&&w>=16&&h>=16&&w<=6000&&h<=6000&&!(w&3)&&!(h&3)&&
    p->stride>=w&&p->stride<=16384&&p->c_height>=h&&!p->x&&!p->y_off&&range(p->y,n)&&range(p->c,n)&&!overlap(p->y,n,p->c,n);
}
static int geometry_equal(const struct tri_picture *p,const struct tri_geometry *g){
  return p->width==g->w&&p->height==g->h&&p->stride==g->stride&&p->c_height==g->ch&&p->x==g->x&&p->y_off==g->y;
}
static void forget(const struct tri_ctx *k,struct tri_state *s){
  if(s->owned)k->release(s->owned);
  s->owned=0;s->scratch=0;s->phase=0;s->generation=0;s->signature=0;s->count=0;s->bytes=0;
}
u32 tri_state_bytes(void){return sizeof(struct tri_state);}
void tri_cancel(const struct tri_ctx *k,struct tri_state *s){
  if(!k||!s)return;
  __atomic_store_n(&s->cancel,1,__ATOMIC_RELEASE);
  if(__atomic_exchange_n(&s->busy,1,__ATOMIC_ACQUIRE))return;
  forget(k,s);__atomic_store_n(&s->cancel,0,__ATOMIC_RELEASE);__atomic_store_n(&s->busy,0,__ATOMIC_RELEASE);
}
static void cache_picture(const struct tri_ctx *k,const struct tri_picture *p,int clean){
  u32 a=(u32)p->y&~63u,b=((u32)p->y+(u32)p->stride*p->height+63u)&~63u;
  u32 c=(u32)p->c&~63u,d=((u32)p->c+(u32)p->stride*p->height+63u)&~63u;
  if(clean){k->clean(a,b-a);k->clean(c,d-c);}else{k->invalidate(a,b-a);k->invalidate(c,d-c);}
}
static int allocate(const struct tri_ctx *k,struct tri_state *s,struct tri_picture *p,u32 count){
  u32 i,n=0,maxw=0,off=0,area;
  for(i=0;i<count;i++){
    area=(p[i].width>>2)*(p[i].height>>2);
    if(area>(LIMIT-n)/2)return 0;
    n+=2*area;if((p[i].width>>2)>maxw)maxw=p[i].width>>2;
  }
  s->bytes=((n+3u)&~3u)+8u*maxw;
  s->owned=(u8 *)k->alloc(s->bytes);if(!s->owned){s->bytes=0;return 0;}
  s->count=count;
  for(i=0;i<count;i++){
    struct tri_saved *v=&s->image[i];area=(p[i].width>>2)*(p[i].height>>2);
    v->r=s->owned+off;off+=area;v->g=s->owned+off;off+=area;
    v->geometry.w=p[i].width;v->geometry.h=p[i].height;v->geometry.stride=p[i].stride;
    v->geometry.ch=p[i].c_height;v->geometry.x=p[i].x;v->geometry.y=p[i].y_off;
  }
  s->scratch=(s16 *)(s->owned+((n+3u)&~3u));return 1;
}
static void block(const struct tri_picture *p,u32 bx,u32 by,u32 *r,u32 *g){
  u32 x,y,rr=0,gg=0;
  for(y=0;y<4;y++){
    const u8 *yp=p->y+(by*4+y)*p->stride+bx*4,*cp=p->c+(by*4+y)*p->stride+bx*4;
    for(x=0;x<4;x++){
      s32 cb=(s32)cp[x&~1u]-128,cr=(s32)cp[(x&~1u)+1]-128,Y=yp[x];
      rr+=clamp(Y+((359*cr+128)>>8));gg+=clamp(Y-((88*cb+183*cr+128)>>8));
    }
  }
  *r=(rr+8)>>4;*g=(gg+8)>>4;
}
static void store_plane(const struct tri_picture *p,u8 *out,u32 channel){
  u32 x,y,r,g,w=p->width>>2,h=p->height>>2;
  for(y=0;y<h;y++)for(x=0;x<w;x++){block(p,x,y,&r,&g);out[y*w+x]=(u8)(channel?g:r);}
}
static void delta_row(const struct tri_picture *p,const struct tri_saved *saved,u32 row,s16 *r,s16 *g){
  u32 x,a,b,w=p->width>>2;
  for(x=0;x<w;x++){block(p,x,row,&a,&b);r[x]=(s16)((s32)saved->r[row*w+x]-(s32)a);g[x]=(s16)((s32)saved->g[row*w+x]-(s32)b);}
}
static s32 interpolate(const s16 *a,const s16 *b,u32 x,u32 w,u32 ty){
  s32 q=(s32)(x>>2),fraction=(s32)(2*(x&3)+1)-4,l,r;
  u32 tx;
  if(fraction<0){q--;fraction+=8;}tx=(u32)fraction;
  l=q<0?0:q>=(s32)w?(s32)w-1:q;r=q+1;
  if(r<0)r=0;if(r>=(s32)w)r=(s32)w-1;
  return ((8-(s32)ty)*((8-(s32)tx)*a[l]+(s32)tx*a[r])+
          (s32)ty*((8-(s32)tx)*b[l]+(s32)tx*b[r])+32)>>6;
}
static void composite(struct tri_picture *p,const struct tri_saved *saved,s16 *work){
  u32 x,y,w=p->width>>2,h=p->height>>2,loaded=1;
  s16 *r[2]={work,work+w},*g[2]={work+2*w,work+3*w};
  delta_row(p,saved,0,r[0],g[0]);delta_row(p,saved,1,r[1],g[1]);
  for(y=0;y<p->height;y++){
    s32 q=(s32)(y>>2),fraction=(s32)(2*(y&3)+1)-4,lo,hi;u32 ty;
    if(fraction<0){q--;fraction+=8;}ty=(u32)fraction;
    lo=q<0?0:q>=(s32)h?(s32)h-1:q;hi=q+1;
    if(hi<0)hi=0;if(hi>=(s32)h)hi=(s32)h-1;
    while(loaded<(u32)hi){loaded++;delta_row(p,saved,loaded,r[loaded&1],g[loaded&1]);}
    for(x=0;x<p->width;x+=2){
      s32 dr0=interpolate(r[lo&1],r[hi&1],x,w,ty),dg0=interpolate(g[lo&1],g[hi&1],x,w,ty);
      s32 dr1=interpolate(r[lo&1],r[hi&1],x+1,w,ty),dg1=interpolate(g[lo&1],g[hi&1],x+1,w,ty);
      s32 sr=dr0+dr1,sg=dg0+dg1;u8 *yp=p->y+y*p->stride+x,*cp=p->c+y*p->stride+x;
      yp[0]=clamp(yp[0]+((77*dr0+150*dg0+128)>>8));
      yp[1]=clamp(yp[1]+((77*dr1+150*dg1+128)>>8));
      cp[0]=clamp(cp[0]+((-43*sr-85*sg+256)>>9));cp[1]=clamp(cp[1]+((128*sr-107*sg+256)>>9));
    }
  }
}
u32 tri_process(const struct tri_ctx *k,struct tri_state *s,const struct tri_identity *id,struct tri_picture *p,u32 count){
  u32 i,j,result=0;
  if(!k||!s||!id||!p)return 0;
  if(__atomic_exchange_n(&s->busy,1,__ATOMIC_ACQUIRE)){__atomic_store_n(&s->cancel,1,__ATOMIC_RELEASE);return 0;}
  if(__atomic_load_n(&s->cancel,__ATOMIC_ACQUIRE))goto fail;
  if(id->kind!=1||!id->generation||id->index<1||id->index>3||count<1||count>3)goto fail;
  for(i=0;i<count;i++)if(!picture_ok(&p[i]))goto fail;
  for(i=0;i<count;i++)for(j=0;j<i;j++){
    u32 a=(u32)p[i].stride*p[i].height,b=(u32)p[j].stride*p[j].height;
    if(overlap(p[i].y,a,p[j].y,b)||overlap(p[i].y,a,p[j].c,b)||
       overlap(p[i].c,a,p[j].y,b)||overlap(p[i].c,a,p[j].c,b))goto fail;
  }
  if(id->index==1){
    forget(k,s);
    if(!allocate(k,s,p,count))goto fail;
    s->generation=id->generation;s->signature=id->signature;
  }else{
    if(s->phase+1!=id->index||id->generation!=s->generation||id->signature!=s->signature||count!=s->count||
       id->milliseconds-s->now>EXPIRY)goto fail;
    for(i=0;i<count;i++)if(!geometry_equal(&p[i],&s->image[i].geometry))goto fail;
  }
  for(i=0;i<count;i++)cache_picture(k,&p[i],0);
  if(id->index<3){
    for(i=0;i<count;i++)store_plane(&p[i],id->index==1?s->image[i].r:s->image[i].g,id->index-1);
    s->phase=id->index;s->now=id->milliseconds;goto done;
  }
  if(__atomic_load_n(&s->cancel,__ATOMIC_ACQUIRE))goto fail;
  for(i=0;i<count;i++)composite(&p[i],&s->image[i],s->scratch);
  for(i=0;i<count;i++)cache_picture(k,&p[i],1);
  result=1;
fail:forget(k,s);
done:
  if(__atomic_load_n(&s->cancel,__ATOMIC_ACQUIRE))forget(k,s);
  __atomic_store_n(&s->cancel,0,__ATOMIC_RELEASE);__atomic_store_n(&s->busy,0,__ATOMIC_RELEASE);
  return result;
}
