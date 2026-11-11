/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GRMOD_TRICHROME_H
#define GRMOD_TRICHROME_H
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef short s16;
typedef int s32;
struct tri_picture {
  u8 format,pad[3]; u8 *y,*c; u32 size;
  u16 width,height,stride,c_height,x,y_off; u8 tail[4];
};
struct tri_ctx {
  void *(*alloc)(u32); void (*release)(void *);
  void (*invalidate)(u32,u32); void (*clean)(u32,u32);
};
/* Supplied by the native capture adapter, never inferred by JPEG call counts.
 * kind1: independently verified continuous capture. kind0: all other sources.
 * signature: adapter's exact settings identity; generation: per-release epoch.
 */
struct tri_identity { u32 generation,index,signature,kind,milliseconds; };
struct tri_geometry { u16 w,h,stride,ch,x,y; };
struct tri_saved { struct tri_geometry geometry; u8 *r,*g; };
struct tri_state {
  volatile u32 busy,cancel; u32 phase,generation,signature,now,count,bytes;
  u8 *owned; s16 *scratch; struct tri_saved image[3];
};
u32 tri_state_bytes(void);
void tri_cancel(const struct tri_ctx *,struct tri_state *);
u32 tri_process(const struct tri_ctx *,struct tri_state *,const struct tri_identity *,struct tri_picture *,u32);
#endif
