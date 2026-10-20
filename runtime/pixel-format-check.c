/* Reproduce the legacy-to-ARB pixel-format selection used by Inventor's
 * Hydra capability check. No Autodesk DLLs or licensing are required. */
#include <windows.h>
#include <GL/gl.h>
#include <stdio.h>
#ifndef WGL_DRAW_TO_WINDOW_ARB
#define WGL_DRAW_TO_WINDOW_ARB 0x2001
#define WGL_ACCELERATION_ARB 0x2003
#define WGL_SUPPORT_OPENGL_ARB 0x2010
#define WGL_DOUBLE_BUFFER_ARB 0x2011
#define WGL_PIXEL_TYPE_ARB 0x2013
#define WGL_COLOR_BITS_ARB 0x2014
#define WGL_ALPHA_BITS_ARB 0x201b
#define WGL_DEPTH_BITS_ARB 0x2022
#define WGL_STENCIL_BITS_ARB 0x2023
#define WGL_FULL_ACCELERATION_ARB 0x2027
#define WGL_TYPE_RGBA_ARB 0x202b
#endif
static void describe(HDC dc, int format) {
 PIXELFORMATDESCRIPTOR p={0}; DescribePixelFormat(dc,format,sizeof(p),&p);
 printf("FORMAT=%d flags=%lx color=%u rgba=%u/%u/%u/%u depth=%u stencil=%u\n",format,p.dwFlags,p.cColorBits,p.cRedBits,p.cGreenBits,p.cBlueBits,p.cAlphaBits,p.cDepthBits,p.cStencilBits);
}
int main(void) {
 HWND wnd=CreateWindowA("STATIC","Pixel format diagnostic",WS_OVERLAPPEDWINDOW,0,0,128,128,NULL,NULL,NULL,NULL);
 if (!wnd) return 2;
 HDC dc=GetDC(wnd); PIXELFORMATDESCRIPTOR p={0};
 if (!dc) { DestroyWindow(wnd); return 2; }
 p.nSize=sizeof(p);p.nVersion=1;p.dwFlags=0x25;p.iPixelType=PFD_TYPE_RGBA;
 p.cColorBits=24;p.cRedBits=p.cGreenBits=p.cBlueBits=p.cAlphaBits=8;p.cDepthBits=24;p.cStencilBits=8;
 int first=ChoosePixelFormat(dc,&p);describe(dc,first);
 BOOL first_set = SetPixelFormat(dc,first,&p);
 printf("FIRST_SET=%d\n",first_set);
 if (!first_set) { ReleaseDC(wnd,dc); DestroyWindow(wnd); return 2; }
 HGLRC rc=wglCreateContext(dc);printf("LEGACY_CONTEXT=%p\n",rc);
 BOOL current = rc && wglMakeCurrent(dc,rc);
 printf("MAKE_CURRENT=%d\n",current);
 if (!current) { if (rc) wglDeleteContext(rc); ReleaseDC(wnd,dc); DestroyWindow(wnd); return 2; }
 printf("GL_VERSION=%s\nGL_RENDERER=%s\n",glGetString(GL_VERSION),glGetString(GL_RENDERER));
 typedef BOOL(WINAPI *choose_fn)(HDC,const int*,const FLOAT*,UINT,int*,UINT*);
 choose_fn choose=(choose_fn)wglGetProcAddress("wglChoosePixelFormatARB");
 int attrs[]={WGL_DRAW_TO_WINDOW_ARB,1,WGL_SUPPORT_OPENGL_ARB,1,WGL_DOUBLE_BUFFER_ARB,1,WGL_ACCELERATION_ARB,WGL_FULL_ACCELERATION_ARB,WGL_PIXEL_TYPE_ARB,WGL_TYPE_RGBA_ARB,WGL_COLOR_BITS_ARB,32,WGL_ALPHA_BITS_ARB,8,WGL_DEPTH_BITS_ARB,24,WGL_STENCIL_BITS_ARB,8,0};
 int second=0;UINT n=0;BOOL ok=choose&&choose(dc,attrs,NULL,1,&second,&n);
 printf("ARB_CHOOSE=%d COUNT=%u\n",ok,n);if(n)describe(dc,second);
 wglMakeCurrent(NULL,NULL);wglDeleteContext(rc);
 SetLastError(0);ok=SetPixelFormat(dc,second,&p);printf("SECOND_SET=%d ERROR=%lu\n",ok,GetLastError());
 ReleaseDC(wnd,dc);DestroyWindow(wnd);
 return ok ? 0 : 1;
}
