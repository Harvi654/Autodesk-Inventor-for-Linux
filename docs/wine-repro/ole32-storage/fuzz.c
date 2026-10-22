/* Random structured-storage operations on a transacted docfile (fuzz.stg in
 * the current directory), looking for ole32 crashes, assertions and broken
 * directory trees. Single-threaded.
 *
 *   fuzz.exe FIRST_SEED SEEDS STEPS [VERBOSE]   VERBOSE 1 = result of each step,
 *                                               2 = also the step before it runs
 * Environment:
 *   FZCHECK=1     after every step count the elements of the tree; more than
 *                 200 means a loop in the directory -> "TREE BROKEN", exit 3
 *   FZDUMP=1      print the tree after every step
 *   FZREC=FILE    record the random numbers of every step, one line per step
 *   FZREP=FILE    replay such a file instead of the random generator
 *                 (ddmin.py shrinks it); FILE is a Windows path
 */
#define COBJMACROS
#include <windows.h>
#include <ole2.h>
#include <stdio.h>
#include <stdlib.h>

#define NSTG 3
#define NSTM 6

static unsigned rnd_state;
static FILE *rec, *rep;
static unsigned q[16]; static int qn, qi;
static unsigned rnd(void)
{
    unsigned v;
    if (rep) return qi < qn ? q[qi++] : 0;
    rnd_state = rnd_state * 1103515245 + 12345; v = (rnd_state >> 8) & 0xffffff;
    if (rec) fprintf(rec, " %u", v);
    return v;
}

static IStorage *root, *sub[NSTG];
static IStream *stm[NSTG + 1][NSTM];
static BYTE buf[70000];
static int verbose;

static IStorage *parent_of(int s) { return s == NSTG ? root : sub[s]; }

static void name(WCHAR *n, const char *p, int i) { swprintf(n, 16, L"%hs%d", p, i); }

static void close_streams(int s)
{
    int i;
    for (i = 0; i < NSTM; i++)
        if (stm[s][i]) { IStream_Release(stm[s][i]); stm[s][i] = NULL; }
}

static int count_tree(IStorage *stg, int depth)
{
    IEnumSTATSTG *e; STATSTG st; int c = 0;
    if (depth > 4 || FAILED(IStorage_EnumElements(stg, 0, NULL, 0, &e))) return 0;
    while (IEnumSTATSTG_Next(e, 1, &st, NULL) == S_OK) {
        if (++c > 200) break;
        if (st.type == STGTY_STORAGE) {
            IStorage *ch;
            if (SUCCEEDED(IStorage_OpenStorage(stg, st.pwcsName, NULL, STGM_READ | STGM_SHARE_EXCLUSIVE, NULL, 0, &ch)))
            { c += count_tree(ch, depth + 1); IStorage_Release(ch); }
        }
        CoTaskMemFree(st.pwcsName);
    }
    IEnumSTATSTG_Release(e);
    return c;
}

static void dump_tree(IStorage *stg, int depth)
{
    IEnumSTATSTG *e; STATSTG st; int c = 0;
    if (depth > 3 || FAILED(IStorage_EnumElements(stg, 0, NULL, 0, &e))) return;
    while (IEnumSTATSTG_Next(e, 1, &st, NULL) == S_OK && ++c < 30) {
        printf("%*s%ls %s %llu\n", depth * 2 + 2, "", st.pwcsName, st.type == STGTY_STORAGE ? "dir" : "stm", st.cbSize.QuadPart);
        if (st.type == STGTY_STORAGE) {
            IStorage *ch;
            if (SUCCEEDED(IStorage_OpenStorage(stg, st.pwcsName, NULL, STGM_READ | STGM_SHARE_EXCLUSIVE, NULL, 0, &ch)))
            { dump_tree(ch, depth + 1); IStorage_Release(ch); }
            else printf("%*s(open failed)\n", depth * 2 + 4, "");
        }
        CoTaskMemFree(st.pwcsName);
    }
    IEnumSTATSTG_Release(e);
}

static void step(int n)
{
    int op = rnd() % 100, s = rnd() % (NSTG + 1), i = rnd() % NSTM;
    IStorage *p = parent_of(s);
    if (verbose > 1) printf("> %d op %d s %d i %d\n", n, op, s, i);
    WCHAR nm[16];
    HRESULT hr;

    if (!p) {
        if (s == NSTG) return;
        name(nm, "SUB", s);
        hr = IStorage_CreateStorage(root, nm, STGM_READWRITE | STGM_SHARE_EXCLUSIVE | STGM_TRANSACTED | STGM_FAILIFTHERE, 0, 0, &sub[s]);
        if (hr == STG_E_FILEALREADYEXISTS)
            hr = IStorage_OpenStorage(root, nm, NULL, STGM_READWRITE | STGM_SHARE_EXCLUSIVE | STGM_TRANSACTED, NULL, 0, &sub[s]);
        if (verbose) printf("%d open sub%d %#lx\n", n, s, hr);
        return;
    }
    name(nm, "S", i);
    if (op < 40) {                       /* write */
        ULONG len = (rnd() % 4 == 0) ? rnd() % 9000 : rnd() % 700, w;
        LARGE_INTEGER pos;
        if (!stm[s][i]) {
            hr = IStorage_CreateStream(p, nm, STGM_READWRITE | STGM_SHARE_EXCLUSIVE | STGM_FAILIFTHERE, 0, 0, &stm[s][i]);
            if (hr == STG_E_FILEALREADYEXISTS)
                hr = IStorage_OpenStream(p, nm, NULL, STGM_READWRITE | STGM_SHARE_EXCLUSIVE, 0, &stm[s][i]);
            if (FAILED(hr)) { if (verbose) printf("%d open stream %d/%d %#lx\n", n, s, i, hr); return; }
        }
        pos.QuadPart = (rnd() % 3 == 0) ? rnd() % 6000 : 0;
        if (rnd() % 2) { ULARGE_INTEGER e; pos.QuadPart = 0; IStream_Seek(stm[s][i], pos, STREAM_SEEK_END, &e); }
        else IStream_Seek(stm[s][i], pos, STREAM_SEEK_SET, NULL);
        memset(buf, n & 0xff, len);
        hr = IStream_Write(stm[s][i], buf, len, &w);
        if (verbose) printf("%d write %d/%d len %lu %#lx\n", n, s, i, len, hr);
    } else if (op < 50) {                /* set size */
        ULARGE_INTEGER sz;
        if (!stm[s][i]) return;
        sz.QuadPart = rnd() % 3 == 0 ? 0 : rnd() % 9000;
        hr = IStream_SetSize(stm[s][i], sz);
        if (verbose) printf("%d setsize %d/%d %llu %#lx\n", n, s, i, sz.QuadPart, hr);
    } else if (op < 60) {                /* read all */
        ULONG r; LARGE_INTEGER z = {{0}};
        if (!stm[s][i]) return;
        IStream_Seek(stm[s][i], z, STREAM_SEEK_SET, NULL);
        hr = IStream_Read(stm[s][i], buf, sizeof(buf), &r);
        if (verbose) printf("%d read %d/%d %lu %#lx\n", n, s, i, r, hr);
    } else if (op < 70) {                /* close stream */
        if (stm[s][i]) { IStream_Release(stm[s][i]); stm[s][i] = NULL; }
    } else if (op < 78) {                /* destroy */
        if (stm[s][i]) { IStream_Release(stm[s][i]); stm[s][i] = NULL; }
        hr = IStorage_DestroyElement(p, nm);
        if (verbose) printf("%d destroy %d/%d %#lx\n", n, s, i, hr);
    } else if (op < 88) {                /* commit */
        hr = IStorage_Commit(p, STGC_DEFAULT);
        if (verbose) printf("%d commit %d %#lx\n", n, s, hr);
    } else if (op < 92) {                /* revert */
        close_streams(s);
        if (s == NSTG) { int k; for (k = 0; k < NSTG; k++) { close_streams(k); if (sub[k]) { IStorage_Release(sub[k]); sub[k] = NULL; } } }
        hr = IStorage_Revert(p);
        if (verbose) printf("%d revert %d %#lx\n", n, s, hr);
    } else if (op < 97 && s != NSTG) {   /* close substorage */
        close_streams(s);
        IStorage_Release(sub[s]); sub[s] = NULL;
        if (verbose) printf("%d close sub%d\n", n, s);
    } else if (s != NSTG) {              /* destroy substorage */
        close_streams(s);
        if (sub[s]) { IStorage_Release(sub[s]); sub[s] = NULL; }
        name(nm, "SUB", s);
        hr = IStorage_DestroyElement(root, nm);
        if (verbose) printf("%d destroy sub%d %#lx\n", n, s, hr);
    }
}

int main(int argc, char **argv)
{
    unsigned seed0 = argc > 1 ? atoi(argv[1]) : 1, seeds = argc > 2 ? atoi(argv[2]) : 1, seed;
    int steps = argc > 3 ? atoi(argv[3]) : 2000, n, s;
    verbose = argc > 4 ? atoi(argv[4]) : 0; setvbuf(stdout, NULL, _IONBF, 0);
    if (getenv("FZREC")) rec = fopen(getenv("FZREC"), "w");
    if (getenv("FZREP")) rep = fopen(getenv("FZREP"), "r");
    CoInitialize(NULL);
    for (seed = seed0; seed < seed0 + seeds; seed++) {
        rnd_state = seed;
        if (FAILED(StgCreateDocfile(L"fuzz.stg", STGM_CREATE | STGM_READWRITE | STGM_SHARE_EXCLUSIVE | STGM_TRANSACTED, 0, &root)))
            return 2;
        printf("seed %u\n", seed); fflush(stdout);
        for (n = 0; n < steps; n++) {
            int c;
            if (rep) {
                char line[512], *t, *e;
                if (!fgets(line, sizeof(line), rep)) break;
                qn = qi = 0;
                for (t = line; qn < 16; t = e) { unsigned v = strtoul(t, &e, 10); if (e == t) break; q[qn++] = v; }
            }
            step(n);
            if (rec) fputc('\n', rec);
            if (getenv("FZDUMP")) dump_tree(root, 0);
            c = getenv("FZCHECK") ? count_tree(root, 0) : 0;
            if (c > 200) { printf("TREE BROKEN after step %d (seed %u)\n", n, seed); return 3; }
        }
        for (s = 0; s <= NSTG; s++) close_streams(s);
        for (s = 0; s < NSTG; s++) if (sub[s]) { IStorage_Commit(sub[s], 0); IStorage_Release(sub[s]); sub[s] = NULL; }
        IStorage_Commit(root, 0);
        IStorage_Release(root);
    }
    printf("done\n");
    return 0;
}
