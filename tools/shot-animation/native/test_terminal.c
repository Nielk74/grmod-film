/* SPDX-License-Identifier: GPL-2.0-only */
#include "terminal.h"
terminal_player player;
uint32_t frame[TERMINAL_PIXELS+2];
uint32_t checks;
#define CHECK(condition) do {++checks;if(!(condition))return __LINE__;} while(0)

int test_terminal_asset(const uint8_t *asset,uint32_t bytes){
  uint32_t i,previous=3,bits=0;
  CHECK(terminal_load(&player,asset,bytes));
  CHECK(!player.active);
  CHECK(terminal_shot(&player,0xfffffff0u,123));
  frame[0]=0xdeadbeefu;frame[TERMINAL_PIXELS+1]=0xcafef00du;
  CHECK(terminal_tick(&player,0xfffffff0u,frame+1,240,TERMINAL_PIXELS)==1);
  CHECK(terminal_tick(&player,0xfffffff1u,frame+1,240,TERMINAL_PIXELS)==0);
  CHECK(terminal_tick(&player,0xfffffff0u+7500u,frame+1,240,TERMINAL_PIXELS)==1);
  CHECK(terminal_tick(&player,0xfffffff0u+7600u,frame+1,240,TERMINAL_PIXELS)==-1);
  CHECK(!player.active);
  CHECK(terminal_tick(&player,0x2000u,frame+1,240,TERMINAL_PIXELS)==0);
  CHECK(frame[0]==0xdeadbeefu&&frame[TERMINAL_PIXELS+1]==0xcafef00du);
  CHECK(!terminal_render(&player,3,3000,frame+1,240,TERMINAL_PIXELS));
  CHECK(!terminal_render(&player,0,7600,frame+1,240,TERMINAL_PIXELS));
  CHECK(!terminal_render(&player,0,3000,frame+1,239,TERMINAL_PIXELS));
  CHECK(!terminal_render(&player,0,3000,frame+1,240,TERMINAL_PIXELS-1));
  CHECK(terminal_load(&player,asset,bytes));
  for(i=0;i<120;i++){
    CHECK(terminal_shot(&player,1000u+i*23u,0x9e3779b9u*i+8));
    CHECK(player.sequence<3&&player.sequence!=previous);
    previous=player.sequence;bits|=1u<<previous;
    if(i%3u==2){CHECK(bits==7);bits=0;}
    CHECK(terminal_tick(&player,1000u+i*23u,frame+1,240,TERMINAL_PIXELS)==1);
    terminal_cancel(&player);CHECK(!player.active);
  }
  CHECK(frame[0]==0xdeadbeefu&&frame[TERMINAL_PIXELS+1]==0xcafef00du);
  return 0;
}

int test_terminal_render(uint32_t sequence,uint32_t ms){
  CHECK(terminal_render(&player,sequence,ms,frame+1,240,TERMINAL_PIXELS));
  CHECK(frame[0]==0xdeadbeefu&&frame[TERMINAL_PIXELS+1]==0xcafef00du);
  return 0;
}

int test_terminal_reject(const uint8_t *asset,uint32_t bytes){
  CHECK(!terminal_load(&player,asset,bytes));CHECK(!player.loaded&&!player.active);
  CHECK(!terminal_shot(&player,0,0));return 0;
}
