/* SPDX-License-Identifier: GPL-2.0-only
 * Experimental GR III face-local JPEG finishing. No allocation/global state.
 * config+0x34 is the CURRENT macro configuration's owned CommonProperty
 * pointer, proved by the original configuration builder and selector.
 * Only current/B face results are copied. A is the preceding detector ring.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int s32;
struct picture { u8 format,pad[3]; u8 *y,*c; u32 size; u16 w,h,stride,ch,x,yo; u8 tail[4]; };
struct context {
  u32 magic; void *(*cache)(void); void (*invalidate)(void*,u32,u32); void (*clean)(void*,u32,u32);
  const u8 *lift; u32 fw,fh,films,reserved; u8 keeper[20];
};
struct rect { u32 x,y,w,h; };
struct ellipse { s32 cx2,cy2; u32 iw,ih; };
static int ram(const void*,u32);
static u32 divide(u32,u32);
static u32 weight(s32,s32,const struct ellipse*,u32);
static void process(const struct context*,void*,const struct picture*,const struct rect*,u32,u32);

void face_fill(const struct context *k,u32 *config) {
  struct rect faces[10]; const struct picture *pics[4]; u32 count,i,j,look,main=0,n=0;
  const u8 *record;
  void *cache;
  if(k->magic!=0x314c4646u || k->films>20 || !k->films || !k->fw || !k->fh ||
      k->fw>6000 || k->fh>4000 || !ram(config,0x4c))return;
  record=(const u8*)config[0x34/4];
  if(!ram(record,0x39270))return;
  /* Movie records excluded. RAW development is unsupported/unverified.
   * Film ID comes from the owned render record, not a global. */
  look=record[0x77c];
  if(look<64 || look>=64+k->films || record[0x44])return;
  if(*(const u32*)(record+0x38d50)!=k->fw || *(const u32*)(record+0x38d54)!=k->fh)return;
  if(*(const u16*)(record+0x38d68)>10)return;
  count=*(const u16*)(record+0x38d6c);
  if(!count || count>10)return;
  for(i=0;i<count;i++) {
    const u32 *p=(const u32*)(record+0x38ff0+i*64);
    struct rect r; r.x=p[0];r.y=p[1];r.w=p[2];r.h=p[3];
    if(!r.w || !r.h || r.w>k->fw || r.h>k->fh || r.x>k->fw-r.w || r.y>k->fh-r.h)return;
    faces[i]=r;
  }
  /* Validate all supported picture planes before writing any picture. */
  for(i=0;i<4;i++) {
    const struct picture *p=(const struct picture*)config[15+i];u32 bytes,ya,ca;
    if(!p)continue;
    if(!ram(p,32))return;
    if(p->format!=1 || p->x || p->yo || p->w<48 || p->h<32 || (p->w&1) || p->w>k->fw || p->h>k->fh ||
       (u32)p->w*k->fh!=(u32)p->h*k->fw)continue;
    if(p->stride<p->w || p->stride>16384 || p->ch<p->h)return;
    bytes=(u32)p->stride*p->h;ya=(u32)p->y;ca=(u32)p->c;
    /* Descriptor+0x0c is opaque here, as in the existing native grain module.
     * Bounds use the verified width/height/stride fields directly. */
    if(!ram(p->y,bytes) || !ram(p->c,bytes) || ya<0x5d000000u || ca<0x5d000000u)return;
    if(ya<ca+bytes && ca<ya+bytes)return;
    for(j=0;j<n;j++) {
      u32 old=(u32)pics[j]->stride*pics[j]->h,oy=(u32)pics[j]->y,oc=(u32)pics[j]->c;
      if(ya==oy && ca==oc && p->w==pics[j]->w && p->h==pics[j]->h && p->stride==pics[j]->stride)break;
      if((ya<oy+old && oy<ya+bytes)||(ya<oc+old && oc<ya+bytes)||
         (ca<oy+old && oy<ca+bytes)||(ca<oc+old && oc<ca+bytes))return;
    }
    if(j<n)continue;
    pics[n++]=p;
    if(p->w==k->fw && p->h==k->fh)main=1;
  }
  if(!main)return; /* no transformed crop/thumbnail-only inference */
  cache=k->cache();
  for(i=0;i<n;i++)process(k,cache,pics[i],faces,count,k->keeper[look-64]!=0);
}

/* Called before native capture. If no result is requested/populated, the JPEG
 * cannot inherit a prior B count. The original capture subsequently owns and
 * writes all metadata, including the actual current count and rectangles. */
void face_capture_clear(u8 *record) {
  if(ram(record,0x39270))*(u16*)(record+0x38d6c)=0;
}

static int ram(const void *p,u32 n) {
  u32 a=(u32)p;
  return a>=0x55000000u && a<0xc0000000u && !(a&3) && n<=0xc0000000u-a;
}
static u32 divide(u32 n,u32 d) {
  u32 q=0,r=0; s32 i;
  if(!d)return 0;
  for(i=31;i>=0;i--){r=(r<<1)|((n>>i)&1);if(r>=d){r-=d;q|=1u<<i;}}
  return q;
}
static u32 weight(s32 x,s32 y,const struct ellipse *e,u32 n) {
  u32 i,best=0;
  for(i=0;i<n;i++) {
    s32 nx=((2*x+1-e[i].cx2)*(s32)e[i].iw)>>8;
    s32 ny=((2*y+1-e[i].cy2)*(s32)e[i].ih)>>8;
    u32 rr,t,q;
    if(nx<=-256 || nx>=256 || ny<=-256 || ny>=256)continue;
    rr=(u32)(nx*nx+ny*ny);if(rr>=65536)continue;
    t=rr<=24576?0:(rr-24576)/160;
    q=256-((t*t*(768-2*t)+32768)>>16);if(q>best)best=q;
  }
  return best;
}
static s32 minimum(s32 a,s32 b){return a<b?a:b;}
static s32 maximum(s32 a,s32 b){return a>b?a:b;}
static void process(const struct context *k,void *cache,const struct picture *p,const struct rect *r,u32 n,u32 keeper) {
  struct ellipse e[10];u32 i,used=0,x,y,x0=p->w,x1=0,y0=p->h,y1=0,bytes=(u32)p->stride*p->h;
  u32 ya=(u32)p->y&~63u,ca=(u32)p->c&~63u;
  u32 yn=(((u32)p->y+bytes+63)&~63u)-ya,cn=(((u32)p->c+bytes+63)&~63u)-ca;
  for(i=0;i<n;i++) {
    u32 a=divide(r[i].x*p->w,k->fw),b=divide(r[i].y*p->h,k->fh);
    u32 c=divide((r[i].x+r[i].w)*p->w,k->fw),d=divide((r[i].y+r[i].h)*p->h,k->fh);
    if(c<=a || d<=b)continue;
    e[used].cx2=(s32)(a+c);e[used].cy2=(s32)(b+d);
    e[used].iw=divide(65536,c-a);e[used].ih=divide(65536,d-b);used++;
    if(a<x0)x0=a;if(c>x1)x1=c;if(b<y0)y0=b;if(d>y1)y1=d;
  }
  if(!used)return;
  x0&=~1u;x1=(x1+1)&~1u;
  k->invalidate(cache,ya,yn);k->invalidate(cache,ca,cn);
  for(y=y0;y<y1;y++)for(x=x0;x<x1;x+=2) {
    u32 at=y*p->stride+x,q[2],j;
    s32 cb=p->c[at],cr=p->c[at+1],gate=256;
    gate=minimum(gate,(cb-72)*16);gate=minimum(gate,(144-cb)*16);
    gate=minimum(gate,(cr-122)*24);gate=minimum(gate,(196-cr)*8);
    gate=maximum(0,minimum(gate,(cr-cb)*24));
    if(!gate)continue;
    for(j=0;j<2;j++) {
      s32 Y=p->y[at+j],g=gate*maximum(0,minimum(256,(Y-4)*32))>>8;
      s32 peak=maximum(Y+((359*(cr-128)+128)>>8),Y-((88*(cb-128)+183*(cr-128)+128)>>8));
      s32 delta;peak=maximum(peak,Y+((454*(cb-128)+128)>>8));
      q[j]=weight((s32)(x+j),(s32)y,e,used)*(u32)g>>8;
      delta=minimum((s32)(k->lift[Y]*q[j]>>8),maximum(0,254-peak));
      p->y[at+j]=(u8)(Y+delta);
    }
    if(keeper) {
      s32 amount=(minimum((s32)q[0],(s32)q[1])*77+128)>>8;
      p->c[at]=(u8)(cb+(((128-cb)*amount+128)>>8));
      p->c[at+1]=(u8)(cr+(((128-cr)*amount+128)>>8));
    }
  }
  k->clean(cache,ya,yn);k->clean(cache,ca,cn);
}
