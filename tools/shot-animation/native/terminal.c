/* SPDX-License-Identifier: GPL-2.0-only */
#include "terminal.h"
#define HEADER 80u
#define SAMPLE 52u
#define SAMPLES 228u
#define POSE_PIXELS 16384u

static uint32_t rd16(const uint8_t *p){return p[0]|(uint32_t)p[1]<<8;}
static uint32_t rd32(const uint8_t *p){return rd16(p)|rd16(p+2)<<16;}
static int32_t si16(const uint8_t *p){return (int16_t)rd16(p);}
static int32_t si32(const uint8_t *p){return (int32_t)rd32(p);}
static uint32_t crc32(const uint8_t *p,uint32_t size){
  uint32_t crc=0xffffffffu,n;
  while(size--){crc^=*p++;for(n=0;n<8;n++)crc=crc&1?(crc>>1)^0xedb88320u:crc>>1;}
  return crc^0xffffffffu;
}
/* No compiler division helper or floating-point runtime is needed. */
static uint32_t divide_u(uint32_t n,uint32_t d){
  uint32_t result=0,bit=1;if(!d)return 0;
  while(d<=(n>>1)&&!(d&0x80000000u)){d<<=1;bit<<=1;}
  while(bit){if(n>=d){n-=d;result|=bit;}d>>=1;bit>>=1;}
  return result;
}
static int32_t divide_i(int32_t n,int32_t d){
  uint32_t a=n<0?(uint32_t)-n:(uint32_t)n,b=d<0?(uint32_t)-d:(uint32_t)d;
  int32_t q=(int32_t)divide_u(a,b);return (n<0)!=(d<0)?-q:q;
}
static uint32_t mul255(uint32_t a,uint32_t b){uint32_t n=a*b+128;return(n+(n>>8))>>8;}
static uint32_t premultiply(const uint8_t *p){
  uint32_t a=p[3];return mul255(p[0],a)|(mul255(p[1],a)<<8)|(mul255(p[2],a)<<16)|(a<<24);
}
static uint32_t scale_color(uint32_t p,uint32_t opacity){
  return mul255(p&255,opacity)|(mul255((p>>8)&255,opacity)<<8)|
    (mul255((p>>16)&255,opacity)<<16)|(mul255(p>>24,opacity)<<24);
}
static void blend(uint32_t *dest,uint32_t source){
  uint32_t a=source>>24,inv=255-a,d=*dest;
  if(!a)return;if(a==255){*dest=source;return;}
  *dest=((source&255)+mul255(d&255,inv))|
    ((((source>>8)&255)+mul255((d>>8)&255,inv))<<8)|
    ((((source>>16)&255)+mul255((d>>16)&255,inv))<<16)|
    ((a+mul255(d>>24,inv))<<24);
}

static int vectors_valid(const uint8_t *data,uint32_t bytes){
  uint32_t count,at=4,n,j;
  if(bytes<4||rd16(data+2))return 0;
  count=rd16(data);if(count>4096)return 0;
  for(n=0;n<count;n++){
    uint32_t points,size;
    if(at>bytes||bytes-at<8)return 0;
    points=rd16(data+at+4);if(points<3||points>256||rd16(data+at+6))return 0;
    size=8+points*4;if(size>bytes-at)return 0;
    for(j=0;j<points*2;j++){
      int32_t q=si16(data+at+8+j*2);if(q< -16384||q>16384)return 0;
    }
    at+=size;
  }
  return at==bytes;
}

int terminal_load(terminal_player *p,const uint8_t *a,uint32_t bytes){
  uint32_t colors,indices,tracks,vectors,i;
  if(!p)return 0;
  p->asset=0;p->bytes=0;p->loaded=0;p->active=0;p->previous=3;p->cursor=3;
  if(!a||bytes<HEADER||bytes>4u*1024u*1024u)return 0;
  if(a[0]!='T'||a[1]!='R'||a[2]!='M'||a[3]!='2'||rd16(a+4)!=2||rd16(a+6)!=HEADER)return 0;
  if(rd16(a+8)!=240||rd16(a+10)!=176||rd16(a+12)!=128||rd16(a+14)!=128||rd16(a+16)!=12)return 0;
  colors=rd16(a+18);
  if(!colors||colors>256||rd16(a+20)!=30||rd16(a+22)!=3||rd16(a+24)!=SAMPLES||rd16(a+26)!=SAMPLE)return 0;
  if(rd32(a+28)!=7600||rd32(a+32)!=1400||rd32(a+36)!=5000||rd32(a+40)!=1200||rd32(a+60)!=bytes)return 0;
  if(rd32(a+68)||rd32(a+72)||rd32(a+76)||rd32(a+44)!=HEADER)return 0;
  indices=HEADER+colors*4;tracks=indices+12*POSE_PIXELS;vectors=tracks+3*SAMPLES*SAMPLE;
  if(rd32(a+48)!=indices||rd32(a+52)!=tracks||rd32(a+56)!=vectors||vectors>bytes||bytes-vectors<4)return 0;
  if(rd32(a+64)!=crc32(a+HEADER,bytes-HEADER))return 0;
  for(i=indices;i<tracks;i++)if(a[i]>=colors)return 0;
  for(i=tracks;i<vectors;i+=SAMPLE){
    uint32_t layer;
    if(rd16(a+i)>=12||a[i+3])return 0;
    if(si16(a+i+28)>si16(a+i+32)||si16(a+i+30)>si16(a+i+34))return 0;
    for(layer=36;layer<=44;layer+=8){
      uint32_t start=rd32(a+i+layer),size=rd32(a+i+layer+4),available=bytes-vectors;
      if(start%4||size%4||size<4||start>available||size>available-start||!vectors_valid(a+vectors+start,size))return 0;
    }
  }
  for(i=0;i<colors;i++)p->colors[i]=premultiply(a+HEADER+i*4);
  p->inverse_alpha[0]=0;
  for(i=1;i<256;i++)p->inverse_alpha[i]=(uint16_t)divide_u(65280,i);
  p->asset=a;p->bytes=bytes;p->indices=indices;p->tracks=tracks;p->vectors=vectors;
  p->loaded=1;p->last_frame=0xffffffffu;return 1;
}

static void polygon(terminal_player *p,uint32_t *frame,uint32_t stride,
                    const uint8_t *points,uint32_t count,uint32_t color){
  int32_t top=176*16,bottom=0,y;
  uint32_t i;
  if(!(color>>24))return;
  for(i=0;i<count;i++){
    int32_t py=si16(points+i*4+2);if(py<top)top=py;if(py>bottom)bottom=py;
  }
  top=top>>4;bottom=(bottom+15)>>4;if(top<0)top=0;if(bottom>176)bottom=176;
  for(y=top;y<bottom;y++){
    int32_t scan=y*16+8;uint32_t hits=0;
    for(i=0;i<count;i++){
      uint32_t next=i+1==count?0:i+1;
      int32_t y1=si16(points+i*4+2),y2=si16(points+next*4+2),x1,x2,x;
      if(!((y1<=scan&&scan<y2)||(y2<=scan&&scan<y1)))continue;
      x1=si16(points+i*4);x2=si16(points+next*4);
      x=x1+divide_i((x2-x1)*(scan-y1),y2-y1);
      {uint32_t j=hits;while(j&&p->intersections[j-1]>x){p->intersections[j]=p->intersections[j-1];--j;}
        p->intersections[j]=x;++hits;}
    }
    for(i=0;i+1<hits;i+=2){
      int32_t left=p->intersections[i],right=p->intersections[i+1],x,first,last;
      if(left<0)left=0;if(right>240*16)right=240*16;
      if(right<=left)continue;first=left>>4;last=(right-1)>>4;
      for(x=first;x<=last;x++){
        int32_t low=x*16>left?x*16:left,high=(x+1)*16<right?(x+1)*16:right;
        uint32_t coverage=(uint32_t)(high-low);
        blend(frame+y*stride+x,coverage==16?color:scale_color(color,coverage*255u/16u));
      }
    }
  }
}

static void draw_vectors(terminal_player *p,uint32_t *frame,uint32_t stride,const uint8_t *data){
  uint32_t count=rd16(data),i;data+=4;
  for(i=0;i<count;i++){
    uint32_t points=rd16(data+4);polygon(p,frame,stride,data+8,points,premultiply(data));data+=8+points*4;
  }
}

static uint32_t mix(uint32_t a,uint32_t b,uint32_t fraction){
  uint32_t inv=256-fraction;
  uint32_t rb=(((a&0x00ff00ffu)*inv+(b&0x00ff00ffu)*fraction+0x00800080u)>>8)&0x00ff00ffu;
  uint32_t ga=((((a>>8)&0x00ff00ffu)*inv+((b>>8)&0x00ff00ffu)*fraction+0x00800080u)>>8)&0x00ff00ffu;
  return rb|(ga<<8);
}
static uint32_t sample(const terminal_player *p,const uint8_t *indices,int32_t x,int32_t y){
  if(x<0||x>=128||y<0||y>=128)return 0;return p->colors[indices[y*128+x]];
}
static void draw_sprite(terminal_player *p,uint32_t *frame,uint32_t stride,const uint8_t *s){
  int32_t a=si32(s+4),b=si32(s+8),c=si32(s+12),d=si32(s+16),tx=si32(s+20),ty=si32(s+24);
  int32_t left=si16(s+28)-1,top=si16(s+30)-1,right=si16(s+32)+1,bottom=si16(s+34)+1,y;
  uint32_t opacity=s[2];const uint8_t *indices=p->asset+p->indices+rd16(s)*POSE_PIXELS;
  if(!opacity)return;
  if(left<0)left=0;if(top<0)top=0;if(right>240)right=240;if(bottom>176)bottom=176;
  for(y=top;y<bottom;y++){
    int32_t x;int64_t u=(int64_t)a*left+(int64_t)c*y+tx+((int64_t)a+c)/2-32768;
    int64_t v=(int64_t)b*left+(int64_t)d*y+ty+((int64_t)b+d)/2-32768;
    for(x=left;x<right;x++,u+=a,v+=b){
      int32_t sx=(int32_t)(u>>16),sy=(int32_t)(v>>16);uint32_t color;
      uint32_t fx=((uint32_t)(u>>8))&255,fy=((uint32_t)(v>>8))&255;
      if(sx< -1||sx>=128||sy< -1||sy>=128)continue;
      color=mix(mix(sample(p,indices,sx,sy),sample(p,indices,sx+1,sy),fx),
                mix(sample(p,indices,sx,sy+1),sample(p,indices,sx+1,sy+1),fx),fy);
      blend(frame+y*stride+x,opacity==255?color:scale_color(color,opacity));
    }
  }
}

int terminal_render(terminal_player *p,uint32_t sequence,uint32_t elapsed,uint32_t *frame,
                    uint32_t stride,uint32_t capacity){
  uint32_t i,y,at;const uint8_t *s;
  if(!p||!p->loaded||!frame||sequence>=3||elapsed>=7600||stride<240||stride>4096||capacity<176*stride)return 0;
  for(y=0;y<176;y++)for(i=0;i<240;i++)frame[y*stride+i]=0;
  at=elapsed*30u/1000u;s=p->asset+p->tracks+(sequence*SAMPLES+at)*SAMPLE;
  draw_vectors(p,frame,stride,p->asset+p->vectors+rd32(s+36));
  draw_sprite(p,frame,stride,s);
  draw_vectors(p,frame,stride,p->asset+p->vectors+rd32(s+44));
  /* Convert the internal premultiplied accumulator to the native RGBA bitmap. */
  for(y=0;y<176;y++)for(i=0;i<240;i++){
    uint32_t value=frame[y*stride+i],alpha=value>>24;
    if(alpha&&alpha!=255){
      uint32_t inverse=p->inverse_alpha[alpha],r=((value&255)*inverse+128)>>8;
      uint32_t g=(((value>>8)&255)*inverse+128)>>8,b=(((value>>16)&255)*inverse+128)>>8;
      if(r>255)r=255;if(g>255)g=255;if(b>255)b=255;
      frame[y*stride+i]=r|(g<<8)|(b<<16)|(alpha<<24);
    }
  }
  return 1;
}

static uint32_t random_next(uint32_t n){n^=n<<13;n^=n>>17;n^=n<<5;return n;}
int terminal_shot(terminal_player *p,uint32_t now,uint32_t entropy){
  uint32_t i;
  if(!p||!p->loaded)return 0;
  if(p->cursor>=3){
    p->bag[0]=0;p->bag[1]=1;p->bag[2]=2;entropy=entropy?entropy:0x9e3779b9u;
    for(i=2;i;i--){uint32_t j;uint8_t swap;entropy=random_next(entropy);j=i==2?entropy%3:entropy&1;swap=p->bag[i];p->bag[i]=p->bag[j];p->bag[j]=swap;}
    if(p->bag[0]==p->previous){uint32_t j=1+(entropy&1);uint8_t swap=p->bag[0];p->bag[0]=p->bag[j];p->bag[j]=swap;}
    p->cursor=0;
  }
  p->sequence=p->bag[p->cursor++];p->previous=p->sequence;p->started=now;
  p->last_frame=0xffffffffu;p->active=1;return 1;
}
int terminal_tick(terminal_player *p,uint32_t now,uint32_t *frame,uint32_t stride,uint32_t capacity){
  uint32_t elapsed,index;
  if(!p||!p->active)return 0;elapsed=now-p->started;
  if(elapsed>=7600){p->active=0;return -1;}
  index=elapsed*30u/1000u;if(index==p->last_frame)return 0;
  if(!terminal_render(p,p->sequence,elapsed,frame,stride,capacity)){p->active=0;return -2;}
  p->last_frame=index;return 1;
}
void terminal_cancel(terminal_player *p){if(p)p->active=0;}
