/*
 * List the child windows of a top-level window, hidden ones included: class,
 * control ID, position, visible/enabled, text and tooltip-like text.
 * Observes from outside (EnumChildWindows, GetWindowText...), changes nothing.
 *
 * Build: x86_64-w64-mingw32-gcc -O2 -o enumwin.exe enumwin.c
 * Run in the prefix while the window is open: wine enumwin.exe "Projects"
 *
 * Written with AI help (Claude) for the Inventor-on-Linux project, LGPL 2.1+.
 */
#include <windows.h>
#include <stdio.h>

static HWND top;

static int depth_of(HWND hwnd)
{
    int d = 0;
    while (hwnd && hwnd != top) { hwnd = GetParent(hwnd); d++; }
    return d;
}

static BOOL CALLBACK child(HWND hwnd, LPARAM lp)
{
    WCHAR cls[128], text[256];
    RECT r;
    LONG style = GetWindowLongW(hwnd, GWL_STYLE);
    POINT p;

    GetClassNameW(hwnd, cls, 128);
    text[0] = 0;
    SendMessageTimeoutW(hwnd, WM_GETTEXT, 256, (LPARAM)text, SMTO_ABORTIFHUNG, 500, NULL);
    GetWindowRect(hwnd, &r);
    p.x = r.left; p.y = r.top;
    ScreenToClient(top, &p);
    printf("%*s%p id=%-6d %-28ls %s%s pos=%ld,%ld size=%ldx%ld style=%08lx text=\"%ls\"\n",
           depth_of(hwnd) * 2, "", hwnd, GetDlgCtrlID(hwnd), cls,
           (style & WS_VISIBLE) ? "visible" : "HIDDEN ",
           (style & WS_DISABLED) ? " disabled" : "",
           p.x, p.y, r.right - r.left, r.bottom - r.top, style, text);
    return TRUE;
}

int main(int argc, char **argv)
{
    WCHAR title[256];

    if (argc < 2) { printf("usage: enumwin.exe \"window title\"\n"); return 1; }
    MultiByteToWideChar(CP_ACP, 0, argv[1], -1, title, 256);
    top = FindWindowW(NULL, title);
    if (!top) { printf("no window titled \"%s\"\n", argv[1]); return 1; }
    printf("top %p \"%ls\"\n", top, title);
    EnumChildWindows(top, child, 0);
    return 0;
}
