//doomgeneric for soso os

#include "doomkeys.h"
#include "m_argv.h"
#include "doomgeneric.h"

#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdint.h>
#include <sys/time.h>
#include <sys/ioctl.h>
#include <sys/mman.h>

#include <termios.h>

static int const FrameBufferFd_init = -1;
int FrameBufferFd;
static int * const FrameBuffer_init = 0;
int * FrameBuffer;

static int const KeyboardFd_init = -1;
int KeyboardFd;

#define KEYQUEUE_SIZE 16

unsigned short s_KeyQueue[KEYQUEUE_SIZE];
static unsigned int const s_KeyQueueWriteIndex_init = 0;
unsigned int s_KeyQueueWriteIndex;
static unsigned int const s_KeyQueueReadIndex_init = 0;
unsigned int s_KeyQueueReadIndex;

static unsigned int const s_PositionX_init = 0;
unsigned int s_PositionX;
static unsigned int const s_PositionY_init = 0;
unsigned int s_PositionY;

static unsigned int const s_ScreenWidth_init = 0;
unsigned int s_ScreenWidth;
static unsigned int const s_ScreenHeight_init = 0;
unsigned int s_ScreenHeight;

enum EnFrameBuferIoctl
{
    FB_GET_WIDTH,
    FB_GET_HEIGHT,
    FB_GET_BITSPERPIXEL
};

static unsigned char convertToDoomKey(unsigned char scancode)
{
    unsigned char key = 0;

    switch (scancode)
    {
    case 0x9C:
    case 0x1C:
        key = KEY_ENTER;
        break;
    case 0x01:
        key = KEY_ESCAPE;
        break;
    case 0xCB:
    case 0x4B:
        key = KEY_LEFTARROW;
        break;
    case 0xCD:
    case 0x4D:
        key = KEY_RIGHTARROW;
        break;
    case 0xC8:
    case 0x48:
        key = KEY_UPARROW;
        break;
    case 0xD0:
    case 0x50:
        key = KEY_DOWNARROW;
        break;
    case 0x1D:
        key = KEY_FIRE;
        break;
    case 0x39:
        key = KEY_USE;
        break;
    case 0x2A:
    case 0x36:
        key = KEY_RSHIFT;
        break;
    case 0x15:
        key = 'y';
        break;
    default:
        break;
    }

    return key;
}

static void addKeyToQueue(int pressed, unsigned char keyCode)
{
	//printf("key hex %x decimal %d\n", keyCode, keyCode);

        unsigned char key = convertToDoomKey(keyCode);

        unsigned short keyData = (pressed << 8) | key;

        s_KeyQueue[s_KeyQueueWriteIndex] = keyData;
        s_KeyQueueWriteIndex++;
        s_KeyQueueWriteIndex %= KEYQUEUE_SIZE;
}


struct termios orig_termios;

void disableRawMode()
{
  //printf("returning original termios\n");
  tcsetattr(STDIN_FILENO, TCSAFLUSH, &orig_termios);
}

void enableRawMode()
{
  tcgetattr(STDIN_FILENO, &orig_termios);
  atexit(disableRawMode);
  struct termios raw = orig_termios;
  raw.c_lflag &= ~(ECHO);
  raw.c_cc[VMIN] = 0;
  tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw);
}

void DG_Init()
{
    FrameBufferFd = open("/dev/fb0", 0);

    if (FrameBufferFd >= 0)
    {
        printf("Getting screen width...");
        s_ScreenWidth = ioctl(FrameBufferFd, FB_GET_WIDTH);
        printf("%d\n", s_ScreenWidth);

        printf("Getting screen height...");
        s_ScreenHeight = ioctl(FrameBufferFd, FB_GET_HEIGHT);
        printf("%d\n", s_ScreenHeight);

        if (0 == s_ScreenWidth || 0 == s_ScreenHeight)
        {
            printf("Unable to obtain screen info!");
            exit(1);
        }

        FrameBuffer = mmap(NULL, s_ScreenWidth * s_ScreenHeight * 4, PROT_READ | PROT_WRITE, 0, FrameBufferFd, 0);

        if (FrameBuffer != (int*)-1)
        {
            printf("FrameBuffer mmap success\n");
        }
        else
        {
            printf("FrameBuffermmap failed\n");
        }
    }
    else
    {
        printf("Opening FrameBuffer device failed!\n");
    }

    enableRawMode();

    KeyboardFd = open("/dev/keyboard", 0);

    if (KeyboardFd >= 0)
    {
        //enter non-blocking mode
        ioctl(KeyboardFd, 1, (void*)1);
    }

    int argPosX = 0;
    int argPosY = 0;

    argPosX = M_CheckParmWithArgs("-posx", 1);
    if (argPosX > 0)
    {
        sscanf(myargv[argPosX + 1], "%d", &s_PositionX);
    }

    argPosY = M_CheckParmWithArgs("-posy", 1);
    if (argPosY > 0)
    {
        sscanf(myargv[argPosY + 1], "%d", &s_PositionY);
    }
}

static void handleKeyInput()
{
    if (KeyboardFd < 0)
    {
        return;
    }

    unsigned char scancode = 0;

    if (read(KeyboardFd, &scancode, 1) > 0)
    {
        unsigned char keyRelease = (0x80 & scancode);

        scancode = (0x7F & scancode);

        //printf("scancode:%x pressed:%d\n", scancode, 0 == keyRelease);

        if (0 == keyRelease)
        {
            addKeyToQueue(1, scancode);
        }
        else
        {
            addKeyToQueue(0, scancode);
        }
    }
}

void DG_DrawFrame()
{
    if (FrameBuffer)
    {
        for (int i = 0; i < DOOMGENERIC_RESY; ++i)
        {
            memcpy(FrameBuffer + s_PositionX + (i + s_PositionY) * s_ScreenWidth, DG_ScreenBuffer + i * DOOMGENERIC_RESX, DOOMGENERIC_RESX * 4);
        }
    }

    handleKeyInput();
}

void DG_SleepMs(uint32_t ms)
{
    usleep(ms * 1000);
}

uint32_t DG_GetTicksMs()
{
    struct timeval  tp;
    struct timezone tzp;

    gettimeofday(&tp, &tzp);

    return (tp.tv_sec * 1000) + (tp.tv_usec / 1000); /* return milliseconds */
}

int DG_GetKey(int* pressed, unsigned char* doomKey)
{
    if (s_KeyQueueReadIndex == s_KeyQueueWriteIndex)
    {
        //key queue is empty

        return 0;
    }
    else
    {
        unsigned short keyData = s_KeyQueue[s_KeyQueueReadIndex];
        s_KeyQueueReadIndex++;
        s_KeyQueueReadIndex %= KEYQUEUE_SIZE;

        *pressed = keyData >> 8;
        *doomKey = keyData & 0xFF;

        return 1;
    }
}

void DG_SetWindowTitle(const char * title)
{
}

int main(int argc, char **argv)
{
    doomgeneric_Create(argc, argv);

    while (1)
    {
        doomgeneric_Tick();
    }
    

    return 0;
}
/* dataless.py: initialised data copied into BSS at module load */
#include <string.h>
void doom_init_data_doomgeneric_soso(void) {
    memcpy(&FrameBufferFd, &FrameBufferFd_init, sizeof(FrameBufferFd));
    memcpy(&FrameBuffer, &FrameBuffer_init, sizeof(FrameBuffer));
    memcpy(&KeyboardFd, &KeyboardFd_init, sizeof(KeyboardFd));
    memcpy(&s_KeyQueueWriteIndex, &s_KeyQueueWriteIndex_init, sizeof(s_KeyQueueWriteIndex));
    memcpy(&s_KeyQueueReadIndex, &s_KeyQueueReadIndex_init, sizeof(s_KeyQueueReadIndex));
    memcpy(&s_PositionX, &s_PositionX_init, sizeof(s_PositionX));
    memcpy(&s_PositionY, &s_PositionY_init, sizeof(s_PositionY));
    memcpy(&s_ScreenWidth, &s_ScreenWidth_init, sizeof(s_ScreenWidth));
    memcpy(&s_ScreenHeight, &s_ScreenHeight_init, sizeof(s_ScreenHeight));
}
