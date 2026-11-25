#include <windows.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
    BOOL smooth=FALSE; UINT type=0;
    NONCLIENTMETRICSA n={0};
    HDC dc=CreateCompatibleDC(NULL); BITMAPINFO bi={0}; void *bits;
    bi.bmiHeader.biSize=sizeof(BITMAPINFOHEADER); bi.bmiHeader.biWidth=700;
    bi.bmiHeader.biHeight=-70; bi.bmiHeader.biPlanes=1; bi.bmiHeader.biBitCount=32;
    HBITMAP bmp=CreateDIBSection(dc,&bi,DIB_RGB_COLORS,&bits,NULL,0);
    HGDIOBJ oldbmp=SelectObject(dc,bmp);
    SystemParametersInfoA(SPI_GETFONTSMOOTHING,0,&smooth,0);
    SystemParametersInfoA(SPI_GETFONTSMOOTHINGTYPE,0,&type,0);
    n.cbSize=sizeof(n); SystemParametersInfoA(SPI_GETNONCLIENTMETRICS,sizeof(n),&n,0);
    printf("SPI smoothing=%d type=%u menu=%s height=%ld quality=%u status=%s height=%ld quality=%u\n",smooth,type,n.lfMenuFont.lfFaceName,n.lfMenuFont.lfHeight,n.lfMenuFont.lfQuality,n.lfStatusFont.lfFaceName,n.lfStatusFont.lfHeight,n.lfStatusFont.lfQuality);
    const char *families[]={"Tahoma","Segoe UI","Noto Sans","Liberation Sans",n.lfMenuFont.lfFaceName,n.lfStatusFont.lfFaceName};
    for(unsigned i=0;i<sizeof(families)/sizeof(families[0]);i++) for(int q=0;q<3;q++) {
        int qualities[]={DEFAULT_QUALITY,ANTIALIASED_QUALITY,CLEARTYPE_QUALITY};
        LOGFONTA lf={0}; lf.lfHeight=-15; lf.lfWeight=400;lf.lfQuality=qualities[q];
        strncpy(lf.lfFaceName,families[i],LF_FACESIZE-1);
        HFONT f=CreateFontIndirectA(&lf); HGDIOBJ oldfont=SelectObject(dc,f);
        memset(bits,0,700*70*4);SetBkColor(dc,RGB(0,0,0));SetTextColor(dc,RGB(255,255,255));
        const char *text="Application Options  Customize  For Help, press F1";
        TextOutA(dc,4,4,text,(int)strlen(text));GdiFlush();
        unsigned partial=0,color=0;unsigned char *p=bits;
        for(int j=0;j<700*70;j++,p+=4){if((p[0]>0&&p[0]<255)||(p[1]>0&&p[1]<255)||(p[2]>0&&p[2]<255))partial++;if(p[0]!=p[1]||p[1]!=p[2])color++;}
        char face[128]={0};GetTextFaceA(dc,sizeof(face),face);
        printf("requested=%s actual=%s quality=%d partial_pixels=%u color_pixels=%u\n",families[i],face,qualities[q],partial,color);
        SelectObject(dc,oldfont);DeleteObject(f);
    }
    SelectObject(dc,oldbmp);DeleteObject(bmp);DeleteDC(dc);return 0;
}
