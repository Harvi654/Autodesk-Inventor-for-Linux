/* Renders sample text with several faces, pixel sizes and qualities into a
 * 32-bit DIB and counts grey (partially covered) and colour (ClearType)
 * pixels. Font files given as arguments are loaded privately first.
 * Output: one line per face/ppem/quality. */
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define W 900
#define H 60

int main(int argc, char **argv)
{
    static const int ppems[] = {11, 12, 13, 15, 16, 17, 19, 21, 24};
    static const struct { int q; const char *n; } quals[] = {
        {DEFAULT_QUALITY, "default"}, {NONANTIALIASED_QUALITY, "nonaa"},
        {ANTIALIASED_QUALITY, "aa"}, {CLEARTYPE_QUALITY, "cleartype"}};
    static const struct { const char *face; int weight; } faces[] = {
        {"Tahoma", 400}, {"Tahoma", 700}, {"Segoe UI", 400},
        {"TTR20", 400}, {"TTR22", 400}, {"TTRNB", 400}, {"TTRSG", 400}, {"TTRBO", 400},
        {"TTB22", 700}, {"TTBBO", 700}};
    const char *text = "Application Options  Customize  For Help, press F1";
    BOOL smooth = FALSE; UINT type = 0, contrast = 0;
    BITMAPINFO bi = {0}; void *bits; int i;

    for (i = 1; i < argc; i++)
        printf("load %s -> %d\n", argv[i], AddFontResourceExA(argv[i], FR_PRIVATE, 0));
    SystemParametersInfoA(SPI_GETFONTSMOOTHING, 0, &smooth, 0);
    SystemParametersInfoA(SPI_GETFONTSMOOTHINGTYPE, 0, &type, 0);
    SystemParametersInfoA(SPI_GETFONTSMOOTHINGCONTRAST, 0, &contrast, 0);
    printf("SPI smoothing=%d type=%u contrast=%u\n", smooth, type, contrast);

    HDC dc = CreateCompatibleDC(NULL);
    bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER); bi.bmiHeader.biWidth = W;
    bi.bmiHeader.biHeight = -H; bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32;
    HBITMAP bmp = CreateDIBSection(dc, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    HGDIOBJ oldbmp = SelectObject(dc, bmp);

    printf("face weight ppem quality actual partial color levels width\n");
    for (unsigned f = 0; f < sizeof(faces)/sizeof(faces[0]); f++)
    for (unsigned p = 0; p < sizeof(ppems)/sizeof(ppems[0]); p++)
    for (unsigned q = 0; q < sizeof(quals)/sizeof(quals[0]); q++)
    {
        LOGFONTA lf = {0}; SIZE sz; char face[64] = {0};
        unsigned partial = 0, color = 0, levels = 0; unsigned char seen[256] = {0};
        unsigned char *px = bits;
        lf.lfHeight = -ppems[p]; lf.lfWeight = faces[f].weight; lf.lfQuality = quals[q].q;
        lf.lfCharSet = DEFAULT_CHARSET;
        strncpy(lf.lfFaceName, faces[f].face, LF_FACESIZE - 1);
        HFONT font = CreateFontIndirectA(&lf); HGDIOBJ old = SelectObject(dc, font);
        memset(bits, 0, W * H * 4);
        SetBkColor(dc, RGB(0,0,0)); SetTextColor(dc, RGB(255,255,255)); SetBkMode(dc, TRANSPARENT);
        TextOutA(dc, 4, 4, text, (int)strlen(text)); GdiFlush();
        GetTextExtentPoint32A(dc, text, (int)strlen(text), &sz);
        GetTextFaceA(dc, sizeof(face), face);
        for (int j = 0; j < W * H; j++, px += 4)
        {
            for (int c = 0; c < 3; c++) seen[px[c]] = 1;
            if ((px[0] > 0 && px[0] < 255) || (px[1] > 0 && px[1] < 255) || (px[2] > 0 && px[2] < 255)) partial++;
            if (px[0] != px[1] || px[1] != px[2]) color++;
        }
        for (int k = 1; k < 255; k++) levels += seen[k];
        for (char *s = face; *s; s++) if (*s == ' ') *s = '_';
        printf("%s %d %d %s %s %u %u %u %ld\n", faces[f].face, faces[f].weight, ppems[p],
               quals[q].n, face[0] ? face : "?",
               partial, color, levels, sz.cx);
        SelectObject(dc, old); DeleteObject(font);
    }
    SelectObject(dc, oldbmp); DeleteObject(bmp); DeleteDC(dc);
    return 0;
}
