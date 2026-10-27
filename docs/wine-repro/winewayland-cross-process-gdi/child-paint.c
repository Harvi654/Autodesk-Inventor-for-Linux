/* Original synthetic reproducer, written with AI assistance. No vendor code.
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

static LRESULT CALLBACK proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WM_PAINT)
    {
        PAINTSTRUCT ps;
        RECT rect;
        HDC dc = BeginPaint(hwnd, &ps);
        LONG_PTR kind = GetWindowLongPtrA(hwnd, GWLP_USERDATA);
        HBRUSH brush = CreateSolidBrush(kind == 1 ? RGB(30,180,70) :
                                       kind == 2 ? RGB(40,100,220) : RGB(180,60,40));
        const char *text = kind == 1 ? "SAME PROCESS: green" :
                           kind == 2 ? "OTHER PROCESS: blue" : "Parent: red";
        GetClientRect(hwnd, &rect);
        FillRect(dc, &rect, brush);
        SetTextColor(dc, RGB(255,255,255));
        SetBkMode(dc, TRANSPARENT);
        TextOutA(dc, 12, 12, text, lstrlenA(text));
        DeleteObject(brush);
        EndPaint(hwnd, &ps);
        GdiFlush();
        printf("paint pid=%lu hwnd=%p kind=%ld\n", (unsigned long)GetCurrentProcessId(), hwnd, (long)kind);
        fflush(stdout);
        return 0;
    }
    if (msg == WM_DESTROY) { PostQuitMessage(0); return 0; }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR args, int show)
{
    WNDCLASSA cls = {0};
    HWND hwnd, child;
    MSG msg;
    cls.lpfnWndProc = proc;
    cls.hInstance = instance;
    cls.lpszClassName = "CrossProcessPaint";
    cls.hCursor = LoadCursorA(NULL, IDC_ARROW);
    if (!RegisterClassA(&cls)) return 1;
    if (*args)
    {
        HWND parent = (HWND)(UINT_PTR)strtoull(args, NULL, 16);
        hwnd = CreateWindowA(cls.lpszClassName, "Other process", WS_CHILD | WS_VISIBLE,
                             310, 50, 270, 180, parent, NULL, instance, NULL);
        if (!hwnd) { printf("child creation failed %lu\n", (unsigned long)GetLastError()); return 2; }
        SetWindowLongPtrA(hwnd, GWLP_USERDATA, 2);
        InvalidateRect(hwnd, NULL, TRUE);
    }
    else
    {
        char module[MAX_PATH], command[2 * MAX_PATH];
        STARTUPINFOA startup = {sizeof(startup)};
        PROCESS_INFORMATION process;
        hwnd = CreateWindowA(cls.lpszClassName, "Cross-process GDI paint", WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN,
                             80, 80, 640, 330, NULL, NULL, instance, NULL);
        if (!hwnd) return 3;
        child = CreateWindowA(cls.lpszClassName, "Same process", WS_CHILD | WS_VISIBLE,
                              20, 50, 270, 180, hwnd, NULL, instance, NULL);
        if (!child) return 4;
        SetWindowLongPtrA(child, GWLP_USERDATA, 1);
        GetModuleFileNameA(NULL, module, sizeof(module));
        snprintf(command, sizeof(command), "\"%s\" %llx", module, (unsigned long long)(UINT_PTR)hwnd);
        ShowWindow(hwnd, show);
        if (!CreateProcessA(NULL, command, NULL, NULL, FALSE, 0, NULL, NULL, &startup, &process))
        { printf("CreateProcess failed %lu\n", (unsigned long)GetLastError()); return 5; }
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
    }
    while (GetMessageA(&msg, NULL, 0, 0) > 0) { TranslateMessage(&msg); DispatchMessageA(&msg); }
    return 0;
}
