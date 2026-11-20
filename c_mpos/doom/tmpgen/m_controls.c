//
// Copyright(C) 1993-1996 Id Software, Inc.
// Copyright(C) 1993-2008 Raven Software
// Copyright(C) 2005-2014 Simon Howard
//
// This program is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public License
// as published by the Free Software Foundation; either version 2
// of the License, or (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//

#include <stdio.h>

#include "doomtype.h"
#include "doomkeys.h"

#include "m_config.h"
#include "m_misc.h"

//
// Keyboard controls
//

static int const key_right_init = KEY_RIGHTARROW;
int key_right;
static int const key_left_init = KEY_LEFTARROW;
int key_left;
static int const key_up_init = KEY_UPARROW;
int key_up;
static int const key_down_init = KEY_DOWNARROW;
int key_down; 
static int const key_strafeleft_init = KEY_STRAFE_L;
int key_strafeleft;
static int const key_straferight_init = KEY_STRAFE_R;
int key_straferight;
static int const key_fire_init = KEY_FIRE;
int key_fire;
static int const key_use_init = KEY_USE;
int key_use;
static int const key_strafe_init = KEY_RALT;
int key_strafe;
static int const key_speed_init = KEY_RSHIFT;
int key_speed; 

// 
// Heretic keyboard controls
//
 
static int const key_flyup_init = KEY_PGUP;
int key_flyup;
static int const key_flydown_init = KEY_INS;
int key_flydown;
static int const key_flycenter_init = KEY_HOME;
int key_flycenter;

static int const key_lookup_init = KEY_PGDN;
int key_lookup;
static int const key_lookdown_init = KEY_DEL;
int key_lookdown;
static int const key_lookcenter_init = KEY_END;
int key_lookcenter;

static int const key_invleft_init = '[';
int key_invleft;
static int const key_invright_init = ']';
int key_invright;
static int const key_useartifact_init = KEY_ENTER;
int key_useartifact;

//
// Hexen key controls
//

static int const key_jump_init = '/';
int key_jump;

static int const key_arti_all_init = KEY_BACKSPACE;
int key_arti_all;
static int const key_arti_health_init = '\\';
int key_arti_health;
static int const key_arti_poisonbag_init = '0';
int key_arti_poisonbag;
static int const key_arti_blastradius_init = '9';
int key_arti_blastradius;
static int const key_arti_teleport_init = '8';
int key_arti_teleport;
static int const key_arti_teleportother_init = '7';
int key_arti_teleportother;
static int const key_arti_egg_init = '6';
int key_arti_egg;
static int const key_arti_invulnerability_init = '5';
int key_arti_invulnerability;

//
// Strife key controls
//
// haleyjd 09/01/10
//

// Note: Strife also uses key_invleft, key_invright, key_jump, key_lookup, and
// key_lookdown, but with different default values.

static int const key_usehealth_init = 'h';
int key_usehealth;
static int const key_invquery_init = 'q';
int key_invquery;
static int const key_mission_init = 'w';
int key_mission;
static int const key_invpop_init = 'z';
int key_invpop;
static int const key_invkey_init = 'k';
int key_invkey;
static int const key_invhome_init = KEY_HOME;
int key_invhome;
static int const key_invend_init = KEY_END;
int key_invend;
static int const key_invuse_init = KEY_ENTER;
int key_invuse;
static int const key_invdrop_init = KEY_BACKSPACE;
int key_invdrop;


//
// Mouse controls
//

static int const mousebfire_init = 0;
int mousebfire;
static int const mousebstrafe_init = 1;
int mousebstrafe;
static int const mousebforward_init = 2;
int mousebforward;

static int const mousebjump_init = -1;
int mousebjump;

static int const mousebstrafeleft_init = -1;
int mousebstrafeleft;
static int const mousebstraferight_init = -1;
int mousebstraferight;
static int const mousebbackward_init = -1;
int mousebbackward;
static int const mousebuse_init = -1;
int mousebuse;

static int const mousebprevweapon_init = -1;
int mousebprevweapon;
static int const mousebnextweapon_init = -1;
int mousebnextweapon;


static int const key_message_refresh_init = KEY_ENTER;
int key_message_refresh;
static int const key_pause_init = KEY_PAUSE;
int key_pause;
static int const key_demo_quit_init = 'q';
int key_demo_quit;
static int const key_spy_init = KEY_F12;
int key_spy;

// Multiplayer chat keys:

static int const key_multi_msg_init = 't';
int key_multi_msg;
int key_multi_msgplayer[8];

// Weapon selection keys:

static int const key_weapon1_init = '1';
int key_weapon1;
static int const key_weapon2_init = '2';
int key_weapon2;
static int const key_weapon3_init = '3';
int key_weapon3;
static int const key_weapon4_init = '4';
int key_weapon4;
static int const key_weapon5_init = '5';
int key_weapon5;
static int const key_weapon6_init = '6';
int key_weapon6;
static int const key_weapon7_init = '7';
int key_weapon7;
static int const key_weapon8_init = '8';
int key_weapon8;
static int const key_prevweapon_init = 0;
int key_prevweapon;
static int const key_nextweapon_init = 0;
int key_nextweapon;

// Map control keys:

static int const key_map_north_init = KEY_UPARROW;
int key_map_north;
static int const key_map_south_init = KEY_DOWNARROW;
int key_map_south;
static int const key_map_east_init = KEY_RIGHTARROW;
int key_map_east;
static int const key_map_west_init = KEY_LEFTARROW;
int key_map_west;
static int const key_map_zoomin_init = '=';
int key_map_zoomin;
static int const key_map_zoomout_init = '-';
int key_map_zoomout;
static int const key_map_toggle_init = KEY_TAB;
int key_map_toggle;
static int const key_map_maxzoom_init = '0';
int key_map_maxzoom;
static int const key_map_follow_init = 'f';
int key_map_follow;
static int const key_map_grid_init = 'g';
int key_map_grid;
static int const key_map_mark_init = 'm';
int key_map_mark;
static int const key_map_clearmark_init = 'c';
int key_map_clearmark;

// menu keys:

static int const key_menu_activate_init = KEY_ESCAPE;
int key_menu_activate;
static int const key_menu_up_init = KEY_UPARROW;
int key_menu_up;
static int const key_menu_down_init = KEY_DOWNARROW;
int key_menu_down;
static int const key_menu_left_init = KEY_LEFTARROW;
int key_menu_left;
static int const key_menu_right_init = KEY_RIGHTARROW;
int key_menu_right;
static int const key_menu_back_init = KEY_BACKSPACE;
int key_menu_back;
static int const key_menu_forward_init = KEY_ENTER;
int key_menu_forward;
static int const key_menu_confirm_init = 'y';
int key_menu_confirm;
static int const key_menu_abort_init = 'n';
int key_menu_abort;

static int const key_menu_help_init = KEY_F1;
int key_menu_help;
static int const key_menu_save_init = KEY_F2;
int key_menu_save;
static int const key_menu_load_init = KEY_F3;
int key_menu_load;
static int const key_menu_volume_init = KEY_F4;
int key_menu_volume;
static int const key_menu_detail_init = KEY_F5;
int key_menu_detail;
static int const key_menu_qsave_init = KEY_F6;
int key_menu_qsave;
static int const key_menu_endgame_init = KEY_F7;
int key_menu_endgame;
static int const key_menu_messages_init = KEY_F8;
int key_menu_messages;
static int const key_menu_qload_init = KEY_F9;
int key_menu_qload;
static int const key_menu_quit_init = KEY_F10;
int key_menu_quit;
static int const key_menu_gamma_init = KEY_F11;
int key_menu_gamma;

static int const key_menu_incscreen_init = KEY_EQUALS;
int key_menu_incscreen;
static int const key_menu_decscreen_init = KEY_MINUS;
int key_menu_decscreen;
static int const key_menu_screenshot_init = 0;
int key_menu_screenshot;

//
// Joystick controls
//

static int const joybfire_init = 0;
int joybfire;
static int const joybstrafe_init = 1;
int joybstrafe;
static int const joybuse_init = 3;
int joybuse;
static int const joybspeed_init = 2;
int joybspeed;

static int const joybstrafeleft_init = -1;
int joybstrafeleft;
static int const joybstraferight_init = -1;
int joybstraferight;

static int const joybjump_init = -1;
int joybjump;

static int const joybprevweapon_init = -1;
int joybprevweapon;
static int const joybnextweapon_init = -1;
int joybnextweapon;

static int const joybmenu_init = -1;
int joybmenu;

// Control whether if a mouse button is double clicked, it acts like 
// "use" has been pressed

static int const dclick_use_init = 1;
int dclick_use;
 
// 
// Bind all of the common controls used by Doom and all other games.
//

void M_BindBaseControls(void)
{
    M_BindVariable("key_right",          &key_right);
    M_BindVariable("key_left",           &key_left);
    M_BindVariable("key_up",             &key_up);
    M_BindVariable("key_down",           &key_down);
    M_BindVariable("key_strafeleft",     &key_strafeleft);
    M_BindVariable("key_straferight",    &key_straferight);
    M_BindVariable("key_fire",           &key_fire);
    M_BindVariable("key_use",            &key_use);
    M_BindVariable("key_strafe",         &key_strafe);
    M_BindVariable("key_speed",          &key_speed);

    M_BindVariable("mouseb_fire",        &mousebfire);
    M_BindVariable("mouseb_strafe",      &mousebstrafe);
    M_BindVariable("mouseb_forward",     &mousebforward);

    M_BindVariable("joyb_fire",          &joybfire);
    M_BindVariable("joyb_strafe",        &joybstrafe);
    M_BindVariable("joyb_use",           &joybuse);
    M_BindVariable("joyb_speed",         &joybspeed);

    M_BindVariable("joyb_menu_activate", &joybmenu);

    // Extra controls that are not in the Vanilla versions:

    M_BindVariable("joyb_strafeleft",    &joybstrafeleft);
    M_BindVariable("joyb_straferight",   &joybstraferight);
    M_BindVariable("mouseb_strafeleft",  &mousebstrafeleft);
    M_BindVariable("mouseb_straferight", &mousebstraferight);
    M_BindVariable("mouseb_use",         &mousebuse);
    M_BindVariable("mouseb_backward",    &mousebbackward);
    M_BindVariable("dclick_use",         &dclick_use);
    M_BindVariable("key_pause",          &key_pause);
    M_BindVariable("key_message_refresh", &key_message_refresh);
}

void M_BindHereticControls(void)
{
    M_BindVariable("key_flyup",          &key_flyup);
    M_BindVariable("key_flydown",        &key_flydown);
    M_BindVariable("key_flycenter",      &key_flycenter);

    M_BindVariable("key_lookup",         &key_lookup);
    M_BindVariable("key_lookdown",       &key_lookdown);
    M_BindVariable("key_lookcenter",     &key_lookcenter);

    M_BindVariable("key_invleft",        &key_invleft);
    M_BindVariable("key_invright",       &key_invright);
    M_BindVariable("key_useartifact",    &key_useartifact);
}

void M_BindHexenControls(void)
{
    M_BindVariable("key_jump",           &key_jump);
    M_BindVariable("mouseb_jump",        &mousebjump);
    M_BindVariable("joyb_jump",          &joybjump);

    M_BindVariable("key_arti_all",             &key_arti_all);
    M_BindVariable("key_arti_health",          &key_arti_health);
    M_BindVariable("key_arti_poisonbag",       &key_arti_poisonbag);
    M_BindVariable("key_arti_blastradius",     &key_arti_blastradius);
    M_BindVariable("key_arti_teleport",        &key_arti_teleport);
    M_BindVariable("key_arti_teleportother",   &key_arti_teleportother);
    M_BindVariable("key_arti_egg",             &key_arti_egg);
    M_BindVariable("key_arti_invulnerability", &key_arti_invulnerability);
}

void M_BindStrifeControls(void)
{
    // These are shared with all games, but have different defaults:
    key_message_refresh = '/';

    // These keys are shared with Heretic/Hexen but have different defaults:
    key_jump     = 'a';
    key_lookup   = KEY_PGUP;
    key_lookdown = KEY_PGDN;
    key_invleft  = KEY_INS;
    key_invright = KEY_DEL;

    M_BindVariable("key_jump",           &key_jump);
    M_BindVariable("key_lookUp",         &key_lookup);
    M_BindVariable("key_lookDown",       &key_lookdown);
    M_BindVariable("key_invLeft",        &key_invleft);
    M_BindVariable("key_invRight",       &key_invright);

    // Custom Strife-only Keys:
    M_BindVariable("key_useHealth",      &key_usehealth);
    M_BindVariable("key_invquery",       &key_invquery);
    M_BindVariable("key_mission",        &key_mission);
    M_BindVariable("key_invPop",         &key_invpop);
    M_BindVariable("key_invKey",         &key_invkey);
    M_BindVariable("key_invHome",        &key_invhome);
    M_BindVariable("key_invEnd",         &key_invend);
    M_BindVariable("key_invUse",         &key_invuse);
    M_BindVariable("key_invDrop",        &key_invdrop);

    // Strife also supports jump on mouse and joystick, and in the exact same
    // manner as Hexen!
    M_BindVariable("mouseb_jump",        &mousebjump);
    M_BindVariable("joyb_jump",          &joybjump);
}

void M_BindWeaponControls(void)
{
    M_BindVariable("key_weapon1",        &key_weapon1);
    M_BindVariable("key_weapon2",        &key_weapon2);
    M_BindVariable("key_weapon3",        &key_weapon3);
    M_BindVariable("key_weapon4",        &key_weapon4);
    M_BindVariable("key_weapon5",        &key_weapon5);
    M_BindVariable("key_weapon6",        &key_weapon6);
    M_BindVariable("key_weapon7",        &key_weapon7);
    M_BindVariable("key_weapon8",        &key_weapon8);

    M_BindVariable("key_prevweapon",     &key_prevweapon);
    M_BindVariable("key_nextweapon",     &key_nextweapon);

    M_BindVariable("joyb_prevweapon",    &joybprevweapon);
    M_BindVariable("joyb_nextweapon",    &joybnextweapon);

    M_BindVariable("mouseb_prevweapon",  &mousebprevweapon);
    M_BindVariable("mouseb_nextweapon",  &mousebnextweapon);
}

void M_BindMapControls(void)
{
    M_BindVariable("key_map_north",      &key_map_north);
    M_BindVariable("key_map_south",      &key_map_south);
    M_BindVariable("key_map_east",       &key_map_east);
    M_BindVariable("key_map_west",       &key_map_west);
    M_BindVariable("key_map_zoomin",     &key_map_zoomin);
    M_BindVariable("key_map_zoomout",    &key_map_zoomout);
    M_BindVariable("key_map_toggle",     &key_map_toggle);
    M_BindVariable("key_map_maxzoom",    &key_map_maxzoom);
    M_BindVariable("key_map_follow",     &key_map_follow);
    M_BindVariable("key_map_grid",       &key_map_grid);
    M_BindVariable("key_map_mark",       &key_map_mark);
    M_BindVariable("key_map_clearmark",  &key_map_clearmark);
}

void M_BindMenuControls(void)
{
    M_BindVariable("key_menu_activate",  &key_menu_activate);
    M_BindVariable("key_menu_up",        &key_menu_up);
    M_BindVariable("key_menu_down",      &key_menu_down);
    M_BindVariable("key_menu_left",      &key_menu_left);
    M_BindVariable("key_menu_right",     &key_menu_right);
    M_BindVariable("key_menu_back",      &key_menu_back);
    M_BindVariable("key_menu_forward",   &key_menu_forward);
    M_BindVariable("key_menu_confirm",   &key_menu_confirm);
    M_BindVariable("key_menu_abort",     &key_menu_abort);

    M_BindVariable("key_menu_help",      &key_menu_help);
    M_BindVariable("key_menu_save",      &key_menu_save);
    M_BindVariable("key_menu_load",      &key_menu_load);
    M_BindVariable("key_menu_volume",    &key_menu_volume);
    M_BindVariable("key_menu_detail",    &key_menu_detail);
    M_BindVariable("key_menu_qsave",     &key_menu_qsave);
    M_BindVariable("key_menu_endgame",   &key_menu_endgame);
    M_BindVariable("key_menu_messages",  &key_menu_messages);
    M_BindVariable("key_menu_qload",     &key_menu_qload);
    M_BindVariable("key_menu_quit",      &key_menu_quit);
    M_BindVariable("key_menu_gamma",     &key_menu_gamma);

    M_BindVariable("key_menu_incscreen", &key_menu_incscreen);
    M_BindVariable("key_menu_decscreen", &key_menu_decscreen);
    M_BindVariable("key_menu_screenshot",&key_menu_screenshot);
    M_BindVariable("key_demo_quit",      &key_demo_quit);
    M_BindVariable("key_spy",            &key_spy);
}

void M_BindChatControls(unsigned int num_players)
{
    char name[32];  // haleyjd: 20 not large enough - Thank you, come again!
    unsigned int i; // haleyjd: signedness conflict

    M_BindVariable("key_multi_msg",     &key_multi_msg);

    for (i=0; i<num_players; ++i)
    {
        M_snprintf(name, sizeof(name), "key_multi_msgplayer%i", i + 1);
        M_BindVariable(name, &key_multi_msgplayer[i]);
    }
}

//
// Apply custom patches to the default values depending on the
// platform we are running on.
//

void M_ApplyPlatformDefaults(void)
{
    // no-op. Add your platform-specific patches here.
}


/* dataless.py: initialised data copied into BSS at module load */
#include <string.h>
void doom_init_data_m_controls(void) {
    memcpy(&key_right, &key_right_init, sizeof(key_right));
    memcpy(&key_left, &key_left_init, sizeof(key_left));
    memcpy(&key_up, &key_up_init, sizeof(key_up));
    memcpy(&key_down, &key_down_init, sizeof(key_down));
    memcpy(&key_strafeleft, &key_strafeleft_init, sizeof(key_strafeleft));
    memcpy(&key_straferight, &key_straferight_init, sizeof(key_straferight));
    memcpy(&key_fire, &key_fire_init, sizeof(key_fire));
    memcpy(&key_use, &key_use_init, sizeof(key_use));
    memcpy(&key_strafe, &key_strafe_init, sizeof(key_strafe));
    memcpy(&key_speed, &key_speed_init, sizeof(key_speed));
    memcpy(&key_flyup, &key_flyup_init, sizeof(key_flyup));
    memcpy(&key_flydown, &key_flydown_init, sizeof(key_flydown));
    memcpy(&key_flycenter, &key_flycenter_init, sizeof(key_flycenter));
    memcpy(&key_lookup, &key_lookup_init, sizeof(key_lookup));
    memcpy(&key_lookdown, &key_lookdown_init, sizeof(key_lookdown));
    memcpy(&key_lookcenter, &key_lookcenter_init, sizeof(key_lookcenter));
    memcpy(&key_invleft, &key_invleft_init, sizeof(key_invleft));
    memcpy(&key_invright, &key_invright_init, sizeof(key_invright));
    memcpy(&key_useartifact, &key_useartifact_init, sizeof(key_useartifact));
    memcpy(&key_jump, &key_jump_init, sizeof(key_jump));
    memcpy(&key_arti_all, &key_arti_all_init, sizeof(key_arti_all));
    memcpy(&key_arti_health, &key_arti_health_init, sizeof(key_arti_health));
    memcpy(&key_arti_poisonbag, &key_arti_poisonbag_init, sizeof(key_arti_poisonbag));
    memcpy(&key_arti_blastradius, &key_arti_blastradius_init, sizeof(key_arti_blastradius));
    memcpy(&key_arti_teleport, &key_arti_teleport_init, sizeof(key_arti_teleport));
    memcpy(&key_arti_teleportother, &key_arti_teleportother_init, sizeof(key_arti_teleportother));
    memcpy(&key_arti_egg, &key_arti_egg_init, sizeof(key_arti_egg));
    memcpy(&key_arti_invulnerability, &key_arti_invulnerability_init, sizeof(key_arti_invulnerability));
    memcpy(&key_usehealth, &key_usehealth_init, sizeof(key_usehealth));
    memcpy(&key_invquery, &key_invquery_init, sizeof(key_invquery));
    memcpy(&key_mission, &key_mission_init, sizeof(key_mission));
    memcpy(&key_invpop, &key_invpop_init, sizeof(key_invpop));
    memcpy(&key_invkey, &key_invkey_init, sizeof(key_invkey));
    memcpy(&key_invhome, &key_invhome_init, sizeof(key_invhome));
    memcpy(&key_invend, &key_invend_init, sizeof(key_invend));
    memcpy(&key_invuse, &key_invuse_init, sizeof(key_invuse));
    memcpy(&key_invdrop, &key_invdrop_init, sizeof(key_invdrop));
    memcpy(&mousebfire, &mousebfire_init, sizeof(mousebfire));
    memcpy(&mousebstrafe, &mousebstrafe_init, sizeof(mousebstrafe));
    memcpy(&mousebforward, &mousebforward_init, sizeof(mousebforward));
    memcpy(&mousebjump, &mousebjump_init, sizeof(mousebjump));
    memcpy(&mousebstrafeleft, &mousebstrafeleft_init, sizeof(mousebstrafeleft));
    memcpy(&mousebstraferight, &mousebstraferight_init, sizeof(mousebstraferight));
    memcpy(&mousebbackward, &mousebbackward_init, sizeof(mousebbackward));
    memcpy(&mousebuse, &mousebuse_init, sizeof(mousebuse));
    memcpy(&mousebprevweapon, &mousebprevweapon_init, sizeof(mousebprevweapon));
    memcpy(&mousebnextweapon, &mousebnextweapon_init, sizeof(mousebnextweapon));
    memcpy(&key_message_refresh, &key_message_refresh_init, sizeof(key_message_refresh));
    memcpy(&key_pause, &key_pause_init, sizeof(key_pause));
    memcpy(&key_demo_quit, &key_demo_quit_init, sizeof(key_demo_quit));
    memcpy(&key_spy, &key_spy_init, sizeof(key_spy));
    memcpy(&key_multi_msg, &key_multi_msg_init, sizeof(key_multi_msg));
    memcpy(&key_weapon1, &key_weapon1_init, sizeof(key_weapon1));
    memcpy(&key_weapon2, &key_weapon2_init, sizeof(key_weapon2));
    memcpy(&key_weapon3, &key_weapon3_init, sizeof(key_weapon3));
    memcpy(&key_weapon4, &key_weapon4_init, sizeof(key_weapon4));
    memcpy(&key_weapon5, &key_weapon5_init, sizeof(key_weapon5));
    memcpy(&key_weapon6, &key_weapon6_init, sizeof(key_weapon6));
    memcpy(&key_weapon7, &key_weapon7_init, sizeof(key_weapon7));
    memcpy(&key_weapon8, &key_weapon8_init, sizeof(key_weapon8));
    memcpy(&key_prevweapon, &key_prevweapon_init, sizeof(key_prevweapon));
    memcpy(&key_nextweapon, &key_nextweapon_init, sizeof(key_nextweapon));
    memcpy(&key_map_north, &key_map_north_init, sizeof(key_map_north));
    memcpy(&key_map_south, &key_map_south_init, sizeof(key_map_south));
    memcpy(&key_map_east, &key_map_east_init, sizeof(key_map_east));
    memcpy(&key_map_west, &key_map_west_init, sizeof(key_map_west));
    memcpy(&key_map_zoomin, &key_map_zoomin_init, sizeof(key_map_zoomin));
    memcpy(&key_map_zoomout, &key_map_zoomout_init, sizeof(key_map_zoomout));
    memcpy(&key_map_toggle, &key_map_toggle_init, sizeof(key_map_toggle));
    memcpy(&key_map_maxzoom, &key_map_maxzoom_init, sizeof(key_map_maxzoom));
    memcpy(&key_map_follow, &key_map_follow_init, sizeof(key_map_follow));
    memcpy(&key_map_grid, &key_map_grid_init, sizeof(key_map_grid));
    memcpy(&key_map_mark, &key_map_mark_init, sizeof(key_map_mark));
    memcpy(&key_map_clearmark, &key_map_clearmark_init, sizeof(key_map_clearmark));
    memcpy(&key_menu_activate, &key_menu_activate_init, sizeof(key_menu_activate));
    memcpy(&key_menu_up, &key_menu_up_init, sizeof(key_menu_up));
    memcpy(&key_menu_down, &key_menu_down_init, sizeof(key_menu_down));
    memcpy(&key_menu_left, &key_menu_left_init, sizeof(key_menu_left));
    memcpy(&key_menu_right, &key_menu_right_init, sizeof(key_menu_right));
    memcpy(&key_menu_back, &key_menu_back_init, sizeof(key_menu_back));
    memcpy(&key_menu_forward, &key_menu_forward_init, sizeof(key_menu_forward));
    memcpy(&key_menu_confirm, &key_menu_confirm_init, sizeof(key_menu_confirm));
    memcpy(&key_menu_abort, &key_menu_abort_init, sizeof(key_menu_abort));
    memcpy(&key_menu_help, &key_menu_help_init, sizeof(key_menu_help));
    memcpy(&key_menu_save, &key_menu_save_init, sizeof(key_menu_save));
    memcpy(&key_menu_load, &key_menu_load_init, sizeof(key_menu_load));
    memcpy(&key_menu_volume, &key_menu_volume_init, sizeof(key_menu_volume));
    memcpy(&key_menu_detail, &key_menu_detail_init, sizeof(key_menu_detail));
    memcpy(&key_menu_qsave, &key_menu_qsave_init, sizeof(key_menu_qsave));
    memcpy(&key_menu_endgame, &key_menu_endgame_init, sizeof(key_menu_endgame));
    memcpy(&key_menu_messages, &key_menu_messages_init, sizeof(key_menu_messages));
    memcpy(&key_menu_qload, &key_menu_qload_init, sizeof(key_menu_qload));
    memcpy(&key_menu_quit, &key_menu_quit_init, sizeof(key_menu_quit));
    memcpy(&key_menu_gamma, &key_menu_gamma_init, sizeof(key_menu_gamma));
    memcpy(&key_menu_incscreen, &key_menu_incscreen_init, sizeof(key_menu_incscreen));
    memcpy(&key_menu_decscreen, &key_menu_decscreen_init, sizeof(key_menu_decscreen));
    memcpy(&key_menu_screenshot, &key_menu_screenshot_init, sizeof(key_menu_screenshot));
    memcpy(&joybfire, &joybfire_init, sizeof(joybfire));
    memcpy(&joybstrafe, &joybstrafe_init, sizeof(joybstrafe));
    memcpy(&joybuse, &joybuse_init, sizeof(joybuse));
    memcpy(&joybspeed, &joybspeed_init, sizeof(joybspeed));
    memcpy(&joybstrafeleft, &joybstrafeleft_init, sizeof(joybstrafeleft));
    memcpy(&joybstraferight, &joybstraferight_init, sizeof(joybstraferight));
    memcpy(&joybjump, &joybjump_init, sizeof(joybjump));
    memcpy(&joybprevweapon, &joybprevweapon_init, sizeof(joybprevweapon));
    memcpy(&joybnextweapon, &joybnextweapon_init, sizeof(joybnextweapon));
    memcpy(&joybmenu, &joybmenu_init, sizeof(joybmenu));
    memcpy(&dclick_use, &dclick_use_init, sizeof(dclick_use));
}
