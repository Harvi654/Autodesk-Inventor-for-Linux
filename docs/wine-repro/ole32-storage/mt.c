/* Four threads use substorages and streams of one transacted docfile at the
 * same time, as Robot's rkernel.exe does (Frame Analysis). Standalone version
 * of test_threads() from patches/ole32-storage-thread-lock.patch.
 *   mt.exe [ITERATIONS]    prints "0 failures" when fixed; Wine 11.20 without
 *                          the lock dies on "blockIndex != nextBlock". */
#define COBJMACROS
#include <windows.h>
#include <ole2.h>
#include <stdio.h>

#define NTHREADS 4
#define NROUNDS 40

static IStorage *root;
static volatile LONG failures;

static DWORD WINAPI worker(void *arg)
{
    int id = (int)(INT_PTR)arg, round;
    BYTE buf[9000], chk[9000];
    WCHAR name[32];
    HRESULT hr;

    CoInitializeEx(NULL, COINIT_MULTITHREADED);
    for (round = 0; round < NROUNDS; round++)
    {
        IStorage *sub;
        IStream *stm;
        ULONG len = 100 + (round * 997 + id * 331) % 8500, done, i;
        LARGE_INTEGER zero = {{0}};

        swprintf(name, 32, L"T%d_%d", id, round % 5);
        hr = IStorage_CreateStorage(root, name, STGM_READWRITE | STGM_SHARE_EXCLUSIVE | STGM_TRANSACTED | STGM_CREATE, 0, 0, &sub);
        if (FAILED(hr)) { InterlockedIncrement(&failures); printf("thread %d CreateStorage %#lx\n", id, hr); continue; }
        hr = IStorage_CreateStream(sub, L"DATA", STGM_READWRITE | STGM_SHARE_EXCLUSIVE | STGM_CREATE, 0, 0, &stm);
        if (FAILED(hr)) { InterlockedIncrement(&failures); printf("thread %d CreateStream %#lx\n", id, hr); IStorage_Release(sub); continue; }
        for (i = 0; i < len; i++) buf[i] = (BYTE)(i * 7 + id + round);
        /* write in small pieces so the stream crosses the small/big block limit */
        for (i = 0; i < len; i += 300)
            IStream_Write(stm, buf + i, min(300, len - i), NULL);
        IStream_Seek(stm, zero, STREAM_SEEK_SET, NULL);
        hr = IStream_Read(stm, chk, len, &done);
        if (FAILED(hr) || done != len || memcmp(buf, chk, len))
        { InterlockedIncrement(&failures); printf("thread %d round %d: bad data (%#lx, %lu/%lu)\n", id, round, hr, done, len); }
        IStream_Release(stm);
        hr = IStorage_Commit(sub, 0);
        if (FAILED(hr)) { InterlockedIncrement(&failures); printf("thread %d Commit %#lx\n", id, hr); }
        IStorage_Release(sub);
    }
    CoUninitialize();
    return 0;
}

int main(int argc, char **argv)
{
    HANDLE th[NTHREADS];
    int i, iter, iters = argc > 1 ? atoi(argv[1]) : 5;

    CoInitializeEx(NULL, COINIT_MULTITHREADED);
    for (iter = 0; iter < iters; iter++)
    {
        if (FAILED(StgCreateDocfile(L"mt.stg", STGM_CREATE | STGM_READWRITE | STGM_SHARE_EXCLUSIVE | STGM_TRANSACTED, 0, &root)))
            return 2;
        for (i = 0; i < NTHREADS; i++) th[i] = CreateThread(NULL, 0, worker, (void *)(INT_PTR)i, 0, NULL);
        WaitForMultipleObjects(NTHREADS, th, TRUE, INFINITE);
        for (i = 0; i < NTHREADS; i++) CloseHandle(th[i]);
        IStorage_Commit(root, 0);
        IStorage_Release(root);
    }
    printf("%ld failures\n", failures);
    return failures != 0;
}
